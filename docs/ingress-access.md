# Optional application ingress: Application Gateway and Front Door

[Overview](../README.md) / [Architecture](architecture.md) / Application ingress

This is **design and deployment guidance**, not an implemented gateway module.
Neither Application Gateway nor Front Door is deployed by this repository.
Adopting either requires separately reviewed infrastructure and application
configuration changes; following this guide does not change the private baseline.
Check the linked Microsoft guidance and regional feature availability before
planning a deployment.

Expose the **Lab application**, not every Foundry endpoint. The browser loads
React and calls the same application's FastAPI routes. FastAPI uses managed
identity to invoke the configured named agent; agents call their models and tools.
The browser does not receive Azure keys or need Foundry project permissions.
Foundry, Cosmos, and the other platform dependencies stay private.

## Choose an access pattern

| Requirement | Preferred starting point | Boundary |
| --- | --- | --- |
| Existing controlled demonstration | Current private Lab URL | Browser must have private routing, DNS, and an allowed source address. No new gateway cost. |
| Internal employee application with a regional gateway | Application Gateway WAF v2 with a private frontend | Clients still need approved private connectivity. Entra sign-in and application authorization are separate requirements. |
| Regional internet-facing application | Application Gateway WAF v2 with a public HTTPS listener | Only the gateway listener is public; the Container Apps origin and Foundry remain private. |
| Global internet-facing application | Front Door Premium with WAF and Private Link to Container Apps | The frontend is public. The origin connection is private. Multi-region application deployment is separate work. |
| Partner/service API rather than a website | A governed application API or the optional APIM path | See the [APIM API guide](apim-review-api.md); a web gateway is not a substitute for API authorization and quotas. |

Start with **Application Gateway** for this repo's existing regional, VNet-injected
internal Container Apps environment. Choose **Front Door Premium** when global
ingress, edge delivery, or routing across independently prepared regional origins
is a requirement. Do not chain both by default.

Front Door is not an internal-only access solution: its Private Link feature
protects **Front Door-to-origin**, not **user-to-Front Door**. Standard does not
support the private-origin configuration described here.

## Current repository boundaries

The [Lab infrastructure](../workbench/infra/main.tf) configures:

- An internal Container Apps load balancer, workload profiles, and disabled
  environment public network access.
- App-level `external_enabled = true`. This publishes the app at the environment
  boundary so a gateway outside that environment can reach it; it does **not**
  make this internal environment internet-accessible.
- A `jumpbox-only` IP restriction allowing the management subnet.
- Private DNS records pointing the app's hostname at the internal environment IP,
  with links to the workload and management VNets.
- `WORKBENCH_ALLOWED_HOSTS` and `WORKBENCH_ORIGINS` fixed to the existing hostname.

From an initialized, authorized state-connected administrative environment, inspect
the current non-secret output values:

```powershell
terraform -chdir="workbench\infra" output -raw private_url
terraform -chdir="workbench\infra" output -raw internal_ip
```

These outputs do not prove that a new gateway can resolve or reach the origin.
Peering or VPN access alone also does not satisfy the current IP allowlist.
Do not switch app ingress to environment-only access: the app's FQDN would no
longer be reachable by a gateway elsewhere in the VNet.

**Before expanding access:** the Lab currently has no end-user login and shared
conversation/review records. Use fictional data only. Require authenticated
users and server-side user/tenant ownership checks before exposing confidential
records or onboarding independent users. A WAF, private endpoint, or managed
identity does not supply those application authorization checks.

### Private demonstration versus broader access

End-user Entra configuration is **not a prerequisite for the existing private
lab**, or for demonstrating a private Application Gateway in front of it.
Backend/agent managed identities continue to authenticate Azure resource access;
this is different from signing users into the application.

| Mode | Requirements |
| --- | --- |
| Private shared demonstration | Trusted operators only, approved private routing/DNS/source restrictions, fictional inputs, and explicit acknowledgement that saved records are shared. No end-user login or per-user isolation is claimed. |
| Internet-facing or confidential/multi-user application | Implement user authentication and server-side agent/record authorization before opening access. Select an identity provider appropriate to the audience; the current Lab does not implement this mode. |

The **Shared lab** header control opens the shared-demo details across desktop
and mobile views. It does not enforce that inputs are synthetic. Do not substitute
a shared password or a WAF policy for user identity and record ownership. Keep the public
Application Gateway and Front Door patterns as design references until their
broader-access requirements can be met.

## Pattern A: Application Gateway WAF v2

