"""Apply one reviewed, narrow set of Lab Terraform changes from the protected runner.

The apply runs only when the full redacted plan contains nothing but the reviewed
change set: the Front Door WAF policy ``managed-by``/``workload`` tags and the
Container App ``WORKBENCH_UNFINISHED_AGENTS_ENABLED`` setting (plus the known
representation-only ``WORKBENCH_CREATION_KEY_SHA256`` difference).
"""

import hashlib
import json
import os
import sys
import time

from check_lab_terraform_plan import (
    LAB_INPUTS,
    LAB_STATE,
    LabBlobs,
    LabTerraform,
    configuration,
    configure_platform_oidc,
    current_image,
    lab_state,
    snapshot_unchanged,
    stage_sources,
    summarize_plan,
    validate_inputs,
    write_supplemental_files,
)
from check_state_backend import CheckError
from reconcile_runner_state import Terraform, cleanup, object_json, private_scratch

CREATION_KEY = "WORKBENCH_CREATION_KEY_SHA256"
UNFINISHED_FLAG = "WORKBENCH_UNFINISHED_AGENTS_ENABLED"
ALERTS = ("request_failures", "dependencies", "heartbeat")
UNCHANGED_ALLOWLIST = {"status": "compared", "relation": "unchanged", "added": 0, "removed": 0}
SAVED_PLAN = "lab.tfplan"
REVISION_WAIT_SECONDS = 600
REVISION_POLL_SECONDS = 15


def reject(reason):
    raise CheckError(f"The plan contains changes outside the reviewed set ({reason}).")


def approved_changes(summary):
    """Return the reviewed changes in a redacted plan summary, or raise if anything else is planned."""
    if (summary["imports"] or summary["data_reads"] or summary["output_changes"]
            or summary["resources_with_unknown_values"] or summary["outputs_with_unknown_values"]
            or summary["nonpassing_checks"]):
        reject("imports, data reads, output changes, unknown values or non-passing checks")
    targets = summary["targets"]
    if any(targets[label]["planned"]["action"] != "no-op" for label in ALERTS):
        reject("an alert")
    changes = []
    waf = targets["waf"]["planned"]
    if waf["action"] != "no-op":
        tags = waf["tag_comparison"]
        pair = (tags.get("workload"), tags.get("managed-by"))
        if (waf["action"] != "update" or waf["fields"] != ["tags"] or waf["unknown_fields"] or waf["import"]
                or waf["allowlist_comparison"] != UNCHANGED_ALLOWLIST
                or tags.get("status") != "compared" or tags.get("other_keys_changed") is not False
                or set(pair) - {"added", "unchanged"} or "added" not in pair):
            reject("the WAF policy")
        changes.append("waf_tags")
    details = summary["other_managed_details"]
    if (len(details) > 1 or summary["other_managed_changes"] != len(details)
            or summary["other_managed_actions"]["update"] != len(details)):
        reject("other managed resources")
    if details:
        app = details[0]
        comparison = app.get("environment_comparison", {})
        changed = comparison.get("changed", {})
        attributes = comparison.get("changed_attributes")
        expected_attributes = {CREATION_KEY: {"value": "empty->null"}} if CREATION_KEY in changed else {}
        if (app["resource"] != "container_app" or app["action"] != "update"
                or app["fields"] != ["template.container.env"] or app["unknown_fields"] or app["import"]
                or comparison.get("status") != "compared" or not changed
                or comparison["order_changed"] or comparison["other_entries_changed"]
                or set(changed) - {UNFINISHED_FLAG, CREATION_KEY}
                or changed.get(UNFINISHED_FLAG, "added") != "added"
                or changed.get(CREATION_KEY, "changed") != "changed"
                or attributes != expected_attributes):
            reject("the Container App")
        changes.append("container_app_environment")
    return changes


class ApplyTerraform(LabTerraform):
    def command(self, *args, allowed=(0,), input_data=None):
        if args[:1] != ("apply",):
            return super().command(*args, allowed=allowed, input_data=input_data)
        saved = self.scratch / SAVED_PLAN
        if (args != ("apply", "-input=false", "-lock=true", "-lock-timeout=5m", str(saved))
                or allowed != (0,) or input_data is not None):
            raise CheckError("Only the guarded apply of the exact saved plan is allowed.")
        return Terraform.command(self, *args, allowed=allowed, input_data=input_data)

    def saved_plan_digest(self):
        return hashlib.sha256((self.scratch / SAVED_PLAN).read_bytes()).digest()

    def apply_saved_plan(self, digest):
        if self.saved_plan_digest() != digest:
            raise CheckError("The guarded saved plan changed; refusing to apply.")
        self.command("apply", "-input=false", "-lock=true", "-lock-timeout=5m", str(self.scratch / SAVED_PLAN))


def state_identity(raw, subscription):
    app = lab_state(raw, subscription)
    state = object_json(raw)
    return app, state["lineage"], state["serial"]


