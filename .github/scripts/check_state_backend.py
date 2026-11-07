"""Verify GitHub OIDC backend access without reading or changing Terraform state."""

import ipaddress
import json
import os
import re
import socket
import sys
import uuid
from urllib import error, parse, request


class CheckError(RuntimeError):
    pass


REQUEST_STAGES = {
    "GITHUB_OIDC_ASSERTION": ("GET",),
    "LAB_STATE": ("GET", "HEAD"),
    "LAB_INPUTS": ("GET", "HEAD"),
    "PLATFORM_STATE": ("GET", "HEAD"),
    "ARM_CURRENT_APP": ("GET",),
    "ARM_CURRENT_REVISION": ("GET",),
}


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def send(url, *, method="GET", headers=None, data=None, expected=(200,)):
    try:
        target = parse.urlsplit(url)
        if (target.scheme != "https" or not target.hostname or target.username
                or target.password or target.port not in (None, 443)):
            raise CheckError("Only HTTPS endpoints without embedded credentials are allowed.")
    except ValueError:
        raise CheckError("Invalid HTTPS endpoint.") from None
    try:
        with request.build_opener(NoRedirect).open(
            request.Request(url, data=data, headers=headers or {}, method=method),  # noqa: S310 -- HTTPS checked above; redirects disabled.
            timeout=30,
        ) as response:
            if response.status not in expected:
                raise CheckError(f"{method} returned unexpected HTTP {response.status}.")
            return response.read(), response.headers
    except error.HTTPError as exc:
        exc.close()
        if exc.code in expected:
            return b"", exc.headers
        raise CheckError(f"{method} failed with HTTP {exc.code}.") from None
    except (error.URLError, OSError):
        raise CheckError(f"{method} could not reach its approved endpoint.") from None


def staged_send(url, *, stage=None, method="GET", **kwargs):
    if (
        type(stage) is not str
        or stage not in REQUEST_STAGES
        or type(method) is not str
        or method not in REQUEST_STAGES[stage]
    ):
        raise CheckError("Unreviewed or missing request stage/method; request refused.")
    try:
        return send(url, method=method, **kwargs)
    except CheckError as exc:
        # Only exact transport-generated messages qualify; never echo arbitrary exception text.
        match = re.fullmatch(
            re.escape(method) + r" (failed with|returned unexpected) HTTP ([1-5][0-9]{2})\.",
            str(exc),
        )
        if match:
            raise CheckError(f"{stage} {method} {match[1]} HTTP {match[2]}.") from None
        if str(exc) == f"{method} could not reach its approved endpoint.":
            raise CheckError(f"{stage} {method} could not reach its approved endpoint.") from None
        raise CheckError(f"{stage} {method} failed; private request diagnostics withheld.") from None


def _response_object(body, label):
    try:
        value = json.loads(body)
    except (ValueError, UnicodeError):
        raise CheckError(f"{label} returned invalid JSON.") from None
    if not isinstance(value, dict):
        raise CheckError(f"{label} returned a non-object response.")
    return value


def json_response(url, **kwargs):
    body, _ = send(url, **kwargs)
    return _response_object(body, "An authentication endpoint")


def staged_json_response(url, *, stage=None, **kwargs):
    body, _ = staged_send(url, stage=stage, **kwargs)
    return _response_object(body, stage)