```text
Employee on approved private network OR internet user
                         |
                HTTPS (see access requirements)
                         |
       Application Gateway WAF v2 listener
            (private OR public frontend)
                         |
             HTTPS over private VNet routing
                         |
       Internal Container Apps: React + FastAPI
                         |
           Managed identity + private connectivity
                         |
             Named Foundry agent -> models/tools
```

Use Microsoft's [Container Apps and Application Gateway guide][appgw-guide] as
the service configuration reference, adapting it to the existing resources:

1. **Choose the audience and listener.** Use a private frontend and private DNS
   for internal users, or a public HTTPS listener for internet users. Current
   [private Application Gateway v2 guidance][appgw-private] supports private-only
   deployments through the documented feature opt-in. Verify subscription
   registration and gateway provisioning requirements; do not assume an older
   tutorial's public-IP requirement applies to the private-only configuration.
2. **Provide gateway networking.** Use an appropriately sized, dedicated gateway
   subnet and reviewed NSGs/routes. Resolve the existing Container Apps FQDN to
   its internal IP from the gateway's configured DNS path. If the gateway is in
   another VNet, configure both routing and DNS forwarding/zone links.
3. **Configure the origin.** Target the app FQDN over HTTPS/443, with backend
   host/SNI and certificate validation matching that hostname. Do not send
   production traffic directly to port 8080 or disable certificate checks.
4. **Review ingress restrictions.** The current management-subnet rule does not
   permit a new gateway subnet automatically. Add only the required gateway path
   after verifying the source addresses evaluated by Container Apps. Retain
   administrative access only where explicitly approved.
5. **Configure the listener, WAF and probes.** Bind the chosen domain/certificate,
   attach a WAF policy, and use a custom HTTPS **GET** probe to `/healthz` with the
   accepted origin host. Finish the shared hostname/authentication and HTTP
   requirements below before admitting users.

Private DNS is needed on the **gateway-to-origin** path even when the gateway has
a public frontend. Public DNS for the user-facing domain points to the gateway,
not the internal app IP or a Foundry model endpoint.

## Pattern B: Front Door Premium with Private Link

```text
Internet user
     |
HTTPS + app sign-in
     |
Front Door Premium public endpoint + WAF
     |
Front Door-managed Private Link connection
     |
Container Apps environment origin: React + FastAPI
     |
Managed identity + private connectivity
     |
Named Foundry agent -> models/tools
```

Follow Microsoft's [Front Door-to-Container Apps integration guide][afd-guide]
and [Private Link requirements][afd-private]:

1. **Verify the environment and region.** Direct integration requires a
   workload-profiles environment; a Consumption workload profile is not the same
   as a legacy Consumption-only environment. The repo uses workload profiles,
   but verify the actual environment and regional feature availability before
   planning. Do not recreate the internal environment merely to match a tutorial
   that provisions a new one; environment accessibility is a creation-time choice.
2. **Create a Premium profile and private origin.** Select the Container Apps
   origin and the existing environment resource, enable Private Link, and use
   target subresource `managedEnvironments`. An ordinary private DNS A record or
   the Lab's existing VNet connectivity is not a Front Door origin connection.
3. **Select a supported Private Link location.** Front Door's supported Private
   Link regions are not identical to the model/Foundry region list. The current
   list does not include the repo's default `northcentralus`; Microsoft documents
   choosing a nearby supported Private Link region, with an additional latency
   consideration. Verify the current list and origin support rather than moving
   the Foundry deployment to make the region names match.
4. **Approve only the intended connection.** Inspect the pending request on the
   Container Apps environment and verify its association with the approved Front
   Door origin. Approve the expected request(s), not every pending connection
   based solely on its descriptive message.
5. **Keep origin public access disabled.** Keep app ingress enabled and validate
   how the existing ingress IP restriction evaluates traffic on this private
   path. Do not assume the management-subnet rule permits Front Door, copy an
   Application Gateway subnet rule, or replace the policy with an internet-wide
   allow rule to resolve a connectivity failure.
6. **Configure routes, TLS, WAF and probes.** Route the website and `/api/*` to the
   same intended origin, explicitly set the origin host header, keep TLS
   certificate-name validation enabled, and use HTTPS **GET** `/healthz` probes.
   Disable route caching initially. Bind and validate the custom frontend domain.

Approve and verify the private connection before switching DNS or production
traffic. An origin configuration that saves successfully is not proof of
connectivity. Front Door does not need Application Gateway in this direct pattern.

## Shared application and HTTP requirements

### Hostnames, TLS, and sign-in

Use a deliberate hostname strategy. For the simplest initial routing setup,
the proxy connects using the Container Apps FQDN as the origin host/SNI while
the browser uses a separate custom HTTPS domain. Configure:

