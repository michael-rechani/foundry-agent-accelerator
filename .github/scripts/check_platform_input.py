"""Check one historical platform-input candidate without reading its contents."""

import os
import sys
from urllib import error, request

import check_lab_terraform_plan as lab
import check_state_backend as backend


def candidate_status(environ=os.environ):
    runtime = lab.configuration(environ)
    host = backend.validate_backend(runtime)
    token = backend.azure_token(runtime)
    url = f"https://{host}/{runtime['TF_STATE_CONTAINER']}/ai-foundry/dev.tfvars.json"
    try:
        with request.build_opener(backend.NoRedirect).open(
            request.Request(  # noqa: S310 -- host and private DNS validated; redirects disabled.
                url, method="HEAD", headers={
                    "Authorization": f"Bearer {token}",
                    "x-ms-version": "2023-11-03",
                },
            ),
            timeout=30,
        ) as response:
            headers = response.headers
            if (response.status == 200 and not headers.get("x-ms-error-code")
                    and headers.get("ETag") and headers.get("x-ms-blob-type") == "BlockBlob"):
                return "present"
    except error.HTTPError as exc:
        try:
            if exc.code == 404 and exc.headers.get("x-ms-error-code") == "BlobNotFound":
                return "absent"
        finally:
            exc.close()
    raise backend.CheckError("Candidate check failed.")


def main():
    try:
        status = candidate_status()
    except Exception:  # noqa: BLE001 -- exceptions can contain private endpoint details.
        print("candidate_platform_input_check_failed", file=sys.stderr)
        return 1
    print(f"candidate_platform_input={status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
