"""Offline tests for optimizer_dataset.py. Nothing here calls Azure, a model or the optimizer."""
import json
import unittest
from pathlib import Path

import optimizer_dataset as od
from library_checks import load_cases

HOSTED = Path(__file__).resolve().parents[1] / "hosted-agents"


class OptimizerDatasetTests(unittest.TestCase):
    def test_every_agent_maps_to_templates_that_have_cases(self):
        known = {case["template_id"] for case in load_cases()["cases"]}
        for agent, templates in od.AGENT_TEMPLATES.items():
            with self.subTest(agent=agent):
                self.assertTrue((HOSTED / agent / "instructions.md").is_file())
                self.assertLessEqual(set(templates), known)

    def test_tasks_follow_the_optimizer_schema(self):
        for agent, templates in od.AGENT_TEMPLATES.items():
            rows = od.tasks(templates)
            with self.subTest(agent=agent):
                self.assertEqual(len(rows), 5 * len(templates))
                self.assertEqual(len({row["name"] for row in rows}), len(rows))
                for row in rows:
                    self.assertEqual(set(row), {"name", "query", "criteria"})
                    self.assertTrue(row["query"].strip())
                    self.assertEqual([c["name"] for c in row["criteria"]], ["rubric"])
                    self.assertTrue(row["criteria"][0]["instruction"].strip())

    def test_sample_input_cases_use_the_catalog_sample(self):
        rows = {row["name"]: row for row in od.tasks(("casework-assistant",))}
        self.assertIn("Note 1", rows["casework-assistant-sample"]["query"])

    def test_unknown_templates_are_an_error(self):
        with self.assertRaises(ValueError):
            od.tasks(("no-such-template",))

    def test_eval_yaml_has_the_fields_the_optimizer_requires(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML is not installed")

        data = yaml.safe_load(od.eval_yaml("agent-x", model="m", eval_model="e", optimization_model="o", max_candidates=3))
        self.assertEqual(data["agent"], {"name": "agent-x", "kind": "hosted", "model": "m"})
        self.assertEqual(data["dataset"], {"local_uri": "./eval.jsonl"})
        self.assertEqual(data["evaluators"], ["builtin.task_adherence"])
        self.assertEqual(data["options"], {"eval_model": "e", "optimization_model": "o", "max_candidates": 3})

    def test_committed_files_match_the_cases_and_instructions(self):
        for agent in od.AGENT_TEMPLATES:
            with self.subTest(agent=agent):
                files = od.render(agent)
                self.assertEqual(od.stale(agent, files), [], "Run python evaluations/optimizer_dataset.py")

    def test_committed_dataset_is_valid_jsonl(self):
        for agent in od.AGENT_TEMPLATES:
            lines = (HOSTED / agent / "eval.jsonl").read_text(encoding="utf-8").splitlines()
            with self.subTest(agent=agent):
                self.assertTrue(lines)
                for line in lines:
                    self.assertIn("query", json.loads(line))

    def test_baseline_is_loadable_by_the_optimizer_package_when_installed(self):
        try:
            from azure.ai.agentserver.optimization import load_config
        except ImportError:
            self.skipTest("azure-ai-agentserver-optimization is not installed")
        for agent in od.AGENT_TEMPLATES:
            with self.subTest(agent=agent):
                config = load_config(config_dir=HOSTED / agent / ".agent_configs")
                self.assertEqual(config.instructions, (HOSTED / agent / "instructions.md").read_text(encoding="utf-8").strip())
                self.assertEqual(config.model, od.DEFAULT_MODEL)

    def test_check_flags_a_stale_file_and_write_clears_it(self):
        files = od.render("case-review-agent")
        files["eval.yaml"] += "# edited\n"
        self.assertEqual(od.stale("case-review-agent", files), ["eval.yaml"])


if __name__ == "__main__":
    unittest.main()
