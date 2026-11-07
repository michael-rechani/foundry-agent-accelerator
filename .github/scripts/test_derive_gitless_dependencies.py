import hashlib
import json
import os
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
            for name in ('.github/workflow.yml', '.gitignore', 'git.txt', 'main.tf'):
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
                def mutation(source_fd, output_fd, records):
                    real_copy(source_fd, output_fd, records)
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


if __name__ == '__main__':
    if os.name != 'posix':
        raise SystemExit('Linux required')
    unittest.main()
