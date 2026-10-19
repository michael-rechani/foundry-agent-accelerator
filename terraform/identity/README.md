# Deploy identities and GitHub environments

[Home](../../README.md) / [Infrastructure](../README.md) / Deploy identities

Creates the keyless Azure identities that GitHub workflows sign in with, their
narrow roles, and the GitHub environments and variables that use them. It
replaces `setup-deploy-identity.ps1`, `setup-runner-start.ps1` and
`setup-recording-identity.ps1`.

This is the only root that needs Microsoft Entra and GitHub admin rights.
Everything else needs Azure resource rights only, so run it separately, once per
subscription, and let a smaller group run the other roots.

## At a glance

| Setting | Value |
| --- | --- |
| Run after | The Lab root (`workbench/infra`) and the runner root, because the roles are scoped to their resources. |
| Run by | Someone who can create Entra app registrations, create role definitions and assignments on the Lab and runner resource groups, and administer the repository's environments. |
| Deploy identity | `gh-lab-image-deploy`. A federated credential for the `lab-deploy` environment only. No secret. |
| Deploy roles | Custom **Lab image deployer** (import an image, update the one Container App), **AcrPush** on the registry, and custom **Lab runner starter** (read and start one VM). |
| Recording identity | `gh-library-recording`, with Foundry User on the one Foundry account and a required reviewer on its environment. Optional. |
| GitHub | The `lab-deploy` and `library-recording` environments, limited to `main`, and the variables the workflows read. |
| Public resources | None. |

## Deploy

1. Sign in to Azure with `az login`, and set `GITHUB_TOKEN` for this shell only.
   The token needs repository administration and environments access. It never
   goes in a file:

   ```powershell
   $env:GITHUB_TOKEN = gh auth token
   ```

1. Copy `backend.hcl.example` to an ignored `backend.hcl` and
   `dev.tfvars.example` to an ignored `dev.tfvars`. Fill in your values. Set
   `lab_state`, `runner_state` and `platform_state` so Terraform reads the names
   from those roots' outputs.
1. Run from this directory and review the saved plan before applying:

   ```powershell
   terraform init -backend-config=backend.hcl
   terraform plan -var-file=dev.tfvars -out=identity.tfplan
   terraform show identity.tfplan
   terraform apply identity.tfplan
   Remove-Item identity.tfplan
   ```

1. Run the **Deploy Lab image** workflow from the Actions tab to confirm it signs
   in. If sign-in fails with "No matching federated identity record", copy the
   subject from the error into `deploy_federated_subject` and apply again.

`recording_reviewer_user_ids` takes numeric GitHub user IDs. Read yours with
`gh api user --jq .id`. Library recording is billable when it runs, so the plan
fails until at least one reviewer is set. Set `enable_library_recording = false`
to skip it.

## Adopt identities the old scripts created

The scripts used the same names, and `prevent_duplicate_names` makes a second
copy fail instead of appearing beside the old one. Import what exists before the
first apply. Imports change only Terraform state.

```powershell
terraform import -var-file=dev.tfvars azuread_application.deploy "/applications/<application-object-id>"
terraform import -var-file=dev.tfvars azuread_service_principal.deploy "/servicePrincipals/<service-principal-object-id>"
terraform import -var-file=dev.tfvars azuread_application_federated_identity_credential.deploy "<application-object-id>/federatedIdentityCredential/<credential-id>"
terraform import -var-file=dev.tfvars azurerm_role_definition.deployer "<role-definition-resource-id>|<lab-resource-group-id>"
terraform import -var-file=dev.tfvars azurerm_role_definition.runner_starter "<role-definition-resource-id>|<runner-vm-id>"
terraform import -var-file=dev.tfvars 'azurerm_role_assignment.deployer["registry"]' "<role-assignment-id>"
```

Do the same for the other role assignments, the recording identity, and the
GitHub environments and variables (`github_repository_environment` imports as
`<repository>:<environment>`). Run `terraform plan` afterward. It must show no
changes, or only the differences you expect.

## Test without Azure or GitHub

```powershell
terraform -chdir=terraform/identity init -backend=false
terraform -chdir=terraform/identity validate
terraform -chdir=terraform/identity test
```
