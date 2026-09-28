import json
import unittest
from pathlib import Path

from agent_templates import catalog_facets, list_templates

FIXTURE = Path(__file__).parent / "frontend" / "tests" / "agent-templates.fixture.json"


class FrontendCatalogFixtureTests(unittest.TestCase):
    def test_frontend_fixture_matches_the_served_catalog(self):
        expected = {
            "schema_version": 1,
            "draft_mode": "template",
            "templates": list_templates(),
            "facets": catalog_facets(),
        }
        self.assertEqual(
            json.loads(FIXTURE.read_text(encoding="utf-8")), expected,
            "Regenerate frontend/tests/agent-templates.fixture.json from the catalog.",
        )


if __name__ == "__main__":
    unittest.main()
