"""Bounded Linux-only extractor for reviewed closure GNU/USTAR tar.gz transport.

No general tar/PAX/sparse support, credentials, Terraform, or trust derivation.
"""
import argparse
import ctypes
import hashlib
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import tempfile
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
FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC


class ExtractionError(Exception):
    pass


def trusted_parent(path):
    if sys.platform != "linux":
        raise ExtractionError("Linux descriptor semantics are required.")
    path = Path(path)
    if not path.is_absolute() or any(part in (".", "..") for part in path.parts):
        raise ExtractionError("An explicit absolute trusted parent is required.")
    fd = os.open("/", FLAGS | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            next_fd = os.open(part, FLAGS | os.O_DIRECTORY, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        info = os.fstat(fd)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ExtractionError("Trusted parent must be owned by the current user and mode 0700.")
        return fd
    except BaseException:
        os.close(fd)
        raise


def same_directory(parent_fd, name, directory_fd):
    info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    owned = os.fstat(directory_fd)
    if not stat.S_ISDIR(info.st_mode) or (info.st_dev, info.st_ino) != (owned.st_dev, owned.st_ino):
        raise ExtractionError("Reserved directory ownership changed.")


def snapshot_archive(path, spool):
    fd = os.open(path, FLAGS)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= MAX_COMPRESSED:
            raise ExtractionError("Archive is not a bounded unlinked regular file.")
        digest = hashlib.sha256()
        count = 0
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            count += len(chunk)
            if count > MAX_COMPRESSED:
                raise ExtractionError("Compressed byte limit exceeded.")
            spool.write(chunk)
            digest.update(chunk)
        after = os.fstat(fd)
        if count != info.st_size or (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ExtractionError("Archive changed during byte capture.")
        spool.seek(0)
        return digest.hexdigest()
    finally:
        os.close(fd)


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
        uid = number(header[108:116], 2**31 - 1)
        gid = number(header[116:124], 2**31 - 1)
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
            if long_name is not None or name != "././@LongLink" or not 1 < size <= MAX_PATH + 1:
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


def open_relative(root_fd, parts):
    fd = os.dup(root_fd)
    try:
        for part in parts:
            next_fd = os.open(part, FLAGS | os.O_DIRECTORY, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def write_all(fd, chunk):
    while chunk:
        written = os.write(fd, chunk)
        if written <= 0:
            raise ExtractionError("Extraction write made no progress.")
        chunk = chunk[written:]


def extract_validated(stream, entries, root_fd):
    directories = []
    for name, directory, mode, size, offset in entries:
        parts = name.split("/")
        parent_fd = open_relative(root_fd, parts[:-1])
        try:
            if directory:
                os.mkdir(parts[-1], mode=0o700, dir_fd=parent_fd)
                directories.append((parts, mode))
            else:
                fd = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                             0o600, dir_fd=parent_fd)
                try:
                    stream.seek(offset)
                    remaining = size
                    while remaining:
                        chunk = stream.read(min(65536, remaining))
                        if not chunk:
                            raise ExtractionError("Validated member bytes became unavailable.")
                        write_all(fd, chunk)
                        remaining -= len(chunk)
                    os.fchmod(fd, mode)
                    os.fsync(fd)
                finally:
                    os.close(fd)
        finally:
            os.close(parent_fd)
    for parts, mode in reversed(directories):
        fd = open_relative(root_fd, parts)
        try:
            os.fchmod(fd, mode)
            os.fsync(fd)
        finally:
            os.close(fd)


def cleanup_owned(root_fd):
    # Descriptor-relative cleanup never traverses links; only this fresh owned staging tree.
    for name in os.listdir(root_fd):
        info = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode):
            fd = os.open(name, FLAGS | os.O_DIRECTORY, dir_fd=root_fd)
            try:
                cleanup_owned(fd)
            finally:
                os.close(fd)
            os.rmdir(name, dir_fd=root_fd)
        else:
            os.unlink(name, dir_fd=root_fd)


def publish_exclusive(parent_fd, staging, destination):
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        rename = libc.renameat2
    except AttributeError:
        raise ExtractionError("Linux no-replace publication is unavailable.") from None
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(parent_fd, staging.encode(), parent_fd, destination.encode(), 1) != 0:
        code = ctypes.get_errno()
        raise OSError(code, "Exclusive extraction publication failed.")


def extract(archive, expected_sha256, parent, destination):
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256 or ""):
        raise ExtractionError("A separately supplied archive SHA256 is required.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", destination or ""):
        raise ExtractionError("Destination must be one bounded child name.")
    try:
        parent_fd = trusted_parent(parent)
    except OSError:
        raise ExtractionError("Trusted parent descriptor access failed.") from None
    stage_fd = None
    staging = ".closure-extract-" + secrets.token_hex(16)
    created = False
    published = False
    try:
        try:
            os.stat(destination, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ExtractionError("Destination collision.")
        os.mkdir(staging, 0o700, dir_fd=parent_fd)
        created = True
        stage_fd = os.open(staging, FLAGS | os.O_DIRECTORY, dir_fd=parent_fd)
        same_directory(parent_fd, staging, stage_fd)
        # O_TMPFILE anonymous spool files beneath the owned staging descriptor.
        with tempfile.TemporaryFile(dir=f"/proc/self/fd/{stage_fd}") as compressed, tempfile.TemporaryFile(dir=f"/proc/self/fd/{stage_fd}") as expanded:
            if snapshot_archive(archive, compressed) != expected_sha256:
                raise ExtractionError("Compressed archive differs from separately selected digest.")
            length = decompress_verified(compressed, expanded)
            entries = validate_tar(expanded, length)
            same_directory(parent_fd, staging, stage_fd)
            extract_validated(expanded, entries, stage_fd)
        same_directory(parent_fd, staging, stage_fd)
        os.fsync(stage_fd)
        os.fsync(parent_fd)
        publish_exclusive(parent_fd, staging, destination)
        published = True
        return Path(parent) / destination / ROOT
    except (OSError, zlib.error, ExtractionError) as exc:
        if created and not published and stage_fd is None:
            raise ExtractionError("Extraction failed; reserved staging descriptor ownership unavailable.") from None
        if created and not published and stage_fd is not None:
            try:
                same_directory(parent_fd, staging, stage_fd)
                cleanup_owned(stage_fd)
                same_directory(parent_fd, staging, stage_fd)
                os.rmdir(staging, dir_fd=parent_fd)
            except (OSError, ExtractionError):
                raise ExtractionError("Extraction failed; owned staging cleanup could not be verified.") from None
        if isinstance(exc, ExtractionError):
            raise
        raise ExtractionError("Extraction filesystem/decoder failure; no successful handoff.") from None
    finally:
        if stage_fd is not None:
            os.close(stage_fd)
        os.close(parent_fd)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--archive-sha256", required=True)
    parser.add_argument("--trusted-parent", type=Path, required=True)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()
    try:
        extract(args.archive, args.archive_sha256, args.trusted_parent, args.destination)
        print("Bounded archive extracted; independent manifest review and host isolation remain required.")
    except ExtractionError as exc:
        raise SystemExit("Extraction stopped: " + str(exc)) from None
