"""Synthetic-only tests: no real token, network, or environment access."""

import io
import json
import unittest
from contextlib import redirect_stdout
from email.message import Message
from unittest.mock import patch

import probe_lab_approval_reads as probe


def response(payload, *, status=200, length=None, link=None):
    headers = Message()
    headers["Content-Length"] = str(len(payload) if length is None else length)
    if link:
        headers["Link"] = link
    result = io.BytesIO(payload)
    result.headers = headers
    result.status = status
    return result


POLICY = b'{"name":"copilot","id":9,"can_admins_bypass":true,"protection_rules":[]}'
EMPTY = b'{"total_count":0,"secrets":[]}'


class ProbeTests(unittest.TestCase):
    def test_fixed_gets_report_only_status_and_shape(self):
        with patch.object(probe.http.client, "HTTPSConnection") as connector, redirect_stdout(io.StringIO()) as out:
            connection = connector.return_value
            connection.getresponse.side_effect = [response(POLICY), response(EMPTY)]
            self.assertEqual(probe.run_probe("mock-token"), 0)
            self.assertEqual(json.loads(out.getvalue()), {
                "policy_http_status": 200, "policy_shape": True,
                "inventory_http_status": 200, "empty_inventory_complete": True,
            })
            self.assertEqual(connector.call_args.args, ("api.github.com",))
            self.assertEqual([call.args for call in connection.request.call_args_list], [
                ("GET", probe.TARGET), ("GET", probe.TARGET + "/secrets?per_page=1"),
            ])

    def test_denied_partial_malformed_or_nonempty_inventory_rejects(self):
        cases = {
            "denied": response(b"not for logs", status=403),
            "redirect": response(EMPTY, status=302),
            "truncated even if JSON parses": response(EMPTY, length=len(EMPTY) + 2),
            "paginated": response(EMPTY, link="<next>; rel=next"),
            "malformed": response(b'{"token-looking-value":'),
            "duplicate key": response(b'{"total_count":2,"total_count":0,"secrets":[]}'),
            "secret name": response(b'{"total_count":1,"secrets":[{"name":"DO_NOT_LOG"}]}'),
            "missing list": response(b'{"total_count":0}'),
        }
        for case, inventory in cases.items():
            with self.subTest(case=case), patch.object(probe.http.client, "HTTPSConnection") as connector:
                connector.return_value.getresponse.side_effect = [response(POLICY), inventory]
                with redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(probe.run_probe("mock-token"), 1)
                self.assertEqual(json.loads(out.getvalue()), {
                    "policy_http_status": 200, "policy_shape": True,
                    "inventory_http_status": inventory.status, "empty_inventory_complete": False,
                })

    def test_missing_bypass_and_transport_failure_reject_without_logging_data(self):
        with patch.object(probe.http.client, "HTTPSConnection") as connector, redirect_stdout(io.StringIO()) as out:
            connector.return_value.getresponse.side_effect = [
                response(b'{"name":"copilot","id":9,"protection_rules":[]}'),
                OSError("DO_NOT_LOG"),
            ]
            self.assertEqual(probe.run_probe("mock-token"), 1)
            self.assertEqual(json.loads(out.getvalue()), {
                "policy_http_status": 200, "policy_shape": False,
                "inventory_http_status": None, "empty_inventory_complete": False,
            })

    def test_push_cannot_call_the_probe(self):
        with patch.object(probe, "run_probe") as run:
            self.assertEqual(probe.main({
                "GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "push",
                "GITHUB_WORKFLOW_REF": probe.WORKFLOW_REF, "GITHUB_RUN_ATTEMPT": "1",
                "PROBE_TOKEN": "mock-token",
            }), 1)
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
