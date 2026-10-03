import re

_TEXT_LIMITS = (
    "Works only from the text you give it. It can't open files, change other systems, "
    "or make legal, medical, eligibility or payment decisions."
)
_DIRECT = "Works on its own from the text you give it. It doesn't call other agents or tools."
# These are also the library's sector names (see SECTORS), so the Create page headings and the
# library filter agree. The Create page lists its groups in the order the jobs first appear in
# LIBRARY_ORDER; SECTORS keeps that same order (a test checks it).
_ANY = "Works in any sector"
_SECTOR = "Healthcare and public sector"
_PRIVATE = "Private sector"
_LOOKUP_RULES = (
    "Say which facts came from sample lookups. If a lookup fails or a detail is missing, "
    "say so instead of guessing."
)


def _lookups(what):
    return f"Works on its own. It uses two built-in lookups with sample data to check {what}."


def _tool(name, description):
    return {"name": name, "description": description + "; no external call or update.", "simulated": True}


def _metadata(sector, industry, tasks, summary, expected_behavior, human_decision, keywords, *, readiness="sample"):
    return {
        "sector": sector, "industry": industry, "tasks": tasks, "summary": summary,
        "expected_behavior": expected_behavior, "human_decision": human_decision,
        "keywords": keywords, "readiness": readiness,
    }


def _words(pattern):
    return re.compile(r"\b(" + pattern + r")\b")
