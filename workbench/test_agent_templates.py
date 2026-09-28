import unittest
from pathlib import Path

from agent_templates import (
    INDUSTRIES,
    MODEL_PROFILES,
    READINESS_LEVELS,
    SECTORS,
    TASKS,
    TEMPLATES,
    TEMPLATE_METADATA,
    TOOL_MODES,
    TemplateRequiredError,
    catalog_facets,
    list_templates,
    prepare_draft,
)
from agent_runtime.demo_tools import TEMPLATE_IDS, create_demo_tools


LOOKUP_JOBS = {
    "workflow-coordinator",
    "medical-bill-reviewer",
    "insurance-preapproval-helper",
    "benefits-renewal-helper",
    "supplier-invoice-reviewer",
    "expense-report-checker",
    "order-delay-helper",
}
SECTOR_JOBS = {
    "medical-bill-reviewer",
    "insurance-preapproval-helper",
    "benefits-renewal-helper",
    "supplier-invoice-reviewer",
}
PREVIEW_JOBS = {
    "contract-playbook-checker": ("legal advice", "legal counsel"),
    "rfp-answer-drafter": ("invent capabilities", "subject-matter experts"),
    "expense-report-checker": ("never approve", "finance approver"),
    "incident-timeline-writer": ("declare a root cause", "incident commander"),
    "customer-feedback-themes": ("decide product priorities", "product owners"),
    "order-delay-helper": ("never issue or promise a refund", "customer service staff"),
}


