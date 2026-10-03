"""Pins that the offline tools use the Lab's one copy of each shared rule, not a second that can drift.

workbench/test_library_rules.py holds the same cases for the Lab's side. The Lab's code can't be
imported here, because this job installs only the evaluation dependencies.
"""
import json
import unittest

import library_checks  # puts workbench/ on sys.path
import library_rules
import library_runs
import scorecards
import agent_scorecards

PROFILE = next(iter(library_runs.TEMPLATES.values()))["model_profile"]
TEMPLATE_ID = next(iter(library_runs.TEMPLATES))
# Each is a model map and whether the Lab and the recorder should both accept it.
PROFILE_MAPS = {
    "good": ({PROFILE: "gpt-5.4"}, True),
    "empty": ({}, True),
    "bad name": ({PROFILE: "bad name"}, False),
    "unknown profile": ({"nonsense": "gpt-5.4"}, False),
    "boolean name": ({PROFILE: True}, False),
    "number name": ({PROFILE: 5}, False),
}


class EvidenceRowTests(unittest.TestCase):
    def test_the_writer_and_the_reader_use_the_one_set_of_keys(self):
        self.assertIs(library_runs.ANSWER_ROW, library_rules.ANSWER_ROW)
        self.assertIs(library_runs.METRICS_ROW, library_rules.METRICS_ROW)
        self.assertIs(library_runs.RUN_ROW, library_rules.RUN_ROW)
        self.assertIs(library_runs.COUNT_KEYS, library_rules.COUNT_KEYS)
        self.assertIs(scorecards.METRIC_KEYS, library_rules.METRIC_KEYS)

    def test_the_keys_the_reader_measures_are_in_every_row_that_carries_a_run(self):
        self.assertTrue(set(library_rules.METRIC_KEYS) <= set(library_rules.METRICS_ROW))
        self.assertTrue(set(library_rules.METRIC_KEYS) <= set(library_rules.RUN_ROW))
        self.assertTrue(set(library_rules.COUNT_KEYS) <= set(library_rules.METRIC_KEYS))
        self.assertTrue({"recorded_on", "instructions_sha256", "case_id"} <= set(library_rules.ANSWER_ROW))

    def test_every_row_in_the_recorded_evidence_has_exactly_those_keys_in_that_order(self):
        for path, keys in ((scorecards.ANSWERS, library_rules.ANSWER_ROW), (scorecards.METRICS, library_rules.METRICS_ROW),
                           (scorecards.REPEATS, library_rules.RUN_ROW)):
            rows = scorecards._lines(path)
            self.assertTrue(rows, path.name)
            for row in rows:
                self.assertEqual(tuple(row), keys, f"{path.name}: {row.get('case_id')}")


class OneCopyTests(unittest.TestCase):
    def test_the_categories_are_one_set(self):
        self.assertIs(agent_scorecards.CATEGORIES, library_rules.CATEGORIES)
        self.assertIs(library_checks.CATEGORIES, library_rules.CATEGORIES)

    def test_the_deployment_name_pattern_is_one_pattern(self):
        self.assertIs(library_runs.DEPLOYMENT_NAME, library_rules.DEPLOYMENT_NAME)

    def test_the_date_rule_is_one_function(self):
        self.assertIs(scorecards.valid_date, library_rules.valid_date)
        self.assertIs(library_runs.valid_date, library_rules.valid_date)
        self.assertFalse(hasattr(scorecards, "_valid_date"))

    def test_the_recorder_accepts_and_refuses_the_profile_maps_the_lab_does(self):
        for label, (models, accepted) in PROFILE_MAPS.items():
            with self.subTest(case=label):
                try:
                    library_runs.resolve_models(
                        [TEMPLATE_ID], model="gpt-5.4", models=None,
                        environ={library_runs.ENV_MODELS: json.dumps(models)}, recorded={})
                except library_runs.Stop:
                    self.assertFalse(accepted)
                else:
                    self.assertTrue(accepted)


if __name__ == "__main__":
    unittest.main()