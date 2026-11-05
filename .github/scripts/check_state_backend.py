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


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def send(url, *, method="GET", headers=None, data=None, expected=(200,)):
    try:
        with request.build_opener(NoRedirect).open(
            request.Request(url, data=data, headers=headers or {}, method=method),
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


def json_response(url, **kwargs):
    body, _ = send(url, **kwargs)
    try:
        value = json.loads(body)
    except (ValueError, UnicodeError):
        raise CheckError("An authentication endpoint returned invalid JSON.") from None
    if not isinstance(value, dict):
        raise CheckError("An authentication endpoint returned a non-object response.")
    return value


def check(environ=os.environ):
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

    oidc_url = parse.urlsplit(environ["ACTIONS_ID_TOKEN_REQUEST_URL"])
    if (oidc_url.scheme != "https" or not oidc_url.hostname
            or not oidc_url.hostname.endswith(".actions.githubusercontent.com")
            or oidc_url.username or oidc_url.password or oidc_url.port not in (None, 443)):
        raise CheckError("Invalid GitHub OIDC request endpoint.")
    query = parse.parse_qsl(oidc_url.query, keep_blank_values=True)
    query = [(key, value) for key, value in query if key != "audience"]
    query.append(("audience", "api://AzureADTokenExchange"))
    assertion = json_response(
        parse.urlunsplit(oidc_url._replace(query=parse.urlencode(query))),
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
            "scope": "https://storage.azure.com/.default",
            "grant_type": "client_credentials",
            "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            "client_assertion": assertion,
        }).encode(),
    ).get("access_token")
    if not token:
        raise CheckError("Azure did not return a storage access token.")
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
