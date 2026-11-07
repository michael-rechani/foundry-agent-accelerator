import gzip
import hashlib
import io
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import extract_platform_dependencies as extractor


def transport(members, format=tarfile.GNU_FORMAT):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=format) as archive:
        for name, kind, body, mode in members:
            info = tarfile.TarInfo(name)
            info.type = kind
            info.mode = mode
            info.uid = 1001
            info.gid = 128
            info.uname = "runner"
            info.gname = "docker"
            if kind == tarfile.REGTYPE:
                info.size = len(body)
                archive.addfile(info, io.BytesIO(body))
            elif kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                info.linkname = body.decode()
                archive.addfile(info)
            else:
                archive.addfile(info)
    return gzip.compress(raw.getvalue())


BASE = [("public-closure", tarfile.DIRTYPE, b"", 0o700),
        ("public-closure/root", tarfile.DIRTYPE, b"", 0o755),
        ("public-closure/root/main.tf", tarfile.REGTYPE, b"fictional public bytes", 0o644)]


class ExtractionTests(unittest.TestCase):
    def attempt(self, archive, failure=False, modify=None):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            parent = base / "parent"
            parent.mkdir(mode=0o700)
            source = base / "archive.gz"
            source.write_bytes(archive)
            digest = hashlib.sha256(archive).hexdigest()
            if modify:
                modify(source, parent)
            if failure:
                with self.assertRaises(extractor.ExtractionError):
                    extractor.extract(source, digest, parent, "accepted")
                self.assertFalse((parent / "accepted").exists())
                self.assertFalse(any(name.name.startswith(".closure-extract-") for name in parent.iterdir()))
            else:
                root = extractor.extract(source, digest, parent, "accepted")
                self.assertEqual((root / "root/main.tf").read_bytes(), b"fictional public bytes")
                self.assertEqual((root / "root").stat().st_mode & 0o777, 0o755)
                self.assertEqual((root / "root/main.tf").stat().st_mode & 0o777, 0o644)
                with self.assertRaises(extractor.ExtractionError):
                    extractor.extract(source, digest, parent, "accepted")

    def test_gnu_and_ustar_and_bounded_long_names(self):
        self.attempt(transport(BASE))
        self.attempt(transport(BASE, tarfile.USTAR_FORMAT))
        long_name = "public-closure/root/" + "a" * 110
        self.attempt(transport(BASE + [(long_name, tarfile.REGTYPE, b"safe", 0o755)]))

    def test_traversal_links_duplicates_special_and_modes(self):
        for name in ("../escape", "/absolute", "public-closure/../escape", "public-closure//ambiguous",
                     "public-closure/./ambiguous", "public-closure/back\\slash", "public-closure/root/main.tf/child"):
            with self.subTest(name=name):
                self.attempt(transport(BASE + [(name, tarfile.REGTYPE, b"escape", 0o644)]), True)
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE, tarfile.BLKTYPE,
                     tarfile.GNUTYPE_SPARSE, tarfile.XHDTYPE, tarfile.XGLTYPE):
            with self.subTest(kind=kind):
                self.attempt(transport(BASE + [("public-closure/root/unsafe", kind, b"../outside", 0o644)]), True)
        self.attempt(transport(BASE + [BASE[-1]]), True)
        self.attempt(transport(BASE + [("public-closure/root/unsafe", tarfile.REGTYPE, b"x", 0o4755)]), True)
        self.attempt(transport(BASE + [("public-closure/root/unsafe", tarfile.REGTYPE, b"x", 0o666)]), True)
        self.attempt(transport(BASE + [("public-closure/root/" + "a" * 110, tarfile.REGTYPE, b"x", 0o644)], tarfile.PAX_FORMAT), True)

    def test_digest_archive_and_parent_substitutions(self):
        archive = transport(BASE)
        self.attempt(archive, True, lambda source, parent: source.write_bytes(transport(BASE + [("public-closure/extra", tarfile.REGTYPE, b"changed", 0o644)])))
        def symlink(source, parent):
            saved = source.with_name("saved.gz")
            source.rename(saved)
            source.symlink_to(saved)
        self.attempt(archive, True, symlink)
        def hardlink(source, parent):
            os.link(source, source.with_name("duplicate.gz"))
        self.attempt(archive, True, hardlink)
        self.attempt(archive, True, lambda source, parent: parent.chmod(0o755))
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            target = base / "target"
            target.mkdir(mode=0o700)
            link = base / "link"
            link.symlink_to(target, target_is_directory=True)
            source = base / "archive.gz"
            source.write_bytes(archive)
            with self.assertRaises(extractor.ExtractionError):
                extractor.extract(source, hashlib.sha256(archive).hexdigest(), link, "out")
            self.assertEqual(list(target.iterdir()), [])

    def test_resource_bounds_and_malformed_headers(self):
        for constant, maximum in (("MAX_COMPRESSED", 20), ("MAX_DECOMPRESSED", 1024), ("MAX_TOTAL", 5),
                                  ("MAX_FILE", 3), ("MAX_ENTRIES", 2), ("MAX_PATH", 10), ("MAX_DEPTH", 2)):
            with self.subTest(constant=constant), patch.object(extractor, constant, maximum):
                self.attempt(transport(BASE), True)
        self.attempt(transport(BASE)[:-4], True)
        self.attempt(transport(BASE) + gzip.compress(b"concatenated"), True)
        raw = bytearray(gzip.decompress(transport(BASE)))
        raw[148] ^= 1
        self.attempt(gzip.compress(raw), True)
        raw = bytearray(gzip.decompress(transport(BASE)))
        raw[124:136] = b"77777777777\0"
        raw[148:156] = b"        "
        checksum = sum(raw[:512])
        raw[148:156] = f"{checksum:06o}\0 ".encode()
        self.attempt(gzip.compress(raw), True)
        raw = gzip.decompress(transport(BASE))
        self.attempt(gzip.compress(raw[:-1024] + b"x" * 1024), True)
        # Huge decompression ratio is bounded before tar parsing, including non-header data.
        with patch.object(extractor, "MAX_DECOMPRESSED", 4096):
            self.attempt(gzip.compress(b"\0" * 1000000), True)
        raw = bytearray(gzip.decompress(transport(BASE)))
        raw[156:157] = tarfile.XHDTYPE
        raw[124:136] = b"77777777777\0"
        raw[148:156] = b"        "
        checksum = sum(raw[:512])
        raw[148:156] = f"{checksum:06o}\0 ".encode()
        self.attempt(gzip.compress(raw), True)

    def test_partial_write_publication_collision_and_cleanup_failure(self):
        real_write = os.write
        calls = 0
        def failed_write(fd, data):
            nonlocal calls
            calls += 1
            if calls == 1:
                return real_write(fd, data[:2])
            raise OSError("fictional disk failure")
        with patch.object(extractor.os, "write", failed_write):
            self.attempt(transport(BASE), True)
        real_publish = extractor.publish_exclusive
        def collision(parent, stage, destination):
            os.mkdir(destination, 0o700, dir_fd=parent)
            real_publish(parent, stage, destination)
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            parent = base / "parent"
            parent.mkdir(mode=0o700)
            source = base / "archive.gz"
            data = transport(BASE)
            source.write_bytes(data)
            with patch.object(extractor, "publish_exclusive", collision):
                with self.assertRaises(extractor.ExtractionError):
                    extractor.extract(source, hashlib.sha256(data).hexdigest(), parent, "collision")
            self.assertEqual(list((parent / "collision").iterdir()), [])
            self.assertEqual([p.name for p in parent.iterdir()], ["collision"])
        # Error cleanup is explicit rather than a success-shaped fallback.
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            parent = base / "parent"
            parent.mkdir(mode=0o700)
            source = base / "archive.gz"
            data = transport(BASE)
            source.write_bytes(data)
            with patch.object(extractor, "extract_validated", side_effect=OSError("fictional")), patch.object(
                    extractor, "cleanup_owned", side_effect=OSError("fictional cleanup")):
                with self.assertRaisesRegex(extractor.ExtractionError, "cleanup could not be verified"):
                    extractor.extract(source, hashlib.sha256(data).hexdigest(), parent, "out")
            self.assertFalse((parent / "out").exists())

    def test_metadata_sparse_long_header_and_footer_rejections(self):
        for offset, value in ((345, b'x'), (329, b'0000001\0'), (108, b'\x80'),
                              (265, b'unsafe\nuser'), (124, b'12\0xx'), (257, b'not-tar!')):
            with self.subTest(offset=offset):
                raw = bytearray(gzip.decompress(transport(BASE)))
                raw[offset:offset + len(value)] = value
                raw[148:156] = b'        '
                checksum = sum(raw[:512])
                raw[148:156] = f'{checksum:06o}\0 '.encode()
                self.attempt(gzip.compress(raw), True)
        long_name = 'public-closure/root/' + 'a' * 110
        data = gzip.decompress(transport(BASE + [(long_name, tarfile.REGTYPE, b'x', 0o644)]))
        raw = bytearray(data)
        # Final long-name header starts after three 512-byte headers and one padded file.
        long_offset = 4 * 512
        raw[long_offset + 124:long_offset + 136] = b'00000020000\0'
        raw[long_offset + 148:long_offset + 156] = b'        '
        checksum = sum(raw[long_offset:long_offset + 512])
        raw[long_offset + 148:long_offset + 156] = f'{checksum:06o}\0 '.encode()
        self.attempt(gzip.compress(raw), True)
        # Dangling long-name extension has no regular member; no partial file is exposed.
        raw = bytearray(data)
        raw[(long_offset + 1024):] = b'\0' * (len(raw) - long_offset - 1024)
        self.attempt(gzip.compress(raw), True)
        raw = bytearray(gzip.decompress(transport(BASE)))
        raw[3 * 512 + len(BASE[-1][2])] = 1
        self.attempt(gzip.compress(raw), True)

    def test_write_path_substitution_never_follows_outside_link(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            parent = base / 'parent'
            parent.mkdir(mode=0o700)
            outside = base / 'outside'
            outside.write_bytes(b'preserve external bytes')
            source = base / 'source.gz'
            data = transport(BASE)
            source.write_bytes(data)
            original_open = extractor.os.open
            def substitution(path, flags, *args, **kwargs):
                if path == 'main.tf' and flags & os.O_CREAT:
                    os.symlink(str(outside), path, dir_fd=kwargs['dir_fd'])
                return original_open(path, flags, *args, **kwargs)
            with patch.object(extractor.os, 'open', substitution):
                with self.assertRaises(extractor.ExtractionError):
                    extractor.extract(source, hashlib.sha256(data).hexdigest(), parent, 'out')
            self.assertEqual(outside.read_bytes(), b'preserve external bytes')
            self.assertEqual(list(parent.iterdir()), [])

    def test_archive_changed_while_snapshotting_fails_before_decode(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            parent = base / 'parent'
            parent.mkdir(mode=0o700)
            source = base / 'source.gz'
            data = transport(BASE)
            source.write_bytes(data)
            original_read = os.read
            changed = False
            def mutation(fd, count):
                nonlocal changed
                chunk = original_read(fd, count)
                if chunk and not changed:
                    changed = True
                    with source.open('ab') as stream:
                        stream.write(b'late bytes')
                return chunk
            with patch.object(extractor.os, 'read', mutation), patch.object(extractor, 'decompress_verified') as decode:
                with self.assertRaises(extractor.ExtractionError):
                    extractor.extract(source, hashlib.sha256(data).hexdigest(), parent, 'out')
                decode.assert_not_called()
            self.assertEqual(list(parent.iterdir()), [])

    def test_reserved_stage_collisions_and_parent_ambiguity(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            parent = base / 'parent'
            parent.mkdir(mode=0o700)
            source = base / 'source.gz'
            data = transport(BASE)
            source.write_bytes(data)
            for suffix in ('//parent', '/parent/./', '/parent/../parent'):
                with self.assertRaises(extractor.ExtractionError):
                    extractor.extract(source, hashlib.sha256(data).hexdigest(), str(base) + suffix, 'out')
            for kind in ('directory', 'symlink'):
                reserved = parent / '.closure-extract-fixed'
                if kind == 'directory':
                    reserved.mkdir(mode=0o700)
                    (reserved / 'external').write_text('preserved')
                else:
                    reserved.symlink_to(base / 'missing', target_is_directory=True)
                with patch.object(extractor.secrets, 'token_hex', return_value='fixed'):
                    with self.assertRaises(extractor.ExtractionError):
                        extractor.extract(source, hashlib.sha256(data).hexdigest(), parent, 'out')
                if kind == 'directory':
                    self.assertEqual((reserved / 'external').read_text(), 'preserved')
                    (reserved / 'external').unlink()
                    reserved.rmdir()
                else:
                    self.assertTrue(reserved.is_symlink())
                    reserved.unlink()
    def test_no_decompression_before_selected_digest_and_full_validation_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            parent.chmod(0o700)
            source = parent / "source.gz"
            data = transport(BASE)
            source.write_bytes(data)
            with patch.object(extractor, "decompress_verified") as decode:
                with self.assertRaises(extractor.ExtractionError):
                    extractor.extract(source, "0" * 64, parent, "out")
                decode.assert_not_called()
            data = transport(BASE + [("../late-traversal", tarfile.REGTYPE, b"x", 0o644)])
            source.write_bytes(data)
            with patch.object(extractor, "extract_validated") as write:
                with self.assertRaises(extractor.ExtractionError):
                    extractor.extract(source, hashlib.sha256(data).hexdigest(), parent, "out")
                write.assert_not_called()


if __name__ == "__main__":
    if os.name != "posix":
        raise SystemExit("Linux required.")
    unittest.main()
