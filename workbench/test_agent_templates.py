import unittest

from agent_templates import MODEL_PROFILES, TEMPLATES, TemplateRequiredError, list_templates, prepare_draft
from agent_runtime.demo_tools import TEMPLATE_IDS, create_demo_tools


LOOKUP_JOBS = {
    "workflow-coordinator", "medical-bill-reviewer", "insurance-preapproval-helper",
    "benefits-renewal-helper", "supplier-invoice-reviewer",
}
SECTOR_JOBS = LOOKUP_JOBS - {"workflow-coordinator"}


class TemplateTests(unittest.TestCase):
    def test_all_nine_jobs_have_complete_bounded_guidance_and_examples(self):
        self.assertEqual(set(TEMPLATES), TEMPLATE_IDS)
        self.assertEqual(len(TEMPLATES), 9)
        fields = {"id", "category", "label", "description", "input", "output", "limits", "delegation",
                  "instructions", "example_request", "sample_input", "tools", "model_profile"}
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

    def test_jobs_are_grouped_so_each_category_is_listed_together(self):
        categories = [template["category"] for template in list_templates()]
        self.assertEqual(categories, ["General"] * 5 + ["Healthcare and public sector"] * 4)
        self.assertEqual({key for key, item in TEMPLATES.items() if item["category"] != "General"}, SECTOR_JOBS)

    def test_each_job_names_the_kind_of_model_it_needs(self):
        expected = {
            "document-analyst": "reasoning", "criteria-checker": "reasoning", "casework-assistant": "reasoning",
            "document-intake": "extraction", "workflow-coordinator": "tool_calling",
            "medical-bill-reviewer": "reasoning", "insurance-preapproval-helper": "tool_calling",
            "benefits-renewal-helper": "reasoning", "supplier-invoice-reviewer": "reasoning",
        }
        self.assertEqual({key: template["model_profile"] for key, template in TEMPLATES.items()}, expected)
        self.assertEqual(set(expected.values()), set(MODEL_PROFILES))
        for profile in MODEL_PROFILES.values():
            self.assertEqual(set(profile), {"label", "reason"})
            self.assertTrue(all(isinstance(text, str) and text.strip() for text in profile.values()))
        for template in list_templates():
            with self.subTest(identifier=template["id"]):
                profile = template["model_profile"]
                self.assertEqual(profile, {"id": expected[template["id"]], **MODEL_PROFILES[profile["id"]]})
        list_templates()[0]["model_profile"]["label"] = "Mutated"
        self.assertEqual(MODEL_PROFILES["reasoning"]["label"], "Reasoning")

    def test_public_metadata_is_an_independent_copy(self):
        data = list_templates()
        data[0]["label"] = "Mutated"
        data[-1]["tools"].clear()
        self.assertNotEqual(TEMPLATES["document-analyst"]["label"], "Mutated")
        self.assertEqual(len(TEMPLATES[data[-1]["id"]]["tools"]), 2)

    def test_examples_match_only_their_own_template(self):
        for identifier, template in TEMPLATES.items():
            with self.subTest(identifier=identifier):
                result = prepare_draft(template["example_request"])
                self.assertEqual(result["template_id"], identifier)
                self.assertEqual(result["source"], "template")
                self.assertIn(template["example_request"], result["instructions"])

    def test_ambiguous_and_unmatched_input_ask_instead_of_guessing(self):
        expected = {
            "Help me with this general review.": [],
            "Analyze policy and extract invoice fields.": ["document-analyst", "document-intake"],
            "Check a supplier invoice for me.": ["document-intake", "supplier-invoice-reviewer"],
        }
        for goal, candidates in expected.items():
            with self.subTest(goal=goal), self.assertRaises(TemplateRequiredError) as error:
                prepare_draft(goal)
            self.assertEqual(error.exception.candidates, candidates)

    def test_everyday_wording_finds_the_new_jobs(self):
        expected = {
            "Find mistakes in my medical bill.": "medical-bill-reviewer",
            "Is this prior authorization packet ready to send?": "insurance-preapproval-helper",
            "Help a caseworker with a family's renewal paperwork.": "benefits-renewal-helper",
            "Compare our purchase order with what was delivered.": "supplier-invoice-reviewer",
        }
        for goal, identifier in expected.items():
            with self.subTest(goal=goal):
                self.assertEqual(prepare_draft(goal)["template_id"], identifier)

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

    def test_only_lookup_jobs_have_tools_and_they_are_simulated(self):
        for identifier, template in TEMPLATES.items():
            with self.subTest(identifier=identifier):
                self.assertEqual(len(template["tools"]), 2 if identifier in LOOKUP_JOBS else 0)
                self.assertTrue(all(tool["simulated"] for tool in template["tools"]))
                for tool in template["tools"]:
                    if identifier in SECTOR_JOBS:
                        self.assertIn(tool["name"], template["instructions"])
                    self.assertTrue(tool["description"].endswith("no external call or update."))
        self.assertIn("experimental", TEMPLATES["criteria-checker"]["limits"])

    def test_healthcare_and_public_sector_jobs_keep_a_person_in_charge(self):
        for identifier in SECTOR_JOBS:
            template = TEMPLATES[identifier]
            with self.subTest(identifier=identifier):
                self.assertIn("UNSENT DRAFT", template["instructions"])
                self.assertIn("simulated lookups", template["instructions"])
                self.assertRegex(template["instructions"], r"(?i)\b(never|do not) (judge|decide|approve)")
                self.assertIn("made up", template["sample_input"])


if __name__ == "__main__":
    unittest.main()
