import copy
import hashlib
import importlib.util
import json
import os
import runpy
import subprocess
import sys
import tempfile
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

    def test_digest_uses_matching_unicode_bytes_once(self):
        path = Path(__file__).with_name("deploy.py")
        spec = importlib.util.spec_from_file_location("byte_bound_profile_deployer", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        configuration = {**self.profile, "instructions": "Review fictional caf\u00e9 evidence \u2014 no decisions."}
        content = json.dumps(configuration, ensure_ascii=False).encode("utf-8")
        with patch.object(Path, "read_bytes", return_value=content) as read:
            profile = module.profile_from_file(Path("fictional.json"), hashlib.sha256(content).hexdigest())
        read.assert_called_once_with()
        self.assertEqual(profile.instructions, configuration["instructions"])
        self.assertEqual(profile.name, configuration["name"])

    def test_digest_mismatch_or_missing_file_never_calls_publication(self):
        directory = Path(__file__).resolve().parent
        sys.path.insert(0, str(directory.parent))
        import deployment
        approved = json.dumps(self.profile).encode("utf-8")
        digest = hashlib.sha256(approved).hexdigest()
        edits = (
            {**self.profile, "instructions": "Changed after approval, same target name."},
            {**self.profile, "name": "different-coordinator"},
        )
        with tempfile.TemporaryDirectory() as temporary:
            profile_path = Path(temporary) / "fictional profile.json"
            for edit in edits:
                # The operator approved the earlier bytes, not this later path content.
                profile_path.write_bytes(json.dumps(edit).encode("utf-8"))
                argv = [str(directory / "deploy.py"), "--profile", str(profile_path), "--profile-sha256", digest]
                with self.subTest(edit=edit), patch.object(deployment, "run") as execute, patch.object(sys, "argv", argv):
                    with self.assertRaisesRegex(ValueError, "SHA-256 does not match"):
                        runpy.run_path(str(directory / "deploy.py"), run_name="__main__")
                    execute.assert_not_called()
            profile_path.unlink()
            with patch.object(deployment, "run") as execute, patch.object(sys, "argv", argv):
                with self.assertRaises(FileNotFoundError):
                    runpy.run_path(str(directory / "deploy.py"), run_name="__main__")
                execute.assert_not_called()

    def test_matching_digest_reaches_publication_with_the_checked_profile(self):
        directory = Path(__file__).resolve().parent
        sys.path.insert(0, str(directory.parent))
        import deployment
        content = json.dumps(self.profile).encode("utf-8")
        argv = [str(directory / "deploy.py"), "--profile", "fictional.json",
                "--profile-sha256", hashlib.sha256(content).hexdigest()]
        with patch.object(deployment, "run") as execute, patch.object(sys, "argv", argv), patch.object(Path, "read_bytes", return_value=content) as read:
            with self.assertRaises(SystemExit) as exit_status:
                runpy.run_path(str(directory / "deploy.py"), run_name="__main__")
        self.assertEqual(exit_status.exception.code, 0)
        read.assert_called_once_with()
        self.assertEqual(execute.call_args.args[0].instructions, self.profile["instructions"])
        self.assertEqual(execute.call_args.args[1], [])

    def test_digest_validation_checks_bytes_without_publication(self):
        directory = Path(__file__).resolve().parent
        sys.path.insert(0, str(directory.parent))
        import deployment
        content = json.dumps(self.profile).encode("utf-8")
        argv = [str(directory / "deploy.py"), "--profile", "fictional.json",
                "--profile-sha256", hashlib.sha256(content).hexdigest(), "--validate-profile"]
        with patch.object(deployment, "run") as execute, patch.object(sys, "argv", argv), patch.object(Path, "read_bytes", return_value=content) as read:
            with self.assertRaises(SystemExit) as exit_status:
                runpy.run_path(str(directory / "deploy.py"), run_name="__main__")
        self.assertEqual(exit_status.exception.code, 0)
        read.assert_called_once_with()
        execute.assert_not_called()

    def test_malformed_or_unscoped_digest_never_calls_publication(self):
        directory = Path(__file__).resolve().parent
        sys.path.insert(0, str(directory.parent))
        import deployment
        arguments = [
            ["--profile", "fictional.json", "--profile-sha256", value]
            for value in ("", "abc", "A" * 64, "g" * 64, "a" * 65)
        ]
        arguments.append(["--profile-sha256", "a" * 64])
        for argument in arguments:
            with self.subTest(argument=argument), patch.object(deployment, "run") as execute, patch.object(sys, "argv", [str(directory / "deploy.py"), *argument]):
                with self.assertRaises(SystemExit) as exit_status:
                    runpy.run_path(str(directory / "deploy.py"), run_name="__main__")
                self.assertEqual(exit_status.exception.code, 2)
                execute.assert_not_called()

    def test_byte_bound_endpoint_name_boundaries_reach_only_the_expected_runner(self):
        directory = Path(__file__).resolve().parent
        sys.path.insert(0, str(directory.parent))
        import deployment
        with tempfile.TemporaryDirectory() as temporary:
            profile_path = Path(temporary) / "fictional-names.json"
            for field in ("coordinator", "specialist"):
                for name in ("A", "7", "A--Z", "9" + "a" * 62):
                    configuration = copy.deepcopy(self.profile)
                    configuration["specialists"][0]["tool"] = "inspect_application"
                    configuration["smoke_tests"][0]["tool"] = "inspect_application"
                    if field == "coordinator":
                        configuration["name"] = name
                    else:
                        configuration["specialists"][0]["agent"] = name
                    content = json.dumps(configuration).encode("utf-8")
                    profile_path.write_bytes(content)
                    for validate_only in (True, False):
                        argv = [str(directory / "deploy.py"), "--profile", str(profile_path),
                                "--profile-sha256", hashlib.sha256(content).hexdigest()]
                        if validate_only:
                            argv.append("--validate-profile")
                        with self.subTest(field=field, name=name, validate_only=validate_only), patch.object(deployment, "run") as execute, patch.object(sys, "argv", argv):
                            with self.assertRaises(SystemExit) as exit_status:
                                runpy.run_path(str(directory / "deploy.py"), run_name="__main__")
                            self.assertEqual(exit_status.exception.code, 0)
                            if validate_only:
                                execute.assert_not_called()
                            else:
                                profile = execute.call_args.args[0]
                                self.assertEqual(profile.name, configuration["name"])
                                self.assertEqual(profile.delegation_checks[0][1:], (
                                    "inspect_application", configuration["specialists"][0]["agent"]))
                                self.assertEqual(json.loads(dict(profile.environment_variables)["SPECIALIST_CONFIG"]),
                                                 configuration["specialists"])

    def test_byte_bound_invalid_endpoint_names_never_reach_publication(self):
        directory = Path(__file__).resolve().parent
        sys.path.insert(0, str(directory.parent))
        import deployment
        with tempfile.TemporaryDirectory() as temporary:
            profile_path = Path(temporary) / "fictional-invalid-names.json"
            for field in ("coordinator", "specialist"):
                for name in ("_coordinator", "agent_name", "-agent", "agent-", "a" * 64, "caf\u00e9", "-"):
                    configuration = copy.deepcopy(self.profile)
                    if field == "coordinator":
                        configuration["name"] = name
                    else:
                        configuration["specialists"][0]["agent"] = name
                    content = json.dumps(configuration).encode("utf-8")
                    profile_path.write_bytes(content)
                    for validate_only in (True, False):
                        argv = [str(directory / "deploy.py"), "--profile", str(profile_path),
                                "--profile-sha256", hashlib.sha256(content).hexdigest()]
                        if validate_only:
                            argv.append("--validate-profile")
                        with self.subTest(field=field, name=name, validate_only=validate_only), patch.object(deployment, "run") as execute, patch.object(sys, "argv", argv):
                            with self.assertRaisesRegex(ValueError, "Deployment profile agent endpoint names"):
                                runpy.run_path(str(directory / "deploy.py"), run_name="__main__")
                            execute.assert_not_called()

    def test_legacy_profile_names_and_shared_runtime_semantics_are_unchanged(self):
        path = Path(__file__).with_name("deploy.py")
        spec = importlib.util.spec_from_file_location("legacy_profile_deployer", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for field in ("coordinator", "specialist"):
            for name in ("_coordinator", "agent_name", "agent-", "a" * 64):
                configuration = copy.deepcopy(self.profile)
                if field == "coordinator":
                    configuration["name"] = name
                else:
                    configuration["specialists"][0]["agent"] = name
                with self.subTest(field=field, name=name), patch.object(Path, "read_text", return_value=json.dumps(configuration)):
                    self.assertEqual(validate_profile(configuration), configuration)
                    selected = module.profile_from_file(Path("fictional.json"))
                    self.assertEqual(selected.name, configuration["name"])
                    self.assertEqual(selected.delegation_checks[0][2], configuration["specialists"][0]["agent"])

    def test_byte_bound_names_preserve_shared_schema_and_self_delegation_guards(self):
        path = Path(__file__).with_name("deploy.py")
        spec = importlib.util.spec_from_file_location("deployment_profile_guards", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self_delegating = copy.deepcopy(self.profile)
        self_delegating["name"] = "7"
        self_delegating["specialists"][0]["agent"] = "7"
        before = copy.deepcopy(self_delegating)
        with self.assertRaisesRegex(ValueError, "cannot delegate to itself"):
            module.validate_deployment_profile(self_delegating)
        self.assertEqual(self_delegating, before)
        for override in ({"smoke_tests": []}, {"unexpected": "field"}, {"instructions": " "}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                module.validate_deployment_profile({**copy.deepcopy(self.profile), **override})

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