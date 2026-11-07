import os
from array import array
from pathlib import Path
import stat
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from unittest import TestCase, main
from unittest.mock import patch

from private_scratch import PrivateScratch, ScratchError


class PrivateScratchTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.parent = self.root / "private-parent"
        self.parent.mkdir(mode=0o700)
        os.chmod(self.parent, 0o700)

    def tearDown(self):
        self.temp.cleanup()

    def test_modes_are_restrictive_even_under_zero_umask(self):
        old = os.umask(0)
        try:
            scratch = PrivateScratch.create(str(self.parent))
            scratch.create_file("input.bin", b"fictional")
            nested = scratch.create_directory("nested")
            nested.create_file("payload.bin", b"test")
        finally:
            os.umask(old)
        root_path = self.parent / scratch.name
        self.assertEqual(stat.S_IMODE(root_path.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((root_path / "input.bin").stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE((root_path / "nested").stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((root_path / "nested" / "payload.bin").stat().st_mode), 0o600)
        scratch.cleanup()
        self.assertFalse(root_path.exists())

    def test_collision_never_adopts_or_removes_existing_directory(self):
        name = "scratch-" + "1" * 32
        collision = self.parent / name
        collision.mkdir(mode=0o700)
        marker = collision / "keep"
        marker.write_bytes(b"fictional")
        with patch("private_scratch.secrets.token_hex", return_value="1" * 32):
            with self.assertRaises(ScratchError):
                PrivateScratch.create(str(self.parent))
        self.assertEqual(marker.read_bytes(), b"fictional")

    def test_symlinked_ancestor_is_rejected(self):
        actual = self.root / "actual"
        actual.mkdir(mode=0o700)
        alias = self.root / "alias"
        alias.symlink_to(actual, target_is_directory=True)
        with self.assertRaises(ScratchError):
            PrivateScratch.create(str(alias))
        self.assertEqual(list(actual.iterdir()), [])

    def test_ancestor_swap_after_open_stays_on_retained_parent_descriptor(self):
        scratch = PrivateScratch.create(str(self.parent))
        moved = self.root / "moved-parent"
        outside = self.root / "outside"
        outside.mkdir(mode=0o700)
        os.rename(self.parent, moved)
        self.parent.symlink_to(outside, target_is_directory=True)
        scratch.create_file("inside.bin", b"fictional")
        scratch.cleanup()
        self.assertEqual(list(moved.iterdir()), [])
        self.assertEqual(list(outside.iterdir()), [])

    def test_replaced_root_is_not_removed(self):
        scratch = PrivateScratch.create(str(self.parent))
        original = self.parent / scratch.name
        moved = self.parent / "held-original"
        os.rename(original, moved)
        original.mkdir(mode=0o700)
        with self.assertRaises(ScratchError):
            scratch.cleanup()
        self.assertTrue(original.is_dir())
        os.rmdir(original)
        os.rename(moved, original)
        scratch.cleanup()

    def test_replaced_file_symlink_is_not_unlinked_or_followed(self):
        scratch = PrivateScratch.create(str(self.parent))
        scratch.create_file("owned.bin", b"fictional")
        outside = self.root / "outside.bin"
        outside.write_bytes(b"must-survive")
        owned = self.parent / scratch.name / "owned.bin"
        owned.unlink()
        owned.symlink_to(outside)
        with self.assertRaises(ScratchError):
            scratch.cleanup()
        self.assertEqual(outside.read_bytes(), b"must-survive")
        self.assertTrue(owned.is_symlink())
        scratch.close_descriptors()

    def test_replaced_directory_and_unexpected_entry_fail_before_deletion(self):
        scratch = PrivateScratch.create(str(self.parent))
        child = scratch.create_directory("owned-dir")
        child.create_file("owned.bin", b"fictional")
        root_path = self.parent / scratch.name
        moved = root_path / "moved-owned-dir"
        os.rename(root_path / "owned-dir", moved)
        (root_path / "owned-dir").mkdir(mode=0o700)
        with self.assertRaises(ScratchError):
            scratch.cleanup()
        self.assertEqual((moved / "owned.bin").read_bytes(), b"fictional")
        self.assertTrue((root_path / "owned-dir").is_dir())
        scratch.close_descriptors()

    def test_unexpected_symlink_blocks_cleanup_without_touching_target(self):
        scratch = PrivateScratch.create(str(self.parent))
        scratch.create_file("owned.bin", b"fictional")
        outside = self.root / "outside.bin"
        outside.write_bytes(b"must-survive")
        (self.parent / scratch.name / "surprise").symlink_to(outside)
        with self.assertRaises(ScratchError):
            scratch.cleanup()
        self.assertEqual(outside.read_bytes(), b"must-survive")
        self.assertTrue((self.parent / scratch.name / "owned.bin").exists())
        scratch.close_descriptors()

    def test_concurrent_exclusive_creation_has_one_owner(self):
        token = "2" * 32
        with patch("private_scratch.secrets.token_hex", return_value=token):
            def create():
                try:
                    return PrivateScratch.create(str(self.parent))
                except ScratchError:
                    return None
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _index: create(), range(2)))
        winners = [result for result in results if result is not None]
        self.assertEqual(len(winners), 1)
        winners[0].cleanup()

    def test_concurrent_cleanup_is_serialized_and_idempotent(self):
        scratch = PrivateScratch.create(str(self.parent))
        scratch.create_file("owned.bin", b"fictional")
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _index: scratch.cleanup(), range(2)))
        self.assertFalse((self.parent / scratch.name).exists())

    def test_context_cleanup_and_exclusive_file_creation(self):
        with PrivateScratch.create(str(self.parent)) as scratch:
            scratch.create_file("owned.bin", b"fictional")
            with self.assertRaises(ScratchError):
                scratch.create_file("owned.bin", b"replacement")
        self.assertFalse((self.parent / scratch.name).exists())


    def test_partial_byte_writes_preserve_formatted_memoryview_bytes(self):
        scratch = PrivateScratch.create(str(self.parent))
        values = array("I", range(1, 24))
        source = memoryview(values)
        expected = source.cast("B").tobytes()
        real_write = os.write
        writes = []

        def short_write(fd, view):
            chunk = memoryview(view).cast("B")[:3]
            written = real_write(fd, chunk)
            writes.append(written)
            return written

        try:
            with patch("private_scratch.os.write", side_effect=short_write):
                scratch.create_file("formatted.bin", source)
        finally:
            source.release()
        self.assertGreater(len(writes), 1)
        self.assertTrue(all(0 < count <= 3 for count in writes))
        self.assertEqual(sum(writes), len(expected))
        self.assertEqual((self.parent / scratch.name / "formatted.bin").read_bytes(), expected)
        scratch.cleanup()

    def test_non_contiguous_memoryview_is_rejected_before_file_creation(self):
        scratch = PrivateScratch.create(str(self.parent))
        source = memoryview(bytearray(b"01234567"))[::2]
        try:
            with self.assertRaisesRegex(TypeError, "contiguous"):
                scratch.create_file("rejected.bin", source)
        finally:
            source.release()
        self.assertEqual(scratch._entries, {})
        self.assertEqual(list((self.parent / scratch.name).iterdir()), [])
        scratch.cleanup()

    def test_zero_progress_write_fails_and_leaves_only_owned_entry(self):
        scratch = PrivateScratch.create(str(self.parent))
        with patch("private_scratch.os.write", return_value=0):
            with self.assertRaisesRegex(ScratchError, "did not make progress"):
                scratch.create_file("stalled.bin", b"fictional")
        directory = self.parent / scratch.name
        self.assertEqual([path.name for path in directory.iterdir()], ["stalled.bin"])
        self.assertEqual((directory / "stalled.bin").read_bytes(), b"")
        self.assertIn("stalled.bin", scratch._entries)
        scratch.cleanup()
        self.assertFalse(directory.exists())
    def _assert_child_setup_failure(self, failure_kind):
        scratch = PrivateScratch.create(str(self.parent))
        opened = {}
        real_open = os.open
        real_fchmod = os.fchmod
        real_fstat = os.fstat

        def capture_open(path, *args, **kwargs):
            fd = real_open(path, *args, **kwargs)
            if path == "nested":
                opened["fd"] = fd
            return fd

        with patch("private_scratch.os.open", side_effect=capture_open):
            if failure_kind == "fchmod":
                def fail_fchmod(fd, mode):
                    if fd == opened.get("fd"):
                        raise OSError("synthetic fchmod failure")
                    return real_fchmod(fd, mode)
                failure = patch("private_scratch.os.fchmod", side_effect=fail_fchmod)
                expected = OSError
            elif failure_kind == "fstat":
                def fail_fstat(fd):
                    if fd == opened.get("fd"):
                        raise OSError("synthetic fstat failure")
                    return real_fstat(fd)
                failure = patch("private_scratch.os.fstat", side_effect=fail_fstat)
                expected = OSError
            else:
                real_verify = PrivateScratch._verify_link
                def fail_child_verify(instance):
                    if instance.name == "nested":
                        raise ScratchError("synthetic link verification failure")
                    return real_verify(instance)
                failure = patch.object(PrivateScratch, "_verify_link", autospec=True,
                                       side_effect=fail_child_verify)
                expected = ScratchError
            with failure, self.assertRaises(expected):
                scratch.create_directory("nested")

        child_fd = opened["fd"]
        with self.assertRaises(OSError):
            os.fstat(child_fd)
        orphan = self.parent / scratch.name / "nested"
        self.assertTrue(orphan.is_dir())
        self.assertEqual(list(orphan.iterdir()), [])
        with self.assertRaises(ScratchError):
            scratch.cleanup()
        scratch.close_descriptors()

    def test_child_fchmod_failure_closes_descriptor_and_leaves_empty_orphan(self):
        self._assert_child_setup_failure("fchmod")

    def test_child_fstat_failure_closes_descriptor_and_leaves_empty_orphan(self):
        self._assert_child_setup_failure("fstat")

    def test_child_link_verification_failure_closes_descriptor_and_leaves_empty_orphan(self):
        self._assert_child_setup_failure("verify")

    def test_untrusted_filesystem_root_is_rejected(self):
        real_open = os.open
        real_fstat = os.fstat
        root_fd = {}

        def capture_root(path, *args, **kwargs):
            fd = real_open(path, *args, **kwargs)
            if path == "/":
                root_fd["fd"] = fd
            return fd

        def make_root_unsafe(fd):
            info = real_fstat(fd)
            if fd != root_fd.get("fd"):
                return info
            fields = list(info)
            fields[0] = stat.S_IFDIR | 0o777
            fields[4] = 0
            return os.stat_result(fields)

        with patch("private_scratch.os.open", side_effect=capture_root):
            with patch("private_scratch.os.fstat", side_effect=make_root_unsafe):
                with self.assertRaises(ScratchError):
                    PrivateScratch.create(str(self.parent))
        self.assertEqual(list(self.parent.iterdir()), [])
if __name__ == "__main__":
    main()