import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import derive_gitless_dependencies as derivation
import platform_dependency_closure as closure


def fixture(root):
    (root / 'root/.terraform/modules/child/.git/hooks').mkdir(parents=True)
    (root / 'root/.terraform/modules/child/.github').mkdir()
    (root / 'root/.terraform/modules/child/nested/.git').mkdir(parents=True)
    (root / 'root/.terraform/modules/child/.git/hooks/post-checkout').write_text('#!/bin/sh\ntouch SHOULD_NEVER_EXIST\n')
    (root / 'root/.terraform/modules/child/.git/hooks/post-checkout').chmod(0o755)
    (root / 'root/.terraform/modules/child/.git/config').write_text('[credential]\n helper = !touch SHOULD_NEVER_EXIST\n')
    (root / 'root/.terraform/modules/child/.github/workflow.yml').write_text('preserve')
    (root / 'root/.terraform/modules/child/.gitignore').write_text('preserve')
    (root / 'root/.terraform/modules/child/git.txt').write_text('preserve')
    (root / 'root/.terraform/modules/child/.gitmodules').write_text('preserve')
    (root / 'root/.terraform/modules/child/.gitkeep').write_text('preserve')
    (root / 'root/.terraform/modules/child/.git-backup').mkdir()
    (root / 'root/.terraform/modules/child/.git-backup/config').write_text('legitimate bytes')
    (root / 'root/.terraform/modules/child/main.tf').write_text('fictional module')
    (root / 'root/main.tf').write_text('fictional root')
    (root / 'root/.terraform.lock.hcl').write_text('synthetic lock')
    (root / 'mirror').mkdir()
    (root / 'mirror/provider.zip').write_bytes(b'fictional provider')
    modules = [{'Key': '', 'Source': '', 'Dir': '.'}, {'Key': 'child', 'Source': 'registry.terraform.io/example/module/provider',
               'Version': '1.0.0', 'Dir': '.terraform/modules/child'}]
    (root / 'root/.terraform/modules/modules.json').write_text(json.dumps({'Modules': modules}))
    manifest = {'format': 1, 'source_sha': closure.SHA, 'source_files': {'main.tf': closure.inventory(root)['root/main.tf']},
                'terraform': closure.VERSION, 'platform': 'linux_amd64', 'provenance': 'generated-public-resolution-not-reviewed',
                'files': closure.inventory(root), 'modules': modules, 'providers': {'registry.terraform.io/example/provider': '1.0.0'}}
    (root / 'manifest.json').write_text(json.dumps(manifest))
    return hashlib.sha256((root / 'manifest.json').read_bytes()).hexdigest()