def validate_backend(environ=os.environ):
    required = (
        "AZURE_CLIENT_ID", "AZURE_TENANT_ID", "TF_STATE_ACCOUNT",
        "TF_STATE_CONTAINER", "TF_STATE_PREFIX", "TF_STATE_PRIVATE_ENDPOINT",
        "ACTIONS_ID_TOKEN_REQUEST_URL", "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
    )
    if environ.get("GITHUB_REF") != "refs/heads/main":
        raise CheckError("Only the protected main workflow may run this check.")
    if any(not environ.get(name) for name in required):
        raise CheckError("Required protected-environment configuration is missing.")
    account, container = environ["TF_STATE_ACCOUNT"], environ["TF_STATE_CONTAINER"]
    prefix = environ["TF_STATE_PREFIX"]
    if not re.fullmatch(r"[a-z0-9]{3,24}", account):
        raise CheckError("Invalid backend account name.")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", container):
        raise CheckError("Invalid backend container name.")
    if prefix != "ai-foundry/":
        raise CheckError("This identity is restricted to the ai-foundry/ namespace.")
    for name in ("AZURE_CLIENT_ID", "AZURE_TENANT_ID"):
        if not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", environ[name]):
            raise CheckError("Invalid Azure identity configuration.")
    try:
        approved_ip = ipaddress.IPv4Address(environ["TF_STATE_PRIVATE_ENDPOINT"])
    except ipaddress.AddressValueError:
        raise CheckError("Invalid approved private endpoint address.") from None
    if not any(approved_ip in ipaddress.ip_network(cidr) for cidr in
               ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")):
        raise CheckError("Only an approved RFC1918 endpoint is allowed.")
    host = f"{account}.blob.core.windows.net"
    try:
        addresses = {entry[4][0] for entry in socket.getaddrinfo(host, 443)}
    except OSError:
        raise CheckError("Backend DNS lookup failed.") from None
    if addresses != {str(approved_ip)}:
        raise CheckError("Backend DNS must resolve only to its approved private endpoint.")
    return host


def azure_token(environ=os.environ, scope="https://storage.azure.com/.default"):
    validate_backend(environ)
    if scope not in ("https://storage.azure.com/.default", "https://management.azure.com/.default"):
        raise CheckError("Only storage and ARM token scopes are allowed.")
    oidc_url = parse.urlsplit(environ["ACTIONS_ID_TOKEN_REQUEST_URL"])
    if (oidc_url.scheme != "https" or not oidc_url.hostname
            or not oidc_url.hostname.endswith(".actions.githubusercontent.com")
            or oidc_url.username or oidc_url.password or oidc_url.port not in (None, 443)):
        raise CheckError("Invalid GitHub OIDC request endpoint.")
    query = parse.parse_qsl(oidc_url.query, keep_blank_values=True)
    query = [(key, value) for key, value in query if key != "audience"]
    query.append(("audience", "api://AzureADTokenExchange"))
    assertion = staged_json_response(
        parse.urlunsplit(oidc_url._replace(query=parse.urlencode(query))),
        stage="GITHUB_OIDC_ASSERTION",
        headers={"Authorization": f"Bearer {environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN']}"},
    ).get("value")
    if not assertion:
        raise CheckError("GitHub did not return an OIDC assertion.")
    token = json_response(
        f"https://login.microsoftonline.com/{environ['AZURE_TENANT_ID']}/oauth2/v2.0/token",
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=parse.urlencode({
            "client_id": environ["AZURE_CLIENT_ID"],
            "scope": scope,
            "grant_type": "client_credentials",
            "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            "client_assertion": assertion,
        }).encode(),
    ).get("access_token")
    if not token:
        raise CheckError("Azure did not return an access token.")
    return token


def check(environ=os.environ):
    host = validate_backend(environ)
    container, prefix = environ["TF_STATE_CONTAINER"], environ["TF_STATE_PREFIX"]
    token = azure_token(environ)
    headers = {"Authorization": f"Bearer {token}", "x-ms-version": "2023-11-03"}
    base = f"https://{host}/{container}"
    send(base + "?" + parse.urlencode({
        "restype": "container", "comp": "list", "prefix": prefix, "maxresults": "1",
    }), headers=headers)
    send(base + "/.access-probe-forbidden/" + str(uuid.uuid4()),
         headers=headers, expected=(403,))
    blob = base + "/" + prefix + ".access-probe/" + str(uuid.uuid4())
    lease_id = str(uuid.uuid4())
    created = leased = False
    try:
        send(blob, method="PUT", headers={
            **headers, "x-ms-blob-type": "BlockBlob", "If-None-Match": "*",
        }, data=b"Disposable state access check; not Terraform state.\n", expected=(201,))
        created = True
        send(blob + "?comp=lease", method="PUT", headers={
            **headers, "x-ms-lease-action": "acquire", "x-ms-lease-duration": "15",
            "x-ms-proposed-lease-id": lease_id,
        }, data=b"", expected=(201,))
        leased = True
        # A concurrent writer must not be able to take the lease.
        send(blob + "?comp=lease", method="PUT", headers={
            **headers, "x-ms-lease-action": "acquire", "x-ms-lease-duration": "15",
        }, data=b"", expected=(409,))
        send(blob + "?comp=lease", method="PUT", headers={
            **headers, "x-ms-lease-action": "release", "x-ms-lease-id": lease_id,
        }, data=b"")
        leased = False
    finally:
        if created:
            send(blob, method="DELETE", headers={
                **headers, **({"x-ms-lease-id": lease_id} if leased else {}),
            }, expected=(202,))
    print("Private DNS, GitHub OIDC, namespace isolation, probe write, exclusive lease and cleanup passed.")
    print("No Terraform state contents were read or changed. No infrastructure apply was run.")


if __name__ == "__main__":
    try:
        check()
    except CheckError as exc:
        print(f"State backend check failed: {exc}", file=sys.stderr)
        sys.exit(1)
