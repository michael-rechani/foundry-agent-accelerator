"""Exact non-extracting parser slice from pinned 1df669da151298a8255fbf188e8cc20b2ac379d4.

Source commit a64919a733101d9b50a44293d4c7dfa0c2fde045; no extraction API.
Bounds, gzip, fields, paths and tar validation are copied without relaxation.
"""
import os
import re
import zlib

MAX_COMPRESSED = 200_000_000
MAX_DECOMPRESSED = 1_000_000_000
MAX_TOTAL = 800_000_000
MAX_FILE = 150_000_000
MAX_ENTRIES = 20000
MAX_PATH = 4096
MAX_DEPTH = 32
BLOCK = 512
ROOT = "public-closure"


class ExtractionError(Exception):
    pass


def decompress_verified(compressed, expanded):
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    total = 0
    finished = False
    while True:
        chunk = compressed.read(65536)
        if not chunk:
            break
        if finished:
            raise ExtractionError("Trailing or concatenated gzip streams are not supported.")
        pending = chunk
        while pending:
            try:
                output = decoder.decompress(pending, min(65536, MAX_DECOMPRESSED - total + 1))
            except zlib.error:
                raise ExtractionError("Malformed gzip stream.") from None
            total += len(output)
            if total > MAX_DECOMPRESSED:
                raise ExtractionError("Decompressed byte limit exceeded.")
            expanded.write(output)
            pending = decoder.unconsumed_tail
            if decoder.eof:
                if decoder.unused_data or pending:
                    raise ExtractionError("Trailing or concatenated gzip streams are not supported.")
                finished = True
                break
    if not finished or not total or total % BLOCK:
        raise ExtractionError("Truncated or unaligned gzip/tar stream.")
    expanded.seek(0)
    return total


def field(raw):
    head, separator, tail = raw.partition(b"\0")
    if separator and any(tail):
        raise ExtractionError("Ambiguous tar string field.")
    try:
        return head.decode("ascii")
    except UnicodeError:
        raise ExtractionError("Non-ASCII tar field is outside the transport contract.") from None


def number(raw, maximum, empty_zero=False):
    if raw[0] & 0x80:
        raise ExtractionError("Base256/sparse numeric headers are unsupported.")
    value = raw.strip(b"\0 ")
    if not value and empty_zero:
        return 0
    if not value or not re.fullmatch(b"[0-7]+", value):
        raise ExtractionError("Malformed octal tar metadata.")
    value = int(value, 8)
    if value > maximum:
        raise ExtractionError("Tar numeric metadata exceeds its bound.")
    return value


def member_path(name, directory=False):
    if directory and name.endswith("/"):
        name = name[:-1]
    if not name or len(name) > MAX_PATH or "\\" in name or ":" in name or name.startswith("/"):
        raise ExtractionError("Unsafe tar path.")
    parts = name.split("/")
    if len(parts) > MAX_DEPTH or parts[0] != ROOT or any(
            not part or part in (".", "..") or len(part) > 255
            or not re.fullmatch(r"[A-Za-z0-9_.@+,-]+", part) for part in parts):
        raise ExtractionError("Escaping or ambiguous tar path.")
    return "/".join(parts)


