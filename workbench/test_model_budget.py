import unittest
from unittest.mock import patch

from agent_scorecards import SCORECARDS
from model_budget import MAX_LIMIT, ModelBudgets, measured_answer_tokens, validate_model_limits

BUSY_MODEL = "gpt-5.4"
OTHER_MODEL = "gpt-4.1"
LIMITS = {BUSY_MODEL: {"requests_per_minute": 100, "tokens_per_minute": 10000},
          OTHER_MODEL: {"requests_per_minute": 50, "tokens_per_minute": 50000}}
ANSWERS = {"small": 1000, "big": 5000, "huge": 10000}


class ValidateModelLimitsTests(unittest.TestCase):
    def test_valid_limits_and_no_limits_are_accepted(self):
        self.assertIs(validate_model_limits(LIMITS), LIMITS)
        self.assertEqual(validate_model_limits({}), {})
        top = {"gpt-5.4": {"requests_per_minute": MAX_LIMIT, "tokens_per_minute": 1}}
        self.assertEqual(validate_model_limits(top), top)

    def test_invalid_limits_are_rejected_with_the_setting_and_deployment_named(self):
        good = {"requests_per_minute": 10, "tokens_per_minute": 1000}
        cases = [
            (["gpt-5.4"], "must be a JSON object"), ("gpt-5.4", "must be a JSON object"), (None, "must be a JSON object"),
            ({"": good}, "invalid deployment name"), ({"bad name": good}, "invalid deployment name"),
            ({"-gpt": good}, "invalid deployment name"), ({"a" * 129: good}, "invalid deployment name"),
            ({"gpt-5.4": 100}, "exactly requests_per_minute and tokens_per_minute"),
            ({"gpt-5.4": {"requests_per_minute": 10}}, "exactly requests_per_minute and tokens_per_minute"),
            ({"gpt-5.4": {**good, "extra": 1}}, "exactly requests_per_minute and tokens_per_minute"),
            ({"gpt-5.4": {"requests_per_minute": 10, "tokens": 1000}}, "exactly requests_per_minute and tokens_per_minute"),
        ]
        for key in good:
            for value in (0, -1, 1.5, "10", True, None, MAX_LIMIT + 1):
                cases.append(({"gpt-5.4": {**good, key: value}}, f"{key} as a whole number from 1 to {MAX_LIMIT}"))
        for value, message in cases:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "WORKBENCH_MODEL_LIMITS") as caught:
                    validate_model_limits(value)
                self.assertIn(message, str(caught.exception))

    def test_a_bad_deployment_is_named_in_the_error(self):
        with self.assertRaisesRegex(ValueError, "for gpt-4.1 needs tokens_per_minute"):
            validate_model_limits({"gpt-4.1": {"requests_per_minute": 5, "tokens_per_minute": 0}})


class MeasuredAnswerTokensTests(unittest.TestCase):
    def test_the_estimate_is_the_largest_answer_recorded_for_the_template(self):
        cards = {"scorecards": [
            {"template_id": "one", "cases": [{"input_tokens": 100, "output_tokens": 50}, {"input_tokens": 700.4, "output_tokens": 300}]},
            {"template_id": "two", "cases": [{"input_tokens": 10, "output_tokens": 5}]},
        ]}
        self.assertEqual(measured_answer_tokens(cards), {"one": 1001, "two": 15})

    def test_cases_without_token_counts_are_skipped_and_a_card_with_none_has_no_estimate(self):
        cards = {"scorecards": [
            {"template_id": "partial", "cases": [{"input_tokens": 100}, {"input_tokens": 5, "output_tokens": 5},
                                                 {"input_tokens": True, "output_tokens": 5}]},
            {"template_id": "none", "cases": [{"seconds": 3}]},
            {"template_id": "zero", "cases": [{"input_tokens": 0, "output_tokens": 0}]},
        ]}
        self.assertEqual(measured_answer_tokens(cards), {"partial": 10})

    def test_every_recorded_scorecard_gives_a_whole_positive_estimate(self):
        estimates = measured_answer_tokens(SCORECARDS)
        measured = {card["template_id"] for card in SCORECARDS["scorecards"]}
        self.assertTrue(measured)
        self.assertEqual(set(estimates), measured)
        self.assertTrue(all(type(value) is int and value > 0 for value in estimates.values()))


