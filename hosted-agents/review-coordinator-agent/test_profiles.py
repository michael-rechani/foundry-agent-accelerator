import copy
import importlib.util
import json
import os
import runpy
import subprocess
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

from configuration import validate_profile


class ProfileTests(unittest.TestCase):
    def test_default_deployment_requires_expected_specialists(self):
        directory = Path(__file__).resolve().parent
        sys.path.insert(0, str(directory.parent))
        import deployment
        with patch.object(deployment, "run") as execute, patch.object(sys, "argv", [str(directory / "deploy.py")]):
            runpy.run_path(str(directory / "deploy.py"), run_name="__main__")
        profile = execute.call_args.args[0]
        self.assertEqual({(check[1], check[2]) for check in profile.delegation_checks},
                         {("review_application", "application-review-agent"), ("review_case", "case-review-agent")})

    def test_validation_cli_needs_no_endpoint_or_credentials(self):
        directory = Path(__file__).resolve().parent
        environment = {key: value for key, value in os.environ.items() if not key.startswith(("FOUNDRY_", "AZURE_"))}
        result = subprocess.run(
            [sys.executable, str(directory / "deploy.py"), "--profile",
             str(directory / "profiles" / "evidence-review.example.json"), "--validate-profile"],
            capture_output=True, text=True, env=environment, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("inspect_application -> application-review-agent", result.stdout)

    def setUp(self):
        self.profile = {
            "schema_version": 1, "name": "customer-coordinator", "description": "Customer review",
            "instructions": "Route supplied evidence to the selected specialist.",
            "specialists": [{"tool": "check_record", "agent": "customer-specialist", "description": "Check supplied records."}],
            "smoke_tests": [{"tool": "check_record", "prompt": "Check source REC-1."}],
        }

    def test_valid_profile(self):
        self.assertEqual(validate_profile(self.profile), self.profile)

    def test_example_matches_base_behavior_with_only_tool_names_changed(self):
        directory = Path(__file__).parent
        example = validate_profile(json.loads(
            (directory / "profiles" / "evidence-review.example.json").read_text(encoding="utf-8")
        ))
        base = (directory / "instructions.md").read_text(encoding="utf-8")
        expected = base.replace("review_application", "inspect_application").replace("review_case", "inspect_case")
        self.assertEqual(example["instructions"].strip(), expected.strip())

    def test_rejects_invalid_or_untested_profiles(self):
        overrides = [
            {"schema_version": 2}, {"schema_version": True}, {"instructions": " "},
            {"smoke_tests": []}, {"smoke_tests": [{"tool": "unknown", "prompt": "Review"}]},
            {"smoke_tests": [{"tool": "check_record", "prompt": ""}]},
            {"name": "customer-specialist"}, {"unexpected": "setting"},
        ]
        for override in overrides:
            with self.subTest(override=override), self.assertRaises(ValueError):
                validate_profile({**copy.deepcopy(self.profile), **override})

    def test_example_compiles_runtime_bindings_and_checks(self):
        path = Path(__file__).with_name("deploy.py")
        spec = importlib.util.spec_from_file_location("profile_deployer", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        profile = module.profile_from_file(Path(__file__).with_name("profiles") / "evidence-review.example.json")
        example = json.loads((path.parent / "profiles" / "evidence-review.example.json").read_text(encoding="utf-8"))
        self.assertEqual(profile.instructions, example["instructions"])
        specialists = json.loads(dict(profile.environment_variables)["SPECIALIST_CONFIG"])
        self.assertEqual(len(specialists), 2)
        self.assertEqual({(check[1], check[2]) for check in profile.delegation_checks},
                         {(item["tool"], item["agent"]) for item in specialists})
        self.assertTrue(all(check[0].strip() for check in profile.delegation_checks))