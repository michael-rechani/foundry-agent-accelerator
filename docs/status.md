# Delivery status

[Overview](../README.md) / Delivery status

Snapshot: **2026-09-05 UTC**. This distinguishes recorded deployment evidence from
local test results. It is not an automated Azure health report.

| Component | Evidence | Next gate |
| --- | --- | --- |
| Private Foundry Workbench | Internal Container Apps deployment; live agent and Cosmos CRUD smoke passed; curated customer-review catalog | Preserve private ingress and synthetic-data boundary; add Entra ownership before real user data |
| Workbench cleanup | Deployed as healthy revision `foundry-workbench--0000002`; private HTTPS, live agent response and Cosmos CRUD passed; GitHub Actions passed for `33233cf`, including Python, Terraform and frontend jobs | Retain the separate state and immutable image digest |
| AI Foundry Lab configuration and composer | Deployed `lab-v1`; private configuration/title, live agent and Cosmos CRUD smoke passed; 23 workbench API and 30 desktop/mobile browser tests passed locally | Publish and run CI for this follow-up separately; retain private access and shared-history boundaries |
| Lab security hardening | Deployed `security-v1`, healthy revision `foundry-workbench--0000004`; 31 API and 30 browser tests passed locally; live HSTS, cached dependency checks, agent response and Cosmos CRUD passed; synthetic test deleted and jumpbox returned to deallocated state | Preserve shared synthetic-only access; concurrency limits remain process-local |
| Lab monitoring | 30-day Log Analytics retention, 0.1-GB daily cap, local auth disabled; three portal alert rules deployed; dependency heartbeats observed in retained logs | Configure an operator action group for notification delivery; cap is not a hard billing limit |
| Lab remote state | Migrated with Entra and locking; lineage and all 15 original managed IDs preserved; Cosmos key-returning lookup removed with no Azure mutations | Backend public access is now disabled; resume from an approved private runner |
| Secret ownership | Expanded field-name-only inventory found platform Cosmos/Storage/Log Analytics keys as well as jumpbox password state copies; keyless Lab Log Analytics transfer is staged and validates locally | Backend HTTP 403 blocks transfer plan/apply; platform rotation and ownership migrations still pending; not Key-Vault-only |
| Private Foundry and management jumpbox | Previously deployed; jumpbox managed identity and project RBAC verified | Recheck before the next deployment |
| Application and case specialists v1 | Fresh private inventory confirmed active at 100% traffic | Preserve existing versions unless an update is needed |
| Coordinator v1 | Retained, not routed | Preserve for recovery until deliberately retired |
| Hardened coordinator v2 | Deployed from commit `731f568`; both structured delegation checks passed; fresh inventory confirmed 100% traffic | Preserve baseline while validating profile-based updates |
| Swappable coordinator profiles | `customer-review-coordinator` v1 deployed; `inspect_application` and `inspect_case` passed target-specific checks; fresh inventory confirmed 100% traffic | Use reviewed profiles for future swaps; retain default coordinator v2 |
| APIM Standard v2 | Service/network baseline deployed; opt-in API resources and policy pass local validation and 11 input cases plus XML checks | Confirm caller audience/allowlists, publish, and run live gateway acceptance tests |
| Client-to-specialist route through APIM | Not tested; no API published | Verify successful calls and rejection of unauthorized callers |
| Publisher variable validation | Six isolated Terraform cases passed | CI now runs the same test |
| Credential provisioning | Key Vault retrieval exists; Terraform still holds secret values; installed write-only/ephemeral capabilities checked and [migration designed](credential-migration.md) | Approve and test ownership transfer, rotate credentials, handle historical copies |
| Specialist dependency preflight | Both default and profile coordinator checks name expected targets; local checks reject missing/unrouted/inactive dependencies before version creation | Used on the next agent deployment; no new coordinator version deployed during GUI cleanup |
| Platform-aware costs | Itemized allocation tested; [APIM and Windows jumpbox capacity rates](../cost-comparison/platform-rates.md) sourced; other dependencies unpriced | ActualCost query returned HTTP 429; reconcile spend and remaining rates; not a current bill |

## Release gates

Lab hardened image: `acrworkbenchdi2mw.azurecr.io/workbench@sha256:c22b3d8fde9c5c1c1cec84cb334d8c16b50fa177dafd2a022677c1a79f473b21`,
ACR run `cp6`. Its Docker base stages and frontend CI container are digest-pinned.
The later staged Log Analytics ownership migration does not change this runtime
image and has not been applied. Source validation is not evidence of a successful
credential migration or of notification delivery.

Profile deployment completed at **2026-09-04 22:54:37 UTC** using the jumpbox's
managed identity. Selective source archive SHA-256:
`07B5770AD35043E92CA8F7D7196EDA27DC77C151F5E511E0D4F3CDDCD47AB5FF`.
This archive included locally tested, uncommitted profile changes. The existing
review coordinator v2 and both specialist v1 routes were preserved.

1. Run the [CI checks](../.github/workflows/validate.yml); local results do not
   establish that a GitHub Actions run has succeeded.
2. Follow the [profile swap lifecycle](agent-profiles.md) and
   [private deployment runbook](private-deployment.md) for the next coordinator
   update; repeat live delegation checks for every configured specialist.
3. Follow the [APIM publication gates](apim-review-api.md) with caller authorization
   and backend managed identity. No approved caller configuration is recorded yet.
4. Test valid, unauthorized, malformed, oversized, rate-limited, and timed-out
   requests. Capture non-sensitive correlation IDs and outcomes.
5. Resolve the credential migration before describing this as Key-Vault-only.

## Known boundaries

- Candidate traffic is promoted before live smoke tests. Recovery is
  conservative but is not an atomic deployment transaction or distributed lock.
- Operator cancellation after candidate creation now attempts conservative
   cleanup and re-raises the interruption. Forced process termination, interruption
   during the create request, or a second interruption during cleanup still needs
   manual inventory and recovery. The new behavior passed local regression tests.
- Cancellation releases client resources; the remote service may finish work
  that was already accepted.
- Workbench history is shared and editable. Stored receipt flags are cleared on
   save/read and the UI labels reopened receipts as not reverified. Live receipts
   remain correlated against expected tool targets.
- Workbench emits request metadata without bodies, credentials or exception
   details. Persistent console/system log collection is enabled with retention
   and a daily cap. Cached Foundry/Cosmos dependency checks run each minute;
   process liveness stays independent of dependency outages.
- Review agents use supplied context, not a connected system of record.
- Review results support human review; they do not approve, deny, or rank people.
- APIM, the jumpbox, NAT, and project dependencies have costs beyond sandbox
   execution. The [cost calculator](../cost-comparison/README.md) now accepts these
   as itemized costs, but its example contains unpriced entries and is not a
   complete bill for this environment. Existing GPU rate snapshots are not a
   current price refresh for the deployed regions.