class ModelBudgetsTests(unittest.TestCase):
    def budgets(self, limits=LIMITS, answers=ANSWERS, **options):
        return ModelBudgets(limits, answers, **options)

    def test_turns_below_the_limits_are_admitted_and_counted(self):
        budgets = self.budgets()
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "big", now=0), 0)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "small", now=1), 0)
        self.assertEqual(list(budgets.recent[BUSY_MODEL]), [(0, 5000), (1, 1000)])

    def test_a_turn_that_would_pass_the_token_limit_is_refused_and_not_counted(self):
        budgets = self.budgets()
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "big", now=0), 0)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "big", now=10), 0)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "small", now=20), 40)
        self.assertEqual(list(budgets.recent[BUSY_MODEL]), [(0, 5000), (10, 5000)])

    def test_the_token_limit_itself_is_allowed_and_one_token_over_is_not(self):
        budgets = self.budgets({BUSY_MODEL: {"requests_per_minute": 100, "tokens_per_minute": 6000}})
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "big", now=0), 0)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "small", now=0), 0)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "small", now=0), 60)
        again = self.budgets({BUSY_MODEL: {"requests_per_minute": 100, "tokens_per_minute": 5999}})
        self.assertEqual(again.try_admit(BUSY_MODEL, "big", now=0), 0)
        self.assertEqual(again.try_admit(BUSY_MODEL, "small", now=0), 60)

    def test_a_turn_that_would_pass_the_request_limit_is_refused_even_with_tokens_to_spare(self):
        budgets = self.budgets({BUSY_MODEL: {"requests_per_minute": 2, "tokens_per_minute": 1000000}})
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "small", now=0), 0)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "small", now=5), 0)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "small", now=6), 54)
        self.assertEqual(len(budgets.recent[BUSY_MODEL]), 2)

    def test_limits_are_per_deployment_so_a_full_model_does_not_block_another(self):
        budgets = self.budgets()
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "huge", now=0), 0)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "small", now=1), 59)
        self.assertEqual(budgets.try_admit(OTHER_MODEL, "huge", now=1), 0)
        self.assertEqual(budgets.try_admit(OTHER_MODEL, "huge", now=2), 0)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "small", now=3), 57)

    def test_a_deployment_without_limits_or_without_a_known_deployment_is_not_budgeted(self):
        budgets = self.budgets()
        for deployment in ("unlisted-model", None, ""):
            for second in range(5):
                with self.subTest(deployment=deployment, second=second):
                    self.assertEqual(budgets.try_admit(deployment, "huge", now=second), 0)
        self.assertEqual(set(budgets.recent), set(LIMITS))
        self.assertEqual(self.budgets({}).try_admit(BUSY_MODEL, "huge", now=0), 0)

    def test_counters_recover_when_the_oldest_turns_leave_the_window(self):
        budgets = self.budgets()
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "big", now=0), 0)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "big", now=10), 0)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "big", now=20), 40)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "big", now=59.9), 1)
        self.assertEqual(list(budgets.recent[BUSY_MODEL]), [(0, 5000), (10, 5000)])
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "big", now=60), 0)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "big", now=69.9), 1)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "big", now=70), 0)
        self.assertEqual(list(budgets.recent[BUSY_MODEL]), [(60, 5000), (70, 5000)])

    def test_the_wait_is_until_enough_turns_expire_for_this_turn_to_fit(self):
        budgets = self.budgets()
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "big", now=0), 0)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "big", now=10), 0)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "huge", now=20), 50)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "huge", now=60), 10)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "huge", now=70), 0)

    def test_the_wait_is_whole_seconds_between_one_and_the_window(self):
        budgets = self.budgets()
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "huge", now=0), 0)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "small", now=0), 60)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "small", now=0.2), 60)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "small", now=30.5), 30)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "small", now=59.999), 1)

    def test_a_turn_larger_than_the_whole_limit_runs_alone_but_never_beside_another(self):
        budgets = self.budgets({BUSY_MODEL: {"requests_per_minute": 100, "tokens_per_minute": 1000}})
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "huge", now=0), 0)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "huge", now=1), 59)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "small", now=1), 59)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "huge", now=60), 0)

    def test_an_unmeasured_template_counts_as_the_largest_measured_answer(self):
        budgets = self.budgets()
        self.assertEqual(budgets.estimate("small"), 1000)
        self.assertEqual(budgets.estimate("not-measured"), 10000)
        self.assertEqual(budgets.estimate(None), 10000)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "not-measured", now=0), 0)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "small", now=1), 59)

    def test_with_no_measurements_only_the_request_limit_applies(self):
        budgets = self.budgets({BUSY_MODEL: {"requests_per_minute": 2, "tokens_per_minute": 1}}, answers={})
        self.assertEqual(budgets.estimate("anything"), 0)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "anything", now=0), 0)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "anything", now=1), 0)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "anything", now=2), 58)

    def test_the_window_length_is_a_parameter(self):
        budgets = self.budgets({BUSY_MODEL: {"requests_per_minute": 1, "tokens_per_minute": 100000}}, window_seconds=10)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "small", now=0), 0)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "small", now=9.5), 1)
        self.assertEqual(budgets.try_admit(BUSY_MODEL, "small", now=10), 0)

    def test_without_a_time_the_clock_is_monotonic(self):
        budgets = self.budgets({BUSY_MODEL: {"requests_per_minute": 1, "tokens_per_minute": 100000}})
        with patch("model_budget.time.monotonic", return_value=500):
            self.assertEqual(budgets.try_admit(BUSY_MODEL, "small"), 0)
            self.assertEqual(budgets.try_admit(BUSY_MODEL, "small"), 60)
        self.assertEqual(list(budgets.recent[BUSY_MODEL]), [(500, 1000)])

    def test_invalid_limits_are_rejected_when_the_budgets_are_built(self):
        for limits in ({"gpt-5.4": {"requests_per_minute": 0, "tokens_per_minute": 10}}, {"bad name": {}}, []):
            with self.subTest(limits=limits):
                with self.assertRaisesRegex(ValueError, "WORKBENCH_MODEL_LIMITS"):
                    self.budgets(limits)


if __name__ == "__main__":
    unittest.main()
