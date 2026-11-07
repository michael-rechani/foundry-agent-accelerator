import gzip
import hashlib
import io
import os
from pathlib import Path
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
        # Reject a disagreeing following header even if both individual paths look safe.
        raw = bytearray(data)
        following = long_offset + 1024
        raw[following:following + 100] = b'public-closure/root/different'.ljust(100, b'\0')
        raw[following + 148:following + 156] = b'        '
        checksum = sum(raw[following:following + 512])
        raw[following + 148:following + 156] = f'{checksum:06o}\0 '.encode()
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
            stages = list(parent.iterdir())
            self.assertEqual(len(stages), 1)
            self.assertTrue((stages[0] / 'public-closure/root/main.tf').is_symlink())

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
    def test_failed_fsync_zero_write_and_staging_identity_stop_publication(self):
        with patch.object(extractor.os, 'fsync', side_effect=OSError('fictional fsync failure')):
            self.attempt(transport(BASE), True)
        with patch.object(extractor.os, 'write', return_value=0):
            self.attempt(transport(BASE), True)
        real_verify = extractor.same_directory
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            parent = base / 'parent'
            parent.mkdir(mode=0o700)
            source = base / 'source.gz'
            data = transport(BASE)
            source.write_bytes(data)
            count = 0
            def ownership_failure(parent_fd, name, directory_fd):
                nonlocal count
                count += 1
                if count >= 2:
                    raise extractor.ExtractionError('fictional ownership mismatch')
                return real_verify(parent_fd, name, directory_fd)
            with patch.object(extractor, 'same_directory', ownership_failure), patch.object(extractor, 'publish_exclusive') as publish:
                with self.assertRaisesRegex(extractor.ExtractionError, 'cleanup could not be verified'):
                    extractor.extract(source, hashlib.sha256(data).hexdigest(), parent, 'out')
                publish.assert_not_called()
            self.assertFalse((parent / 'out').exists())
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


    def test_synthetic_execution_non_root_without_credentials(self):
        self.assertNotEqual(os.geteuid(), 0)
        self.assertFalse(any(name.startswith(('AZURE_', 'ARM_', 'ACTIONS_ID_TOKEN_'))
                             or name in ('GH_TOKEN', 'GITHUB_TOKEN') for name in os.environ))

    def test_unknown_file_and_moved_external_directory_prevent_all_cleanup(self):
        for kind in ('unknown-file', 'moved-directory', 'replace-file', 'replace-directory', 'hardlink'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                base = Path(folder)
                parent = base / 'parent'
                parent.mkdir(mode=0o700)
                source = base / 'source.gz'
                data = transport(BASE)
                source.write_bytes(data)
                outside = base / 'outside'
                outside.mkdir()
                (outside / 'preserve').write_bytes(b'UNOWNED DATA')
                original = extractor.extract_validated
                stage = None
                def inject(stream, entries, root_fd, ledger, *, original=original, parent=parent, kind=kind, outside=outside, base=base):
                    nonlocal stage
                    original(stream, entries, root_fd, ledger)
                    stage = next(parent.iterdir())
                    if kind == 'unknown-file':
                        (stage / 'unknown').write_bytes(b'UNOWNED DATA')
                    elif kind == 'moved-directory':
                        outside.rename(stage / 'unowned-directory')
                    elif kind == 'replace-file':
                        (stage / 'public-closure/root/main.tf').rename(base / 'displaced-file')
                        (stage / 'public-closure/root/main.tf').write_bytes(b'UNOWNED DATA')
                    elif kind == 'replace-directory':
                        (stage / 'public-closure/root').rename(base / 'displaced-root')
                        outside.rename(stage / 'public-closure/root')
                    else:
                        os.link(stage / 'public-closure/root/main.tf', outside / 'hardlinked')
                    raise OSError('fictional ordinary extraction failure')
                with patch.object(extractor, 'extract_validated', inject), patch.object(extractor.os, 'unlink', wraps=os.unlink) as unlink, patch.object(extractor.os, 'rmdir', wraps=os.rmdir) as rmdir:
                    with self.assertRaisesRegex(extractor.ExtractionError, 'cleanup could not be verified'):
                        extractor.extract(source, hashlib.sha256(data).hexdigest(), parent, 'out')
                    unlink.assert_not_called()
                    rmdir.assert_not_called()
                self.assertFalse((parent / 'out').exists())
                self.assertTrue(stage.exists())
                if kind == 'unknown-file':
                    self.assertEqual((stage / 'unknown').read_bytes(), b'UNOWNED DATA')
                elif kind == 'moved-directory':
                    self.assertEqual((stage / 'unowned-directory/preserve').read_bytes(), b'UNOWNED DATA')
                elif kind == 'replace-file':
                    self.assertEqual((stage / 'public-closure/root/main.tf').read_bytes(), b'UNOWNED DATA')
                    self.assertEqual((base / 'displaced-file').read_bytes(), BASE[-1][2])
                elif kind == 'replace-directory':
                    self.assertEqual((stage / 'public-closure/root/preserve').read_bytes(), b'UNOWNED DATA')
                    self.assertEqual((base / 'displaced-root/main.tf').read_bytes(), BASE[-1][2])
                else:
                    self.assertEqual((outside / 'hardlinked').read_bytes(), BASE[-1][2])
                if kind not in ('replace-file', 'replace-directory'):
                    self.assertEqual((stage / 'public-closure/root/main.tf').read_bytes(), BASE[-1][2])

    def test_creation_succeeds_but_descriptor_binding_fails_retains_staging(self):
        for kind in ('directory-open', 'file-bind', 'directory-bind', 'stage-open', 'ledger-open'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                base = Path(folder)
                parent = base / 'parent'
                parent.mkdir(mode=0o700)
                source = base / 'source.gz'
                data = transport(BASE)
                source.write_bytes(data)
                real_open = os.open
                real_bind = extractor.OwnershipLedger.bind
                def open_failure(path, flags, *args, kind=kind, real_open=real_open, **kwargs):
                    if ((kind == 'directory-open' and path == 'root' and flags & os.O_DIRECTORY)
                            or (kind == 'stage-open' and str(path).startswith('.closure-extract-'))):
                        raise OSError('fictional descriptor failure')
                    return real_open(path, flags, *args, **kwargs)
                def bind_failure(ledger, name, fd, directory, *, kind=kind, real_bind=real_bind):
                    if ((kind == 'file-bind' and not directory)
                            or (kind == 'directory-bind' and name == 'public-closure/root')):
                        raise OSError('fictional failed identity binding')
                    return real_bind(ledger, name, fd, directory)
                with patch.object(extractor.os, 'open', open_failure), patch.object(extractor.OwnershipLedger, 'bind', bind_failure):
                    if kind == 'ledger-open':
                        with patch.object(extractor.OwnershipLedger, '__init__', side_effect=OSError('ledger allocation')):
                            with self.assertRaises(extractor.ExtractionError):
                                extractor.extract(source, hashlib.sha256(data).hexdigest(), parent, 'out')
                    else:
                        with self.assertRaises(extractor.ExtractionError):
                            extractor.extract(source, hashlib.sha256(data).hexdigest(), parent, 'out')
                self.assertFalse((parent / 'out').exists())
                stages = list(parent.iterdir())
                self.assertEqual(len(stages), 1)
                if kind in ('directory-open', 'directory-bind'):
                    self.assertTrue((stages[0] / 'public-closure/root').is_dir())
                elif kind == 'file-bind':
                    self.assertTrue((stages[0] / 'public-closure/root/main.tf').exists())

    def test_unledgered_cleanup_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'unknown').write_bytes(b'UNOWNED DATA')
            fd = os.open(root, extractor.FLAGS | os.O_DIRECTORY)
            try:
                with self.assertRaisesRegex(extractor.ExtractionError, 'ledger required'):
                    extractor.cleanup_owned(fd)
            finally:
                os.close(fd)
            self.assertEqual((root / 'unknown').read_bytes(), b'UNOWNED DATA')

    def test_late_unknown_entry_after_preflight_stops_without_sweeping_it(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            parent = base / 'parent'
            parent.mkdir(mode=0o700)
            source = base / 'source.gz'
            data = transport(BASE)
            source.write_bytes(data)
            original_extract = extractor.extract_validated
            original_verify = extractor.OwnershipLedger.verify
            injected = False
            def fail(stream, entries, root_fd, ledger):
                original_extract(stream, entries, root_fd, ledger)
                raise OSError('fictional ordinary failure')
            def late(ledger, root_fd):
                nonlocal injected
                original_verify(ledger, root_fd)
                if not injected:
                    injected = True
                    stage = next(parent.iterdir())
                    (stage / 'public-closure/root/unowned').write_bytes(b'UNOWNED DATA')
            with patch.object(extractor, 'extract_validated', fail), patch.object(extractor.OwnershipLedger, 'verify', late):
                with self.assertRaisesRegex(extractor.ExtractionError, 'cleanup could not be verified'):
                    extractor.extract(source, hashlib.sha256(data).hexdigest(), parent, 'out')
            stage = next(parent.iterdir())
            self.assertEqual((stage / 'public-closure/root/unowned').read_bytes(), b'UNOWNED DATA')
            self.assertEqual((stage / 'public-closure/root/main.tf').read_bytes(), BASE[-1][2])

    def test_spool_has_no_named_unlink_fallback(self):
        real_open = os.open
        def unsupported(path, flags, *args, **kwargs):
            if hasattr(os, 'O_TMPFILE') and flags & os.O_TMPFILE == os.O_TMPFILE:
                raise OSError('fictional filesystem lacks O_TMPFILE')
            return real_open(path, flags, *args, **kwargs)
        with patch.object(extractor.os, 'open', unsupported):
            self.attempt(transport(BASE), True)
        with tempfile.TemporaryDirectory() as folder:
            fd = os.open(folder, extractor.FLAGS | os.O_DIRECTORY)
            try:
                with extractor.anonymous_spool(fd) as stream:
                    self.assertEqual(os.fstat(stream.fileno()).st_nlink, 0)
                    self.assertEqual(os.listdir(fd), [])
                    stream.write(b'fictional')
            finally:
                os.close(fd)

    def test_replacement_before_binding_preserves_unknown_inode(self):
        for directory in (False, True):
            with self.subTest(directory=directory), tempfile.TemporaryDirectory() as folder:
                base = Path(folder)
                parent = base / 'parent'
                parent.mkdir(mode=0o700)
                data = transport(BASE)
                source = base / 'source.gz'
                source.write_bytes(data)
                original_bind = extractor.OwnershipLedger.bind
                displaced = base / 'displaced'
                replacement = None
                def replace(ledger, name, fd, is_directory, *, directory=directory, parent=parent, displaced=displaced, original_bind=original_bind):
                    nonlocal replacement
                    target_name = 'public-closure/root' if directory else 'public-closure/root/main.tf'
                    if name == target_name:
                        stage = next(parent.iterdir())
                        replacement = stage / name
                        replacement.rename(displaced)
                        if directory:
                            replacement.mkdir()
                            (replacement / 'unknown').write_bytes(b'UNOWNED DATA')
                        else:
                            replacement.write_bytes(b'UNOWNED DATA')
                    return original_bind(ledger, name, fd, is_directory)
                with patch.object(extractor.OwnershipLedger, 'bind', replace):
                    with self.assertRaisesRegex(extractor.ExtractionError, 'cleanup could not be verified'):
                        extractor.extract(source, hashlib.sha256(data).hexdigest(), parent, 'out')
                self.assertTrue(displaced.exists())
                self.assertEqual((replacement / 'unknown' if directory else replacement).read_bytes(), b'UNOWNED DATA')
                self.assertFalse((parent / 'out').exists())

    def test_successful_mkdir_then_failure_and_failed_ledger_dup_are_not_swept(self):
        for kind in ('mkdir', 'dup'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                base = Path(folder)
                parent = base / 'parent'
                parent.mkdir(mode=0o700)
                data = transport(BASE)
                source = base / 'source.gz'
                source.write_bytes(data)
                real_mkdir = os.mkdir
                real_bind = extractor.OwnershipLedger.bind
                def mkdir(name, *args, kind=kind, real_mkdir=real_mkdir, **kwargs):
                    real_mkdir(name, *args, **kwargs)
                    if kind == 'mkdir' and name == 'root':
                        raise OSError('fictional failure after directory creation')
                def bind(ledger, name, fd, directory, *, kind=kind, real_bind=real_bind):
                    if kind == 'dup' and not directory:
                        with patch.object(extractor.os, 'dup', side_effect=OSError('fictional descriptor exhaustion')):
                            return real_bind(ledger, name, fd, directory)
                    return real_bind(ledger, name, fd, directory)
                with patch.object(extractor.os, 'mkdir', mkdir), patch.object(extractor.OwnershipLedger, 'bind', bind):
                    with self.assertRaisesRegex(extractor.ExtractionError, 'cleanup could not be verified'):
                        extractor.extract(source, hashlib.sha256(data).hexdigest(), parent, 'out')
                stage = next(parent.iterdir())
                self.assertTrue((stage / 'public-closure/root').exists())
                if kind == 'dup':
                    self.assertTrue((stage / 'public-closure/root/main.tf').exists())
                self.assertFalse((parent / 'out').exists())

    def test_missing_known_entry_and_preflight_error_delete_nothing(self):
        for kind in ('missing', 'verification'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                base = Path(folder)
                parent = base / 'parent'
                parent.mkdir(mode=0o700)
                data = transport(BASE)
                source = base / 'source.gz'
                source.write_bytes(data)
                original = extractor.extract_validated
                def fail(stream, entries, root_fd, ledger, *, original=original, kind=kind, parent=parent, base=base):
                    original(stream, entries, root_fd, ledger)
                    if kind == 'missing':
                        stage = next(parent.iterdir())
                        (stage / 'public-closure/root/main.tf').rename(base / 'displaced')
                    raise OSError('fictional ordinary failure')
                original_verify = extractor.OwnershipLedger.verify
                def verify(ledger, root_fd, *, kind=kind, original_verify=original_verify):
                    if kind == 'verification':
                        raise OSError('fictional verification failure')
                    original_verify(ledger, root_fd)
                with patch.object(extractor, 'extract_validated', fail), patch.object(extractor.OwnershipLedger, 'verify', verify), patch.object(extractor.os, 'unlink', wraps=os.unlink) as unlink, patch.object(extractor.os, 'rmdir', wraps=os.rmdir) as rmdir:
                    with self.assertRaisesRegex(extractor.ExtractionError, 'cleanup could not be verified'):
                        extractor.extract(source, hashlib.sha256(data).hexdigest(), parent, 'out')
                    unlink.assert_not_called()
                    rmdir.assert_not_called()
                stage = next(parent.iterdir())
                self.assertTrue((stage / 'public-closure/root').exists())
                kept = base / 'displaced' if kind == 'missing' else stage / 'public-closure/root/main.tf'
                self.assertEqual(kept.read_bytes(), BASE[-1][2])

if __name__ == "__main__":
    if os.name != "posix":
        raise SystemExit("Linux required.")
    unittest.main()
