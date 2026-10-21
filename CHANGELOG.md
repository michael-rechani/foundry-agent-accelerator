# Changelog

[Home](README.md) / Changelog

Notable changes to the Foundry Agent Accelerator. Each release is a snapshot of
`main`. Only the latest commit on `main` receives fixes (see
[SECURITY.md](SECURITY.md)), so redeploy from `main` rather than an old tag.
The version number marks milestones, not a compatibility promise.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Pull request numbers link to the full discussion.

## [Unreleased]

### Added

- **Agent designer spec.** When an idea is clear, the Agent designer can end its
  reply with an agent spec card: a Foundry prompt agent definition to download,
  and a button to start from the closest pre-built agent in Create agent. No
  extra model call, and nothing is created until you act.
  ([#404](https://github.com/michael-rechani/foundry-agent-accelerator/issues/404))

### Changed

- The Agent designer now knows where export lives (Find an agent > Take it to
  Foundry) and says the Lab has no import.
  ([#403](https://github.com/michael-rechani/foundry-agent-accelerator/pull/403))

## [0.1.0] - 2026-10-19

First tagged release. The repository went public on 2026-10-15
([#302](https://github.com/michael-rechani/foundry-agent-accelerator/pull/302)).

### Added

- **The Lab.** A private browser app for trying, testing and creating agents,
  with guided demos, a presenter mode, shared history and Document reviews
  ([#24](https://github.com/michael-rechani/foundry-agent-accelerator/pull/24),
  [#67](https://github.com/michael-rechani/foundry-agent-accelerator/pull/67)).
- **Agent library.** 18 sample agents, one JSON file each, with test results,
  sign-off status, sector and task filters, and a **Take it to Foundry** export
  ([#86](https://github.com/michael-rechani/foundry-agent-accelerator/pull/86),
  [#89](https://github.com/michael-rechani/foundry-agent-accelerator/pull/89),
  [#224](https://github.com/michael-rechani/foundry-agent-accelerator/pull/224)).
- **Clean Chat and Agent designer.** Chat opens as a plain conversation, with a
  designer for talking through an agent you want to build, per-answer ratings
  and **Try again** ([#375](https://github.com/michael-rechani/foundry-agent-accelerator/pull/375),
  [#377](https://github.com/michael-rechani/foundry-agent-accelerator/pull/377),
  [#357](https://github.com/michael-rechani/foundry-agent-accelerator/pull/357),
  [#361](https://github.com/michael-rechani/foundry-agent-accelerator/pull/361)).
- **Find an agent.** Describe a job and get a ready agent or template
  ([#314](https://github.com/michael-rechani/foundry-agent-accelerator/pull/314)).
- **Create agent.** Prepare an agent from a template, with operator-protected
  publishing ([#280](https://github.com/michael-rechani/foundry-agent-accelerator/pull/280)).
- **Add-ons.** A preview catalog, a manifest format and validator, and a drafted
  knowledge search package ([#99](https://github.com/michael-rechani/foundry-agent-accelerator/pull/99),
  [#233](https://github.com/michael-rechani/foundry-agent-accelerator/pull/233),
  [#234](https://github.com/michael-rechani/foundry-agent-accelerator/pull/234)).
- **Hosted agents.** Four prebuilt review agents and a coordinator, plus
  evaluation tooling for answer quality
  ([#38](https://github.com/michael-rechani/foundry-agent-accelerator/pull/38),
  [#44](https://github.com/michael-rechani/foundry-agent-accelerator/pull/44)).
- **Terraform.** A private-network foundation built on Azure Verified Modules,
  with optional Bastion, monitoring, Front Door and a self-hosted runner, all
  tested offline ([#1](https://github.com/michael-rechani/foundry-agent-accelerator/pull/1),
  [#196](https://github.com/michael-rechani/foundry-agent-accelerator/pull/196)).
- **CI and deploy.** The **Validate** workflow (Python, TypeScript, Terraform,
  docs, secret scan), Dependabot, and an automatic Lab deploy when a Lab change
  merges to `main` ([#262](https://github.com/michael-rechani/foundry-agent-accelerator/pull/262),
  [#368](https://github.com/michael-rechani/foundry-agent-accelerator/pull/368)).
- **Community files.** MIT license, security policy, contributing guide, issue
  and pull request templates
  ([#26](https://github.com/michael-rechani/foundry-agent-accelerator/pull/26),
  [#302](https://github.com/michael-rechani/foundry-agent-accelerator/pull/302),
  [#305](https://github.com/michael-rechani/foundry-agent-accelerator/pull/305)).
- **Dark-mode diagrams and screenshots** rebuilt from templates
  ([#273](https://github.com/michael-rechani/foundry-agent-accelerator/pull/273)).

### Changed

- Moved to Python 3.14 and the latest tool versions
  ([#27](https://github.com/michael-rechani/foundry-agent-accelerator/pull/27)).
- Library copy and agent instructions rewritten in plain language
  ([#328](https://github.com/michael-rechani/foundry-agent-accelerator/pull/328),
  [#344](https://github.com/michael-rechani/foundry-agent-accelerator/pull/344)).
- Unfinished library agents are hidden by default
  ([#371](https://github.com/michael-rechani/foundry-agent-accelerator/pull/371)).

### Removed

- Mobile and phone-width support. The Lab is a desktop web app
  ([#335](https://github.com/michael-rechani/foundry-agent-accelerator/pull/335)).

[Unreleased]: https://github.com/michael-rechani/foundry-agent-accelerator/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/michael-rechani/foundry-agent-accelerator/releases/tag/v0.1.0
