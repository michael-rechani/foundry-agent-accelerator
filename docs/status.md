# Delivery status

[Overview](../README.md) / Delivery status

Snapshot: **2026-09-06 UTC**. This distinguishes recorded deployment evidence from
local test results. It is not an automated Azure health report.

**Readiness:** hardened private Lab for synthetic demonstrations. Not a
production multi-user application or a fully private-endpoint-only deployment.

| Component | Current deployment | Verification |
| --- | --- | --- |
| AI Foundry Lab | Internal Container App, revision `foundry-workbench--private-v2`; curated customer-review catalog and shared Cosmos history | Healthy; private HTTPS, HSTS, live agent call and Cosmos create/read/update/delete passed on the final image; 31 API and 30 browser tests previously passed |
| Review agents | Application/case specialists v1, review coordinator v2, customer-review coordinator v1 | Both specialist delegation paths passed; previous coordinator v1 retained for recovery |
| Monitoring | Private ingestion/query, 30-day retention, 0.1-GB daily cap, local auth disabled; three portal alerts | Private query and retained heartbeats verified after key rotation; notification delivery not configured |
| Lab state | Separate Entra-authenticated backend key, Blob private endpoint, keyless Cosmos/Log Analytics reads | Ownership transfer applied without Azure mutations; full follow-up plan empty |
| Platform credentials | Credential-free VM, Cosmos, Storage and Log Analytics state owners | Ownership changes applied without Azure mutations; full plan empty; jumpbox password and all affected account/workspace keys rotated; Windows logon verified |
| Registry and builds | Premium ACR, public access and admin account disabled; private endpoint and DNS | Disposable private Linux builder built/pushed/pulled the final image with public access disabled; non-root import check passed |
| Private execution | Existing jumpbox with managed identity; private DNS and peered VNets | State access verified; jumpbox returned to deallocated state |
| APIM | Removed to avoid idle capacity charges; optional configuration and soft-delete recovery retained | APIM-only removal verified; shared resource IDs/state lineage preserved; full plan empty; private Lab agent/CRUD smoke passed afterward |

## Open gates

| Area | Required before production use |
| --- | --- |
| User access | Add end-user authentication and owner-scoped history authorization before confidential multi-user use |
| Availability | Replace process-local admission controls before scaling beyond one worker/replica; establish recovery objectives and test restore procedures |
| Notifications | Configure an action group and verify delivered alerts; daily ingestion cap is not a hard billing limit |
| Gateway (optional) | Redeploy APIM only when needed; approve caller settings and test authorization and failure paths before publication |
| Costs | Reconcile actual spend after Cost Management HTTP 429 and replace usage allowances; the itemized [budget](../cost-comparison/platform-rates.md) is not a current Azure bill |

## Release reference

Lab image: `acrworkbenchdi2mw.azurecr.io/workbench@sha256:16d1e6691b55999e61a059de2619152cec7111c8a34770b5bcad8e96304c2d55`.
Its Docker base stages and frontend CI container are digest-pinned. Both refreshed
Terraform plans are empty after ownership and network reconciliation. Historical
state and backups remain protected and retained; rotation invalidated old
credential copies. See [credential handling](credential-migration.md).

The post-APIM-removal planning scenario totals **$1,584.76/month**, including $200 labor
and $87.60 of explicitly unverified Container Apps feature contingency. It uses
illustrative model/runtime usage, not measured reviews or invoiced consumption.
All 21 calculator tests pass. No equivalent-IaaS savings is claimed.

The deployed image was verified with private live smoke tests. Check the
validation workflow for the CI result of the source revision being used;
root Terraform changes remain local-only and are excluded from publication.

Use the [validation workflow](../.github/workflows/validate.yml) for source checks,
the [private deployment runbook](private-deployment.md) for delivery, and the
[profile lifecycle](agent-profiles.md) for specialist changes. CI uses mocks and
does not establish live Azure health; repeat private smoke tests after deployment.

## Known boundaries

- Candidate traffic is promoted before live smoke tests. Recovery is
  conservative but is not an atomic deployment transaction or distributed lock.
- Forced termination or interruption during resource creation/cleanup can require
   manual inventory and recovery.
- Cancellation releases client resources; the remote service may finish work
  that was already accepted.
- Workbench history is shared and editable. Stored receipt flags are cleared on
   save/read and the UI labels reopened receipts as not reverified. Live receipts
   remain correlated against expected tool targets.
- Review agents use supplied context, not a connected system of record.
- Review results support human review; they do not approve, deny, or rank people.
