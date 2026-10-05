import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from agent_templates import LIBRARY_ORDER, RETIRED_TEMPLATES, TEMPLATE_METADATA, TEMPLATES
from agent_templates._loader import AGENTS_DIRECTORY, AgentFileError, load_agents
from agent_templates.catalog import _MATCHERS

HERE = Path(__file__).resolve().parent
VOCABULARY = {
    "sectors": {"cross-sector": "Works in any sector", "private": "Private sector", "public": "Public sector"},
    "industries": {"finance", "retail"},
    "tasks": {"review", "extract"},
    "readiness": {"sample", "reviewed"},
    "model_profiles": {"extraction", "reasoning"},
}


def agent(identifier="sample-agent", **changes):
    document = {
        "id": identifier,
        "order": 10,
        "template": {
            "model_profile": "extraction", "label": "Sample", "description": "Does a sample job.",
            "input": "Text.", "output": "A table.", "limits": "Works only from the text.",
            "delegation": "Works on its own.", "instructions": "Check the text.",
            "example_request": "Create a sample agent.", "sample_input": "Check this.",
            "tools": [{"name": "look_up", "description": "Looks up a sample record"}],
        },
        "metadata": {
            "sector": "private", "industry": "finance", "tasks": ["review"], "summary": "Checks things.",
            "expected_behavior": "Quotes the text.", "human_decision": "A person decides.",
            "keywords": ["sample"], "readiness": "sample",
        },
        "match": ["sample", "thing"],
    }
    document.update(changes)
    return document


class AgentFileTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def write(self, document, name=None):
        text = document if isinstance(document, str) else json.dumps(document)
        (self.root / f"{name or document['id']}.json").write_text(text, encoding="utf-8")

    def load(self):
        return load_agents(self.root, VOCABULARY)

    def assertRejected(self, document, expected, name=None):
        self.write(document, name)
        with self.assertRaisesRegex(AgentFileError, expected):
            self.load()

    def test_the_catalog_has_one_file_per_agent_named_by_its_id(self):
        files = {path.stem for path in AGENTS_DIRECTORY.glob("*.json")}
        self.assertEqual(files, set(TEMPLATES))
        self.assertEqual(files, set(TEMPLATE_METADATA))
        self.assertEqual(files, set(_MATCHERS))
        for identifier in files:
            document = json.loads((AGENTS_DIRECTORY / f"{identifier}.json").read_text(encoding="utf-8"))
            self.assertEqual(document["id"], identifier)

    def test_the_catalog_tables_follow_the_library_order_with_retired_agents_last(self):
        expected = [*LIBRARY_ORDER, *sorted(RETIRED_TEMPLATES)]
        self.assertEqual(list(TEMPLATES), expected)
        self.assertEqual(list(TEMPLATE_METADATA), expected)
        self.assertEqual(list(_MATCHERS), expected)

    def test_a_file_becomes_a_template_its_metadata_and_a_matcher(self):
        self.write(agent())
        library = self.load()
        template = library.templates["sample-agent"]
        self.assertEqual(list(template)[:3], ["id", "category", "model_profile"])
        self.assertEqual(template["category"], "Private sector")
        self.assertEqual(template["tools"], [{
            "name": "look_up", "description": "Looks up a sample record; no external call or update.",
            "simulated": True,
        }])
        self.assertEqual(list(library.metadata["sample-agent"]), [
            "sector", "industry", "tasks", "summary", "expected_behavior", "human_decision", "keywords", "readiness",
        ])
        self.assertEqual([pattern.pattern for pattern in library.matchers["sample-agent"]],
                         [r"\b(sample)\b", r"\b(thing)\b"])
        self.assertEqual(library.library_order, ("sample-agent",))
        self.assertEqual(library.retired, frozenset())

    def test_library_order_follows_order_and_retired_agents_are_not_listed(self):
        self.write(agent("last-agent", order=30))
        self.write(agent("first-agent", order=10))
        retired = agent("old-agent", retired=True)
        del retired["order"]
        self.write(retired)
        library = self.load()
        self.assertEqual(library.library_order, ("first-agent", "last-agent"))
        self.assertEqual(library.retired, {"old-agent"})
        self.assertEqual(list(library.templates), ["first-agent", "last-agent", "old-agent"])
        self.assertEqual(list(library.metadata), list(library.templates))
        self.assertEqual(list(library.matchers), list(library.templates))

    def test_retired_agents_follow_the_listed_ones_by_id(self):
        for identifier in ("zeta-agent", "alpha-agent"):
            retired = agent(identifier, retired=True)
            del retired["order"]
            self.write(retired)
        self.write(agent("only-agent", order=50))
        self.assertEqual(list(self.load().templates), ["only-agent", "alpha-agent", "zeta-agent"])

    def test_a_directory_without_agents_is_an_error(self):
        with self.assertRaisesRegex(AgentFileError, "No agent files"):
            self.load()

    def test_files_that_do_not_fit_are_rejected_with_the_file_name(self):
        def without(path):
            document = agent()
            target = document
            for key in path[:-1]:
                target = target[key]
            del target[path[-1]]
            return document

        def changed(path, value):
            document = agent()
            target = document
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            return document

        cases = {
            "not json": ("{", "sample-agent.json: "),
            "not an object": ("[]", "the file must be an object"),
            "repeated key": ('{"id": "sample-agent", "id": "sample-agent"}', "a key appears twice"),
            "missing template": (without(["template"]), "the file is missing template"),
            "unknown top field": (agent() | {"colour": "red"}, "unknown field colour"),
            "missing template field": (without(["template", "label"]), "template is missing label"),
            "unknown template field": (changed(["template", "extra"], "x"), "template has unknown field extra"),
            "empty template text": (changed(["template", "label"], " "), "template label must be non-empty text"),
            "unknown model profile": (changed(["template", "model_profile"], "huge"), "unknown model_profile 'huge'"),
            "tools not a list": (changed(["template", "tools"], {}), "template tools must be a list"),
            "tool field": (changed(["template", "tools"], [{"name": "a"}]), "a tool is missing description"),
            "repeated tool": (changed(["template", "tools"], [{"name": "a", "description": "x"}] * 2),
                              "two tools share a name"),
            "unknown sector": (changed(["metadata", "sector"], "space"), "unknown sector 'space'"),
            "unknown industry": (changed(["metadata", "industry"], "mining"), "unknown industry 'mining'"),
            "unknown task": (changed(["metadata", "tasks"], ["dance"]), "unknown task 'dance'"),
            "repeated task": (changed(["metadata", "tasks"], ["review", "review"]), "a task is listed twice"),
            "no tasks": (changed(["metadata", "tasks"], []), "metadata tasks must be a non-empty list"),
            "unknown readiness": (changed(["metadata", "readiness"], "great"), "unknown readiness 'great'"),
            "missing readiness": (without(["metadata", "readiness"]), "metadata is missing readiness"),
            "no match": (changed(["match"], []), "match must be a non-empty list"),
            "bad pattern": (changed(["match"], ["(open"]), "missing"),
            "no place in the library": (without(["order"]), "needs an order"),
            "listed and retired": (agent() | {"retired": True}, "needs an order"),
            "retired is not a flag": (agent() | {"retired": "yes"}, "retired must be true"),
            "order is zero": (agent() | {"order": 0}, "order must be a whole number"),
            "order is a flag": (agent() | {"order": True}, "order must be a whole number"),
            "dropped definition order": (agent() | {"definition_order": 1}, "unknown field definition_order"),
            "id is not a slug": (agent("Sample_Agent"), "id must be lowercase words"),
        }
        for name, (document, expected) in cases.items():
            with self.subTest(name):
                for stale in self.root.glob("*.json"):
                    stale.unlink()
                file_name = "Sample_Agent" if name == "id is not a slug" else "sample-agent"
                self.write(document, file_name)
                with self.assertRaisesRegex(AgentFileError, expected) as raised:
                    self.load()
                self.assertTrue(str(raised.exception).startswith(f"{file_name}.json: "), str(raised.exception))

    def test_an_id_must_match_the_file_name(self):
        self.assertRejected(agent("other-agent"), "id must be lowercase words joined by hyphens, and match the file name",
                            name="sample-agent")

    def test_two_agents_cannot_share_a_place(self):
        self.write(agent("one-agent", order=10))
        self.write(agent("two-agent", order=10))
        with self.assertRaisesRegex(AgentFileError, r"two-agent.json: order 10 is already used by one-agent"):
            self.load()

    def test_adding_one_file_adds_an_agent_to_the_whole_catalog(self):
        shutil.copytree(HERE / "agent_templates", self.root / "agent_templates",
                        ignore=shutil.ignore_patterns("__pycache__"))
        order = max(json.loads(path.read_text(encoding="utf-8")).get("order", 0)
                    for path in (self.root / "agent_templates" / "agents").glob("*.json")) + 10
        document = agent("zebra-herd-counter", order=order)
        document["metadata"] |= {"sector": "cross-sector", "industry": "general-operations", "tasks": ["extract"]}
        document["match"] = ["zebra herds?", "count\\w*"]
        (self.root / "agent_templates" / "agents" / "zebra-herd-counter.json").write_text(
            json.dumps(document), encoding="utf-8")
        script = (
            "import json\n"
            "import agent_templates as at\n"
            "listed = at.list_templates()\n"
            "draft = at.prepare_draft('Please count the zebra herds in this survey.')\n"
            "print(json.dumps({'ids': [item['id'] for item in listed],\n"
            "  'sectors': {item['id']: item['count'] for item in at.catalog_facets()['sectors']},\n"
            "  'draft': draft['template_id'], 'category': at.TEMPLATES['zebra-herd-counter']['category'],\n"
            "  'instructions': at.TEMPLATES['zebra-herd-counter']['instructions'].endswith('A person decides.')}))\n"
        )
        result = subprocess.run([sys.executable, "-c", script], cwd=self.root,
                                capture_output=True, text=True, check=False, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        served = json.loads(result.stdout)
        self.assertEqual(served["ids"], [*LIBRARY_ORDER, "zebra-herd-counter"])
        self.assertEqual(served["draft"], "zebra-herd-counter")
        self.assertEqual(served["category"], "Works in any sector")
        self.assertTrue(served["instructions"])
        self.assertEqual(sum(served["sectors"].values()), len(LIBRARY_ORDER) + 1)

    def test_retired_agents_in_the_catalog_have_no_place_in_the_library(self):
        for identifier in RETIRED_TEMPLATES:
            document = json.loads((AGENTS_DIRECTORY / f"{identifier}.json").read_text(encoding="utf-8"))
            self.assertTrue(document["retired"])
            self.assertNotIn("order", document)
            self.assertNotIn(identifier, LIBRARY_ORDER)


if __name__ == "__main__":
    unittest.main()
