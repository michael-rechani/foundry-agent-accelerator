# Copilot instructions

## Never create public resources without explicit approval

Do not create, enable, or expose anything publicly reachable unless the user
explicitly approves that specific resource or setting first. This includes:

- Resources with public network access, such as registries, storage accounts,
  Key Vaults, Foundry or AI Services accounts, and Container Apps.
- Public IP addresses, public ingress, firewall openings, and IP allow rules.
- Anonymous or shared-key access, admin users, and public blob containers.

This applies even when a documented fallback uses a public endpoint, even when
the resource is temporary, and even when a broader task has been approved.
Approval of a rollout or deployment isn't approval to create a public resource.
If the only path requires public exposure, stop and ask. Say what would be
public, for how long, and what private alternatives exist.

## Track work you can't finish now as GitHub issues

When work is deferred, blocked on approval, or out of scope for the current
change, open a GitHub issue in this repository instead of leaving it only in
chat. Check open issues first and update a matching one rather than filing a
duplicate. Each issue states the goal, what already exists, what needs
approval, and a "Done when" checklist. Use these labels where they fit:

- `agent-library`: library templates, acceptance cases, and library GUI.
- `add-on`: optional agent tools and skills, such as storage or caching.
- `cost`: cost visibility, estimates, or controls.
- `needs-approval`: billable calls, shared data, infrastructure, or deployment.

Reference the issue from code comments, docs, or the PR description when the
deferred work affects them.
