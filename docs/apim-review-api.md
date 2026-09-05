# Governed review API

[Overview](../README.md) / APIM review API

The optional API exposes `POST /reviews/responses` and forwards to a named
coordinator in the private Foundry project. Changing the selected agent does
not require a different client URL. The Terraform resources and policy have
passed local validation; the API is not yet published or live-tested.

## Publication prerequisites

- Deploy APIM and verify private DNS, VNet integration, and project RBAC.
- Deploy the selected coordinator and pass every live specialist check first.
- Obtain an approved single-tenant Entra API registration and the exact audience
  emitted in its access tokens. This sample accepts a GUID or `api://GUID`.
- Approve both client application IDs and caller principal object IDs. For
  app-only callers, the object ID is the tenant's service principal object ID,
  not its application ID. For delegated access, it is the user's object ID.
- Configure the appropriate delegated permission or application permission and
  consent for token acquisition. Terraform does not create registrations, grant
  consent, or broaden tenant access.

Supply the following object in reviewed local Terraform configuration, replacing
all placeholders with non-secret approved identifiers. Leave `review_api = null`
to keep the route unpublished.

```hcl
enable_api_management = true
review_api = {
  audience                  = "<dedicated-api-audience>"
  allowed_caller_object_ids = ["<approved-principal-object-id>"]
  allowed_client_app_ids    = ["<approved-client-application-id>"]
  agent_name               = "customer-review-coordinator"
}
```

Review a full Terraform plan before applying it; do not apply unrelated
infrastructure changes merely to publish this API. State and plan files must
remain restricted because other infrastructure resources contain credentials.
After applying, retrieve `review_api_url` from Terraform outputs.

## Request contract

Send an Entra bearer access token for the configured audience and
`Content-Type: application/json`. The complete accepted body is:

```json
{"input":"Review this application: CRIT-1 requires a budget; APP-1 contains none."}
```

The request schema permits a nonblank string of at most 60,000 characters and
rejects additional properties. The gateway also enforces a 65,536-byte body
limit. There are no file uploads, conversation IDs, caller-selected agents,
streaming, or caller-supplied model/tool overrides in this initial contract.

## Request flow and controls

1. Validate the Entra tenant, audience, client application ID, and `oid` allowlist.
2. Apply a per-principal limit of 10 calls per 60 seconds. Distributed APIM rate
   limiting is approximate, not a strict billing cap or concurrency semaphore.
3. Validate JSON against the operation's request schema before forwarding.
4. Rebuild the request with only `input`, `store=false`, and `stream=false`.
5. Replace caller authorization with APIM managed-identity authentication for
   `https://ai.azure.com`. Use the fixed named-agent backend and discard unmatched
   query parameters. No automatic retries or redirects are enabled.
6. Wait up to 180 seconds for backend response headers. This is not a total
   execution deadline and does not cancel remote work already accepted.
7. Return the Responses body with `x-correlation-id` and `Cache-Control: no-store`.

The operation depends on the authorization policy and request schema, so a
fresh deployment installs those before making the operation available. The API
has no default service URL; its backend is set only by its policy. Do not add
other operations or override this policy without reviewing the resulting flow.
Parent inbound/outbound policies are inherited and must also be reviewed for
logging, caching, and other behavior. This API adds no body logging or cache.

Policy failures map to sanitized JSON categories: `unauthorized` (401),
`rate_limited` (429), `invalid_request` (400, including oversized input), and
`backend_unavailable` (502, including backend authentication and timeout errors).
Errors include a correlation ID but not backend exception messages. APIM's
platform-level errors outside this policy may use its native response format.

HTTP 200 does not establish review correctness or specialist success. Clients
must inspect Responses status and correlated tool receipts, and handle a
clarifying question separately from a completed review. No automatic business
decision or record-level authorization is supplied by this gateway.

## Acceptance gates

Run the local checks without deploying Azure resources:

```powershell
./terraform/test-review-api-validation.ps1
terraform -chdir=terraform validate
```

Before calling the route usable, verify it in Azure with synthetic input:

| Test | Expected result |
| --- | --- |
| Approved caller, application and case requests | Completed response with expected correlated specialist receipts |
| Missing, expired, wrong-tenant, or wrong-audience token | 401, no backend call |
| Correct audience but unapproved client or principal | 401, no backend call |
| Invalid JSON, blank input, extra properties | 400, no backend call |
| Oversized body | 400, no backend call |
| Burst over configured caller limit | 429, allowing for distributed-counter approximation |
| Controlled backend failure/timeout in a test environment | Sanitized 502, no exception text or review body |
| Successful and failed requests | Correlation ID present; sensitive bodies absent from gateway diagnostics |

Offline tests check Terraform inputs and rendered XML, not Azure's policy
compiler, token validation, DNS, schema enforcement, or the live error contract.
Do not use live customer records for acceptance tests. The source profile smoke
tests already passed privately but do not establish APIM-to-Foundry connectivity.