# Delivery status

[Overview](../README.md) / Delivery status

Snapshot: **2026-09-05 UTC**. This distinguishes recorded deployment evidence from
local test results. It is not an automated Azure health report.

**Readiness:** hardened private Lab for synthetic demonstrations. Not a
production multi-user application or a fully private-endpoint-only deployment.

| Component | Current deployment | Verification |
| --- | --- | --- |
| AI Foundry Lab | Internal Container App, revision `foundry-workbench--0000004`; curated customer-review catalog and shared Cosmos history | Private HTTPS, HSTS, agent calls and Cosmos CRUD passed; 31 API and 30 desktop/mobile browser tests passed |
| Review agents | Application/case specialists v1, review coordinator v2, customer-review coordinator v1 | Both specialist delegation paths passed; previous coordinator v1 retained for recovery |
| Monitoring | 30-day retention, 0.1-GB daily cap, local auth disabled; three portal alerts | Cached dependency probes and retained heartbeats verified; notification delivery not configured |
| Lab state | Separate Entra-authenticated backend key, Blob private endpoint, keyless Cosmos/Log Analytics reads | Ownership transfer applied without Azure mutations; full follow-up plan empty |
| Private execution | Existing jumpbox with managed identity; private DNS and peered VNets | State access verified; jumpbox returned to deallocated state |
| APIM | Standard v2 infrastructure only; review API unpublished | Configuration and policy tests pass locally; live gateway acceptance remains open |

## Open gates

| Area | Required before production use |
| --- | --- |
| Credentials | Complete [platform ownership migration and rotation](credential-migration.md); protected state still contains platform password/key copies |
| User access | Add end-user authentication and owner-scoped history authorization before confidential multi-user use |
| Availability | Replace process-local admission controls before scaling beyond one worker/replica; establish recovery objectives and test restore procedures |
| Notifications | Configure an action group and verify delivered alerts; daily ingestion cap is not a hard billing limit |
| Networking | Review authenticated public ACR and Log Analytics endpoints against the target landing-zone policy |
| Gateway | Approve caller settings, publish APIM policy/API, and test authorization and failure paths |
| Costs | Reconcile actual spend and unpriced dependencies; the [calculator](../cost-comparison/README.md) is not a current Azure bill |

## Release reference

Lab hardened image: `acrworkbenchdi2mw.azurecr.io/workbench@sha256:c22b3d8fde9c5c1c1cec84cb334d8c16b50fa177dafd2a022677c1a79f473b21`,
ACR run `cp6`. Its Docker base stages and frontend CI container are digest-pinned.
The Log Analytics ownership migration is applied and does not change this runtime
image. Published source `224befa` passed CI. Platform credential migration and
alert notification delivery remain separate open gates.

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
