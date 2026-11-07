import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import platform_dependency_closure as closure


class ClosureTests(unittest.TestCase):
    def fixture(self, root):
        (root / 'root' / '.terraform' / 'modules' / 'child').mkdir(parents=True)
        (root / 'root' / '.terraform.lock.hcl').write_text('synthetic lock')
        (root / 'root' / 'main.tf').write_text('synthetic source')
        graph = {'Modules': [{'Key': '', 'Source': '', 'Dir': '.'},
                            {'Key': 'child', 'Source': 'example/module/provider', 'Version': '1.0.0',
                             'Dir': '.terraform/modules/child'}]}
        (root / 'root' / '.terraform' / 'modules' / 'modules.json').write_text(json.dumps(graph))
        (root / 'root' / '.terraform' / 'modules' / 'child' / 'main.tf').write_text('nested synthetic source')
        (root / 'mirror').mkdir()
        (root / 'mirror' / 'provider.zip').write_bytes(b'synthetic package')
        manifest = {'format': 1, 'source_sha': closure.SHA, 'terraform': closure.VERSION,
                    'platform': 'linux_amd64', 'provenance': 'generated-public-resolution-not-reviewed',
                    'files': closure.inventory(root), 'modules': graph['Modules'],
                    'source_files': {'main.tf': closure.inventory(root)['root/main.tf']},
                    'providers': {'registry.terraform.io/example/provider': '1.0.0'}}
        (root / 'manifest.json').write_text(json.dumps(manifest))
        return manifest

    def test_exact_inventory_and_nested_graph(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            closure.check(root, hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest())

    def test_missing_extra_changed_and_nested_artifacts(self):
        for mutation in ('missing', 'extra', 'emptydir', 'changed', 'nested', 'mode', 'lock'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.fixture(root)
                if mutation == 'missing':
                    (root / 'mirror' / 'provider.zip').unlink()
                elif mutation == 'extra':
                    (root / 'mirror' / 'extra.zip').write_bytes(b'extra')
                elif mutation == 'emptydir':
                    (root / 'mirror' / 'extra').mkdir()
                elif mutation == 'mode':
                    (root / 'root' / 'main.tf').chmod(0o777)
                elif mutation == 'lock':
                    (root / 'root' / '.terraform.lock.hcl').unlink()
                else:
                    target = root / 'root' / 'main.tf' if mutation == 'changed' else root / 'root' / '.terraform/modules/child/main.tf'
                    target.write_text('tampered')
                with self.assertRaises(closure.ClosureError):
                    closure.check(root, hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest())

    def test_escaping_graph_and_symlinks(self):
        for mutation in ('escape', 'link', 'hardlink', 'duplicate'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                manifest = self.fixture(root)
                if mutation == 'escape':
                    manifest['modules'][1]['Dir'] = '../outside'
                    (root / 'root/.terraform/modules/modules.json').write_text(json.dumps({'Modules': manifest['modules']}))
                    manifest['files'] = closure.inventory(root)
                    manifest['files'].pop('manifest.json')
                    (root / 'manifest.json').write_text(json.dumps(manifest))
                elif mutation == 'link':
                    (root / 'root' / 'redirect').symlink_to(root / 'mirror', target_is_directory=True)
                elif mutation == 'hardlink':
                    os.link(root / 'mirror' / 'provider.zip', root / 'mirror' / 'duplicate.zip')
                else:
                    (root / 'manifest.json').write_text('{"format":1,"format":1}')
                with self.assertRaises(closure.ClosureError):
                    closure.check(root, hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest())

    def test_version_revision_and_unreviewed_provenance_fail_closed(self):
        for key, value in (('terraform', '1.17.0'), ('source_sha', '0' * 40), ('platform', 'windows_amd64'),
                           ('provenance', 'trusted'), ('providers', {})):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                manifest = self.fixture(root)
                manifest[key] = value
                (root / 'manifest.json').write_text(json.dumps(manifest))
                with self.assertRaises(closure.ClosureError):
                    closure.check(root, hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest())

    def test_manifest_digest_cannot_be_self_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self.fixture(root)
            selected = hashlib.sha256((root / 'manifest.json').read_bytes()).hexdigest()
            manifest['files']['mirror/provider.zip']['sha256'] = '0' * 64
            (root / 'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaises(closure.ClosureError):
                closure.check(root, selected)
            with self.assertRaises(closure.ClosureError):
                closure.check(root, None)

    def test_git_source_missing_changed_extra_and_mode(self):
        for mutation in ('none', 'missing', 'changed', 'extra', 'mode'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                file = root / 'main.tf'
                raw = b'synthetic exact Git bytes'
                file.write_bytes(raw)
                file.chmod(0o644)
                oid = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
                if mutation == 'missing':
                    file.unlink()
                elif mutation == 'changed':
                    file.write_bytes(b'changed')
                elif mutation == 'extra':
                    (root / 'extra.tf').write_text('extra')
                elif mutation == 'mode':
                    file.chmod(0o755)
                with patch.object(closure.subprocess, 'run') as run:
                    run.return_value.returncode = 0
                    run.return_value.stdout = f'100644 blob {oid}\tterraform/main.tf\n'.encode()
                    if mutation == 'none':
                        self.assertIn('main.tf', closure.source_inventory(root))
                    else:
                        with self.assertRaises(closure.ClosureError):
                            closure.source_inventory(root)

    def test_schema_mutation_or_terraform_failure_does_not_verify(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            selected = hashlib.sha256((root / 'manifest.json').read_bytes()).hexdigest()
            def simulated(binary, working, home, args):
                if args == ['version', '-json']:
                    return json.dumps({'terraform_version': closure.VERSION, 'platform': 'linux_amd64',
                                       'provider_selections': {'registry.terraform.io/example/provider': '1.0.0'}}).encode()
                if args == ['providers', 'schema', '-json']:
                    (root / 'mirror' / 'provider.zip').write_bytes(b'swap during verification')
                return b'{}'
            with patch.object(closure, 'terraform', side_effect=simulated):
                with self.assertRaises(closure.ClosureError):
                    closure.verify(root, 'terraform', selected)
            with patch.object(closure.subprocess, 'run') as run:
                run.return_value.returncode = 1
                run.return_value.stdout = b'provider output withheld'
                run.return_value.stderr = b''
                with self.assertRaises(closure.ClosureError):
                    closure.terraform('terraform', root, root, ['providers', 'schema', '-json'])
    def test_no_credentials_and_exact_command_allowlist(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {'AZURE_CLIENT_SECRET': 'synthetic', 'ACTIONS_ID_TOKEN_REQUEST_TOKEN': 'synthetic'}):
                with patch.object(closure.subprocess, 'run') as run:
                    run.return_value.returncode = 0
                    run.return_value.stdout = b'{}'
                    closure.terraform('terraform', root, root, ['providers', 'schema', '-json'])
                    env = run.call_args.kwargs['env']
                    self.assertNotIn('AZURE_CLIENT_SECRET', env)
                    self.assertNotIn('ACTIONS_ID_TOKEN_REQUEST_TOKEN', env)
                    for args in (['apply'], ['plan'], ['import'], ['state', 'push'], ['refresh'],
                                 ['init', '-backend=true'], ['init', '-upgrade']):
                        with self.assertRaises(closure.ClosureError):
                            closure.terraform('terraform', root, root, args)


    def test_copied_scratch_mutation_does_not_verify(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            self.fixture(bundle)
            selected = hashlib.sha256((bundle / 'manifest.json').read_bytes()).hexdigest()
            def simulated(binary, working, home, args):
                if args == ['version', '-json']:
                    return json.dumps({'terraform_version': closure.VERSION, 'platform': 'linux_amd64',
                                       'provider_selections': {'registry.terraform.io/example/provider': '1.0.0'}}).encode()
                if args == ['providers', 'schema', '-json']:
                    (working / 'main.tf').write_text('scratch changed during schema loading')
                return b'{}'
            with patch.object(closure, 'terraform', side_effect=simulated):
                with self.assertRaisesRegex(closure.ClosureError, 'Scratch closure changed'):
                    closure.verify(bundle, 'terraform', selected)
    @unittest.skipUnless(os.environ.get('PUBLIC_CLOSURE_TEST_BUNDLE'), 'Public integration bundle not selected.')
    def test_captured_provider_and_module_artifacts_fail_closed(self):
        import shutil
        bundle = Path(os.environ['PUBLIC_CLOSURE_TEST_BUNDLE'])
        selected = hashlib.sha256((bundle / 'manifest.json').read_bytes()).hexdigest()
        closure.check(bundle, selected)
        for mutation in ('provider', 'module', 'missing-provider', 'extra-module'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                copy = Path(directory) / 'copy'
                shutil.copytree(bundle, copy)
                manifest = json.loads((copy / 'manifest.json').read_bytes())
                packages = sorted(name for name in manifest['files'] if name.startswith('mirror/') and name.endswith('.zip'))
                modules = sorted(name for name in manifest['files']
                                 if name.startswith('root/.terraform/modules/') and name.endswith('.tf'))
                self.assertTrue(packages and modules)
                if mutation == 'provider':
                    with (copy / packages[0]).open('ab') as package:
                        package.write(b'changed public package')
                elif mutation == 'module':
                    (copy / modules[0]).write_text('changed module')
                elif mutation == 'missing-provider':
                    (copy / packages[0]).unlink()
                else:
                    (copy / 'root/.terraform/modules/extra.tf').write_text('extra')
                with patch.object(closure.subprocess, 'run') as run:
                    with self.assertRaises(closure.ClosureError):
                        closure.verify(copy, 'terraform', selected)
                    run.assert_not_called()

if __name__ == '__main__':
    if os.name != 'posix':
        raise SystemExit('Linux filesystem tests are mandatory.')
    unittest.main()