"""Synthetic, standard-library-only tests. No network or operational hooks."""

import hashlib
import unittest

from check_runner_restart_candidate import (
    check_configured_vm,
    check_observed_vm,
    check_source,
    classify_power_state,
)

SHA = "a" * 40
CONTEXT = {
    "repository": "michael-rechani/foundry-agent-accelerator",
    "repository_owner": "michael-rechani",
    "actor_id": "97264614",
    "workflow_ref": (
        "michael-rechani/foundry-agent-accelerator/"
        ".github/workflows/start-private-runner-reviewed.yml@refs/heads/main"
    ),
    "ref": "refs/heads/main",
    "event_name": "workflow_dispatch",
    "run_number": "1",
    "run_attempt": "1",
    "sha": SHA,
    "workflow_sha": SHA,
}
MAIN = {"name": "main", "protected": True, "commit": {"sha": SHA}}
ARM_ID = (
    "/subscriptions/00000000-0000-0000-0000-000000000001"
    "/resourceGroups/fixture-RG/providers/Microsoft.Compute/virtualMachines/fixture-VM"
)
VM_UUID = "00000000-0000-0000-0000-0000000000ab"
ARM_HASH = hashlib.sha256(ARM_ID.lower().encode()).hexdigest()
UUID_HASH = hashlib.sha256(VM_UUID.encode()).hexdigest()


class RestartCandidateTests(unittest.TestCase):
    def test_exact_run_and_current_main(self):
        check_source(CONTEXT, SHA, MAIN)
        for key in CONTEXT:
            with self.subTest(missing=key), self.assertRaises(ValueError):
                check_source({k: v for k, v in CONTEXT.items() if k != key}, SHA, MAIN)
        for key, wrong in {
            "repository": "fork/foundry-agent-accelerator",
            "actor_id": "97264615",
            "workflow_ref": CONTEXT["workflow_ref"].replace("reviewed", "once-20261107"),
            "ref": "refs/heads/other",
            "event_name": "push",
            "run_number": "2",
            "run_attempt": "2",
            "sha": "b" * 40,
            "workflow_sha": "b" * 40,
        }.items():
            with self.subTest(key=key), self.assertRaises(ValueError):
                check_source(CONTEXT | {key: wrong}, SHA, MAIN)
        for stale_or_invalid in (
            None,
            MAIN | {"protected": 1},
            MAIN | {"protected": False},
            MAIN | {"name": "other"},
            MAIN | {"commit": {"sha": "b" * 40}},
        ):
            with self.subTest(main=stale_or_invalid), self.assertRaises(ValueError):
                check_source(CONTEXT, SHA, stale_or_invalid)
        with self.assertRaises(ValueError):
            check_source(CONTEXT, SHA.upper(), MAIN)

    def test_normalized_exact_arm_path_and_instance(self):
        check_configured_vm(ARM_ID.upper(), ARM_HASH)
        check_observed_vm(ARM_ID, ARM_ID.lower(), VM_UUID.upper(), ARM_HASH, UUID_HASH)
        for bad_id, bad_hash in (
            (ARM_ID + "\n", ARM_HASH),
            (ARM_ID + "/", ARM_HASH),
            (ARM_ID.replace("000001", "000002"), ARM_HASH),
            (ARM_ID, ARM_HASH.upper()),
            (ARM_ID, hashlib.sha256((ARM_ID.lower() + "\n").encode()).hexdigest()),
        ):
            with self.subTest(configured=bad_id, fingerprint=bad_hash), self.assertRaises(ValueError):
                check_configured_vm(bad_id, bad_hash)
        for observed_id, instance_id in (
            (ARM_ID.replace("fixture-VM", "other-VM"), VM_UUID),
            (ARM_ID.replace("fixture-RG", "other-RG"), VM_UUID),
            (ARM_ID, VM_UUID[:-1] + "c"),
            (ARM_ID, ""),
        ):
            with self.subTest(observed=observed_id, instance=instance_id), self.assertRaises(ValueError):
                check_observed_vm(ARM_ID, observed_id, instance_id, ARM_HASH, UUID_HASH)

    def test_only_stopped_or_deallocated_can_start(self):
        for state in ("stopped", "deallocated"):
            self.assertEqual(classify_power_state([f"PowerState/{state}"]), "start")
        for state in ("starting", "running"):
            self.assertEqual(classify_power_state([f"PowerState/{state}"]), "observe")
        for states in (
            None,
            [],
            ["PowerState/stopping"],
            ["PowerState/deallocating"],
            ["PowerState/unknown"],
            ["PowerState/deallocated", "PowerState/running"],
            ["PowerState/deallocated", "PowerState/deallocated"],
        ):
            with self.subTest(states=states), self.assertRaises(ValueError):
                classify_power_state(states)
