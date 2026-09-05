import re


def validate_specialists(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 16:
        raise ValueError("specialists must contain between 1 and 16 entries")
    names = set()
    for specialist in value:
        if not isinstance(specialist, dict) or set(specialist) != {"tool", "agent", "description"}:
            raise ValueError("Each specialist requires tool, agent, and description only")
        for field in ("tool", "agent"):
            if not isinstance(specialist[field], str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,63}", specialist[field]):
                raise ValueError(f"Invalid specialist {field}")
        if specialist["tool"] in names:
            raise ValueError("Specialist tool names must be unique")
        names.add(specialist["tool"])
        if not isinstance(specialist["description"], str) or not specialist["description"].strip():
            raise ValueError("Specialist description must be nonempty")
    return value


def validate_profile(value):
    required = {"schema_version", "name", "description", "instructions", "specialists", "smoke_tests"}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("Profile requires schema_version, name, description, instructions, specialists, and smoke_tests only")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("Unsupported profile schema_version")
    if not isinstance(value["name"], str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,63}", value["name"]):
        raise ValueError("Invalid coordinator name")
    for field in ("description", "instructions"):
        if not isinstance(value[field], str) or not value[field].strip():
            raise ValueError(f"Profile {field} must be nonempty")
    specialists = validate_specialists(value["specialists"])
    if any(item["agent"] == value["name"] for item in specialists):
        raise ValueError("Coordinator cannot delegate to itself")
    tests = value["smoke_tests"]
    if not isinstance(tests, list):
        raise ValueError("smoke_tests must be a list")
    tools = {item["tool"] for item in specialists}
    covered = set()
    for test in tests:
        if not isinstance(test, dict) or set(test) != {"tool", "prompt"}:
            raise ValueError("Each smoke test requires tool and prompt only")
        if not isinstance(test["tool"], str) or test["tool"] not in tools:
            raise ValueError("Smoke test references an unknown tool")
        if not isinstance(test["prompt"], str) or not test["prompt"].strip():
            raise ValueError("Smoke test prompt must be nonempty")
        covered.add(test["tool"])
    if covered != tools:
        raise ValueError("Every specialist tool requires a smoke test")
    return value