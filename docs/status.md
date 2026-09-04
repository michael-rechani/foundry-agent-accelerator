# Delivery status

[Overview](../README.md) / Delivery status

Snapshot: **2026-09-04**. This distinguishes recorded deployment evidence from
local test results. It is not an automated Azure health report.

| Component | Evidence | Next gate |
| --- | --- | --- |
| Private Foundry and management jumpbox | Previously deployed; jumpbox managed identity and project RBAC verified | Recheck before the next deployment |
| Application and case specialists v1 | Previously active at 100% traffic; basic live smoke tests passed | Preserve existing versions unless an update is needed |
| Coordinator v1 | Previously active; returned a nonempty review | Earlier test did not prove specialist invocation |
| Hardened coordinator | 21 local Python tests passed, including two real-SDK contract tests | Deploy a new version and pass both structured delegation checks |
| APIM Standard v2 | Service, network integration, diagnostics, and project role previously deployed | Publish coordinator API, backend, and authorization policies |
| Client-to-specialist route through APIM | Not tested; no API published | Verify successful calls and rejection of unauthorized callers |
| Publisher variable validation | Six isolated Terraform cases passed | CI now runs the same test |
| Credential provisioning | Key Vault retrieval exists; Terraform still holds secret values | Design migration, rotate credentials, handle historical copies |

## Release gates

1. Run the [CI checks](../.github/workflows/validate.yml); local results do not
   establish that a GitHub Actions run has succeeded.
2. Follow the [private deployment runbook](private-deployment.md) to deploy only
   the hardened coordinator and verify application and case delegation.
3. Publish the APIM route with caller authorization and backend managed identity.
4. Test valid, unauthorized, malformed, oversized, rate-limited, and timed-out
   requests. Capture non-sensitive correlation IDs and outcomes.
5. Resolve the credential migration before describing this as Key-Vault-only.

## Known boundaries

- Candidate traffic is promoted before live smoke tests. Recovery is
  conservative but is not an atomic deployment transaction or distributed lock.
- Cancellation releases client resources; the remote service may finish work
  that was already accepted.
- Review agents use supplied context, not a connected system of record.
- Review results support human review; they do not approve, deny, or rank people.
- APIM, the jumpbox, NAT, and project dependencies have costs beyond sandbox
  execution. The [cost calculator](../cost-comparison/README.md) is not a complete
  bill for this environment.