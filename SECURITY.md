# Security policy

Foundry Agent Lab is a sample, not an official Microsoft product. It has no
support agreement or response-time commitment, but security reports are
welcome and handled as a priority.

## Supported versions

Only the latest commit on `main` receives fixes. Redeploy from `main` to pick
them up.

## Report a vulnerability

Report privately. Don't open an issue, pull request, or discussion for a
suspected vulnerability.

- **In this repository's code, infrastructure, or workflows:** email the
  repository owner, [@michael-rechani](https://github.com/michael-rechani), at
  [mrechani@microsoft.com](mailto:mrechani@microsoft.com).
- **In Microsoft Foundry, Azure, or a Microsoft SDK:** report it to the
  [Microsoft Security Response Center (MSRC)](https://msrc.microsoft.com/create-report).

Include as much of the following as you can:

- The affected file, component, or Terraform root.
- Steps to reproduce, using fictional data only.
- The impact you expect, such as data exposure or privilege escalation.
- Any suggested fix or mitigation.

Never include real credentials, customer data, or personal information in a
report.

## Exposed credentials

If a credential reaches source control, a log, or a chat, rotate it first.
Rewriting history doesn't revoke a value that was already pushed. Then follow
[Credentials and protected state](docs/credentials.md).

## Known limitations

These documented design limits aren't vulnerabilities on their own:

- The Lab has no sign-in. Access is controlled by the private network.
- Everyone with network access shares the same saved records.
- Template lookup tools use simulated, read-only data.

A way to reach the Lab or its data from outside the approved private network,
or to obtain credentials or elevated Azure access, is in scope. See
[Scope and limitations](README.md#scope-and-limitations) and the
[trust boundaries](docs/architecture.md#trust-boundaries).
