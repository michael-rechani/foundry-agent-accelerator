import unittest

from agent_templates import TEMPLATES, TemplateRequiredError, list_templates, prepare_draft
from agent_runtime.demo_tools import TEMPLATE_IDS, create_demo_tools


class TemplateTests(unittest.TestCase):
    def test_all_five_jobs_have_complete_bounded_guidance_and_examples(self):
        self.assertEqual(set(TEMPLATES), TEMPLATE_IDS)
        self.assertEqual(len(TEMPLATES), 5)
        fields = {"id", "label", "description", "input", "output", "limits", "delegation",
                  "instructions", "example_request", "sample_input", "tools"}
        for identifier, template in TEMPLATES.items():
            with self.subTest(identifier=identifier):
                self.assertEqual(set(template), fields)
                self.assertEqual(template["id"], identifier)
                for key in fields - {"tools"}:
                    self.assertIsInstance(template[key], str)
                    self.assertTrue(template[key].strip())
                self.assertLessEqual(len(template["instructions"]), 6000)
                self.assertLessEqual(len(template["sample_input"]), 4000)
                self.assertIn("fictional", (template["sample_input"] + template["example_request"]).lower())
                self.assertEqual(
                    [tool["name"] for tool in template["tools"]],
                    [tool.__name__ for tool in create_demo_tools(identifier, "test-demo-agent")],
                )

    def test_public_metadata_is_an_independent_copy(self):
        data = list_templates()
        data[0]["label"] = "Mutated"
        data[-1]["tools"].clear()
        self.assertNotEqual(TEMPLATES["document-analyst"]["label"], "Mutated")
        self.assertEqual(len(TEMPLATES["workflow-coordinator"]["tools"]), 2)

    def test_examples_match_only_their_own_template(self):
        for identifier, template in TEMPLATES.items():
            with self.subTest(identifier=identifier):
                result = prepare_draft(template["example_request"])
                self.assertEqual(result["template_id"], identifier)
                self.assertEqual(result["source"], "template")
                self.assertIn(template["example_request"], result["instructions"])

    def test_ambiguous_and_unmatched_input_ask_instead_of_guessing(self):
        for goal in ("Help me with this general review.", "Analyze policy and extract invoice fields."):
            with self.subTest(goal=goal), self.assertRaises(TemplateRequiredError) as error:
                prepare_draft(goal)
            if "invoice" in goal:
                self.assertEqual(error.exception.candidates, ["document-analyst", "document-intake"])
            else:
                self.assertEqual(error.exception.candidates, [])

    def test_explicit_choice_allows_task_wording_without_matching_keywords(self):
        result = prepare_draft("Help me with this general review.", "casework-assistant")
        self.assertEqual(result["template_id"], "casework-assistant")
        self.assertIn("Task described by the user:", result["instructions"])

    def test_goal_bounds_and_invalid_template_fail_explicitly(self):
        for goal in ("short", " " * 10, "x" * 1201, "valid description\x00", None, 123):
            with self.subTest(goal=goal), self.assertRaises(ValueError):
                prepare_draft(goal, "document-analyst")
        for identifier in ("", "unknown", [], 7):
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                prepare_draft("A valid task description.", identifier)
        result = prepare_draft("\U0001f600" * 1200, "document-analyst")
        self.assertEqual(len(result["goal"]), 1200)
        self.assertLessEqual(len(result["instructions"]), 6000)

    def test_only_workflow_has_tools_and_they_are_simulated(self):
        for identifier, template in TEMPLATES.items():
            with self.subTest(identifier=identifier):
                self.assertEqual(len(template["tools"]), 2 if identifier == "workflow-coordinator" else 0)
                self.assertTrue(all(tool["simulated"] for tool in template["tools"]))
        self.assertIn("EXPERIMENTAL", TEMPLATES["criteria-checker"]["limits"])


if __name__ == "__main__":
    unittest.main()
