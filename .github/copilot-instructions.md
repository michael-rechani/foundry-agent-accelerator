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