def unchanged(blobs, snapshots, names):
    return all(snapshot_unchanged(name, snapshots[name], blobs.snapshot(name)) for name in names)


def wait_for_image(runtime, app, previous_revision, expect_new_revision):
    """Return the active image digest, waiting for the new revision when the app was updated."""
    deadline = time.monotonic() + REVISION_WAIT_SECONDS
    while True:
        try:
            revision, digest = current_image(runtime, app)
            if revision != previous_revision or not expect_new_revision:
                return digest
        except CheckError:
            if time.monotonic() >= deadline:
                raise
        if time.monotonic() >= deadline:
            raise CheckError("The updated Lab revision did not become the active ready revision in time.")
        time.sleep(REVISION_POLL_SECONDS)


def verify_applied(baseline, terraform, values, expect_new_revision):
    runtime, blobs = baseline["runtime"], baseline["blobs"]
    body, _, _ = blobs.snapshot(LAB_STATE)
    _, lineage, serial = state_identity(body, runtime["AZURE_SUBSCRIPTION_ID"])
    if lineage != baseline["lineage"] or serial <= baseline["serial"]:
        raise CheckError("The Lab state did not record the apply with its original lineage.")
    others = [name for name in baseline["snapshots"] if name != LAB_STATE]
    if not unchanged(blobs, baseline["snapshots"], others):
        raise CheckError("A protected input or platform state blob changed during the apply.")
    digest = wait_for_image(runtime, baseline["app"], baseline["revision"], expect_new_revision)
    if digest != baseline["digest"]:
        raise CheckError("The active Lab image digest changed during the apply; investigate before any rollout.")
    plan, exit_code = terraform.full_plan()
    follow_up = summarize_plan(plan, exit_code, values)
    remaining = approved_changes(follow_up)
    print("Follow-up plan after the apply; actions and schema fields only:")
    print(json.dumps(follow_up, indent=2, sort_keys=True))
    return remaining


def run(environ=os.environ):
    operation = environ.get("TF_LAB_APPLY_OPERATION")
    if operation not in ("check", "apply"):
        raise CheckError("Only a check or the reviewed apply is allowed.")
    runtime = configuration(environ)
    blobs = LabBlobs(runtime)
    snapshots = {name: blobs.snapshot(name) for name in (LAB_STATE, LAB_INPUTS)}
    app, lineage, serial = state_identity(snapshots[LAB_STATE][0], runtime["AZURE_SUBSCRIPTION_ID"])
    revision, digest = current_image(runtime, app)
    baseline = {
        "runtime": runtime, "blobs": blobs, "snapshots": snapshots, "app": app,
        "lineage": lineage, "serial": serial, "revision": revision, "digest": digest,
    }
    old_umask = os.umask(0o077)
    applying = False
    try:
        with private_scratch(runtime) as scratch:
            root = stage_sources(scratch, runtime)
            configure_platform_oidc(root)
            write_supplemental_files(root, digest)
            terraform = ApplyTerraform(root, scratch, runtime, snapshots[LAB_INPUTS][0])
            values = terraform.inputs_resolved()
            platform = validate_inputs(values, app, digest, runtime)
            if platform:
                snapshots[platform] = blobs.snapshot(platform)
            plan, exit_code = terraform.full_plan()
            planned = terraform.saved_plan_digest()
            summary = summarize_plan(plan, exit_code, values)
            changes = approved_changes(summary)
            print("Private full-root Lab plan; actions and schema fields only:")
            print(json.dumps(summary, indent=2, sort_keys=True))
            if (current_image(runtime, app) != (revision, digest)
                    or not unchanged(blobs, snapshots, list(snapshots))):
                raise CheckError("The active Lab revision, state or inputs changed during planning.")
            if not changes:
                print("The Lab plan has no changes; nothing to apply.")
                return
            print(f"Reviewed changes: {', '.join(changes)}.")
            if operation == "check":
                print("Check only; nothing was applied.")
                return
            applying = True
            terraform.apply_saved_plan(planned)
            print("Terraform apply completed; verifying the result.")
            remaining = verify_applied(baseline, terraform, values, "container_app_environment" in changes)
            print("Verified: state advanced with the same lineage; inputs and image digest unchanged. "
                  f"Reviewed changes still planned: {', '.join(remaining) or 'none'}.")
    except (CheckError, OSError):
        print(
            "The apply was started; inspect the Lab and its state before retrying. A re-run re-plans "
            "under the same guard." if applying else "Nothing was applied.",
            file=sys.stderr,
        )
        raise
    finally:
        os.umask(old_umask)


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["--cleanup"]:
            cleanup()
        elif not sys.argv[1:]:
            run()
        else:
            raise CheckError("This operation accepts no Terraform or file arguments.")
    except (CheckError, OSError) as exc:
        message = str(exc) if isinstance(exc, CheckError) else "Private local file or process access failed."
        print(f"Lab Terraform apply failed: {message}", file=sys.stderr)
        sys.exit(1)
