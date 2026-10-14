# Governed review API

[Home](../README.md) / [Docs](README.md) / Governed review API

The optional review API runs through Azure API Management (APIM). It exposes
`POST /reviews/responses` and forwards each request to a named coordinator in
the private Foundry project, so changing the selected agent doesn't require a
different client URL. Below you'll find the inputs, prerequisites, steps, and
acceptance gates for publishing it.

> [!IMPORTANT]
> APIM is currently disabled to avoid idle capacity charges. The Terraform module
> and policy are retained. To redeploy, set `enable_api_management = true` and
> `approve_public_api_management = true` in local configuration, review the plan
> and current networking and cost requirements, and apply from the private
> runner. The gateway is publicly reachable, so approve that exposure first. Basic and Basic v2 don't
> support this private backend connection. If Azure retains the deleted service
> name, review soft-delete recovery before reusing it. Don't purge recovery data
> automatically.

## In this guide

- [At a glance](#at-a-glance)
- [Terraform inputs](#terraform-inputs)
- [Publication prerequisites](#publication-prerequisites)
- [Publication steps](#publication-steps)
- [Request contract](#request-contract)
- [Request flow and controls](#request-flow-and-controls)
- [Acceptance gates](#acceptance-gates)
- [Related content](#related-content)

## At a glance

| Item | Value |
| --- | --- |
| Client route | `POST /reviews/responses` |
| APIM API and operation | API path `reviews`, operation `POST /responses` |
| Policy file | `terraform\policies\review.xml.tftpl` |
| Backend route | `/responses?api-version=v1` on the selected named-agent endpoint |
| Authentication | Microsoft Entra ID bearer token for the configured tenant, audience, client application ID, and `oid` allowlist |
| Backend identity | APIM managed identity for `https://ai.azure.com` |
| Rate limit | 10 calls per principal per 60 seconds |
| Request size | Nonblank `input` up to 60,000 characters and an APIM body limit of 65,536 bytes |
| Backend wait | Up to 180 seconds for response headers |
| Cache behavior | `Cache-Control: no-store` |
| Default state | No APIM service or review API is deployed unless you enable it |

## Terraform inputs

Configure APIM only in reviewed local Terraform input. Keep secrets out of source
control and protect any plan or state files that include these values.

| Variable or field | Purpose and validation |
| --- | --- |
| `enable_api_management` | Creates a one-unit Standard v2 APIM gateway. Defaults to `false`. |
| `approve_public_api_management` | Approval for the publicly reachable gateway. Defaults to `false`. Terraform refuses to plan with `enable_api_management = true` until it is `true`. |
| `api_management_location` | Azure region for APIM and its virtual network (VNet) integration subnet. Defaults to `westus`. Allowed values are `westus`, `westus3`, `southcentralus`, and `northcentralus`. When APIM is enabled, it must equal `jumpbox_location` for the shared management VNet region. |
| `api_management_subnet_address_prefixes` | Address prefixes for the dedicated APIM VNet integration subnet. Defaults to `["10.43.1.0/24"]`. |
| `api_management_publisher_email` | Publisher email. Required when APIM is enabled and validated as an email address. |
| `api_management_publisher_name` | Publisher name shown by APIM. Defaults to `Foundry Agent Accelerator`. |
| `review_api` | Optional coordinator API authorization object. Defaults to `null`, which leaves the API unpublished. Requires `enable_api_management = true` when set. |
| `review_api.audience` | Dedicated Microsoft Entra ID API audience. Terraform accepts a GUID or `api://GUID`, and it rejects a general Azure audience. |
| `review_api.allowed_caller_object_ids` | Nonempty set of approved caller principal object IDs. For app-only callers, use the tenant's service principal object ID, not the application ID. For delegated access, use the user's object ID. |
| `review_api.allowed_client_app_ids` | Nonempty set of approved client application IDs. |
| `review_api.agent_name` | Named coordinator endpoint. Defaults to `review-coordinator-agent`. Use a valid named agent, not a URL or path. |

## Publication prerequisites

Complete these prerequisites before you publish the route:

- [ ] Deploy APIM and verify private Domain Name System (DNS), VNet integration,
      and project role-based access control (RBAC).
- [ ] Deploy the selected coordinator and pass every live specialist check first.
- [ ] Obtain an approved single-tenant Microsoft Entra ID API registration and
      the exact audience emitted in its access tokens. This sample accepts a GUID
      or `api://GUID`.
- [ ] Approve both client application IDs and caller principal object IDs. For
      app-only callers, the object ID is the tenant's service principal object ID,
      not its application ID. For delegated access, it is the user's object ID.
- [ ] Configure the appropriate delegated permission or application permission
      and consent for token acquisition. Terraform doesn't create registrations,
      grant consent, or broaden tenant access.

## Publication steps

Run commands from the repository root, using an approved private
backend-connected environment. Stop on errors. These steps are optional; don't
enable APIM just to use the internal Lab.

1. Configure the approved gateway and callers.

   Supply the following object in reviewed local Terraform configuration,
   replacing all placeholders with non-secret approved identifiers. Leave
   `review_api = null` to keep the route unpublished.

   ```hcl
   enable_api_management = true
   approve_public_api_management = true
   api_management_publisher_email = "<approved-publisher-email>"
   review_api = {
     audience                  = "<dedicated-api-audience>"
     allowed_caller_object_ids = ["<approved-principal-object-id>"]
     allowed_client_app_ids    = ["<approved-client-application-id>"]
     agent_name               = "customer-review-coordinator"
   }
   ```

2. Initialize and validate Terraform.

   Follow the [baseline Terraform procedure](../terraform/README.md#2-initialize-and-validate)
   with the existing environment's variables and state, starting at
   initialization. Run the local [acceptance checks](#acceptance-gates) before
   planning.

3. Review the saved plan.

   Review the full saved plan. Don't apply unrelated infrastructure changes
   merely to publish this API. State and plan files can contain sensitive data,
   so keep them restricted.

4. Apply only the reviewed plan.

   Apply only the reviewed plan, then delete it after the attempt or when the
   attempt is abandoned.

5. Retrieve the URL and verify live behavior.

   After a successful apply, run:

   ```powershell
   terraform -chdir=terraform output -raw review_api_url
   ```

   The expected result is the review endpoint URL. An output URL isn't proof of
   authorization or backend connectivity. Complete every live
   [acceptance gate](#acceptance-gates) with fictional inputs before calling the
   route usable. On failure, inspect the policy and backend. Don't broaden caller
   permissions or weaken receipt checks to make the test pass.

## Request contract

Send a Microsoft Entra bearer access token for the configured audience and
`Content-Type: application/json`. The complete accepted body is:

```json
{"input":"Review this application: CRIT-1 requires a budget; APP-1 contains none."}
```

The request schema permits a nonblank string of at most 60,000 characters and
rejects additional properties. The gateway also enforces a 65,536-byte body
limit. There are no file uploads, conversation IDs, caller-selected agents,
streaming, or caller-supplied model or tool overrides in this initial contract.

## Request flow and controls

1. Validate the Microsoft Entra tenant, audience, client application ID, and
   `oid` allowlist.
2. Apply a per-principal limit of 10 calls per 60 seconds. Distributed APIM rate
   limiting is approximate, not a strict billing cap or concurrency semaphore.
3. Validate JSON against the operation's request schema before forwarding.
4. Rebuild the request with only `input`, `store=false`, and `stream=false`.
5. Replace caller authorization with APIM managed-identity authentication for
   `https://ai.azure.com`. Use the fixed named-agent backend and discard unmatched
   query parameters. No automatic retries or redirects are enabled.
6. Wait up to 180 seconds for backend response headers. This isn't a total
   execution deadline, and it doesn't cancel remote work already accepted.
7. Return the Responses body with `x-correlation-id` and
   `Cache-Control: no-store`.

| Header or route | Policy behavior |
| --- | --- |
| `Authorization` | Validated as a Microsoft Entra ID bearer token by `validate-azure-ad-token`. |
| `Content-Type` | Required as `application/json` on the request and overridden to `application/json` before forwarding. Error responses also set `Content-Type: application/json`. |
| `api-key` | Deleted before forwarding. |
| `Ocp-Apim-Subscription-Key` | Deleted before forwarding. |
| `x-ms-client-request-id` | Overridden with the APIM request ID before forwarding. |
| `x-correlation-id` | Returned on successful and policy-generated error responses. |
| `Cache-Control` | Returned as `no-store` on successful and policy-generated error responses. |
| `/responses?api-version=v1` | APIM rewrites to this backend route and sets `copy-unmatched-params="false"`. |

The operation depends on the authorization policy and request schema, so a fresh
deployment installs those before making the operation available. The API has no
default service URL; its backend is set only by its policy. Don't add other
operations or override this policy without reviewing the resulting flow. Parent
inbound and outbound policies are inherited and must also be reviewed for
logging, caching, and other behavior. This API adds no body logging or cache.

Policy failures map to sanitized JSON categories: `unauthorized` (401),
`rate_limited` (429), `invalid_request` (400, including oversized input), and
`backend_unavailable` (502, including backend authentication and timeout errors).
Errors include a correlation ID but not backend exception messages. APIM's
platform-level errors outside this policy may use its native response format.

HTTP 200 doesn't establish review correctness or specialist success. Clients must
inspect Responses status and correlated tool receipts, and handle a clarifying
question separately from a completed review. This gateway supplies no automatic
business decision or record-level authorization.

## Acceptance gates

Run the local checks without deploying Azure resources:

```powershell
./terraform/test-review-api-validation.ps1
terraform -chdir=terraform validate
```

The expected result is that Terraform input validation and rendered policy checks
pass locally. These checks don't contact Azure.

Before calling the route usable, verify it in Azure with fictional input:

| Test | Expected result |
| --- | --- |
| Approved caller, application and case requests | Completed response with expected correlated specialist receipts |
| Missing, expired, wrong-tenant, or wrong-audience token | 401, no backend call |
| Correct audience but unapproved client or principal | 401, no backend call |
| Invalid JSON, blank input, extra properties | 400, no backend call |
| Oversized body | 400, no backend call |
| Burst over configured caller limit | 429, allowing for distributed-counter approximation |
| Controlled backend failure or timeout in a test environment | Sanitized 502, no exception text or review body |
| Successful and failed requests | Correlation ID present; sensitive bodies absent from gateway diagnostics |

Offline tests check Terraform inputs and rendered XML, not Azure's policy
compiler, token validation, DNS, schema enforcement, or the live error contract.
Don't use live customer records for acceptance tests. Agent-profile smoke tests
don't establish APIM-to-Foundry connectivity. Test the gateway path separately.

## Related content

- [Optional integrations](optional-integrations.md)
- [Application ingress options](ingress-access.md)
- [Coordinator profiles](agent-profiles.md)
- [Infrastructure](../terraform/README.md)
- [Private deployment runbook](private-deployment.md)
