"""Fail closed before a manually reviewed private Lab image release."""

import argparse
import json
import os
import re
import sys
from urllib.parse import quote

from check_state_backend import CheckError, json_response

SHA = re.compile(r"[0-9a-f]{40}")
IMAGE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.-]*/workbench@sha256:[0-9a-f]{64}")
UUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._()-]{0,89}")
REVISION = re.compile(r"[A-Za-z0-9-]+")


def validate_dispatch(environ):
    if environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch" or environ.get("GITHUB_REF") != "refs/heads/main":
        raise CheckError("Only a manual dispatch from main can release a Lab image.")
    reviewed = environ.get("REVIEWED_SOURCE_SHA", "")
    if not SHA.fullmatch(reviewed) or environ.get("GITHUB_SHA") != reviewed:
        raise CheckError("The reviewed source SHA must match the dispatched main commit.")
    if environ.get("CONFIRM_ROLLOUT") != "true":
        raise CheckError("The staged rollout and recovery inventory must be explicitly confirmed.")
    expected_image = environ.get("EXPECTED_CURRENT_IMAGE", "")
    if not IMAGE.fullmatch(expected_image):
        raise CheckError("The recorded current Lab image must be an immutable workbench digest.")
    return reviewed, expected_image


def verify_main(environ, reviewed):
    repository = environ.get("GITHUB_REPOSITORY", "")
    parts = repository.split("/")
    if (
        environ.get("GITHUB_API_URL") != "https://api.github.com"
        or len(parts) != 2
        or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", part) or part in (".", "..") for part in parts)
        or not environ.get("GH_TOKEN")
    ):
        raise CheckError("GitHub main-branch verification is not configured.")
    path = "/".join(quote(part, safe="") for part in parts)
    response = json_response(
        f"https://api.github.com/repos/{path}/git/ref/heads/main",
        headers={
            "Authorization": f"Bearer {environ['GH_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    obj = response.get("object")
    if not isinstance(obj, dict) or obj.get("sha") != reviewed:
        raise CheckError("Main no longer matches the reviewed source SHA.")


def verify_live_image(environ, expected_image, snapshot, *, recovery=False):
    subscription = environ.get("AZURE_SUBSCRIPTION_ID", "")
    group = environ.get("AZURE_RESOURCE_GROUP", "")
    name = environ.get("LAB_CONTAINER_APP", "")
    if not UUID.fullmatch(subscription) or not NAME.fullmatch(group) or not NAME.fullmatch(name):
        raise CheckError("The protected Lab subscription or app identity is invalid.")
    if not isinstance(snapshot, dict):
        raise CheckError("The active Lab revision could not be verified.")
    app, revisions, registry = snapshot.get("app"), snapshot.get("revisions"), snapshot.get("registry")
    if (
        not isinstance(app, dict)
        or not isinstance(revisions, list)
        or not isinstance(registry, str)
        or expected_image != f"{registry}/workbench@sha256:{expected_image.rsplit(':', 1)[-1]}"
    ):
        raise CheckError("The expected image does not identify the configured private registry.")
    app_id = f"/subscriptions/{subscription}/resourceGroups/{group}/providers/Microsoft.App/containerApps/{name}"
    latest, ready = app.get("latest"), app.get("ready")
    attempted_revision = environ.get("ATTEMPTED_REVISION", "")
    attempted_image = environ.get("ATTEMPTED_IMAGE", "")
    if recovery and (
        not REVISION.fullmatch(attempted_revision)
        or not IMAGE.fullmatch(attempted_image)
        or attempted_image != f"{registry}/workbench@sha256:{attempted_image.rsplit(':', 1)[-1]}"
        or attempted_image == expected_image
    ):
        raise CheckError("The attempted revision or its immutable image is not confirmed.")
    template_image = attempted_image if recovery else expected_image
    if (
        not isinstance(app.get("id"), str)
        or app["id"].lower() != app_id.lower()
        or app.get("revisionMode") != "Single"
        or not isinstance(latest, str)
        or not REVISION.fullmatch(latest)
        or not isinstance(ready, str)
        or not REVISION.fullmatch(ready)
        or latest != (attempted_revision if recovery else ready)
        or app.get("containers") != [{"name": "workbench", "image": template_image}]
    ):
        raise CheckError("The Lab does not have a single confirmed ready revision and expected image.")
    seen = set()
    for item in revisions:
        if not isinstance(item, dict) or type(item.get("active")) is not bool:
            raise CheckError("The active Lab revisions are ambiguous.")
        revision_name, revision_id = item.get("name"), item.get("id")
        if (
            not isinstance(revision_name, str)
            or not REVISION.fullmatch(revision_name)
            or not isinstance(revision_id, str)
            or revision_id.lower() != (app_id + "/revisions/" + revision_name).lower()
            or revision_name.lower() in seen
        ):
            raise CheckError("The Lab revision inventory is ambiguous.")
        seen.add(revision_name.lower())
    active = [item for item in revisions if item["active"]]
    if len(active) != 1:
        raise CheckError("The Lab must have exactly one active revision.")
    revision = active[0]
    containers = revision.get("containers")
    allowed_images = (expected_image, attempted_image) if recovery else (expected_image,)
    if (
        revision.get("name") != ready
        or not isinstance(revision.get("id"), str)
        or revision["id"].lower() != (app_id + "/revisions/" + ready).lower()
        or revision.get("state") not in ("Running", "RunningAtMaxScale")
        or not isinstance(containers, list)
        or len(containers) != 1
        or not isinstance(containers[0], dict)
        or containers[0].get("name") != "workbench"
        or containers[0].get("image") not in allowed_images
        or set(containers[0]) != {"name", "image"}
    ):
        raise CheckError("The active Lab revision or its immutable image is not confirmed.")


def main(argv=None, environ=os.environ):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--live", action="store_true", help="Also verify the active revision snapshot on stdin.")
    parser.add_argument("--recovery", action="store_true", help="Check the attempted rollout before restoration.")
    args = parser.parse_args(argv)
    try:
        if args.recovery and not args.live:
            raise CheckError("Recovery requires a live revision snapshot.")
        reviewed, expected_image = validate_dispatch(environ)
        verify_main(environ, reviewed)
        if args.live:
            try:
                snapshot = json.load(sys.stdin)
            except (ValueError, UnicodeError):
                raise CheckError("The active Lab revision snapshot is invalid.") from None
            verify_live_image(environ, expected_image, snapshot, recovery=args.recovery)
    except CheckError as error:
        print(f"::error::{error}", file=sys.stderr)
        return 1
    print("Reviewed main and Lab image release inputs are confirmed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