class GitlessTests(unittest.TestCase):
    def test_exact_omission_and_deterministic_binding_never_executes_git(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = base / 'source'
            source.mkdir()
            digest = fixture(source)
            before = closure.inventory(source)
            parent = base / 'parent'
            parent.mkdir(mode=0o700)
            with patch('subprocess.run', side_effect=AssertionError('No process allowed during derivation')):
                first, first_digest = derivation.derive(source, digest, parent, 'first')
                second, second_digest = derivation.derive(source, digest, parent, 'second')
            self.assertEqual(first_digest, second_digest)
            self.assertEqual(closure.inventory(first), closure.inventory(second))
            self.assertEqual(closure.inventory(source), before)
            self.assertEqual(derivation.verify_derived(first, source, digest), first_digest)
            child = first / 'bundle/root/.terraform/modules/child'
            self.assertFalse((child / '.git').exists())
            self.assertFalse((child / 'nested/.git').exists())
            for name in ('.github/workflow.yml', '.gitignore', '.gitmodules', '.gitkeep', '.git-backup/config', 'git.txt', 'main.tf'):
                self.assertEqual((child / name).read_bytes(), (source / 'root/.terraform/modules/child' / name).read_bytes())
            self.assertFalse(list(base.rglob('SHOULD_NEVER_EXIST')))
            with self.assertRaises(derivation.DerivationError):
                derivation.derive(source, digest, parent, 'first')

    def test_links_missing_extra_changes_wrong_digest_and_unknown_git_pointer(self):
        for mutation in ('symlink', 'hardlink', 'missing', 'extra', 'changed', 'pointer', 'wrongdigest'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as folder:
                base = Path(folder)
                source = base / 'source'
                source.mkdir()
                digest = fixture(source)
                parent = base / 'parent'
                parent.mkdir(mode=0o700)
                target = source / 'root/.terraform/modules/child/main.tf'
                if mutation == 'symlink':
                    target.unlink()
                    target.symlink_to(base / 'absent')
                elif mutation == 'hardlink':
                    os.link(target, source / 'hardlink')
                elif mutation == 'missing':
                    target.unlink()
                elif mutation == 'extra':
                    (source / 'extra').write_text('unexpected')
                elif mutation == 'changed':
                    target.write_text('changed')
                elif mutation == 'pointer':
                    import shutil
                    shutil.rmtree(source / 'root/.terraform/modules/child/.git')
                    (source / 'root/.terraform/modules/child/.git').write_text('gitdir: /outside')
                    manifest = json.loads((source / 'manifest.json').read_bytes())
                    files = closure.inventory(source)
                    files.pop('manifest.json')
                    manifest['files'] = files
                    (source / 'manifest.json').write_text(json.dumps(manifest))
                    digest = hashlib.sha256((source / 'manifest.json').read_bytes()).hexdigest()
                else:
                    digest = '0' * 64
                with self.assertRaises((derivation.DerivationError, closure.ClosureError, OSError)):
                    derivation.derive(source, digest, parent, 'out')
                self.assertEqual(list(parent.iterdir()), [])

    def test_source_copy_mutation_and_output_corruption_fail_before_publication(self):
        for case in ('source', 'output'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as folder:
                base = Path(folder)
                source = base / 'source'
                source.mkdir()
                digest = fixture(source)
                parent = base / 'parent'
                parent.mkdir(mode=0o700)
                real_copy = derivation.copy_inventory
                def mutation(source_fd, output_fd, records, ledger):
                    real_copy(source_fd, output_fd, records, ledger)
                    if case == 'source':
                        (source / 'root/main.tf').write_text('changed during copy')
                    else:
                        fd = derivation.extraction.open_relative(output_fd, ['root'])
                        try:
                            file = os.open('main.tf', os.O_WRONLY | os.O_TRUNC, dir_fd=fd)
                            os.write(file, b'corrupt output')
                            os.close(file)
                        finally:
                            os.close(fd)
                with patch.object(derivation, 'copy_inventory', mutation):
                    with self.assertRaises((derivation.DerivationError, closure.ClosureError)):
                        derivation.derive(source, digest, parent, 'out')
                self.assertEqual(list(parent.iterdir()), [])

    def test_parent_symlink_partial_write_and_derived_extra_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = base / 'source'
            source.mkdir()
            digest = fixture(source)
            parent = base / 'parent'
            parent.mkdir(mode=0o700)
            link = base / 'parent-link'
            link.symlink_to(parent, target_is_directory=True)
            with self.assertRaises(OSError):
                derivation.derive(source, digest, link, 'out')
            with patch.object(derivation.extraction, 'write_all', side_effect=OSError('fictional partial write')):
                with self.assertRaises(OSError):
                    derivation.derive(source, digest, parent, 'out')
            self.assertEqual(list(parent.iterdir()), [])
            wrapper, new_digest = derivation.derive(source, digest, parent, 'out')
            (wrapper / 'extra').write_text('unexpected')
            with self.assertRaises(derivation.DerivationError):
                derivation.verify_derived(wrapper, source, digest)


    def test_outside_cache_metadata_and_module_inside_metadata_rejected(self):
        for mutation in ('outside', 'module-inside'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as folder:
                base = Path(folder)
                source = base / 'source'
                source.mkdir()
                digest = fixture(source)
                parent = base / 'parent'
                parent.mkdir(mode=0o700)
                manifest = json.loads((source / 'manifest.json').read_bytes())
                if mutation == 'outside':
                    (source / 'root/.git').mkdir()
                    (source / 'root/.git/config').write_text('unreviewed outside cache')
                else:
                    manifest['modules'][1]['Dir'] = '.terraform/modules/child/.git'
                    (source / 'root/.terraform/modules/modules.json').write_text(json.dumps({'Modules': manifest['modules']}))
                inventory = closure.inventory(source)
                inventory.pop('manifest.json')
                manifest['files'] = inventory
                (source / 'manifest.json').write_text(json.dumps(manifest))
                digest = hashlib.sha256((source / 'manifest.json').read_bytes()).hexdigest()
                with self.assertRaises(derivation.DerivationError):
                    derivation.derive(source, digest, parent, 'out')
                self.assertEqual(list(parent.iterdir()), [])

    def test_source_manifest_link_and_output_parent_inside_source_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = base / 'source'
            source.mkdir()
            digest = fixture(source)
            before = closure.inventory(source)
            with self.assertRaises(derivation.DerivationError):
                derivation.derive(source, digest, source / 'root', 'out')
            self.assertEqual(closure.inventory(source), before)
            path = source / 'manifest.json'
            saved = base / 'outside-manifest'
            path.rename(saved)
            path.symlink_to(saved)
            parent = base / 'parent'
            parent.mkdir(mode=0o700)
            with self.assertRaises(OSError):
                derivation.derive(source, digest, parent, 'out')
            self.assertEqual(list(parent.iterdir()), [])
            self.assertTrue(saved.exists())

    def test_source_directory_swap_and_output_write_link_do_not_follow(self):
        for case in ('source', 'output'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as folder:
                base = Path(folder)
                source = base / 'source'
                source.mkdir()
                digest = fixture(source)
                parent = base / 'parent'
                parent.mkdir(mode=0o700)
                outside = base / 'outside'
                outside.mkdir()
                (outside / 'main.tf').write_text('do not change')
                real_copy = derivation.copy_inventory
                def substitution(source_fd, output_fd, records, ledger):
                    if case == 'source':
                        (source / 'root/.terraform/modules/child').rename(source / 'root/.terraform/modules/displaced')
                        (source / 'root/.terraform/modules/child').symlink_to(outside, target_is_directory=True)
                    real_copy(source_fd, output_fd, records, ledger)
                real_open = derivation.os.open
                def output_link(name, flags, *args, **kwargs):
                    if case == 'output' and name == 'main.tf' and flags & os.O_CREAT:
                        os.symlink(str(outside / 'main.tf'), name, dir_fd=kwargs['dir_fd'])
                    return real_open(name, flags, *args, **kwargs)
                with patch.object(derivation, 'copy_inventory', substitution), patch.object(derivation.os, 'open', output_link):
                    with self.assertRaises((OSError, derivation.DerivationError)):
                        derivation.derive(source, digest, parent, 'out')
                self.assertEqual((outside / 'main.tf').read_text(), 'do not change')
                if case == 'output':
                    stages = list(parent.iterdir())
                    self.assertEqual(len(stages), 1)
                    self.assertTrue((stages[0] / 'bundle/root/main.tf').is_symlink())
                else:
                    self.assertEqual(list(parent.iterdir()), [])

    def test_duplicate_manifest_binding_tamper_and_modes_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = base / 'source'
            source.mkdir()
            digest = fixture(source)
            parent = base / 'parent'
            parent.mkdir(mode=0o700)
            wrapper, new_digest = derivation.derive(source, digest, parent, 'out')
            binding = wrapper / 'derivation.json'
            binding.write_text('{}')
            with self.assertRaises(derivation.DerivationError):
                derivation.verify_derived(wrapper, source, digest)
            path = source / 'manifest.json'
            path.write_text('{"files":{},"files":{}}')
            duplicate_digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaises(closure.ClosureError):
                derivation.derive(source, duplicate_digest, parent, 'second')

    def test_parent_rename_symlink_swap_preserves_outside_and_owned_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = base / 'source'
            source.mkdir()
            digest = fixture(source)
            parent = base / 'parent'
            parent.mkdir(mode=0o700)
            displaced = base / 'displaced-parent'
            outside = base / 'outside'
            outside.mkdir()
            (outside / 'preserve').write_text('untouched')
            original = derivation.copy_inventory
            def swap(source_fd, output_fd, records, ledger):
                original(source_fd, output_fd, records, ledger)
                parent.rename(displaced)
                parent.symlink_to(outside, target_is_directory=True)
            with patch.object(derivation, 'copy_inventory', swap):
                with self.assertRaises(OSError):
                    derivation.derive(source, digest, parent, 'out')
            self.assertEqual(list(displaced.iterdir()), [])
            self.assertEqual([path.name for path in outside.iterdir()], ['preserve'])
            self.assertEqual((outside / 'preserve').read_text(), 'untouched')

    def test_file_mode_output_link_cleanup_error_and_late_collision(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = base / 'source'
            source.mkdir()
            digest = fixture(source)
            before = closure.inventory(source)
            parent = base / 'parent'
            parent.mkdir(mode=0o700)
            original_publish = derivation.extraction.publish_exclusive
            def collision(parent_fd, stage, destination):
                os.mkdir(destination, 0o700, dir_fd=parent_fd)
                original_publish(parent_fd, stage, destination)
            with patch.object(derivation.extraction, 'publish_exclusive', collision):
                with self.assertRaises(OSError):
                    derivation.derive(source, digest, parent, 'collision')
            self.assertEqual(list((parent / 'collision').iterdir()), [])
            self.assertEqual(closure.inventory(source), before)
            with patch.object(derivation, 'copy_inventory', side_effect=OSError('fictional disk error')), patch.object(
                    derivation.extraction, 'cleanup_owned', side_effect=OSError('fictional cleanup error')):
                with self.assertRaisesRegex(derivation.DerivationError, 'cleanup could not be verified'):
                    derivation.derive(source, digest, parent, 'failed')
            self.assertFalse((parent / 'failed').exists())
            wrapper, new_digest = derivation.derive(source, digest, parent, 'out')
            target = wrapper / 'bundle/root/main.tf'
            target.chmod(0o777)
            with self.assertRaises(derivation.DerivationError):
                derivation.verify_derived(wrapper, source, digest)
            target.chmod(before['root/main.tf']['mode'])
            binding = wrapper / 'derivation.json'
            saved = base / 'saved-binding'
            binding.rename(saved)
            binding.symlink_to(saved)
            with self.assertRaises(derivation.DerivationError):
                derivation.verify_derived(wrapper, source, digest)
            self.assertEqual(closure.inventory(source), before)

    def test_inventory_bounds_and_copy_growth_stop_before_publication(self):
        for bound in ('MAX_ENTRIES', 'MAX_TOTAL_BYTES', 'MAX_FILE_BYTES'):
            with self.subTest(bound=bound), tempfile.TemporaryDirectory() as folder:
                base = Path(folder)
                source = base / 'source'
                source.mkdir()
                digest = fixture(source)
                parent = base / 'parent'
                parent.mkdir(mode=0o700)
                with patch.object(derivation, bound, 2):
                    with self.assertRaises(derivation.DerivationError):
                        derivation.derive(source, digest, parent, 'out')
                self.assertEqual(list(parent.iterdir()), [])
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = base / 'source'
            source.mkdir()
            digest = fixture(source)
            parent = base / 'parent'
            parent.mkdir(mode=0o700)
            real_read = derivation.os.read
            real_copy = derivation.copy_inventory
            active = False
            count = 0
            def start(source_fd, output_fd, records, ledger):
                nonlocal active
                active = True
                real_copy(source_fd, output_fd, records, ledger)
            def endless(fd, size):
                nonlocal count
                if active:
                    count += 1
                    return b'x' * size
                return real_read(fd, size)
            with patch.object(derivation, 'copy_inventory', start), patch.object(derivation.os, 'read', endless):
                with self.assertRaisesRegex(derivation.DerivationError, 'grew beyond verified size'):
                    derivation.derive(source, digest, parent, 'out')
            self.assertLess(count, 4)
            self.assertEqual(list(parent.iterdir()), [])

    def test_malformed_selected_manifest_cli_is_fixed_and_never_publishes(self):
        cases = {
            'utf8': b'\xffPRIVATE_MARKER',
            'syntax': b'{"files": PRIVATE_MARKER}',
            'deep': b'{"files":' + b'[' * 10000 + b'0' + b']' * 10000 + b'}',
            'huge-integer': b'{"files":' + b'9' * 10000 + b'}',
            'null-root': b'null',
            'list-root': b'[]',
            'string-root': b'"PRIVATE_MARKER"',
            'number-root': b'1',
            'boolean-root': b'true',
            'missing-files': b'{}',
            'null-files': b'{"files":null}',
            'list-files': b'{"files":[]}',
            'pairs-files': b'{"files":[["PRIVATE_MARKER",{}]]}',
            'string-files': b'{"files":"PRIVATE_MARKER"}',
            'number-files': b'{"files":1}',
            'boolean-files': b'{"files":false}',
            'duplicate': b'{"files":{},"files":{}}',
        }
        script = Path(derivation.__file__).resolve()
        for case, raw in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as folder:
                base = Path(folder)
                source = base / 'source'
                source.mkdir()
                fixture(source)
                (source / 'manifest.json').write_bytes(raw)
                before = closure.inventory(source)
                parent = base / 'parent'
                parent.mkdir(mode=0o700)
                sentinel = base / 'outside-sentinel'
                sentinel.write_bytes(b'untouched')
                digest = hashlib.sha256(raw).hexdigest()
                with self.assertRaises((derivation.DerivationError, closure.ClosureError)):
                    derivation.derive(source, digest, parent, 'direct')
                result = subprocess.run(
                    [sys.executable, str(script), str(source), '--original-manifest-sha256', digest,
                     '--trusted-parent', str(parent), '--destination', 'cli'],
                    cwd=base, env={'PATH': os.defpath, 'HOME': str(base), 'LANG': 'C.UTF-8'},
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, check=False)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, b'')
                self.assertEqual(result.stderr, b'Metadata-free derivation stopped; no verified handoff.\n')
                self.assertNotIn(b'Traceback', result.stderr)
                self.assertNotIn(b'PRIVATE_MARKER', result.stderr)
                self.assertEqual(list(parent.iterdir()), [])
                self.assertEqual(closure.inventory(source), before)
                self.assertEqual(sentinel.read_bytes(), b'untouched')

    def test_hash_precedes_parse_and_closure_errors_remain_distinct(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = base / 'source'
            source.mkdir()
            digest = fixture(source)
            parent = base / 'parent'
            parent.mkdir(mode=0o700)
            with patch.object(derivation.json, 'loads', side_effect=AssertionError('Must not parse')):
                with self.assertRaisesRegex(derivation.DerivationError, 'separately selected digest'):
                    derivation.derive(source, '0' * 64, parent, 'wrong')
            with patch.object(closure, 'check', side_effect=closure.ClosureError('Provider selection rejected')):
                with self.assertRaisesRegex(closure.ClosureError, 'Provider selection rejected'):
                    derivation.derive(source, digest, parent, 'provider')
            self.assertEqual(list(parent.iterdir()), [])

    def test_malformed_inventory_records_cli_rejects_before_staging(self):
        cases = ('file-float', 'directory-float', 'true', 'false', 'negative', 'too-large',
                 'null-mode', 'string-mode', 'null-record', 'list-record', 'missing-mode',
                 'extra-field', 'null-hash', 'list-hash', 'invalid-hash')
        script = Path(derivation.__file__).resolve()
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as folder:
                base = Path(folder)
                source = base / 'source'
                source.mkdir()
                fixture(source)
                path = source / 'manifest.json'
                manifest = json.loads(path.read_bytes())
                name = 'root' if case == 'directory-float' else 'root/main.tf'
                record = manifest['files'][name]
                if case in ('file-float', 'directory-float'):
                    record['mode'] = float(record['mode'])
                elif case == 'null-record':
                    manifest['files'][name] = None
                elif case == 'list-record':
                    manifest['files'][name] = []
                elif case == 'missing-mode':
                    del record['mode']
                elif case == 'extra-field':
                    record['unexpected'] = 'PRIVATE_MARKER'
                elif case.endswith('hash'):
                    record['sha256'] = {'null-hash': None, 'list-hash': [], 'invalid-hash': 'PRIVATE_MARKER'}[case]
                else:
                    record['mode'] = {'true': True, 'false': False, 'negative': -1,
                                      'too-large': 0o10000, 'null-mode': None, 'string-mode': '420'}[case]
                path.write_text(json.dumps(manifest))
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                before = closure.inventory(source)
                parent = base / 'parent'
                parent.mkdir(mode=0o700)
                sentinel = base / 'outside'
                sentinel.write_text('unchanged')
                with self.assertRaisesRegex(derivation.DerivationError, 'Invalid selected inventory record'):
                    derivation.derive(source, digest, parent, 'direct')
                result = subprocess.run(
                    [sys.executable, str(script), str(source), '--original-manifest-sha256', digest,
                     '--trusted-parent', str(parent), '--destination', 'cli'],
                    cwd=base, env={'PATH': os.defpath, 'HOME': str(base), 'LANG': 'C.UTF-8'},
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, check=False)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, b'')
                self.assertEqual(result.stderr, b'Metadata-free derivation stopped; no verified handoff.\n')
                self.assertEqual(list(parent.iterdir()), [])
                self.assertEqual(closure.inventory(source), before)
                self.assertEqual(sentinel.read_text(), 'unchanged')

    def test_strict_format_and_module_graph_cli_shapes_fail_before_staging(self):
        cases = ('format-true', 'format-float', 'manifest-null', 'manifest-dict', 'manifest-string',
                 'manifest-item-null', 'disk-null', 'disk-number', 'disk-dict', 'disk-string',
                 'disk-empty', 'disk-item-null', 'disk-record-wrong-type', 'disk-json', 'disk-utf8',
                 'disk-deep')
        script = Path(derivation.__file__).resolve()
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as folder:
                base = Path(folder)
                source = base / 'source'
                source.mkdir()
                fixture(source)
                path = source / 'manifest.json'
                manifest = json.loads(path.read_bytes())
                graph = source / 'root/.terraform/modules/modules.json'
                if case.startswith('format-'):
                    manifest['format'] = True if case == 'format-true' else 1.0
                elif case.startswith('manifest-'):
                    manifest['modules'] = {'manifest-null': None, 'manifest-dict': {},
                                           'manifest-string': 'PRIVATE_MARKER', 'manifest-item-null': [None]}[case]
                else:
                    value = {'disk-null': None, 'disk-number': 1, 'disk-dict': {'unexpected': 'PRIVATE_MARKER'},
                             'disk-string': 'PRIVATE_MARKER', 'disk-empty': [], 'disk-item-null': [None],
                             'disk-record-wrong-type': [{'Key': '', 'Source': '', 'Dir': None}]}
                    if case == 'disk-json':
                        raw = b'{"Modules": PRIVATE_MARKER}'
                    elif case == 'disk-utf8':
                        raw = b'\xffPRIVATE_MARKER'
                    elif case == 'disk-deep':
                        raw = b'{"Modules":' + b'[' * 10000 + b'0' + b']' * 10000 + b'}'
                    else:
                        raw = json.dumps({'Modules': value[case]}).encode()
                    graph.write_bytes(raw)
                    inventory = closure.inventory(source)
                    inventory.pop('manifest.json')
                    manifest['files'] = inventory
                path.write_text(json.dumps(manifest))
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                before = closure.inventory(source)
                parent = base / 'parent'
                parent.mkdir(mode=0o700)
                sentinel = base / 'outside'
                sentinel.write_text('unchanged')
                with self.assertRaises(derivation.DerivationError):
                    derivation.derive(source, digest, parent, 'direct')
                result = subprocess.run(
                    [sys.executable, str(script), str(source), '--original-manifest-sha256', digest,
                     '--trusted-parent', str(parent), '--destination', 'cli'],
                    cwd=base, env={'PATH': os.defpath, 'HOME': str(base), 'LANG': 'C.UTF-8'},
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, check=False)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, b'')
                self.assertEqual(result.stderr, b'Metadata-free derivation stopped; no verified handoff.\n')
                self.assertEqual(list(parent.iterdir()), [])
                self.assertEqual(closure.inventory(source), before)
                self.assertEqual(sentinel.read_text(), 'unchanged')

    def test_unowned_derivation_entries_survive_failure_without_deletion(self):
        for kind in ('file', 'directory', 'replace-file', 'replace-directory', 'manifest', 'binding'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                base = Path(folder)
                source = base / 'source'
                source.mkdir()
                digest = fixture(source)
                before = closure.inventory(source)
                parent = base / 'parent'
                parent.mkdir(mode=0o700)
                outside = base / 'outside'
                outside.mkdir()
                (outside / 'preserve').write_bytes(b'UNOWNED DATA')
                original = derivation.verify_derived
                target = None
                def inject(wrapper, original_source, original_digest):
                    nonlocal target
                    original(wrapper, original_source, original_digest)
                    if kind == 'file':
                        target = wrapper / 'unowned'
                        target.write_bytes(b'UNOWNED DATA')
                    elif kind == 'directory':
                        target = wrapper / 'unowned-directory'
                        outside.rename(target)
                    else:
                        relative = {'replace-file': 'bundle/root/main.tf',
                                    'replace-directory': 'bundle/root/.terraform/modules/child',
                                    'manifest': 'bundle/manifest.json', 'binding': 'derivation.json'}[kind]
                        target = wrapper / relative
                        target.rename(base / 'displaced')
                        if kind == 'replace-directory':
                            outside.rename(target)
                        else:
                            target.write_bytes(b'UNOWNED DATA')
                    raise OSError('fictional ordinary derivation failure')
                with patch.object(derivation, 'verify_derived', inject), patch.object(derivation.os, 'unlink', wraps=os.unlink) as unlink, patch.object(derivation.os, 'rmdir', wraps=os.rmdir) as rmdir:
                    with self.assertRaisesRegex(derivation.DerivationError, 'cleanup could not be verified'):
                        derivation.derive(source, digest, parent, 'out')
                    unlink.assert_not_called()
                    rmdir.assert_not_called()
                self.assertFalse((parent / 'out').exists())
                self.assertEqual((target / 'preserve' if target.is_dir() else target).read_bytes(), b'UNOWNED DATA')
                if kind.startswith('replace') or kind in ('manifest', 'binding'):
                    self.assertTrue((base / 'displaced').exists())
                self.assertEqual(closure.inventory(source), before)

    def test_unbound_bundle_copy_and_json_creations_retain_staging(self):
        for name in ('bundle', 'bundle/root', 'bundle/root/main.tf', 'bundle/manifest.json', 'derivation.json'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                base = Path(folder)
                source = base / 'source'
                source.mkdir()
                digest = fixture(source)
                before = closure.inventory(source)
                parent = base / 'parent'
                parent.mkdir(mode=0o700)
                real_bind = derivation.extraction.OwnershipLedger.bind
                def failure(ledger, relative, fd, directory):
                    if relative == name:
                        raise OSError('fictional binding failure')
                    return real_bind(ledger, relative, fd, directory)
                with patch.object(derivation.extraction.OwnershipLedger, 'bind', failure):
                    with self.assertRaisesRegex(derivation.DerivationError, 'cleanup could not be verified'):
                        derivation.derive(source, digest, parent, 'out')
                self.assertFalse((parent / 'out').exists())
                stages = list(parent.iterdir())
                self.assertEqual(len(stages), 1)
                self.assertTrue((stages[0] / name).exists())
                self.assertEqual(closure.inventory(source), before)

    def test_derivation_passes_exact_populated_ledger_to_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = base / 'source'
            source.mkdir()
            digest = fixture(source)
            parent = base / 'parent'
            parent.mkdir(mode=0o700)
            original_verify = derivation.verify_derived
            real_cleanup = derivation.extraction.cleanup_owned
            observed = []
            def fail(wrapper, original, original_digest):
                original_verify(wrapper, original, original_digest)
                raise OSError('fictional ordinary failure')
            def cleanup(root_fd, ledger):
                self.assertIsInstance(ledger, derivation.extraction.OwnershipLedger)
                observed.append(set(ledger.entries))
                self.assertTrue({'bundle', 'bundle/manifest.json', 'derivation.json'} <= set(ledger.entries))
                self.assertFalse(ledger.pending)
                return real_cleanup(root_fd, ledger)
            with patch.object(derivation, 'verify_derived', fail), patch.object(derivation.extraction, 'cleanup_owned', cleanup):
                with self.assertRaises(OSError):
                    derivation.derive(source, digest, parent, 'out')
            self.assertEqual(len(observed), 1)
            self.assertEqual(list(parent.iterdir()), [])

    def test_non_root_synthetic_derivation_without_credential_environment(self):
        self.assertNotEqual(os.geteuid(), 0)
        self.assertFalse(any(name.startswith(('AZURE_', 'ARM_', 'ACTIONS_ID_TOKEN_'))
                             or name in ('GH_TOKEN', 'GITHUB_TOKEN') for name in os.environ))

if __name__ == '__main__':
    if os.name != 'posix':
        raise SystemExit('Linux required')
    unittest.main()
