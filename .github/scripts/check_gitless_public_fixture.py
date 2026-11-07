"""Execute only public original/derived closure semantic inspection, no live plan."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile

import derive_gitless_dependencies as derivation
import platform_dependency_closure as closure

DIGEST = "f6cee223894fae61d3d9bb2cac17ae86df38c1c6ed72d390dd7498b9a1df70b0"
source = Path(os.environ["GITLESS_ORIGINAL"])
parent = Path(os.environ["GITLESS_PARENT"])
binary = os.environ["GITLESS_TERRAFORM"]
assert [name for index, name in socket.if_nameindex()] == ["lo"]
assert not any(line.strip() for line in Path("/proc/net/route").read_text().splitlines()[1:])
# Fail loudly if Terraform attempts the ordinary git executable at all.
trap_bin = parent / "git-trap-bin"
trap_bin.mkdir(mode=0o700)
git_marker = parent / "unexpected-git-invocation"
(trap_bin / "git").write_text('#!/bin/sh\nprintf invoked > ' + str(git_marker) + '\nexit 111\n')
(trap_bin / "git").chmod(0o700)
os.environ["PATH"] = str(trap_bin) + os.pathsep + os.environ["PATH"]
original = closure.check(source, DIGEST)
before = closure.inventory(source)
wrapper, digest = derivation.derive(source, DIGEST, parent, "gitless")
derivation.verify_derived(wrapper, source, DIGEST)
sanitized = wrapper / "bundle"
parsed = closure.check(sanitized, digest)
assert parsed["source_sha"] == "446b078df12c9a08daec7bc5e9f0b5a57d8d7a5d"
assert original["modules"] == parsed["modules"]
assert original["providers"] == parsed["providers"]
assert original["source_files"] == parsed["source_files"]
binding = json.loads((wrapper / "derivation.json").read_bytes())
assert binding["removed_roots"]
print("Original module-cache Git roots (unreviewed):", json.dumps(binding["removed_roots"]))
print("Removed metadata inventory records:", len(binding["omitted_inventory"]))
print("Generated metadata-free manifest SHA256 (NOT APPROVED):", digest)
for name in parsed["files"]:
    assert derivation.metadata_component(name) is None
    assert original["files"][name] == parsed["files"][name]
semantic = []
for bundle in (source, sanitized):
    closure.verify(bundle, binary, DIGEST if bundle == source else digest)
    with tempfile.TemporaryDirectory() as folder:
        base = Path(folder)
        root = base / "root"
        shutil.copytree(bundle / "root", root)
        home = base / "home"
        home.mkdir(mode=0o700)
        (home / "terraform.rc").write_text('disable_checkpoint = true\nprovider_installation {\n filesystem_mirror {\n path = '
                                           + json.dumps(str(bundle / "mirror")) + '\n }\n}\n')
        env = {"PATH": os.environ["PATH"], "HOME": str(home), "TF_CLI_CONFIG_FILE": str(home / "terraform.rc"),
               "TF_INPUT": "0", "TF_IN_AUTOMATION": "true", "CHECKPOINT_DISABLE": "1", "LANG": "C.UTF-8"}
        def run(args):
            allowed = (["version", "-json"],
                       ["init", "-backend=false", "-get=false", "-lockfile=readonly", "-input=false", "-no-color"],
                       ["providers", "schema", "-json"], ["validate", "-json"])
            if args not in allowed:
                raise RuntimeError("Public semantic test command not permitted.")
            result = subprocess.run([binary, f"-chdir={root}", *args], env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, timeout=180, check=False)
            if result.returncode:
                raise RuntimeError("Public metadata-free semantic test failed: " + args[0] + "; raw output withheld")
            return result.stdout
        version = json.loads(run(["version", "-json"]))
        assert version["terraform_version"] == "1.16.4" and version["platform"] == "linux_amd64"
        run(["init", "-backend=false", "-get=false", "-lockfile=readonly", "-input=false", "-no-color"])
        schema = json.loads(run(["providers", "schema", "-json"]))
        validation = json.loads(run(["validate", "-json"]))
        assert validation["valid"] and validation["error_count"] == 0
        modules = (root / ".terraform/modules/modules.json").read_bytes()
        selections = json.loads(run(["version", "-json"]))["provider_selections"]
        semantic.append((schema, modules, selections))
        if bundle == sanitized:
            assert not any(path.name == ".git" for path in (root / ".terraform/modules").rglob("*"))
assert semantic[0] == semantic[1], "Full provider schema/module graph/selection changed"
assert not git_marker.exists(), "Unexpected Git invocation consulted metadata"
assert closure.inventory(source) == before
assert derivation.verify_derived(wrapper, source, DIGEST) == digest
print("Complete provider schemas, module graph bytes and selections identical; both full-root validate passed; original unchanged.")
print("No Git subprocess through PATH; isolated HOME and credential-free environments; no module-cache .git regenerated.")
print("Schema SHA256:", hashlib.sha256(json.dumps(semantic[0][0], sort_keys=True).encode()).hexdigest())
