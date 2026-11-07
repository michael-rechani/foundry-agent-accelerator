"""Capture public Terraform dependencies; verify byte closure without credentials.

Generated manifests are observations, never independent approval or authenticity.
No backend, plan, apply, import, or resource refresh is permitted.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile

VERSION = "1.16.4"
SHA = "5e5d20db25519657bc9205e8436641f958066c48"

class ClosureError(Exception):
    pass


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ClosureError("Duplicate manifest key.")
        result[key] = value
    return result


def read_json(path):
    try:
        return json.loads(path.read_bytes(), object_pairs_hook=pairs)
    except (ValueError, UnicodeError) as exc:
        raise ClosureError("Invalid closure JSON.") from exc


def safe_relative(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ClosureError("Unsafe dependency path.")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or str(path) != value:
        raise ClosureError("Unsafe dependency path.")
    return path


def inventory(folder, include_directories=True):
    if folder.is_symlink() or not folder.is_dir():
        raise ClosureError("Closure must be a regular directory.")
    result = {}
    for directory, dirs, files in os.walk(folder, followlinks=False):
        for name in dirs + files:
            path = Path(directory) / name
            metadata = path.lstat()
            mode = metadata.st_mode
            if stat.S_ISREG(mode) and metadata.st_nlink != 1:
                raise ClosureError("Hard-linked artifacts are ambiguous.")
            if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise ClosureError("Links or special files are not closure artifacts.")
        if include_directories:
            for name in dirs:
                path = Path(directory) / name
                result[path.relative_to(folder).as_posix()] = {"sha256": "directory", "mode": stat.S_IMODE(path.stat().st_mode)}
        for name in files:
            path = Path(directory) / name
            relative = path.relative_to(folder).as_posix()
            safe_relative(relative)
            result[relative] = {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "mode": stat.S_IMODE(path.stat().st_mode),
            }
    return result


def module_graph(root):
    value = read_json(root / ".terraform" / "modules" / "modules.json")
    if not isinstance(value, dict) or set(value) != {"Modules"} or not value["Modules"]:
        raise ClosureError("Missing module graph.")
    seen = set()
    for item in value["Modules"]:
        if (not isinstance(item, dict) or set(item) - {"Key", "Source", "Version", "Dir"}
                or not {"Key", "Source", "Dir"} <= set(item)
                or not all(isinstance(v, str) for v in item.values()) or item["Key"] in seen):
            raise ClosureError("Ambiguous module graph.")
        seen.add(item["Key"])
        relative = item["Dir"]
        if relative in ("", "."):
            if item["Key"] != "":
                raise ClosureError("Non-root module redirects to root.")
            continue
        safe_relative(relative)
        target = root / relative
        if target.is_symlink() or not target.is_dir() or root.resolve() not in target.resolve().parents:
            raise ClosureError("Module path escapes closure.")
    if "" not in seen:
        raise ClosureError("Missing root module.")
    return value["Modules"]


def source_inventory(source):
    """Check the complete source files against Git objects at the required SHA."""
    with tempfile.TemporaryDirectory() as directory:
        env = {"PATH": os.environ.get("PATH", ""), "HOME": directory,
               "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
        process = subprocess.run(["git", "-C", str(source), "ls-tree", "-r", "--full-tree", SHA, "--", "terraform"],
                                 env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if process.returncode:
        raise ClosureError("Reviewed Git source objects unavailable.")
    expected = {}
    for line in process.stdout.decode().splitlines():
        metadata, name = line.split("\t", 1)
        mode, kind, digest = metadata.split()
        if kind != "blob" or mode not in ("100644", "100755") or not name.startswith("terraform/"):
            raise ClosureError("Unsupported reviewed source entry.")
        relative = name[len("terraform/"):]
        safe_relative(relative)
        file = source / relative
        if file.is_symlink() or not file.is_file():
            raise ClosureError("Missing or redirected reviewed source.")
        raw = file.read_bytes()
        if hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() != digest:
            raise ClosureError("Source bytes differ from reviewed Git objects.")
        expected[relative] = {"sha256": hashlib.sha256(raw).hexdigest(), "mode": int(mode, 8) & 0o777}
    if not expected or inventory(source, include_directories=False) != expected:
        raise ClosureError("Source contains missing, extra or changed files.")
    return expected

def check(bundle, expected_digest, expected_sha=SHA):
    if (not re.fullmatch(r"[0-9a-f]{64}", expected_digest or "")
            or hashlib.sha256((bundle / "manifest.json").read_bytes()).hexdigest() != expected_digest):
        raise ClosureError("Manifest differs from separately selected digest.")
    manifest = read_json(bundle / "manifest.json")
    if (not isinstance(manifest, dict) or set(manifest) != {
            "format", "source_sha", "source_files", "terraform", "platform", "provenance", "files", "modules", "providers"}
            or manifest["format"] != 1 or manifest["source_sha"] != expected_sha
            or manifest["terraform"] != VERSION or manifest["platform"] != "linux_amd64"
            or manifest["provenance"] != "generated-public-resolution-not-reviewed"):
        raise ClosureError("Closure context does not match reviewed source/runtime.")
    providers = manifest["providers"]
    if (not isinstance(providers, dict) or not providers
            or not all(isinstance(name, str) and isinstance(version, str) and name and version
                       for name, version in providers.items())):
        raise ClosureError("Installed provider selections are missing or ambiguous.")
    files = manifest["files"]
    if not isinstance(files, dict) or not files:
        raise ClosureError("Missing artifact inventory.")
    for name, record in files.items():
        path = safe_relative(name)
        if path.parts[0] not in ("root", "mirror") or not isinstance(record, dict) or set(record) != {"sha256", "mode"}:
            raise ClosureError("Unsupported artifact record.")
    source_files = manifest["source_files"]
    if not isinstance(source_files, dict) or not source_files:
        raise ClosureError("Source provenance is missing.")
    for name, record in source_files.items():
        safe_relative(name)
        if files.get("root/" + name) != record:
            raise ClosureError("Reviewed source bytes do not match bundle.")
    actual = inventory(bundle)
    actual.pop("manifest.json", None)
    if actual != files:
        raise ClosureError("Missing, extra, changed or mode-changed closure artifact.")
    if "root/.terraform.lock.hcl" not in files:
        raise ClosureError("Provider lock is missing.")
    if module_graph(bundle / "root") != manifest["modules"]:
        raise ClosureError("Module graph changed.")
    return manifest


def terraform(binary, root, home, args):
    if os.name != "posix":
        raise ClosureError("Linux validation is required.")
    allowed = (
        args == ["version", "-json"]
        or args == ["init", "-backend=false", "-input=false", "-no-color"]
        or args == ["init", "-backend=false", "-get=false", "-lockfile=readonly", "-input=false", "-no-color"]
        or args == ["providers", "schema", "-json"]
        or len(args) == 4 and args[:3] == ["providers", "mirror", "-platform=linux_amd64"]
    )
    if not allowed:
        raise ClosureError("Terraform command is not permitted.")
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(home),
           "TF_CLI_CONFIG_FILE": str(home / "terraform.rc"), "TF_IN_AUTOMATION": "true",
           "TF_INPUT": "0", "CHECKPOINT_DISABLE": "1", "LANG": "C.UTF-8"}
    process = subprocess.run([binary, f"-chdir={root}", *args], env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if process.returncode:
        public_categories = ("Failed to download module", "Failed to query available provider packages",
                             "Failed to install provider", "Module not installed", "Inconsistent dependency lock file",
                             "Duplicate required providers configuration", "Invalid provider configuration",
                             "Unsupported argument", "Invalid single-argument block definition")
        output = (process.stdout + process.stderr).decode(errors="replace")
        categories = ", ".join(category for category in public_categories if category in output)
        raise ClosureError(f"Credential-free Terraform {args[0]} failed (exit {process.returncode}; {categories or 'unclassified initialization error'}); raw output withheld.")
    return process.stdout


def capture(source, bundle, binary):
    if bundle.exists():
        raise ClosureError("Bundle collision.")
    original_files = source_inventory(source)
    bundle.mkdir(mode=0o700)
    shutil.copytree(source, bundle / "root")
    root = bundle / "root"
    if (root / ".terraform").exists() or (root / ".terraform.lock.hcl").exists():
        raise ClosureError("Source includes unreviewed installation state.")
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        (home / "terraform.rc").write_text("disable_checkpoint = true\n")
        version = json.loads(terraform(binary, root, home, ["version", "-json"]))
        if version["terraform_version"] != VERSION or version["platform"] != "linux_amd64":
            raise ClosureError("Exact Terraform 1.16.4 Linux amd64 is required.")
        terraform(binary, root, home, ["init", "-backend=false", "-input=false", "-no-color"])
        providers = json.loads(terraform(binary, root, home, ["version", "-json"]))["provider_selections"]
        terraform(binary, root, home, ["providers", "mirror", "-platform=linux_amd64", str(bundle / "mirror")])
    # Installed provider symlinks are not transported. Reinstallation must verify lock checksums.
    shutil.rmtree(root / ".terraform" / "providers")
    modules = module_graph(root)
    manifest = {"format": 1, "source_sha": SHA, "terraform": VERSION, "platform": "linux_amd64",
                "provenance": "generated-public-resolution-not-reviewed", "modules": modules, "source_files": original_files,
                "files": inventory(bundle), "providers": providers}
    (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    digest = hashlib.sha256((bundle / "manifest.json").read_bytes()).hexdigest()
    check(bundle, digest)
    print("Generated manifest SHA256: " + digest)


def verify(bundle, binary, digest):
    baseline = check(bundle, digest)
    with tempfile.TemporaryDirectory() as directory:
        working = Path(directory)
        root = working / "root"
        shutil.copytree(bundle / "root", root)
        home = working / "home"
        home.mkdir(mode=0o700)
        mirror = (bundle / "mirror").resolve().as_posix()
        (home / "terraform.rc").write_text(
            'disable_checkpoint = true\nprovider_installation {\n  filesystem_mirror {\n'
            f'    path = "{mirror}"\n  }}\n}}\n')
        version = json.loads(terraform(binary, root, home, ["version", "-json"]))
        if version["terraform_version"] != VERSION or version["platform"] != "linux_amd64":
            raise ClosureError("Exact Terraform runtime mismatch.")
        terraform(binary, root, home, ["init", "-backend=false", "-get=false", "-lockfile=readonly", "-input=false", "-no-color"])
        providers = json.loads(terraform(binary, root, home, ["version", "-json"]))["provider_selections"]
        if providers != baseline["providers"]:
            raise ClosureError("Installed provider selections differ from captured closure.")
        terraform(binary, root, home, ["providers", "schema", "-json"])
        if (root / ".terraform.lock.hcl").read_bytes() != (bundle / "root" / ".terraform.lock.hcl").read_bytes():
            raise ClosureError("Provider lock changed during verification.")
        if module_graph(root) != baseline["modules"]:
            raise ClosureError("Module graph changed during verification.")
    check(bundle, digest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("capture", "verify"))
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--terraform", default="terraform")
    args = parser.parse_args()
    try:
        if args.operation == "capture":
            if not args.source:
                raise ClosureError("Source is required.")
            capture(args.source, args.bundle, args.terraform)
        else:
            verify(args.bundle, args.terraform, args.manifest_sha256)
        print("Public dependency capture/check completed; independent review and rollout gates remain required.")
    except (ClosureError, OSError, KeyError) as error:
        raise SystemExit(f"Dependency closure stopped: {str(error) if isinstance(error, ClosureError) else type(error).__name__}") from None