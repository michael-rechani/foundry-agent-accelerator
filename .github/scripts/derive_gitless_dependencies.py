"""Derive, never modify, an observed closure without module-cache .git directories.

No git process, metadata evaluation, download, Terraform or credential integration.
Requires isolated same-UID/host access, not merely filesystem ownership checks.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import secrets
import stat

import extract_platform_dependencies as extraction
import platform_dependency_closure as closure


class DerivationError(Exception):
    pass


def metadata_component(name):
    parts = name.split("/")
    if parts[:3] != ["root", ".terraform", "modules"]:
        return None
    for index in range(3, len(parts)):
        if parts[index] == ".git":
            return "/".join(parts[:index + 1])
    return None


def open_absolute_directory(path):
    raw = os.fspath(path)
    if not raw.startswith("/") or raw != str(Path(raw)) or raw.startswith("//") or "\\" in raw:
        raise DerivationError("An absolute canonical source directory is required.")
    fd = os.open("/", extraction.FLAGS | os.O_DIRECTORY)
    try:
        for part in Path(raw).parts[1:]:
            if part in (".", ".."):
                raise DerivationError("Unsafe source path.")
            next_fd = os.open(part, extraction.FLAGS | os.O_DIRECTORY, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def fd_inventory(root_fd, prefix="", expected=None):
    records = {}
    for name in sorted(os.listdir(root_fd)):
        if len(records) > 20000 or len(prefix.split("/")) > 34:
            raise DerivationError("Source inventory count/depth bound exceeded.")
        relative = prefix + name
        closure.safe_relative(relative)
        if expected is not None and relative not in expected:
            raise DerivationError("Unexpected source/output descriptor inventory entry.")
        info = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode):
            fd = os.open(name, extraction.FLAGS | os.O_DIRECTORY, dir_fd=root_fd)
            try:
                current = os.fstat(fd)
                if (info.st_dev, info.st_ino) != (current.st_dev, current.st_ino):
                    raise DerivationError("Source directory changed during inventory.")
                records[relative] = {"sha256": "directory", "mode": stat.S_IMODE(current.st_mode)}
                records.update(fd_inventory(fd, relative + "/", expected))
            finally:
                os.close(fd)
        elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
            fd = os.open(name, extraction.FLAGS, dir_fd=root_fd)
            try:
                current = os.fstat(fd)
                if (info.st_dev, info.st_ino) != (current.st_dev, current.st_ino) or current.st_nlink != 1:
                    raise DerivationError("Source file changed during inventory.")
                if current.st_size > 150_000_000:
                    raise DerivationError("Source file exceeds captured transport bound.")
                digest = hashlib.sha256()
                read = 0
                while chunk := os.read(fd, 65536):
                    read += len(chunk)
                    if read > 150_000_000:
                        raise DerivationError("Source file grew beyond captured transport bound.")
                    digest.update(chunk)
                after = os.fstat(fd)
                if (current.st_size, current.st_mtime_ns, current.st_ctime_ns) != (
                        after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                    raise DerivationError("Source file mutated during inventory.")
                records[relative] = {"sha256": digest.hexdigest(), "mode": stat.S_IMODE(current.st_mode)}
            finally:
                os.close(fd)
        else:
            raise DerivationError("Links, hardlinks and special metadata/files are forbidden.")
    if len(records) > 20000:
        raise DerivationError("Inventory total entry bound exceeded.")
    return records


def canonical_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def selected_source(source, digest):
    if not re.fullmatch(r"[0-9a-f]{64}", digest or ""):
        raise DerivationError("A separately supplied original manifest digest is required.")
    source_fd = open_absolute_directory(source)
    try:
        fd = os.open("manifest.json", extraction.FLAGS, dir_fd=source_fd)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 10_000_000:
                raise DerivationError("Invalid source manifest descriptor.")
            chunks = []
            remaining = 10_000_001
            while chunk := os.read(fd, min(65536, remaining)):
                chunks.append(chunk)
                remaining -= len(chunk)
                if remaining <= 0:
                    raise DerivationError("Original manifest byte bound exceeded.")
            raw = b"".join(chunks)
        finally:
            os.close(fd)
        if hashlib.sha256(raw).hexdigest() != digest:
            raise DerivationError("Original manifest bytes do not match separately selected digest.")
        manifest = json.loads(raw, object_pairs_hook=closure.pairs)
        expected = dict(manifest["files"])
        expected["manifest.json"] = {"sha256": digest, "mode": stat.S_IMODE(info.st_mode)}
        if fd_inventory(source_fd, expected=expected) != expected:
            raise DerivationError("Source descriptor inventory differs from selected original manifest.")
        if closure.check(source, digest) != manifest:
            raise DerivationError("Selected original manifest changed during verification.")
        return manifest, source_fd, expected
    except BaseException:
        os.close(source_fd)
        raise

def select_omissions(manifest):
    files = manifest["files"]
    caches = {module["Dir"] for module in manifest["modules"] if module["Dir"].startswith(".terraform/modules/")}
    omitted = {}
    roots = set()
    for name, record in files.items():
        component = metadata_component(name)
        if component is None:
            if ".git" in name.split("/"):
                raise DerivationError("Git metadata outside installed module caches requires review.")
            continue
        if files.get(component, {}).get("sha256") != "directory":
            raise DerivationError("Unknown .git file/worktree pointer is not omitted.")
        if not any(component.startswith("root/" + cache + "/") for cache in caches):
            raise DerivationError(".git metadata outside a recorded installed module is ambiguous.")
        if any(("root/" + cache) == component or ("root/" + cache).startswith(component + "/") for cache in caches):
            raise DerivationError("Recorded module resolves inside .git metadata.")
        omitted[name] = record
        roots.add(component)
    if not omitted:
        raise DerivationError("No recorded module-cache .git metadata found; derivation requires review.")
    return dict(sorted(omitted.items())), sorted(roots)


def copy_regular(source_fd, output_fd, name, expected):
    parts = name.split("/")
    source_parent = extraction.open_relative(source_fd, parts[:-1])
    output_parent = extraction.open_relative(output_fd, parts[:-1])
    source_file = output_file = None
    try:
        source_file = os.open(parts[-1], extraction.FLAGS, dir_fd=source_parent)
        before = os.fstat(source_file)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or stat.S_IMODE(before.st_mode) != expected["mode"]:
            raise DerivationError("Source copy file type/mode changed.")
        output_file = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                              0o600, dir_fd=output_parent)
        digest = hashlib.sha256()
        while chunk := os.read(source_file, 65536):
            extraction.write_all(output_file, chunk)
            digest.update(chunk)
        after = os.fstat(source_file)
        if digest.hexdigest() != expected["sha256"] or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise DerivationError("Source copy bytes changed from selected manifest.")
        os.fchmod(output_file, expected["mode"])
        os.fsync(output_file)
    finally:
        for fd in (source_file, output_file, source_parent, output_parent):
            if fd is not None:
                os.close(fd)


def copy_inventory(source_fd, output_fd, records):
    directories = sorted((name for name, record in records.items() if record["sha256"] == "directory"),
                         key=lambda value: (value.count("/"), value))
    for name in directories:
        parts = name.split("/")
        parent = extraction.open_relative(output_fd, parts[:-1])
        try:
            os.mkdir(parts[-1], mode=0o700, dir_fd=parent)
        finally:
            os.close(parent)
    for name in sorted(set(records) - set(directories)):
        copy_regular(source_fd, output_fd, name, records[name])
    for name in reversed(directories):
        fd = extraction.open_relative(output_fd, name.split("/"))
        try:
            os.fchmod(fd, records[name]["mode"])
            os.fsync(fd)
        finally:
            os.close(fd)


def write_json(root_fd, name, value):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=root_fd)
    try:
        extraction.write_all(fd, canonical_bytes(value))
        os.fsync(fd)
    finally:
        os.close(fd)


def verify_derived(wrapper, original, original_digest):
    manifest = closure.check(original, original_digest)
    omitted, roots = select_omissions(manifest)
    expected_files = {name: value for name, value in manifest["files"].items() if name not in omitted}
    derived = dict(manifest, files=expected_files)
    derived_digest = hashlib.sha256(canonical_bytes(derived)).hexdigest()
    bundle = wrapper / "bundle"

    expected_binding = {
        "format": 1, "kind": "generated-gitless-observation-not-approved",
        "original_manifest_sha256": original_digest, "derived_manifest_sha256": derived_digest,
        "source_sha": manifest["source_sha"], "removed_roots": roots, "omitted_inventory": omitted,
    }

    expected = {"bundle": {"sha256": "directory", "mode": 0o700},
                "bundle/manifest.json": {"sha256": derived_digest, "mode": 0o600},
                "derivation.json": {"sha256": hashlib.sha256(canonical_bytes(expected_binding)).hexdigest(), "mode": 0o600}}
    expected.update({"bundle/" + name: record for name, record in expected_files.items()})
    fd = open_absolute_directory(wrapper)
    try:
        if fd_inventory(fd, expected=expected) != expected:
            raise DerivationError("Missing, extra, changed or linked derived wrapper files.")
    finally:
        os.close(fd)
    checked = closure.check(bundle, derived_digest)
    binding = closure.read_json(wrapper / "derivation.json")
    if binding != expected_binding or checked != derived:
        raise DerivationError("Derived manifest/binding differs from selected original transformation.")
    if any(metadata_component(name) for name in checked["files"]):
        raise DerivationError("Module-cache Git metadata remains.")
    return derived_digest


def derive(source, original_digest, parent, destination):
    source = Path(source)
    if source == Path(parent) or source in Path(parent).parents:
        raise DerivationError("Output parent must not be inside the original closure.")
    if not destination or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", destination):
        raise DerivationError("One bounded fresh destination name is required.")
    manifest, source_fd, original_inventory = selected_source(source, original_digest)
    parent_fd = stage_fd = bundle_fd = None
    stage = ".gitless-derive-" + secrets.token_hex(16)
    created = False
    published = False
    try:
        parent_fd = extraction.trusted_parent(parent)
        try:
            os.stat(destination, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise DerivationError("Derived destination collision.")
        omitted, roots = select_omissions(manifest)
        retained = {name: value for name, value in manifest["files"].items() if name not in omitted}
        os.mkdir(stage, 0o700, dir_fd=parent_fd)
        created = True
        stage_fd = os.open(stage, extraction.FLAGS | os.O_DIRECTORY, dir_fd=parent_fd)
        extraction.same_directory(parent_fd, stage, stage_fd)
        os.mkdir("bundle", 0o700, dir_fd=stage_fd)
        bundle_fd = os.open("bundle", extraction.FLAGS | os.O_DIRECTORY, dir_fd=stage_fd)
        copy_inventory(source_fd, bundle_fd, retained)
        derived = dict(manifest, files=retained)
        digest = hashlib.sha256(canonical_bytes(derived)).hexdigest()
        write_json(bundle_fd, "manifest.json", derived)
        binding = {"format": 1, "kind": "generated-gitless-observation-not-approved",
                   "original_manifest_sha256": original_digest, "derived_manifest_sha256": digest,
                   "source_sha": manifest["source_sha"], "removed_roots": roots, "omitted_inventory": omitted}
        write_json(stage_fd, "derivation.json", binding)
        wrapper = Path(parent) / stage
        verify_derived(wrapper, source, original_digest)
        if fd_inventory(source_fd, expected=original_inventory) != original_inventory:
            raise DerivationError("Original descriptor source changed during derivation.")
        closure.check(source, original_digest)
        extraction.same_directory(parent_fd, stage, stage_fd)
        os.fsync(bundle_fd)
        os.fsync(stage_fd)
        os.fsync(parent_fd)
        extraction.publish_exclusive(parent_fd, stage, destination)
        published = True
        return Path(parent) / destination, digest
    except (OSError, closure.ClosureError, extraction.ExtractionError, DerivationError):
        if created and not published:
            if stage_fd is None:
                raise DerivationError("Derivation failed; reserved descriptor ownership unavailable.") from None
            try:
                extraction.same_directory(parent_fd, stage, stage_fd)
                extraction.cleanup_owned(stage_fd)
                extraction.same_directory(parent_fd, stage, stage_fd)
                os.rmdir(stage, dir_fd=parent_fd)
            except (OSError, extraction.ExtractionError):
                raise DerivationError("Derivation failed; owned cleanup could not be verified.") from None
        raise
    finally:
        for fd in (bundle_fd, stage_fd, parent_fd, source_fd):
            if fd is not None:
                os.close(fd)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--original-manifest-sha256", required=True)
    parser.add_argument("--trusted-parent", required=True)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()
    try:
        wrapper, digest = derive(args.source, args.original_manifest_sha256, args.trusted_parent, args.destination)
        print("Generated metadata-free manifest SHA256 (unapproved observation): " + digest)
    except (OSError, closure.ClosureError, extraction.ExtractionError, DerivationError):
        raise SystemExit("Metadata-free derivation stopped; no verified handoff.") from None