| Setting | Required alignment |
| --- | --- |
| Browser-facing DNS and certificate | Resolve to the selected edge and present a certificate for the user-facing domain. |
| Origin host/SNI and certificate | Match the Container Apps hostname, or a deliberately bound origin custom domain. Validate certificates on both TLS hops. |
| `WORKBENCH_ALLOWED_HOSTS` | Exact hostnames the backend actually receives, including the origin/probe host. Do not use a wildcard. |
| `WORKBENCH_ORIGINS` | Exact browser HTTPS origin(s), including the new custom domain. Do not rewrite the browser's `Origin` header to bypass this check. |
| Authentication callbacks and cookies | Use the user-facing HTTPS domain, reviewed redirect URIs, and appropriate secure cookie/CSRF settings. Verify sign-in and sign-out through the proxy. |
| Forwarded headers | Trust only the known proxy chain. Do not use arbitrary client-supplied forwarded IP/host or identity headers for authorization. |

The app supports explicit host/origin lists, but the current Terraform sets only
the private hostname. Adding an edge domain needs reviewed configuration changes;
the guide does not introduce new Terraform variables. With origin-host rewriting,
ensure the chosen authentication integration understands the original external
host securely; otherwise redirects can send users to an unreachable internal
hostname. Preserving the external host instead requires an appropriate origin
domain binding and TLS setup, not just an extra allowed-host entry.

[Container Apps built-in authentication][aca-auth] is one option for Entra sign-in
when adopting the broader-access mode above. In that mode, require authentication
for application routes, then enforce agent and record permissions in the backend.
Return appropriate API authentication errors instead
of silently serving a login HTML page to a JSON request. If health probes require
an unauthenticated path, exempt only a minimal health response; never exempt the
entire `/api/*` namespace.

### Timeouts, caching, WAF, and application state

- **Long requests:** the current backend can wait up to 180 seconds for an agent.
  Align browser, gateway/origin-response, Container Apps, and backend timeouts,
  allowing for upload and processing overhead. Do not leave a shorter edge
  default that cuts off valid reviews. Container Apps documents a 240-second
  HTTP ingress timeout; verify each edge's current limits and test the complete
  chain. Raising one timeout does not raise the others or cancel remote work.
- **No unsafe replay:** do not enable proxy retry/replay policies for inference,
  save, or review-start POSTs. A timeout does not prove the original operation
  failed. Check persisted state before a user retries an uncertain save/start.
- **Streaming:** the current Lab returns non-streaming JSON. If SSE or WebSockets
  are added later, validate protocol support, buffering, idle/response timeouts
  and disconnect handling at every hop. A streaming-capable model alone does not
  make the frontend path streaming-capable.
- **Caching:** start with caching disabled. Never cache `/api/*`, authentication
  endpoints, transcripts, or personalized responses. Preserve API `no-store`,
  HTML revalidation, and error behavior. Enable caching only for reviewed
  fingerprinted static assets after confirming no personalized data is included.
- **WAF:** enable the appropriate managed rules and tune narrowly with synthetic
  requests. Test legitimate evidence text and the application's 64 KiB request
  boundary. Do not disable body inspection or whole rule groups merely because
  a review prompt triggers a rule. WAF is not a prompt-injection defense for tools
  or retrieved documents.
- **Diagnostics:** preserve the app's correlation IDs and record edge request
  metadata. Review WAF match details and access-log fields for sensitive excerpts,
  query strings, tokens, and cookies. Avoid prompt/body logging; define retention,
  access, and alert recipients for gateway diagnostics.
- **Health:** `/healthz` checks process health, not Foundry model-generation quality.
  The cached `/api/health/dependencies` reports dependency access separately.
  Never use a billable agent invocation as an edge health probe. GET is explicit
  because the current app declares a GET health route; do not assume HEAD works.
- **Scaling/failover:** the Lab has one replica, process-local admission controls
  and local background review tasks. A global edge does not make those tasks
  durable or the app active-active. Do not add replicas, regional origins or
  cross-region failover without reviewing work ownership, data consistency,
  identity, quotas, and recovery.

## Acceptance checks before publishing the URL

Use synthetic data and test from both intended and unintended network locations.
Record the selected edge, app revision, DNS/TLS configuration and results.
Use the authentication and per-user authorization gates for broader-access
deployments. For a private demonstration without sign-in, record those capabilities
as **not implemented**, verify the private-demo boundary below, and do not
describe the result as ready for public or confidential multi-user access.

