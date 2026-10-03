"""Small rules the Lab and the offline evaluation tools both apply.

The Lab image contains only workbench/, and evaluations/ puts workbench/ on sys.path, so
the single copy lives here. The module imports only the standard library, so reading a
regular expression doesn't load the scorecards or the templates. See
docs/shared-plumbing-design.md for what is shared and what is deliberately left as copies.
"""

import datetime
import re

CATEGORIES = frozenset({"grounded", "missing", "conflict", "injection", "decision-boundary"})
DEPLOYMENT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


def is_int(value):
    """A real integer. True and False are not integers here (#166)."""
    return isinstance(value, int) and not isinstance(value, bool)


def is_number(value):
    """An integer or a float, but not True or False."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def valid_date(value):
    """Whether the text is a real calendar date written exactly as YYYY-MM-DD."""
    value = str(value)
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None


def is_profile_map(value, profiles):
    """Whether this maps only the given model profiles to valid deployment names."""
    return isinstance(value, dict) and all(
        profile in profiles and isinstance(name, str) and DEPLOYMENT_NAME.fullmatch(name) is not None
        for profile, name in value.items()
    )