"""Fictional inventory timings; no archives, providers or privileged operations."""
import os
from pathlib import Path
import resource
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
                start = time.monotonic()
                with patch.object(extractor.os, "listdir", counted):
                    extractor.cleanup_owned(root_fd, ledger)
                seconds = time.monotonic() - start
                self.assertEqual(os.listdir(root_fd), [])
                print(f"synthetic inventory entries={count} directories={fanout} creation_seconds={create_seconds:.6f} cleanup_seconds={seconds:.6f} listing_calls={calls} enumerated_names={enumerated}", flush=True)
            finally:
                ledger.close()
                os.close(root_fd)

    def test_realistic_distributed_fictional_inventory(self):
        self.measure(1337, 37)

    def test_realistic_flat_fictional_inventory(self):
        self.measure(1337, 0)

    def test_maximum_flat_fictional_inventory(self):
        self.measure(20000, 0)


if __name__ == "__main__":
    unittest.main()
