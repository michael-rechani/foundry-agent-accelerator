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
                    'source_files': {'main.tf': closure.inventory(root)['root/main.tf']}}
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
                           ('provenance', 'trusted')):
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


if __name__ == '__main__':
    if os.name != 'posix':
        raise SystemExit('Linux filesystem tests are mandatory.')
    unittest.main()