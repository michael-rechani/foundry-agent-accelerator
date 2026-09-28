import io
import json
import random
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

import bundle


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.path = self.directory / "sample.agent-bundle.zip"

    def write_bundle(self, sample="case-review-agent", **options):
        self.path.write_bytes(bundle.export_sample(sample, **options))
        return bundle.read_bundle(self.path)

    def rewrite(self, content, *, manifest_changes=None, code=None):
        files = bundle.zip_contents(content)
        manifest = bundle.read_json(files["manifest.json"])
        manifest.update(manifest_changes or {})
        return bundle.zip_bytes({
            "manifest.json": json.dumps(manifest).encode(),
            "agent.zip": code if code is not None else files["agent.zip"],
        })

    def created_record(self):
        previous = sys.path[:]
        try:
            sys.path.insert(0, str(bundle.HERE.parent / "workbench"))
            from agent_package import runtime_package
            code, runtime_hash = runtime_package()
        finally:
            sys.path[:] = previous
        record = {
            "status": "ready", "runtime_name": "lab-demo-source",
            "template_id": "document-analyst", "model": "source-model",
            "instructions": "Summarize only the fictional supplied document.",
            "runtime_hash": runtime_hash, "operator_key": "must-not-be-exported",
            "project": "must-not-be-exported", "events": ["must-not-be-exported"],
        }
        path = self.directory / "created.json"
        path.write_text(json.dumps(record))
        return record, path, code

    def test_all_prebuilt_samples_round_trip_deterministically_without_sdk(self):
        for sample in bundle.SAMPLES:
            with self.subTest(sample=sample):
                first = bundle.export_sample(sample)
                self.assertEqual(first, bundle.export_sample(sample))
                self.path.write_bytes(first)
                manifest, code, digest = bundle.read_bundle(self.path)
                self.assertEqual(manifest["name"], sample)
                self.assertEqual(manifest["code_sha256"], bundle.digest(code))
                self.assertEqual(digest, bundle.digest(first))
                self.assertIn("requirements.txt", manifest["files"])
                self.assertNotIn("deploy.py", manifest["files"])
                self.assertNotIn("FOUNDRY_PROJECT_ENDPOINT", manifest["environment"])
                instructions = bundle.HERE / sample / "instructions.md"
                if instructions.is_file():
                    self.assertEqual(manifest["instructions"], instructions.read_text(encoding="utf-8"))
                    self.assertEqual(bundle.zip_contents(code)["instructions.md"], instructions.read_bytes())

    def test_profiles_and_instruction_overrides_are_preserved(self):
        profile = bundle.HERE / "review-coordinator-agent" / "profiles" / "evidence-review.example.json"
        manifest, _, _ = self.write_bundle("review-coordinator-agent", profile_path=profile)
        self.assertEqual(manifest["name"], "customer-review-coordinator")
        self.assertEqual({check[1] for check in manifest["delegation_checks"]}, {"inspect_application", "inspect_case"})
        instructions = self.directory / "instructions.txt"
        instructions.write_text("Use this reviewed fictional instruction override.")
        manifest, _, _ = self.write_bundle(instructions_path=instructions, model="source-model", cpu="1", memory="2Gi")
        self.assertEqual(manifest["instructions"], instructions.read_text())
        self.assertEqual(manifest["model"], "source-model")
        self.assertEqual(manifest["memory"], "2Gi")
        with self.assertRaises(ValueError):
            bundle.export_sample("case-review-agent", profile)
        with self.assertRaises(ValueError):
            bundle.export_sample("review-coordinator-agent", profile, instructions)

    def test_created_export_uses_exact_runtime_and_only_portable_record_fields(self):
        record, path, original = self.created_record()
        self.path.write_bytes(bundle.export_created(path))
        manifest, code, _ = bundle.read_bundle(self.path)
        self.assertEqual(code, original)
        self.assertEqual(manifest["code_sha256"], record["runtime_hash"])
        self.assertEqual(manifest["environment"], {"DEMO_TEMPLATE_ID": "document-analyst"})
        self.assertEqual(manifest["instructions"], record["instructions"])
        self.assertEqual(manifest["smoke_test_prompt"], "")
        self.assertNotIn("must-not-be-exported", json.dumps(manifest))
        self.assertEqual(set(bundle.zip_contents(code)), {"main.py", "demo_tools.py", "requirements.txt"})

    def test_created_export_requires_ready_record_and_matching_runtime(self):
        record, path, _ = self.created_record()
        for change in ({"status": "interrupted"}, {"runtime_hash": "a" * 64}, {"runtime_hash": None}):
            with self.subTest(change=change):
                path.write_text(json.dumps({**record, **change}))
                with self.assertRaises(ValueError):
                    bundle.export_created(path)
        record.pop("runtime_hash")
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, "refresh"):
            bundle.export_created(path)

    def test_created_export_can_use_a_matching_archived_source_directory(self):
        _, path, code = self.created_record()
        runtime = self.directory / "runtime"
        runtime.mkdir()
        for name, content in bundle.zip_contents(code).items():
            (runtime / name).write_bytes(content)
        original = bundle.export_created(path, runtime)
        (runtime / "main.py").write_text("print('different runtime')")
        with self.assertRaisesRegex(ValueError, "Runtime changed"):
            bundle.export_created(path, runtime)
        self.assertGreater(len(original), 0)

    def test_corrupt_hashes_unknown_fields_and_environments_are_rejected(self):
        original = bundle.export_sample("case-review-agent")
        for changes in (
            {"schema_version": True}, {"schema_version": 2}, {"unknown": "field"},
            {"environment": {"AZURE_CLIENT_SECRET": "not-exportable"}},
            {"code_sha256": "a" * 64}, {"files": {}}, {"memory": "4Gi"},
            {"name": "../escape"}, {"runtime": "python_arbitrary"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.path.write_bytes(self.rewrite(original, manifest_changes=changes))
                bundle.read_bundle(self.path)
        self.path.write_bytes(self.rewrite(original, code=b"modified"))
        with self.assertRaisesRegex(ValueError, "hash"):
            bundle.read_bundle(self.path)

    def test_unexpected_source_file_is_rejected_even_with_matching_hashes(self):
        manifest, code, _ = self.write_bundle()
        files = bundle.zip_contents(code)
        files[".env"] = b"not allowed"
        code = bundle.zip_bytes(files)
        manifest.update(code_sha256=bundle.digest(code), files={name: bundle.digest(data) for name, data in files.items()})
        with self.assertRaisesRegex(ValueError, "unsupported files"):
            bundle.validate_manifest(manifest, code)

    def test_traversal_symlinks_duplicate_entries_and_oversized_sources_are_rejected(self):
        for name, mode in (("../main.py", stat.S_IFREG), ("folder\\main.py", stat.S_IFREG), ("main.py", stat.S_IFLNK)):
            output = io.BytesIO()
            with ZipFile(output, "w") as archive:
                info = ZipInfo(name)
                info.external_attr = (mode | 0o644) << 16
                archive.writestr(info, "data")
            with self.subTest(name=name), self.assertRaises(ValueError):
                bundle.zip_contents(output.getvalue())
        output = io.BytesIO()
        with ZipFile(output, "w") as archive, self.assertWarns(UserWarning):
            archive.writestr("same.py", "a")
            archive.writestr("same.py", "b")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            bundle.zip_contents(output.getvalue())
        with self.assertRaisesRegex(ValueError, "size"):
            bundle.zip_contents(bundle.zip_bytes({"large.py": b"x" * (bundle.MAX_FILE_BYTES + 1)}))
        with self.assertRaisesRegex(ValueError, "Duplicate JSON"):
            bundle.read_json('{"schema_version":1,"schema_version":2}')

    def test_large_runtime_archive_round_trips_with_bounded_source_files(self):
        random_bytes = random.Random(0)
        sources = {
            name: random_bytes.randbytes(bundle.MAX_FILE_BYTES)
            for name in ("main.py", "requirements.txt")
        }
        code = bundle.zip_bytes(sources)
        self.assertGreater(len(code), bundle.MAX_FILE_BYTES)
        profile = bundle.AgentProfile(self.directory, "large-agent", "Large source fixture", "Review evidence.", "")
        self.path.write_bytes(bundle.make_bundle(profile, code))
        manifest, restored, _ = bundle.read_bundle(self.path)
        self.assertEqual(restored, code)
        self.assertEqual(manifest["files"], {name: bundle.digest(data) for name, data in sources.items()})

    def test_export_rejects_outer_expansion_over_budget_before_writing(self):
        profile = bundle.AgentProfile(self.directory, "agent", "Size fixture", "x" * 2000, "")
        code = bundle.zip_bytes({"main.py": b"pass", "requirements.txt": b""})
        with patch.object(bundle, "MAX_BYTES", 1024), self.assertRaisesRegex(ValueError, "Expanded archive"):
            bundle.make_bundle(profile, code)

    def test_remapping_updates_runtime_bindings_and_all_checks(self):
        manifest, code, _ = self.write_bundle("review-coordinator-agent")
        profile = bundle.deployment_profile(
            manifest, code, "destination-coordinator",
            ["application-review-agent=destination-application", "case-review-agent=destination-case"],
        )
        specialists = json.loads(dict(profile.environment_variables)["SPECIALIST_CONFIG"])
        self.assertEqual({item["agent"] for item in specialists}, {"destination-application", "destination-case"})
        self.assertEqual({check[2] for check in profile.delegation_checks}, {"destination-application", "destination-case"})
        self.assertEqual(profile.code_archive, code)
        self.assertEqual(manifest["name"], "review-coordinator-agent")
        for mappings in (
            ["unknown=destination"], ["case-review-agent=destination-coordinator"],
            ["case-review-agent=a", "case-review-agent=b"], ["case-review-agent=../invalid"],
        ):
            with self.subTest(mappings=mappings), self.assertRaises(ValueError):
                bundle.deployment_profile(manifest, code, "destination-coordinator", mappings)

    def test_cli_export_refuses_overwrite_and_inspect_omits_prompt_content(self):
        with redirect_stdout(io.StringIO()):
            bundle.main(["export", "--sample", "case-review-agent", "--output", str(self.path)])
        before = self.path.read_bytes()
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            bundle.main(["export", "--sample", "basic-responses-agent", "--output", str(self.path)])
        self.assertEqual(raised.exception.code, 1)
        self.assertEqual(self.path.read_bytes(), before)
        output = io.StringIO()
        with redirect_stdout(output), patch.object(bundle, "deploy") as deploy:
            bundle.main(["inspect", str(self.path)])
        deploy.assert_not_called()
        self.assertNotIn("instructions", json.loads(output.getvalue()))

    def test_deploy_requires_explicit_destination_and_passes_validated_archive(self):
        manifest, code, _ = self.write_bundle()
        with patch.object(bundle, "deploy") as publish:
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                bundle.main(["deploy", str(self.path)])
            publish.assert_not_called()
            bundle.main([
                "deploy", str(self.path), "--endpoint", "https://target.services.ai.azure.com/api/projects/demo",
                "--model", "destination-model", "--agent-name", "destination-case",
            ])
        profile, options = publish.call_args.args
        self.assertEqual(profile.code_archive, code)
        self.assertEqual(options.model, "destination-model")
        self.assertEqual(options.agent_name, "destination-case")
        self.assertEqual(options.instructions, manifest["instructions"])

    def test_invalid_destination_never_calls_deployer(self):
        self.write_bundle()
        for endpoint in (
            "http://target.services.ai.azure.com/api/projects/demo",
            "https://user:password@target.services.ai.azure.com/api/projects/demo",
            "https://target.services.ai.azure.com/api/projects/demo?token=not-allowed",
        ):
            with self.subTest(endpoint=endpoint), patch.object(bundle, "deploy") as publish:
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    bundle.main(["deploy", str(self.path), "--endpoint", endpoint, "--model", "model", "--agent-name", "agent"])
                publish.assert_not_called()

    def test_created_bundle_deploys_without_lab_ownership_or_hidden_model_calls(self):
        _, record, _ = self.created_record()
        self.path.write_bytes(bundle.export_created(record))
        with patch.object(bundle, "deploy") as publish:
            bundle.main([
                "deploy", str(self.path), "--endpoint", "https://target.services.ai.azure.com/api/projects/demo",
                "--model", "new-model", "--agent-name", "independent-demo",
            ])
        profile, options = publish.call_args.args
        self.assertEqual(options.smoke_test_prompt, "")
        self.assertEqual(options.model, "new-model")
        self.assertEqual(profile.name, "independent-demo")
        self.assertEqual(dict(profile.environment_variables), {"DEMO_TEMPLATE_ID": "document-analyst"})


if __name__ == "__main__":
    unittest.main()