def validate_tar(stream, length):
    entries = []
    seen = {}
    total = 0
    headers = 0
    long_name = None
    while stream.tell() < length:
        header = stream.read(BLOCK)
        headers += 1
        if headers > MAX_ENTRIES * 2 + 2:
            raise ExtractionError("Tar header count exceeded.")
        if header == b"\0" * BLOCK:
            if long_name is not None or stream.read(BLOCK) != b"\0" * BLOCK:
                raise ExtractionError("Missing canonical tar end marker.")
            while True:
                padding = stream.read(65536)
                if not padding:
                    break
                if any(padding):
                    raise ExtractionError("Nonzero bytes after tar end marker.")
            break
        if len(header) != BLOCK:
            raise ExtractionError("Truncated tar header.")
        checksum = number(header[148:156], 200000)
        if checksum != sum(header[:148]) + 8 * 32 + sum(header[156:]):
            raise ExtractionError("Tar header checksum mismatch.")
        signature = header[257:265]
        if signature not in (b"ustar\x0000", b"ustar  \x00"):
            raise ExtractionError("Only USTAR/GNU tar headers are accepted.")
        mode = number(header[100:108], 0o7777)
        number(header[108:116], 2**31 - 1)
        number(header[116:124], 2**31 - 1)
        size = number(header[124:136], MAX_FILE)
        number(header[136:148], 2**40)
        for metadata_name in (field(header[265:297]), field(header[297:329])):
            if metadata_name and not re.fullmatch(r"[A-Za-z0-9_.-]{1,32}", metadata_name):
                raise ExtractionError("Unsafe owner/group metadata.")
        if number(header[329:337], 0, empty_zero=True) or number(header[337:345], 0, empty_zero=True):
            raise ExtractionError("Device metadata is not accepted.")
        kind = header[156:157]
        name = field(header[:100])
        if field(header[157:257]):
            raise ExtractionError("Tar links are forbidden.")
        if signature == b"ustar\x0000":
            prefix = field(header[345:500])
            if prefix:
                name = prefix + "/" + name
            if any(header[500:]):
                raise ExtractionError("Unexpected USTAR header extensions.")
        elif any(header[345:]):
            raise ExtractionError("GNU sparse/extended metadata is unsupported.")
        padded = ((size + BLOCK - 1) // BLOCK) * BLOCK
        if stream.tell() + padded > length:
            raise ExtractionError("Tar member length escapes decompressed bytes.")
        offset = stream.tell()
        if kind == b"L":
            if (long_name is not None or name != "././@LongLink" or mode not in (0, 0o644)
                    or not 1 < size <= MAX_PATH + 1):
                raise ExtractionError("Unbounded or ambiguous GNU long-name header.")
            value = stream.read(size)
            if value[-1:] != b"\0" or b"\0" in value[:-1]:
                raise ExtractionError("Malformed GNU long-name contents.")
            long_name = field(value)
            member_path(long_name.rstrip("/"), directory=False)
            if any(stream.read(padded - size)):
                raise ExtractionError("Nonzero long-name padding.")
            continue
        if kind not in (b"0", b"\0", b"5"):
            raise ExtractionError("PAX, sparse, links and special tar members are forbidden.")
        if long_name is not None:
            if name != long_name[:100]:
                raise ExtractionError("GNU long-name and regular header names disagree.")
            name = long_name
            long_name = None
        directory = kind == b"5"
        name = member_path(name, directory)
        if directory and size or not directory and name == ROOT:
            raise ExtractionError("Invalid tar root/directory size.")
        if directory and mode not in (0o700, 0o755) or not directory and mode not in (0o400, 0o444, 0o600, 0o644, 0o700, 0o755):
            raise ExtractionError("Unsafe or unsupported tar permissions.")
        if name in seen:
            raise ExtractionError("Duplicate canonical tar member.")
        parts = name.split("/")
        if name != ROOT and ("/".join(parts[:-1]) not in seen or not seen["/".join(parts[:-1])]):
            raise ExtractionError("Member parent is absent or is not a directory.")
        if name == ROOT and (entries or not directory):
            raise ExtractionError("Transport root must be the first regular directory.")
        seen[name] = directory
        total += size
        if total > MAX_TOTAL or len(entries) >= MAX_ENTRIES:
            raise ExtractionError("Tar file/count/total bounds exceeded.")
        entries.append((name, directory, mode, size, offset))
        # Validate every member's padding without allocating its body.
        stream.seek(size, os.SEEK_CUR)
        if any(stream.read(padded - size)):
            raise ExtractionError("Nonzero file padding.")
    else:
        raise ExtractionError("Tar end marker is missing.")
    if not entries or ROOT not in seen:
        raise ExtractionError("Empty dependency transport.")
    return entries


