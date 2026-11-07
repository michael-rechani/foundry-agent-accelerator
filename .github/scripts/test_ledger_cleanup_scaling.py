"""Fictional inventory timings; no archives, providers or privileged operations."""
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import extract_platform_dependencies as extractor


class CleanupScalingTests(unittest.TestCase):
    def measure(self, count, fanout):
        self.assertNotEqual(os.geteuid(), 0)
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        print(f"synthetic descriptor limits soft={soft} hard={hard}", flush=True)
        self.assertGreater(soft, count + 128, "Insufficient descriptor budget for this fictional fixture")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            root_fd = os.open(root, extractor.FLAGS | os.O_DIRECTORY)
            ledger = extractor.OwnershipLedger(root_fd)
            try:
                start = time.monotonic()
                directories = []
                if fanout:
                    for index in range(fanout):
                        name = f"d{index:05d}"
                        ledger.begin(name)
                        os.mkdir(name, dir_fd=root_fd)
                        fd = os.open(name, extractor.FLAGS | os.O_DIRECTORY, dir_fd=root_fd)
                        try:
                            ledger.bind(name, fd, True)
                        finally:
                            os.close(fd)
                        directories.append(name)
                for index in range(count - fanout):
                    prefix = directories[index % fanout] + "/" if fanout else ""
                    name = prefix + f"f{index:05d}"
                    parent_fd = ledger.entries[prefix[:-1]] if prefix else root_fd
                    ledger.begin(name)
                    fd = os.open(name.split("/")[-1], os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600, dir_fd=parent_fd)
                    try:
                        ledger.bind(name, fd, False)
                    finally:
                        os.close(fd)
                create_seconds = time.monotonic() - start
                listdir = os.listdir
                calls = 0
                enumerated = 0
                def counted(fd):
                    nonlocal calls, enumerated
                    names = listdir(fd)
                    calls += 1
                    enumerated += len(names)
                    return names
                sizes = [((count - fanout) // fanout) + (index < (count - fanout) % fanout)
                         for index in range(fanout)] if fanout else [count]
                expected = sum(size * (size + 1) // 2 for size in sizes)
                if fanout:
                    expected += fanout * (fanout + 1) // 2
                refused = expected > extractor.MAX_CLEANUP_ENUMERATION
                start = time.monotonic()
                with patch.object(extractor.os, "listdir", counted):
                    if refused:
                        with patch.object(extractor.os, "unlink", wraps=os.unlink) as unlink, patch.object(extractor.os, "rmdir", wraps=os.rmdir) as rmdir:
                            with self.assertRaisesRegex(extractor.ExtractionError, "enumeration budget exceeded"):
                                extractor.cleanup_owned(root_fd, ledger)
                            unlink.assert_not_called()
                            rmdir.assert_not_called()
                    else:
                        extractor.cleanup_owned(root_fd, ledger)
                seconds = time.monotonic() - start
                if refused:
                    ledger.verify(root_fd)
                    self.assertEqual(calls, 0)
                    self.assertEqual(enumerated, 0)
                    self.assertEqual(len(ledger.entries), count)
                else:
                    self.assertEqual(os.listdir(root_fd), [])
                    self.assertEqual(calls, count + fanout)
                    self.assertEqual(enumerated, expected)
                print(f"synthetic inventory entries={count} directories={fanout} creation_seconds={create_seconds:.6f} cleanup_seconds={seconds:.6f} budget_refused={refused} listing_calls={calls} enumerated_names={enumerated} initial_enumeration_work={expected}", flush=True)
            finally:
                ledger.close()
                os.close(root_fd)

    def test_realistic_distributed_fictional_inventory(self):
        self.measure(1337, 37)

    def test_realistic_flat_fictional_inventory(self):
        self.measure(1337, 0)

    def test_maximum_flat_fictional_inventory(self):
        self.measure(20000, 0)


    def test_maximum_distributed_fictional_inventory(self):
        self.measure(20000, 100)

    def test_exact_enumeration_budget_boundary(self):
        with patch.object(extractor, "MAX_CLEANUP_ENUMERATION", 6):
            self.measure(3, 0)
        with patch.object(extractor, "MAX_CLEANUP_ENUMERATION", 5):
            self.measure(3, 0)

    def test_late_unknown_high_sibling_data_is_not_swept(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            root = base / "stage"
            root.mkdir()
            outside = base / "outside"
            outside.mkdir()
            (outside / "preserve").write_bytes(b"unowned synthetic directory")
            root_fd = os.open(root, extractor.FLAGS | os.O_DIRECTORY)
            ledger = extractor.OwnershipLedger(root_fd)
            try:
                for index in range(1337):
                    name = f"known{index:05d}"
                    ledger.begin(name)
                    fd = os.open(name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600, dir_fd=root_fd)
                    try:
                        ledger.bind(name, fd, False)
                    finally:
                        os.close(fd)
                unlink = os.unlink
                deleted = []
                def inject(name, *, dir_fd):
                    unlink(name, dir_fd=dir_fd)
                    deleted.append(name)
                    (root / "unknown").write_bytes(b"unowned synthetic file")
                    outside.rename(root / "unknown-directory")
                with patch.object(extractor.os, "unlink", inject):
                    with self.assertRaisesRegex(extractor.ExtractionError, "inventory changed"):
                        extractor.cleanup_owned(root_fd, ledger)
                self.assertEqual(len(deleted), 1)
                self.assertEqual((root / "unknown").read_bytes(), b"unowned synthetic file")
                self.assertEqual((root / "unknown-directory/preserve").read_bytes(), b"unowned synthetic directory")
                self.assertEqual(len(list(root.glob("known*"))), 1336)
            finally:
                ledger.close()
                os.close(root_fd)

    def test_descriptor_exhaustion_retains_unbound_extraction_stage(self):
        code = """
import os
from pathlib import Path
import resource
import tempfile
import extract_platform_dependencies as extractor
from test_extract_platform_dependencies import BASE, transport
import hashlib
soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
resource.setrlimit(resource.RLIMIT_NOFILE, (min(soft, 64), hard))
with tempfile.TemporaryDirectory() as folder:
    base = Path(folder)
    parent = base / 'parent'
    parent.mkdir(mode=0o700)
    source = base / 'synthetic.gz'
    archive = transport(BASE + [(f'public-closure/root/f{index}', b'0', b'fictional', 0o600) for index in range(160)])
    source.write_bytes(archive)
    try:
        extractor.extract(source, hashlib.sha256(archive).hexdigest(), parent, 'accepted')
    except extractor.ExtractionError as error:
        assert 'cleanup' in str(error)
    else:
        raise AssertionError('Descriptor exhaustion must not publish')
    assert not (parent / 'accepted').exists()
    stages = list(parent.iterdir())
    assert len(stages) == 1
    assert list(stages[0].rglob('f*'))
    assert source.read_bytes() == archive
print('Synthetic reduced-descriptor extraction failed closed with retained staging')
"""
        result = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).parent,
                                env={"PATH": os.environ["PATH"], "LANG": "C.UTF-8", "PYTHONNOUSERSITE": "1"},
                                capture_output=True, text=True, check=False, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stdout.strip(), flush=True)

    def test_gitless_cleanup_budget_refusal_preserves_complete_stage(self):
        import derive_gitless_dependencies as derivation
        import platform_dependency_closure as closure
        from test_derive_gitless_dependencies import fixture
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = base / "source"
            source.mkdir()
            digest = fixture(source)
            before = closure.inventory(source)
            parent = base / "parent"
            parent.mkdir(mode=0o700)
            verify = derivation.verify_derived
            def fail(wrapper, original, original_digest):
                verify(wrapper, original, original_digest)
                raise OSError("fictional ordinary derivation failure")
            with patch.object(extractor, "MAX_CLEANUP_ENUMERATION", 0), patch.object(derivation, "verify_derived", fail), patch.object(extractor.os, "unlink", wraps=os.unlink) as unlink, patch.object(extractor.os, "rmdir", wraps=os.rmdir) as rmdir:
                with self.assertRaisesRegex(derivation.DerivationError, "cleanup could not be verified"):
                    derivation.derive(source, digest, parent, "out")
                unlink.assert_not_called()
                rmdir.assert_not_called()
            stages = list(parent.iterdir())
            self.assertEqual(len(stages), 1)
            self.assertFalse((parent / "out").exists())
            self.assertTrue((stages[0] / "bundle/manifest.json").is_file())
            self.assertTrue((stages[0] / "derivation.json").is_file())
            self.assertTrue((stages[0] / "bundle/root/main.tf").is_file())
            self.assertEqual(closure.inventory(source), before)

if __name__ == "__main__":
    unittest.main()
