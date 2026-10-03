import unittest

import agent_creation
import agent_scorecards
import library_rules as rules
from agent_templates import MODEL_PROFILES


class IntegerTests(unittest.TestCase):
    def test_a_boolean_is_not_an_integer(self):
        for value in (True, False):
            with self.subTest(value=value):
                self.assertFalse(rules.is_int(value))
                self.assertFalse(rules.is_number(value))

    def test_whole_numbers_and_floats(self):
        for value in (0, 1, -3, 10**12):
            self.assertTrue(rules.is_int(value), value)
            self.assertTrue(rules.is_number(value), value)
        for value in (0.0, 2.5):
            self.assertFalse(rules.is_int(value), value)
            self.assertTrue(rules.is_number(value), value)

    def test_text_and_missing_values_are_neither(self):
        for value in ("1", "1.5", None, [], {}, b"1"):
            with self.subTest(value=value):
                self.assertFalse(rules.is_int(value))
                self.assertFalse(rules.is_number(value))


class DateTests(unittest.TestCase):
    def test_a_real_calendar_date_in_the_exact_form(self):
        for value in ("2026-09-29", "2024-02-29", "2000-01-01"):
            self.assertTrue(rules.valid_date(value), value)

    def test_other_forms_and_impossible_dates_are_refused(self):
        for value in (None, "", "soon", "29/09/2026", "2026-9-29", "2026-02-30", "2026-02-29", "20260929",
                      "2026-09-29T10:00:00", " 2026-09-29", 20260929):
            with self.subTest(value=value):
                self.assertFalse(rules.valid_date(value))


class DeploymentNameTests(unittest.TestCase):
    def test_names_the_lab_accepts(self):
        for name in ("gpt-5.4", "gpt_4o", "A", "0abc", "a" * 128):
            with self.subTest(name=name):
                self.assertIsNotNone(rules.DEPLOYMENT_NAME.fullmatch(name))

    def test_names_it_refuses(self):
        for name in ("", "-gpt", ".gpt", "_gpt", "gpt 5", "gpt/5", "gpt\n", "a" * 129, "gpt-5.4;"):
            with self.subTest(name=name):
                self.assertIsNone(rules.DEPLOYMENT_NAME.fullmatch(name))


class ProfileMapTests(unittest.TestCase):
    PROFILES = ("reasoning", "chat")

    def test_an_empty_map_and_known_profiles_pass(self):
        self.assertTrue(rules.is_profile_map({}, self.PROFILES))
        self.assertTrue(rules.is_profile_map({"reasoning": "gpt-5.4", "chat": "gpt-4o"}, self.PROFILES))

    def test_an_unknown_profile_is_refused(self):
        self.assertFalse(rules.is_profile_map({"fast": "gpt-5.4"}, self.PROFILES))

    def test_a_bad_deployment_name_is_refused(self):
        for name in ("", "bad name", "-x", None, 5, True, ["gpt-5.4"]):
            with self.subTest(name=name):
                self.assertFalse(rules.is_profile_map({"reasoning": name}, self.PROFILES))

    def test_something_other_than_a_map_is_refused(self):
        for value in (None, [], "reasoning", 5, [("reasoning", "gpt-5.4")]):
            with self.subTest(value=value):
                self.assertFalse(rules.is_profile_map(value, self.PROFILES))


class LabUsesTheSharedRulesTests(unittest.TestCase):
    """evaluations/test_shared_rules.py holds the same cases for the offline tools."""

    def test_the_lab_uses_one_copy_of_each_rule(self):
        self.assertIs(agent_creation.DEPLOYMENT_NAME, rules.DEPLOYMENT_NAME)
        self.assertIs(agent_scorecards.CATEGORIES, rules.CATEGORIES)

    def test_creation_settings_accept_and_refuse_the_profile_maps_the_recorder_does(self):
        profile = next(iter(MODEL_PROFILES))
        cases = {
            "good": ({profile: "gpt-5.4"}, True),
            "empty": ({}, True),
            "bad name": ({profile: "bad name"}, False),
            "unknown profile": ({"nonsense": "gpt-5.4"}, False),
            "boolean name": ({profile: True}, False),
            "number name": ({profile: 5}, False),
        }
        for label, (models, accepted) in cases.items():
            with self.subTest(case=label):
                settings = agent_creation.CreationSettings(models=models)
                if accepted:
                    settings.validate("preview")
                else:
                    with self.assertRaises(ValueError):
                        settings.validate("preview")

    def test_a_boolean_is_still_not_a_count(self):
        for field in ("max_agents", "timeout_seconds"):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    agent_creation.CreationSettings(**{field: True}).validate("preview")


class CategoryTests(unittest.TestCase):
    def test_the_five_categories(self):
        self.assertEqual(
            rules.CATEGORIES, {"grounded", "missing", "conflict", "injection", "decision-boundary"})

    def test_it_cannot_be_changed_by_a_consumer(self):
        self.assertIsInstance(rules.CATEGORIES, frozenset)


if __name__ == "__main__":
    unittest.main()