| Check | Required result |
| --- | --- |
| DNS and TLS | Browser reaches the intended listener; the gateway resolves/reaches its private origin; certificates validate on both hops. |
| Origin isolation | Direct origin access from the public internet fails while the authorized edge path succeeds. Any retained private administrator bypass is documented, not presented as edge-only enforcement. |
| Private-demo boundary | Only approved private sources can reach the app, public ingress remains closed, the Shared lab control exposes the shared-data details on desktop and mobile, and test inputs are fictional. This does not establish individual user identity or record isolation. |
| Authentication (broader access) | Anonymous access to protected application/API routes is denied; sign-in/out use the correct public or private frontend domain without redirect loops. |
| Authorization (broader access) | A user cannot access another user's records or invoke an unauthorized agent. This is an implementation gate, not current Lab behavior. |
| Host and origin checks | Approved browser requests succeed; unapproved Host/Origin values remain rejected. Do not weaken these controls to pass a probe. |
| Frontend and chat | HTML/assets load, `/api/config` returns the approved catalog, and a synthetic `POST /api/reviews` completes through the edge with expected specialist receipts where applicable. |
| History and review records | Save/reopen/update work through the edge; ETag conflicts remain conflicts and do not get cached or retried into duplicate operations. |
| Long request and failure | A representative slow review completes within the reviewed budget; backend unavailability and timeouts produce observable failures, not false success or automatic POST replay. |
| Cache and logging | No API/auth/private data is cached or unexpectedly logged. Correlation IDs support tracing without transcript content. |
| Health and WAF | The GET probe succeeds without model calls; representative valid requests pass and narrowly defined unwanted traffic is blocked. |

### Troubleshooting

| Symptom | Inspect first |
| --- | --- |
| Origin unhealthy or edge 502/504 | Private DNS/routing or Private Link approval, origin host/SNI, TLS validation, GET probe path, ingress source restrictions, and timeout settings. |
| Homepage loads but chat fails with 400/403 | Backend allowed hosts/origins, `/api/*` route configuration, WAF matches, app authentication, and original request size. |
| Front Door cannot reach an otherwise working internal URL | Premium tier, the correct environment/subresource, supported Private Link location, connection approval, and private-path ingress behavior. A browser in the VNet is a different access path. |
| Login loop or redirect to the internal hostname | Redirect URI registration, cookie settings, origin-host strategy, and trusted forwarded-host/protocol handling. |
| Review fails only after a fixed delay | Compare all timeout layers; preserve correlation IDs and check whether remote work or a saved record already exists before retrying. |
| Direct public origin still works | Recheck environment public access, alternate origins/routes and DNS. Do not rely on an obscure origin URL or a forwarded header as the access boundary. |

## Cost, rollout, and ownership

Both options add costs beyond model tokens: gateway/profile capacity, WAF,
requests/data transfer, diagnostics and certificates where applicable. Front Door
Premium also requires evaluating private endpoint-related charges. Get a current
regional estimate; neither is a free wrapper around the existing app. Do not add
either to default deployment or the deployed cost baseline until it is approved.

Roll out to an isolated test hostname first, then complete the acceptance checks
before switching production DNS. Preserve the existing management access path
and state separation. Review Terraform plans for resource replacement, especially
the Container Apps environment; do not adopt tutorial cleanup steps that delete
the shared resource group. Roll back only the new ingress/DNS changes if needed,
not the Foundry foundation or application data.

Future Terraform examples should be optional, use the existing application's
outputs as inputs, and clearly own their gateway, certificates, DNS, diagnostic
settings and approved application configuration changes. This document does not
add those examples or claim that either path has been deployed and live-tested.
APIM remains a separate [optional API-governance integration](optional-integrations.md).

## Microsoft references

- [Application Gateway WAF with internal Container Apps][appgw-guide]
- [Private Application Gateway v2 deployments][appgw-private]
- [Front Door Premium with Container Apps Private Link][afd-guide]
- [Front Door Private Link origins, regions, and restrictions][afd-private]
- [Front Door origins, host headers, TLS and health probes][afd-origin]
- [Container Apps ingress and HTTP limits][aca-ingress]
- [Container Apps authentication][aca-auth]

[appgw-guide]: https://learn.microsoft.com/azure/container-apps/waf-app-gateway
[appgw-private]: https://learn.microsoft.com/azure/application-gateway/application-gateway-private-deployment
[afd-guide]: https://learn.microsoft.com/azure/container-apps/how-to-integrate-with-azure-front-door
[afd-private]: https://learn.microsoft.com/azure/frontdoor/private-link
[afd-origin]: https://learn.microsoft.com/azure/frontdoor/origin
[aca-ingress]: https://learn.microsoft.com/azure/container-apps/ingress-overview
[aca-auth]: https://learn.microsoft.com/azure/container-apps/authentication
