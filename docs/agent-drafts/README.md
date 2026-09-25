# Public sector and healthcare agent drafts

[Overview](../../README.md) / Agent drafts

**Status: Initial documentation-only drafts; not implemented, registered, or
deployed.** These are copy-ready definitions and personas for later design work,
not executable coordinator profiles or deployment instructions. Workflows,
integrations, actions, and MVPs below describe proposed capabilities, not
capabilities connected or available in this repository.

## Draft index

| Draft | Intended focus |
| --- | --- |
| [Caseworker Assistance Agent](caseworker-assistance-agent.md) | Source-backed case preparation for internal caseworkers |
| [Citizen Service and Benefits Navigation Agent](citizen-service-and-benefits-navigation-agent.md) | Resident-facing program navigation and application preparation |
| [Patient Access and Scheduling Agent](patient-access-and-scheduling-agent.md) | Administrative appointment access and scheduling |
| [Internal Staff Workflow Assistant](internal-staff-workflow-assistant.md) | Cross-functional administrative work packets and approved follow-through |

[Shared requirements](shared-requirements.md) apply to all four drafts and must
accompany any copied agent definition. Each draft retains its own persona,
users, workflow, output, boundaries, MVP, and success measures.

These new concepts neither replace nor rename the existing
[case-review agent](../../hosted-agents/case-review-agent/README.md) or
[application-review agent](../../hosted-agents/application-review-agent/README.md).
In particular, the Caseworker Assistance Agent is a separate proposed workflow,
and the Internal Staff Workflow Assistant is not case-management-specific.

No agent registration, runtime integration, application change, deployment, or
Terraform change is included. No connection to a case-management system, policy
library, status service, scheduling system, or other system of record is implied.
Use clearly labelled synthetic data wherever an integration is unavailable.
The [existing agent profile mechanism](../agent-profiles.md) is separate;
these Markdown drafts do not create specialists, profiles, or permissions.