class TemplateTests(unittest.TestCase):
    def test_supplier_showcase_input_matches_the_reviewed_template(self):
        sample = (
            Path(__file__).resolve().parents[1]
            / "docs"
            / "demo-inputs"
            / "supplier-invoice.txt"
        )
        self.assertEqual(
            sample.read_text(encoding="utf-8").strip(),
            TEMPLATES["supplier-invoice-reviewer"]["sample_input"],
        )

    def test_all_jobs_have_complete_bounded_guidance_and_examples(self):
        self.assertEqual(set(TEMPLATES), TEMPLATE_IDS)
        self.assertEqual(len(TEMPLATES), 21)
        fields = {
            "id",
            "category",
            "label",
            "description",
            "input",
            "output",
            "limits",
            "delegation",
            "instructions",
            "example_request",
            "sample_input",
            "tools",
            "model_profile",
        }
        for identifier, template in TEMPLATES.items():
            with self.subTest(identifier=identifier):
                self.assertEqual(set(template), fields)
                self.assertEqual(template["id"], identifier)
                for key in fields - {"tools"}:
                    self.assertIsInstance(template[key], str)
                    self.assertTrue(template[key].strip())
                self.assertLessEqual(len(template["instructions"]), 6000)
                self.assertLessEqual(len(template["sample_input"]), 4000)
                self.assertIn(
                    "fictional",
                    (template["sample_input"] + template["example_request"]).lower(),
                )
                self.assertEqual(
                    [tool["name"] for tool in template["tools"]],
                    [
                        tool.__name__
                        for tool in create_demo_tools(identifier, "test-demo-agent")
                    ],
                )

    def test_jobs_are_grouped_so_each_category_is_listed_together(self):
        categories = [template["category"] for template in list_templates()]
        self.assertEqual(
            categories,
            ["General"] * 5
            + ["Healthcare and public sector"] * 7
            + ["Private sector"] * 9,
        )
        self.assertEqual(
            {key for key, item in TEMPLATES.items() if item["category"] == "Healthcare and public sector"},
            SECTOR_JOBS | {"public-records-intake", "grant-reporting-checker", "community-program-brief"},
        )

    def test_each_job_names_the_kind_of_model_it_needs(self):
        expected = {
            "document-analyst": "reasoning",
            "criteria-checker": "reasoning",
            "casework-assistant": "reasoning",
            "document-intake": "extraction",
            "workflow-coordinator": "tool_calling",
            "medical-bill-reviewer": "reasoning",
            "insurance-preapproval-helper": "tool_calling",
            "benefits-renewal-helper": "reasoning",
            "supplier-invoice-reviewer": "reasoning",
            "public-records-intake": "extraction",
            "grant-reporting-checker": "reasoning",
            "community-program-brief": "reasoning",
            "customer-support-brief": "reasoning",
            "cash-application-reviewer": "extraction",
            "maintenance-work-order-planner": "reasoning",
            "contract-playbook-checker": "reasoning",
            "rfp-answer-drafter": "reasoning",
            "expense-report-checker": "tool_calling",
            "incident-timeline-writer": "reasoning",
            "customer-feedback-themes": "reasoning",
            "order-delay-helper": "tool_calling",
        }
        self.assertEqual(
            {key: template["model_profile"] for key, template in TEMPLATES.items()},
            expected,
        )
        self.assertEqual(set(expected.values()), set(MODEL_PROFILES))
        for profile in MODEL_PROFILES.values():
            self.assertEqual(set(profile), {"label", "reason"})
            self.assertTrue(
                all(isinstance(text, str) and text.strip() for text in profile.values())
            )
        for template in list_templates():
            with self.subTest(identifier=template["id"]):
                profile = template["model_profile"]
                self.assertEqual(
                    profile,
                    {"id": expected[template["id"]], **MODEL_PROFILES[profile["id"]]},
                )
        list_templates()[0]["model_profile"]["label"] = "Mutated"
        self.assertEqual(MODEL_PROFILES["reasoning"]["label"], "Reasoning")

    def test_public_metadata_is_an_independent_copy(self):
        data = list_templates()
        data[0]["label"] = "Mutated"
        data[-1]["tasks"].clear()
        supplier = next(item for item in data if item["id"] == "supplier-invoice-reviewer")
        supplier["tools"].clear()
        self.assertNotEqual(TEMPLATES["document-analyst"]["label"], "Mutated")
        self.assertTrue(TEMPLATE_METADATA[data[-1]["id"]]["tasks"])
        self.assertEqual(len(TEMPLATES["supplier-invoice-reviewer"]["tools"]), 2)

    def test_catalog_metadata_uses_closed_taxonomy_and_complete_display_fields(self):
        sector_ids = {item["id"] for item in SECTORS}
        industry_ids = {item["id"] for item in INDUSTRIES}
        task_ids = {item["id"] for item in TASKS}
        readiness_ids = {item["id"] for item in READINESS_LEVELS}
        tool_mode_ids = {item["id"] for item in TOOL_MODES}
        templates = list_templates()
        self.assertEqual(len({item["id"] for item in templates}), len(templates))
        self.assertEqual(set(TEMPLATE_METADATA), set(TEMPLATES))
        for template in templates:
            with self.subTest(identifier=template["id"]):
                self.assertIn(template["sector"]["id"], sector_ids)
                self.assertIn(template["industry"]["id"], industry_ids)
                self.assertTrue(template["tasks"])
                self.assertTrue({item["id"] for item in template["tasks"]} <= task_ids)
                self.assertIn(template["readiness"]["id"], readiness_ids)
                self.assertIn(template["tool_mode"]["id"], tool_mode_ids)
                self.assertLessEqual(len(template["summary"]), 140)
                for key in ("summary", "expected_behavior", "human_decision"):
                    self.assertIsInstance(template[key], str)
                    self.assertTrue(template[key].strip())
                self.assertIsInstance(template["keywords"], list)
                self.assertTrue(all(isinstance(value, str) and value.strip() for value in template["keywords"]))
                export = template["export"]
                self.assertEqual(export["exportable"], export["availability"] == "after_creation")
                if template["tool_mode"]["id"] == "connected-required":
                    self.assertTrue(any("connection" in item.lower() for item in template["prerequisites"]))

    def test_facets_have_stable_order_and_counts_matching_templates(self):
        templates = list_templates()
        facets = catalog_facets()
        sources = {
            "sectors": (SECTORS, lambda item: [item["sector"]["id"]]),
            "industries": (INDUSTRIES, lambda item: [item["industry"]["id"]]),
            "tasks": (TASKS, lambda item: [task["id"] for task in item["tasks"]]),
            "readiness": (READINESS_LEVELS, lambda item: [item["readiness"]["id"]]),
            "tool_modes": (TOOL_MODES, lambda item: [item["tool_mode"]["id"]]),
        }
        for name, (definitions, identifiers) in sources.items():
            with self.subTest(facet=name):
                expected = [
                    {
                        **definition,
                        "count": sum(definition["id"] in identifiers(template) for template in templates),
                    }
                    for definition in definitions
                    if any(definition["id"] in identifiers(template) for template in templates)
                ]
                self.assertEqual(facets[name], expected)

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
            "Analyze policy and extract invoice fields.": [
                "document-analyst",
                "document-intake",
            ],
            "Check a supplier invoice for me.": [
                "document-intake",
                "supplier-invoice-reviewer",
            ],
        }
        for goal, candidates in expected.items():
            with (
                self.subTest(goal=goal),
                self.assertRaises(TemplateRequiredError) as error,
            ):
                prepare_draft(goal)
            self.assertEqual(error.exception.candidates, candidates)

    def test_everyday_wording_finds_the_new_jobs(self):
        expected = {
            "Find mistakes in my medical bill.": "medical-bill-reviewer",
            "Is this prior authorization packet ready to send?": "insurance-preapproval-helper",
            "Help a caseworker with a family's renewal paperwork.": "benefits-renewal-helper",
            "Compare our purchase order with what was delivered.": "supplier-invoice-reviewer",
            "Find overcharges on my hospital statement.": "medical-bill-reviewer",
            "Help families renew their food assistance.": "benefits-renewal-helper",
            "Compare this contract with our clause playbook.": "contract-playbook-checker",
            "Draft answers to this security questionnaire.": "rfp-answer-drafter",
            "Check my expense report before I submit it.": "expense-report-checker",
            "Write a timeline for last night's outage.": "incident-timeline-writer",
            "Group our survey feedback into themes.": "customer-feedback-themes",
            "Where is my late order?": "order-delay-helper",
        }
        for goal, identifier in expected.items():
            with self.subTest(goal=goal):
                self.assertEqual(prepare_draft(goal)["template_id"], identifier)

    def test_trigger_words_outside_their_field_ask_instead_of_guessing(self):
        for goal in (
            "Help staff review business-license renewal paperwork.",
            "Find overcharges on my electricity statement.",
            "Check whether this mortgage pre-approval has the right paperwork.",
            "Check our car insurance pre-approval.",
            "Summarize supplier correspondence and draft follow-up questions.",
        ):
            with (
                self.subTest(goal=goal),
                self.assertRaises(TemplateRequiredError) as error,
            ):
                prepare_draft(goal)
            self.assertEqual(error.exception.candidates, [])

    def test_explicit_choice_allows_task_wording_without_matching_keywords(self):
        result = prepare_draft(
            "Help me with this general review.", "casework-assistant"
        )
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
                self.assertEqual(
                    len(template["tools"]), 2 if identifier in LOOKUP_JOBS else 0
                )
                self.assertTrue(all(tool["simulated"] for tool in template["tools"]))
                for tool in template["tools"]:
                    if identifier in SECTOR_JOBS or identifier in PREVIEW_JOBS:
                        self.assertIn(tool["name"], template["instructions"])
                    self.assertTrue(
                        tool["description"].endswith("no external call or update.")
                    )
        self.assertIn("in preview", TEMPLATES["criteria-checker"]["limits"])

    def test_healthcare_and_public_sector_jobs_keep_a_person_in_charge(self):
        for identifier in SECTOR_JOBS:
            template = TEMPLATES[identifier]
            with self.subTest(identifier=identifier):
                self.assertIn("UNSENT DRAFT", template["instructions"])
                self.assertIn("simulated lookups", template["instructions"])
                self.assertRegex(
                    template["instructions"],
                    r"(?i)\b(never|do not) (judge|decide|approve)",
                )
                self.assertIn("made up", template["sample_input"])

    def test_new_library_jobs_preserve_their_human_decision_boundary(self):
        expected = {
            "public-records-intake": ("release", "records officer"),
            "grant-reporting-checker": ("certify compliance", "grant officer"),
            "community-program-brief": ("allocate funding", "program staff"),
            "customer-support-brief": ("issue credits", "support staff"),
            "cash-application-reviewer": ("post cash", "finance staff"),
            "maintenance-work-order-planner": ("diagnose equipment", "qualified staff"),
        }
        public = {item["id"]: item for item in list_templates()}
        for identifier, (prohibited_action, owner) in expected.items():
            with self.subTest(identifier=identifier):
                template = TEMPLATES[identifier]
                self.assertIn(prohibited_action, template["instructions"].lower())
                self.assertIn(owner, public[identifier]["human_decision"].lower())
                self.assertIn("fictional", template["sample_input"].lower())
                self.assertEqual(template["tools"], [])

    def test_private_preview_jobs_are_previews_that_keep_a_person_in_charge(self):
        public = {item["id"]: item for item in list_templates()}
        for identifier, (prohibited, owner) in PREVIEW_JOBS.items():
            with self.subTest(identifier=identifier):
                template = TEMPLATES[identifier]
                self.assertEqual(template["category"], "Private sector")
                self.assertEqual(public[identifier]["sector"]["id"], "private")
                self.assertEqual(public[identifier]["readiness"], {"id": "sample", **{
                    key: value for key, value in READINESS_LEVELS[1].items() if key != "id"}})
                self.assertEqual(public[identifier]["readiness"]["label"], "In progress")
                self.assertIn(prohibited, template["instructions"].lower())
                self.assertIn(owner, public[identifier]["human_decision"].lower())
                self.assertIn("made up", template["sample_input"])
                if identifier != "customer-feedback-themes":
                    self.assertRegex(template["instructions"], r"UNSENT DRAFT|SUGGESTION FOR COUNSEL REVIEW")

if __name__ == "__main__":
    unittest.main()
