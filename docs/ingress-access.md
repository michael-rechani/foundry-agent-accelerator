# Optional application ingress

[Home](../README.md) / [Docs](README.md) / [Architecture](architecture.md) / Application ingress

Use this guide to plan Azure Application Gateway or Azure Front Door access to
the Lab. The guide is for operators and architects who need a reviewed ingress
pattern while keeping Microsoft Foundry, Azure Cosmos DB, and other platform
dependencies private.

> [!IMPORTANT]
> This repository does **not** deploy Application Gateway. For Front Door, it
> holds one opt-in, off-by-default Terraform draft that admits only your own IP
> (see [Draft: Front Door limited to your own IP](#draft-front-door-limited-to-your-own-ip)).
> Nothing is applied until you approve each public resource, and the private
> baseline doesn't change. Anything beyond that draft requires separately
> reviewed infrastructure, Domain Name System (DNS), certificate, application,
> and cost changes. Check the linked Microsoft guidance and regional feature
> availability before planning a deployment.

Expose the Lab application, not every Foundry endpoint. The browser loads React
and calls the same application's FastAPI routes. FastAPI uses managed identity to
invoke the configured named agent. Agents call their models and tools. The
browser doesn't receive Azure keys or need Foundry project permissions.

## In this guide

- [Choose an ingress pattern](#choose-an-ingress-pattern)
- [Current repository boundaries](#current-repository-boundaries)
- [Who uses the Lab today](#who-uses-the-lab-today)
- [Pattern A: Application Gateway WAF v2](#pattern-a-application-gateway-waf-v2)
- [Pattern B: Front Door Premium with Private Link](#pattern-b-front-door-premium-with-private-link)
- [Shared application and HTTP requirements](#shared-application-and-http-requirements)
- [Acceptance checks before publishing the URL](#acceptance-checks-before-publishing-the-url)
- [Cost, rollout, and ownership](#cost-rollout-and-ownership)
- [Related content](#related-content)

## Choose an ingress pattern

Start by choosing the edge that matches the audience and routing model. Both
options can use a web application firewall (WAF), and both add resources and
operational cost beyond the private demo.

| Option | When to use | Private origin support | WAF | Cost notes | What's required |
| --- | --- | --- | --- | --- | --- |
| Application Gateway WAF v2 | Regional access to the existing virtual network (VNet)-injected Container Apps environment. Use a private frontend for internal users or a public listener for a regional website. | Reaches the internal Container Apps origin over private VNet routing and private DNS. | Uses an Application Gateway WAF policy on the listener. | Adds gateway capacity, WAF, diagnostics, certificates, and data transfer costs. | Dedicated gateway subnet, reviewed routes and network security groups (NSGs), origin DNS, host and Transport Layer Security (TLS) alignment, updated ingress allowlists, and application authentication for broader access. |
| Front Door Premium | Global internet-facing entry point, edge delivery, or routing across independently prepared regional origins. | Uses Front Door-managed Private Link from Front Door to the Container Apps environment origin. Standard doesn't support this private-origin pattern. | Uses a Front Door WAF policy on the public endpoint. | Adds Premium profile, WAF, requests, data transfer, diagnostics, certificates, and private endpoint-related charges. | Supported Private Link location, approved origin connection, origin host header and TLS validation, routes and probes, custom domain, and application authentication for broader access. |

| Requirement | Preferred starting point | Boundary |
| --- | --- | --- |
| Existing controlled demonstration | Current private Lab URL | Browser must have private routing, DNS, and an allowed source address. No new gateway cost. |
| Internal employee application with a regional gateway | Application Gateway WAF v2 with a private frontend | Clients still need approved private connectivity. Microsoft Entra ID sign-in and application authorization are separate requirements. |
| Regional internet-facing application | Application Gateway WAF v2 with a public HTTPS listener | Only the gateway listener is public. The Container Apps origin and Foundry remain private. |
| Global internet-facing application | Front Door Premium with WAF and Private Link to Container Apps | The frontend is public. The origin connection is private. Multi-region application deployment is separate work. |
| Partner or service API rather than a website | A governed application API or the optional Azure API Management (APIM) path | See the [governed review API guide](apim-review-api.md). A web gateway isn't a substitute for API authorization and quotas. |

Start with Application Gateway for this repository's existing regional,
VNet-injected internal Container Apps environment. Choose Front Door Premium when
global ingress, edge delivery, or routing across independently prepared regional
origins is a requirement. Don't chain both by default.

Front Door isn't an internal-only access solution. Its Private Link feature
protects **Front Door-to-origin**, not **user-to-Front Door**. Standard doesn't
support the private-origin configuration described here.

## Current repository boundaries

Before designing an edge, verify what the [Lab infrastructure](../workbench/infra/main.tf)
already configures:

- [ ] An internal Container Apps load balancer, workload profiles, and disabled
      environment public network access.
- [ ] App-level `external_enabled = true`. This publishes the app at the
      environment boundary so a gateway outside that environment can reach it. It
      doesn't make this internal environment internet-accessible.
- [ ] A `jumpbox-only` Internet Protocol (IP) restriction that allows the
      management subnet.
- [ ] Private DNS records that point the app hostname at the internal environment
      IP, with links to the workload and management VNets.
- [ ] `WORKBENCH_ALLOWED_HOSTS` and `WORKBENCH_ORIGINS` fixed to the existing
      hostname.

From an initialized, authorized, state-connected administrative environment,
inspect the current non-secret output values:

```powershell
terraform -chdir="workbench\infra" output -raw private_url
terraform -chdir="workbench\infra" output -raw internal_ip
```

These outputs don't prove that a new gateway can resolve or reach the origin.
Peering or virtual private network (VPN) access alone also doesn't satisfy the
current IP allowlist. Don't switch app ingress to environment-only access. The
app's fully qualified domain name (FQDN) would no longer be reachable by a
gateway elsewhere in the VNet.

> [!WARNING]
> The Lab currently has no end-user login and uses shared conversation and review
> records. Use fictional data only. Require authenticated users and server-side
> user or tenant ownership checks before exposing confidential records or
> onboarding independent users. A WAF, private endpoint, or managed identity
> doesn't supply those application authorization checks.

### Who uses the Lab today

**Decision (#103): an operator presents the Lab from the jump box. Customers
don't use it themselves yet.**

- The Lab's environment is internal with public network access disabled, and the
  app only accepts the jump box's address, so a customer's browser can't reach
  it. That is intended for now.
- No public listener, Front Door, Application Gateway or IP allow rule is on by
  default. Each would be a separate approval of that specific resource. The one
  exception in code is the off-by-default
  [Front Door draft limited to your own IP](#draft-front-door-limited-to-your-own-ip)
  ([#240](https://github.com/michael-rechani/foundry-agent-accelerator/issues/240)),
  which stays off unless you set both of its switches.
- Chat is capped at 20 turns a minute across all users, and 4 at once, and each
  model deployment also has its own requests and tokens budget (see
  [Model limits](lab-configuration-and-cost.md#model-limits)). That is fine for one
  presenter and tight for a group. How many people can use the Lab at once hasn't
  been decided.
- To let customers use it themselves, first add end-user sign-in (Microsoft Entra
  ID) and per-user ownership of saved records. Then choose Pattern A or B below.

For the presenter's steps, see [Present from the jump box](showcase.md#present-from-the-jump-box).

### Private demonstration versus broader access

End-user Microsoft Entra ID configuration isn't a prerequisite for the existing
private Lab, or for demonstrating a private Application Gateway in front of it.
Backend and agent managed identities continue to authenticate Azure resource
access. That differs from signing users in to the application.

| Mode | Requirements |
| --- | --- |
| Private shared demonstration | Trusted operators only, approved private routing, DNS, source restrictions, fictional inputs, and explicit acknowledgement that saved records are shared. No end-user login or per-user isolation is claimed. |
| Internet-facing or confidential multi-user application | Implement user authentication and server-side agent and record authorization before opening access. Select an identity provider appropriate to the audience. The current Lab doesn't implement this mode. |

The **Shared lab** header control opens the shared-demo details across desktop
and mobile views. It doesn't enforce that inputs are fictional. Don't substitute
a shared password or a WAF policy for user identity and record ownership. Keep
the public Application Gateway and Front Door patterns as design references until
their broader-access requirements can be met.

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
the service configuration reference. Adapt it to the existing resources and
complete this checklist before admitting users:

- [ ] Choose the audience and listener. Use a private frontend and private DNS
      for internal users, or a public HTTPS listener for internet users. Current
      [private Application Gateway v2 guidance][appgw-private] supports
      private-only deployments through the documented feature opt-in. Verify
      subscription registration and gateway provisioning requirements. Don't
      assume an older tutorial's public IP requirement applies to the private-only
      configuration.
- [ ] Provide gateway networking. Use an appropriately sized, dedicated gateway
      subnet and reviewed NSGs and routes. Resolve the existing Container Apps
      FQDN to its internal IP from the gateway's configured DNS path. If the
      gateway is in another VNet, configure both routing and DNS forwarding or
      zone links.
- [ ] Configure the origin. Target the app FQDN over HTTPS/443, with backend
      host, Server Name Indication (SNI), and certificate validation matching that
      hostname. Don't send production traffic directly to port 8080 or disable
      certificate checks.
- [ ] Review ingress restrictions. The current management-subnet rule doesn't
      permit a new gateway subnet automatically. Add only the required gateway
      path after verifying the source addresses evaluated by Container Apps.
      Retain administrative access only where explicitly approved.
- [ ] Configure the listener, WAF, and probes. Bind the chosen domain and
      certificate, attach a WAF policy, and use a custom HTTPS **GET** probe to
      `/healthz` with the accepted origin host. Finish the shared hostname,
      authentication, and HTTP requirements before admitting users.

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
and [Private Link requirements][afd-private]. Complete this checklist before you
switch DNS or traffic:

- [ ] Verify the environment and region. Direct integration requires a workload
      profiles environment. A Consumption workload profile isn't the same as a
      legacy Consumption-only environment. The repository uses workload profiles,
      but verify the actual environment and regional feature availability before
      planning. Don't recreate the internal environment merely to match a tutorial
      that provisions a new one. Environment accessibility is a creation-time
      choice.
- [ ] Create a Premium profile and private origin. Select the Container Apps
      origin and the existing environment resource, enable Private Link, and use
      target subresource `managedEnvironments`. An ordinary private DNS A record
      or the Lab's existing VNet connectivity isn't a Front Door origin
      connection.
- [ ] Select a supported Private Link location. Front Door's supported Private
      Link regions aren't identical to the model or Foundry region list. The
      current list doesn't include the repository's default `northcentralus`.
      Microsoft documents choosing a nearby supported Private Link region, with
      an additional latency consideration. Verify the current list and origin
      support rather than moving the Foundry deployment to make the region names
      match.
- [ ] Approve only the intended connection. Inspect the pending request on the
      Container Apps environment and verify its association with the approved
      Front Door origin. Approve the expected request or requests, not every
      pending connection based only on its descriptive message.
- [ ] Keep origin public access disabled. Keep app ingress enabled and validate
      how the existing ingress IP restriction evaluates traffic on this private
      path. Don't assume the management-subnet rule permits Front Door, copy an
      Application Gateway subnet rule, or replace the policy with an
      internet-wide allow rule to resolve a connectivity failure.
- [ ] Configure routes, TLS, WAF, and probes. Route the website and `/api/*` to
      the same intended origin, explicitly set the origin host header, keep TLS
      certificate-name validation enabled, and use HTTPS **GET** `/healthz`
      probes. Disable route caching initially. Bind and validate the custom
      frontend domain.

Approve and verify the private connection before switching DNS or production
traffic. An origin configuration that saves successfully isn't proof of
connectivity. Front Door doesn't need Application Gateway in this direct pattern.

### Draft: Front Door limited to your own IP

[`workbench/infra/front-door.tf`](../workbench/infra/front-door.tf) implements
Pattern B for one person, from their own machine. It uses the Azure Verified Module
[`Azure/avm-res-cdn-profile/azurerm`](https://registry.terraform.io/modules/Azure/avm-res-cdn-profile/azurerm)
(pinned to 0.1.9) beside the existing Lab Terraform. It is off by default. It has
been applied once to the dev Lab to test it from a single address, and it is tracked in
[#240](https://github.com/michael-rechani/foundry-agent-accelerator/issues/240).
It changes the [#103 decision](#who-uses-the-lab-today) only for that one approved
path.

| What | How |
| --- | --- |
| Switches | `enable_front_door` creates it. `approve_public_front_door` must also be true, because the endpoint name is publicly resolvable. Without both, nothing is created. |
| Who gets in | The WAF runs in Prevention mode with one custom rule that blocks any client whose connecting address (`SocketAddr`) isn't in `front_door_allowed_cidrs`. Entries must be single hosts: `/32`, or `/128` for IPv6. At most 10 entries, and ranges, `0.0.0.0/0`, private, loopback, link-local, shared (CGNAT) and multicast addresses are rejected. `SocketAddr` is the address Front Door sees connecting, so a forged `X-Forwarded-For` header can't satisfy it. |
| Path to the Lab | Front Door Premium, then Private Link (`managedEnvironments`) to the internal environment. The Lab's own hostname is sent as the host header, with certificate-name checks on and a `GET /healthz` probe over HTTPS. Responses may take up to 200 seconds, to cover the Lab's 180-second review deadline. |
| Lab settings | The Front Door address is added to `WORKBENCH_ORIGINS` so the browser's origin check passes. `front_door_ingress_allow_cidrs` adds ingress rules after the jump box rule. Front Door's Private Link traffic arrives from the shared address space `100.64.0.0/10`, so set it to `["100.64.0.0/10"]` or the app answers Front Door's probes with 403. It is empty by default and accepts only private IPv4 ranges of `/16` or narrower, or `100.64.0.0/10` or narrower. |
| Region | Front Door Private Link doesn't support `northcentralus`. Set `front_door_private_link_location` (for example `centralus`) if the Lab is there. Null uses the environment's region. |
| Your address | Put it in an untracked `.tfvars` file (`*.tfvars` is ignored). Don't commit it or add it to `dev.tfvars.example`. |
| Offline checks | `workbench/infra/tests/front-door.tftest.hcl` runs under mock providers, so it needs no Azure access: the switches, every address rejection, the WAF rule and mode, the origin and Private Link settings, and the Lab's origin and ingress changes. |

**Rollout order.** Don't skip the 403 check.

1. Register the `Microsoft.Cdn` resource provider. Approve the public endpoint, the
   Premium cost and your IP in [#240](https://github.com/michael-rechani/foundry-agent-accelerator/issues/240).
2. Plan, and confirm only the Front Door resources and the Lab's ingress and origin
   settings change. Set `front_door_ingress_allow_cidrs = ["100.64.0.0/10"]` in the
   same apply. Apply.
3. Before approving any Private Link connection, confirm the WAF is associated with
   the endpoint and that a request from an address that isn't on the list gets 403.
4. Approve the pending Private Link connection on the Container Apps environment.
   Front Door creates a second, duplicate request, so approve each one that matches
   the Front Door origin. The first apply fails at the origin (`InternalError`) if
   the connection is still pending. Approve it, apply again, and if the origin is
   left in a failed state, re-save it and import it into the state with a
   temporary `import` block (`terraform import` can't evaluate the module's
   `for_each`).
5. Wait. The address can answer `404 Page not found` for about 20 minutes while the
   route propagates, then it answers `403` to an address that isn't on the list.
   Check the origin with the `OriginHealthPercentage` metric. A WAF block never
   reaches the origin, so a blocked request proves the block but not the path. If
   health stays at 0% with the connection approved, turn on the
   `FrontDoorHealthProbeLog` category: `HTTP 403` with `OriginError` means the
   app's ingress is refusing Front Door, not that the link is down.
6. Open the Front Door address from your machine. Record the result and region
   in #240. To tear down, set `enable_front_door = false` and apply. On 12 Oct 2026
   the decision was to keep Front Door up with no end date; see
   [Storage and cost](lab-configuration-and-cost.md#storage-and-cost).

**Measured.** The Lab's ingress sees Front Door's Private Link traffic from
`100.64.0.0/10`, not from the Lab's own network (`10.42.0.0/16` was refused). The
Lab's `jumpbox-only` rule alone left origin health at 0%. Adding `100.64.0.0/10`
brought it to 100% within three minutes and it stayed there once the other trial
private ranges were removed. The exact subrange inside `100.64.0.0/10` wasn't
identified, so the rule uses the whole shared range, which isn't routable on the
internet. Still unverified: whether the environment needs its own private endpoint
for the Front Door link (it worked without one).

The Lab has no end-user sign-in, so the IP rule is the only gate. Use fictional data
only, and don't treat a single-IP WAF rule as a substitute for the sign-in described
above before opening access to others.

#### Operate and recover the draft Front Door

**Test it.** From the machine whose address is in `front_door_allowed_cidrs`, with
no VPN, open the Front Door address in a browser. From PowerShell, `GET /healthz`
and `GET /api/config` return `200` with no extra header. Calls to the rest of
`/api/*` also need the header `X-Workbench-Request: 1`, which the page sends.

**Change the allowed address.** Edit the untracked `.tfvars`, plan from the private
runner, confirm only the WAF rule changes, apply, then confirm the Lab loads. Each
change is an IP allow-rule change and needs its own approval.

**Two different 403s.**

- Front Door's own page, "The request is blocked", means the WAF doesn't see the
  client's address on the list. A VPN is the usual cause.
- A JSON body of `{"error":"request_not_allowed", ...}` comes from the app's
  request guard (`workbench/request_guard.py`). The request already passed the WAF
  and lacked `X-Workbench-Request: 1`. `/api/config` isn't guarded.

The address Front Door sees can differ from the one an IP-check site reports. A VPN,
or a network that sends Microsoft-bound traffic out a different address, can cause
it. The caller address on your own Azure Resource Manager writes in the activity log
is a good proxy, because Resource Manager is also a Microsoft destination. The
`FrontDoorWebApplicationFirewallLog` category records the address Front Door saw.
Don't add Microsoft egress ranges to the allow-list to get around a 403: they're
shared with other customers, so it would effectively make the Lab public.

**After a subscription suspension.** A disabled or `Warned` subscription can leave
the Front Door endpoint at `enabledState = Disabled`, even after the subscription
is `Enabled` again and the Lab itself has recovered (see
[Recover after a subscription suspension](lab-deployment.md#recover-after-a-subscription-suspension)).
Front Door then answers every path with its own HTML `404 Page not found`. Terraform
expects `Enabled`, so a plan from the private runner shows the drift. To restore it
without a full apply, set only that property (the WAF, route and origin are not
touched):

```powershell
az rest --method patch --url "https://management.azure.com/subscriptions/<subscription_id>/resourceGroups/<resource_group>/providers/Microsoft.Cdn/profiles/<profile>/afdEndpoints/<endpoint>?api-version=2024-02-01" --body '{"properties":{"enabledState":"Enabled"}}'
```

Before re-enabling, confirm the WAF policy is still in Prevention mode with its
single allow-list rule and is attached to the endpoint. Then allow up to an hour
for the edge to catch up: on 9 October 2026 the address went from `404`, to the
WAF's `403`, to `200` over about 50 minutes. Confirm the origin with the
`OriginHealthPercentage` metric.

**Front Door logging.** With `enable_front_door`, Terraform also creates the
diagnostic setting `diag-front-door-240`. It sends the `FrontDoorHealthProbeLog`,
`FrontDoorWebApplicationFirewallLog` and `FrontDoorAccessLog` categories of the
Front Door profile to the Lab's Log Analytics workspace, so a rebuilt Lab gets the
same logs. The workspace stays private. Don't enable public access to read them.

The dev Lab's setting was first created with the Azure CLI (#240), so it already
exists. To adopt it without an "already exists" error, set
`import_front_door_diagnostic_setting = true` for one apply from the private
runner, then set it back to `false`. The plan must show one import and no other
change. If it shows anything else, stop and report. A new Lab doesn't need the
flag. Tracked in
[#256](https://github.com/michael-rechani/foundry-agent-accelerator/issues/256).

## Shared application and HTTP requirements

### Hostnames, TLS, and sign-in

Use a deliberate hostname strategy. For the simplest initial routing setup, the
proxy connects using the Container Apps FQDN as the origin host and SNI while the
browser uses a separate custom HTTPS domain.

| Setting | Required alignment |
| --- | --- |
| Browser-facing DNS and certificate | Resolve to the selected edge and present a certificate for the user-facing domain. |
| Origin host, SNI, and certificate | Match the Container Apps hostname, or a deliberately bound origin custom domain. Validate certificates on both TLS hops. |
| `WORKBENCH_ALLOWED_HOSTS` | Exact hostnames the backend actually receives, including the origin or probe host. Don't use a wildcard. |
| `WORKBENCH_ORIGINS` | Exact browser HTTPS origins, including the new custom domain. Don't rewrite the browser's `Origin` header to bypass this check. |
| Authentication callbacks and cookies | Use the user-facing HTTPS domain, reviewed redirect URIs, and appropriate secure cookie and cross-site request forgery (CSRF) settings. Verify sign-in and sign-out through the proxy. |
| Forwarded headers | Trust only the known proxy chain. Don't use arbitrary client-supplied forwarded IP, host, or identity headers for authorization. |

The app supports explicit host and origin lists, but the current Terraform sets
only the private hostname. Adding an edge domain needs reviewed configuration
changes. This guide doesn't introduce new Terraform variables. With origin-host
rewriting, ensure the chosen authentication integration understands the original
external host securely. Otherwise, redirects can send users to an unreachable
internal hostname. Preserving the external host instead requires an appropriate
origin domain binding and TLS setup, not just an extra allowed-host entry.

[Container Apps built-in authentication][aca-auth] is one option for Microsoft
Entra ID sign-in when adopting the broader-access mode above. In that mode,
require authentication for application routes, then enforce agent and record
permissions in the backend. Return appropriate API authentication errors instead
of silently serving a login HTML page to a JSON request. If health probes require
an unauthenticated path, exempt only a minimal health response. Never exempt the
entire `/api/*` namespace.

### Timeouts, caching, WAF, and application state

Review these requirements for both Application Gateway and Front Door:

- [ ] **Long requests:** The current backend can wait up to 180 seconds for an
      agent. Align browser, gateway or origin-response, Container Apps, and
      backend timeouts, allowing for upload and processing overhead. Don't leave a
      shorter edge default that cuts off valid reviews. Container Apps documents a
      240-second HTTP ingress timeout. Verify each edge's current limits and test
      the complete chain. Raising one timeout doesn't raise the others or cancel
      remote work.
- [ ] **No unsafe replay:** Don't enable proxy retry or replay policies for
      inference, save, or review-start `POST` requests. A timeout doesn't prove
      the original operation failed. Check persisted state before a user retries
      an uncertain save or start.
- [ ] **Streaming:** The current Lab returns non-streaming JSON. If Server-Sent
      Events (SSE) or WebSockets are added later, validate protocol support,
      buffering, idle or response timeouts, and disconnect handling at every hop.
      A streaming-capable model alone doesn't make the frontend path
      streaming-capable.
- [ ] **Caching:** Start with caching disabled. Never cache `/api/*`,
      authentication endpoints, transcripts, or personalized responses. Preserve
      API `no-store`, HTML revalidation, and error behavior. Enable caching only
      for reviewed fingerprinted static assets after confirming no personalized
      data is included.
- [ ] **WAF:** Enable the appropriate managed rules and tune narrowly with
      fictional requests. Test legitimate evidence text and the application's
      64 KiB request boundary. Don't disable body inspection or whole rule groups
      merely because a review prompt triggers a rule. WAF isn't a prompt-injection
      defense for tools or retrieved documents.
- [ ] **Diagnostics:** Preserve the app's correlation IDs and record edge request
      metadata. Review WAF match details and access-log fields for sensitive
      excerpts, query strings, tokens, and cookies. Avoid prompt and body logging.
      Define retention, access, and alert recipients for gateway diagnostics.
- [ ] **Health:** `/healthz` checks process health, not Foundry model-generation
      quality. The cached `/api/health/dependencies` reports dependency access
      separately. Never use a billable agent invocation as an edge health probe.
      **GET** is explicit because the current app declares a `GET` health route.
      Don't assume `HEAD` works.
- [ ] **Scaling and failover:** The Lab has one replica, process-local admission
      controls, and local background review tasks. A global edge doesn't make
      those tasks durable or the app active-active. Don't add replicas, regional
      origins, or cross-region failover without reviewing work ownership, data
      consistency, identity, quotas, and recovery.

## Acceptance checks before publishing the URL

Use fictional data and test from both intended and unintended network locations.
Record the selected edge, app revision, DNS and TLS configuration, and results.
Use the authentication and per-user authorization gates for broader-access
deployments. For a private demonstration without sign-in, record those
capabilities as **not implemented**, verify the private-demo boundary below, and
don't describe the result as ready for public or confidential multi-user access.

| Check | Required result |
| --- | --- |
| DNS and TLS | Browser reaches the intended listener; the gateway resolves and reaches its private origin; certificates validate on both hops. |
| Origin isolation | Direct origin access from the public internet fails while the authorized edge path succeeds. Any retained private administrator bypass is documented, not presented as edge-only enforcement. |
| Private-demo boundary | Only approved private sources can reach the app, public ingress remains closed, the **Shared lab** control exposes the shared-data details on desktop and mobile, and test inputs are fictional. This doesn't establish individual user identity or record isolation. |
| Authentication for broader access | Anonymous access to protected application and API routes is denied; sign-in and sign-out use the correct public or private frontend domain without redirect loops. |
| Authorization for broader access | A user can't access another user's records or invoke an unauthorized agent. This is an implementation gate, not current Lab behavior. |
| Host and origin checks | Approved browser requests succeed; unapproved `Host` and `Origin` values remain rejected. Don't weaken these controls to pass a probe. |
| Frontend and chat | HTML and assets load, `/api/config` returns the approved catalog, and a fictional `POST /api/reviews` completes through the edge with expected specialist receipts where applicable. |
| History and review records | Save, reopen, and update work through the edge; ETag conflicts remain conflicts and don't get cached or retried into duplicate operations. |
| Long request and failure | A representative slow review completes within the reviewed budget; backend unavailability and timeouts produce observable failures, not false success or automatic `POST` replay. |
| Cache and logging | No API, authentication, or private data is cached or unexpectedly logged. Correlation IDs support tracing without transcript content. |
| Health and WAF | The `GET` probe succeeds without model calls; representative valid requests pass and narrowly defined unwanted traffic is blocked. |

### Troubleshooting

| Symptom | Inspect first |
| --- | --- |
| Origin unhealthy or edge `502`/`504` | Private DNS and routing or Private Link approval, origin host and SNI, TLS validation, `GET` probe path, ingress source restrictions, and timeout settings. |
| Homepage loads but chat fails with `400`/`403` | Backend allowed hosts and origins, `/api/*` route configuration, WAF matches, app authentication, and original request size. |
| Front Door can't reach an otherwise working internal URL | Premium tier, the correct environment and subresource, supported Private Link location, connection approval, and private-path ingress behavior. Probes that the app refuses with 403 mean the ingress rules lack `100.64.0.0/10`. A browser in the VNet is a different access path. |
| Login loop or redirect to the internal hostname | Redirect URI registration, cookie settings, origin-host strategy, and trusted forwarded-host and protocol handling. |
| Review fails only after a fixed delay | Compare all timeout layers; preserve correlation IDs and check whether remote work or a saved record already exists before retrying. |
| Direct public origin still works | Recheck environment public access, alternate origins and routes, and DNS. Don't rely on an obscure origin URL or a forwarded header as the access boundary. |

## Cost, rollout, and ownership

Both options add costs beyond model tokens: gateway or profile capacity, WAF,
requests and data transfer, diagnostics, and certificates where applicable. Front
Door Premium also requires evaluating private endpoint-related charges. Get a
current regional estimate. Neither option is a free wrapper around the existing
app. Don't add either to default deployment or the deployed cost baseline until
it is approved.

Roll out before switching production DNS. Preserve the existing management access
path and state separation. Review Terraform plans for resource replacement,
especially the Container Apps environment. Don't adopt tutorial cleanup steps
that delete the shared resource group. Roll back only the new ingress and DNS
changes if needed, not the Foundry foundation or application data.

Future Terraform examples should be optional, use the existing application's
outputs as inputs, and clearly own their gateway, certificates, DNS, diagnostic
settings, and approved application configuration changes. This document doesn't
add those examples or claim that either path has been deployed and live-tested.
APIM remains a separate [optional API-governance integration](optional-integrations.md).

## Related content

- [Architecture](architecture.md)
- [The Lab](../workbench/README.md)
- [Governed review API](apim-review-api.md)
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
