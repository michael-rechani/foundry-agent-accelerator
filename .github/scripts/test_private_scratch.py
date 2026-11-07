import os
from array import array
from pathlib import Path
import stat
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


    def test_nested_context_managers_remove_child_inventory_before_parent_exit(self):
        with PrivateScratch.create(str(self.parent)) as scratch:
            with scratch.create_directory("nested") as child:
                child.create_file("payload.bin", b"fictional")
                self.assertIn("nested", scratch._entries)
            self.assertNotIn("nested", scratch._entries)
            self.assertFalse((self.parent / scratch.name / "nested").exists())
        self.assertFalse((self.parent / scratch.name).exists())

    def test_explicit_and_repeated_child_cleanup_detaches_once(self):
        scratch = PrivateScratch.create(str(self.parent))
        child = scratch.create_directory("nested")
        child.create_file("payload.bin", b"fictional")
        child.cleanup()
        self.assertNotIn("nested", scratch._entries)
        child.cleanup()
        self.assertNotIn("nested", scratch._entries)
        scratch.cleanup()
        self.assertFalse((self.parent / scratch.name).exists())

    def test_nested_grandchild_cleanup_updates_each_ownership_level(self):
        scratch = PrivateScratch.create(str(self.parent))
        child = scratch.create_directory("child")
        grandchild = child.create_directory("grandchild")
        grandchild.create_file("payload.bin", b"fictional")
        grandchild.cleanup()
        self.assertNotIn("grandchild", child._entries)
        child.cleanup()
        self.assertNotIn("child", scratch._entries)
        scratch.cleanup()
        self.assertFalse((self.parent / scratch.name).exists())

    def test_successfully_removed_child_name_can_be_reused(self):
        scratch = PrivateScratch.create(str(self.parent))
        first = scratch.create_directory("nested")
        first.cleanup()
        second = scratch.create_directory("nested")
        second.create_file("new.bin", b"fictional")
        scratch.cleanup()
        self.assertFalse((self.parent / scratch.name).exists())

    def test_concurrent_parent_and_child_cleanup_is_serialized(self):
        scratch = PrivateScratch.create(str(self.parent))
        child = scratch.create_directory("nested")
        child.create_file("payload.bin", b"fictional")
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(scratch.cleanup), pool.submit(child.cleanup)]
            for future in futures:
                future.result()
        child.cleanup()
        scratch.cleanup()
        self.assertFalse((self.parent / scratch.name).exists())

    def test_child_failure_retains_parent_ownership_and_refuses_unknown_files(self):
        scratch = PrivateScratch.create(str(self.parent))
        child = scratch.create_directory("nested")
        unexpected = self.parent / scratch.name / "nested" / "provider-generated.cache"
        unexpected.write_bytes(b"synthetic")
        record = scratch._entries["nested"]
        with self.assertRaises(ScratchError):
            child.cleanup()
        self.assertIs(scratch._entries.get("nested"), record)
        self.assertTrue(unexpected.exists())
        with self.assertRaises(ScratchError):
            scratch.cleanup()
        self.assertIs(scratch._entries.get("nested"), record)
        unexpected.unlink()
        child.cleanup()
        self.assertNotIn("nested", scratch._entries)
        scratch.cleanup()

    def test_child_rmdir_failure_retains_parent_ownership_for_retry(self):
        scratch = PrivateScratch.create(str(self.parent))
        child = scratch.create_directory("nested")
        record = scratch._entries["nested"]
        real_rmdir = os.rmdir
        failed = False

        def fail_child_once(name, *, dir_fd=None):
            nonlocal failed
            if name == "nested" and dir_fd == child._parent_fd and not failed:
                failed = True
                raise OSError("synthetic rmdir failure")
            return real_rmdir(name, dir_fd=dir_fd)

        with patch("private_scratch.os.rmdir", side_effect=fail_child_once):
            with self.assertRaises(OSError):
                child.cleanup()
        self.assertTrue(failed)
        self.assertIs(scratch._entries.get("nested"), record)
        self.assertTrue((self.parent / scratch.name / "nested").is_dir())
        child.cleanup()
        self.assertNotIn("nested", scratch._entries)
        scratch.cleanup()
    def test_fchmod_failure_records_bound_file_for_parent_cleanup(self):
        scratch = PrivateScratch.create(str(self.parent))
        scratch.create_file("earlier.bin", b"fictional-sensitive")
        with patch("private_scratch.os.fchmod", side_effect=OSError("synthetic fchmod failure")):
            with self.assertRaises(OSError):
                scratch.create_file("new.bin", b"fictional")
        self.assertIn("new.bin", scratch._entries)
        scratch.cleanup()
        self.assertFalse((self.parent / scratch.name).exists())

    def test_transient_fstat_failure_recovers_bound_file_for_cleanup(self):
        scratch = PrivateScratch.create(str(self.parent))
        scratch.create_file("earlier.bin", b"fictional-sensitive")
        opened = {}
        real_open = os.open
        real_fstat = os.fstat
        failed = False

        def capture_open(path, *args, **kwargs):
            fd = real_open(path, *args, **kwargs)
            if path == "new.bin":
                opened["fd"] = fd
            return fd

        def fail_once(fd):
            nonlocal failed
            if fd == opened.get("fd") and not failed:
                failed = True
                raise OSError("synthetic transient fstat failure")
            return real_fstat(fd)

        with patch("private_scratch.os.open", side_effect=capture_open), \
                patch("private_scratch.os.fstat", side_effect=fail_once):
            with self.assertRaises(OSError):
                scratch.create_file("new.bin", b"fictional")
        self.assertTrue(failed)
        self.assertIn("new.bin", scratch._entries)
        scratch.cleanup()
        self.assertFalse((self.parent / scratch.name).exists())

    def test_persistent_fstat_failure_retains_unverified_orphan(self):
        scratch = PrivateScratch.create(str(self.parent))
        scratch.create_file("earlier.bin", b"fictional-sensitive")
        opened = {}
        real_open = os.open
        real_fstat = os.fstat

        def capture_open(path, *args, **kwargs):
            fd = real_open(path, *args, **kwargs)
            if path == "new.bin":
                opened["fd"] = fd
            return fd

        def fail_created_file(fd):
            if fd == opened.get("fd"):
                raise OSError("synthetic persistent fstat failure")
            return real_fstat(fd)

        with patch("private_scratch.os.open", side_effect=capture_open), \
                patch("private_scratch.os.fstat", side_effect=fail_created_file):
            with self.assertRaisesRegex(ScratchError, "could not be safely recorded"):
                scratch.create_file("new.bin", b"fictional")
        root = self.parent / scratch.name
        self.assertEqual((root / "earlier.bin").read_bytes(), b"fictional-sensitive")
        self.assertTrue((root / "new.bin").is_file())
        self.assertNotIn("new.bin", scratch._entries)
        with self.assertRaises(ScratchError):
            scratch.cleanup()
        self.assertTrue((root / "earlier.bin").exists())
        self.assertTrue((root / "new.bin").exists())
        scratch.close_descriptors()

    def test_fstat_recovery_refuses_renamed_original_and_replacement_name(self):
        scratch = PrivateScratch.create(str(self.parent))
        scratch.create_file("earlier.bin", b"fictional-sensitive")
        opened = {}
        real_open = os.open
        real_fstat = os.fstat
        renamed = False

        def capture_open(path, *args, **kwargs):
            fd = real_open(path, *args, **kwargs)
            if path == "new.bin":
                opened["fd"] = fd
            return fd

        def rename_before_recovery(fd):
            nonlocal renamed
            if fd == opened.get("fd") and not renamed:
                renamed = True
                os.rename("new.bin", "held-original.bin", src_dir_fd=scratch._fd, dst_dir_fd=scratch._fd)
                replacement = real_open(
                    "new.bin", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=scratch._fd
                )
                os.close(replacement)
                raise OSError("synthetic fstat failure after name replacement")
            return real_fstat(fd)

        with patch("private_scratch.os.open", side_effect=capture_open), \
                patch("private_scratch.os.fstat", side_effect=rename_before_recovery):
            with self.assertRaisesRegex(ScratchError, "could not be safely recorded"):
                scratch.create_file("new.bin", b"fictional")
        root = self.parent / scratch.name
        self.assertTrue(renamed)
        self.assertTrue((root / "held-original.bin").is_file())
        self.assertTrue((root / "new.bin").is_file())
        self.assertNotIn("new.bin", scratch._entries)
        with self.assertRaises(ScratchError):
            scratch.cleanup()
        self.assertTrue((root / "earlier.bin").exists())
        self.assertTrue((root / "held-original.bin").exists())
        self.assertTrue((root / "new.bin").exists())
        scratch.close_descriptors()

    def test_owned_file_descriptor_lives_until_verified_cleanup(self):
        scratch = PrivateScratch.create(str(self.parent))
        scratch.create_file("owned.bin", b"fictional")
        owned_fd = scratch._entries["owned.bin"][2]
        self.assertIsInstance(owned_fd, int)
        self.assertFalse(os.get_inheritable(owned_fd))
        os.fstat(owned_fd)
        scratch.cleanup()
        with self.assertRaises(OSError):
            os.fstat(owned_fd)

    def test_held_inode_prevents_reused_inode_replacement_from_being_adopted(self):
        scratch = PrivateScratch.create(str(self.parent))
        scratch.create_file("owned.bin", b"fictional")
        owned_fd = scratch._entries["owned.bin"][2]
        original_info = os.fstat(owned_fd)
        path = self.parent / scratch.name / "owned.bin"
        path.unlink()
        path.write_bytes(b"replacement")
        os.chmod(path, 0o600)
        replacement_info = path.stat()
        self.assertNotEqual((original_info.st_dev, original_info.st_ino),
                            (replacement_info.st_dev, replacement_info.st_ino))
        with self.assertRaises(ScratchError):
            scratch.cleanup()
        self.assertEqual(path.read_bytes(), b"replacement")
        self.assertEqual(os.fstat(owned_fd).st_ino, original_info.st_ino)
        scratch.close_descriptors()
        with self.assertRaises(OSError):
            os.fstat(owned_fd)

    def test_duplicate_failure_leaves_unowned_file_and_preserves_prior_file(self):
        scratch = PrivateScratch.create(str(self.parent))
        scratch.create_file("earlier.bin", b"fictional-sensitive")
        with patch("private_scratch.os.dup", side_effect=OSError("synthetic dup failure")):
            with self.assertRaisesRegex(ScratchError, "could not be safely recorded"):
                scratch.create_file("new.bin", b"fictional")
        root = self.parent / scratch.name
        self.assertEqual((root / "earlier.bin").read_bytes(), b"fictional-sensitive")
        self.assertTrue((root / "new.bin").is_file())
        self.assertNotIn("new.bin", scratch._entries)
        with self.assertRaises(ScratchError):
            scratch.cleanup()
        (root / "new.bin").unlink()
        scratch.cleanup()

    def test_duplicate_fstat_failure_closes_duplicate_and_fails_closed(self):
        scratch = PrivateScratch.create(str(self.parent))
        duplicated = set()
        real_dup = os.dup
        real_fstat = os.fstat

        def capture_dup(fd):
            duplicate = real_dup(fd)
            duplicated.add(duplicate)
            return duplicate

        def fail_duplicate_fstat(fd):
            if fd in duplicated:
                raise OSError("synthetic duplicate fstat failure")
            return real_fstat(fd)

        with patch("private_scratch.os.dup", side_effect=capture_dup), \
                patch("private_scratch.os.fstat", side_effect=fail_duplicate_fstat):
            with self.assertRaisesRegex(ScratchError, "could not be safely recorded"):
                scratch.create_file("new.bin", b"fictional")
        self.assertTrue(duplicated)
        for fd in duplicated:
            with self.assertRaises(OSError):
                real_fstat(fd)
        self.assertNotIn("new.bin", scratch._entries)
        (self.parent / scratch.name / "new.bin").unlink()
        scratch.cleanup()

    def test_owned_descriptor_close_error_is_reported_without_retry(self):
        scratch = PrivateScratch.create(str(self.parent))
        scratch.create_file("owned.bin", b"fictional")
        owned_fd = scratch._entries["owned.bin"][2]
        real_close = os.close
        failed = False

        def close_then_report_error(fd):
            nonlocal failed
            if fd == owned_fd and not failed:
                failed = True
                real_close(fd)
                raise OSError("synthetic close error")
            return real_close(fd)

        with patch("private_scratch.os.close", side_effect=close_then_report_error):
            with self.assertRaisesRegex(ScratchError, "could not be closed"):
                scratch.cleanup()
        self.assertTrue(failed)
        self.assertFalse((self.parent / scratch.name / "owned.bin").exists())
        self.assertNotIn("owned.bin", scratch._entries)
        scratch.cleanup()
        with self.assertRaises(OSError):
            os.fstat(owned_fd)

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
