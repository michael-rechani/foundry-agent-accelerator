# Foundry agent monitoring

This independent Terraform root connects an existing Foundry project to a
workspace-based Application Insights resource. It reuses the platform's private
Log Analytics workspace and Azure Monitor Private Link Scope (AMPLS), without
taking ownership of those resources or changing their network access.

Application Insights ingestion and queries remain private, and local/key
authentication is disabled. The project and explicitly listed agent identities
receive **Monitoring Metrics Publisher** on this component only. No agent receives
permission to read other agents' traces. Portal users need appropriate reader
permissions and private-network access, such as the browser inside the jumpbox.
Project-managed-identity trace ingestion is currently documented as preview.

## Metadata-only prerequisite

The hosting SDK can enable sensitive content recording by default. **Do not
connect Application Insights first and fix the agents afterward.** Both repository
publication paths now set these values:

```text
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=false
ENABLE_SENSITIVE_DATA=false
AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED=false
APPLICATIONINSIGHTS_AUTH_MODE=entra
APPLICATIONINSIGHTS_STATSBEAT_DISABLED_ALL=true
```

These disable SDK recording of prompts, responses, and sensitive tool data while
retaining operation metadata. Disabling statsbeat stops the exporter's own usage
telemetry, including a virtual-machine metadata probe that otherwise fails in the
hosted container and appears as `requests.exceptions.ConnectionError` rows in
`AppExceptions`. Versions published before this setting keep emitting those
harmless rows until they are republished. These settings do not sanitize arbitrary application log
messages; keep those metadata-only too. `AGENT_STORE_RESPONSES=false` controls
response persistence separately and is not a substitute for these tracing flags.

Existing agent versions are immutable: publish equivalent versions with these
settings, preserve instructions, source code, tools, protocol authorization, and
agent names, then verify and route the new versions. Retire older versions only
with approval; an unrouted version may still be directly callable. Do not enable
the project connection while an unsafe version can still run. Deploy the updated
Lab publisher before enabling its optional agent-creation feature.

For each subsequently created agent, add its runtime `instance_identity.principal_id`
to `agent_principal_ids` and apply the scoped publisher assignment. A project
identity grant alone does not authorize a new hosted agent's SDK exporter.

## Deployment

Use `dev.tfvars.example` and `backend.hcl.example` to create ignored environment
inputs. Use a separate protected state key, such as
`ai-foundry/monitoring-dev.tfstate`; never reuse the platform, Lab, or Bastion
state. Authenticate from the authorized private-network runner.

The deployment identity needs monitoring resource and project-connection
permissions. Creating the publisher role assignments also requires scoped RBAC
administration. Alternatively, an authorized administrator can create those
assignments and import them into their declared Terraform addresses before the
full apply. Do not grant broad permanent administration to a runtime identity.

Start with `enable_project_connection = false`. This provisions the monitoring
destination, private link association, and scoped publishing permissions without
turning on project-wide tracing.

```powershell
terraform init "-backend-config=backend.hcl"
$plan = Join-Path $env:TEMP ("monitoring-" + [guid]::NewGuid() + ".tfplan")
terraform plan "-var-file=dev.tfvars" "-out=$plan"
```

Review the plan, then apply the saved plan and delete it. After the metadata-only
agent rollout is verified, set `enable_project_connection = true`, review a new
plan, and apply it. The connection uses the project identity, not key-based
authentication. Foundry still requires the component connection string as routing
metadata; Terraform marks it sensitive, and the protected state contains it.
Setting this flag back to false removes only the connection and stops new
project-connected tracing; it does not erase already retained telemetry.

## Verification and portal use

1. Confirm the component is attached to the existing AMPLS and resolves through
   private DNS. Do not reopen ingestion, query endpoints, or the state backend.
2. Confirm the project connection is `AppInsights` with
   `ProjectManagedIdentity` authentication.
3. Send a synthetic request with a unique non-sensitive marker. After ingestion,
   query the trace by response/operation ID. Confirm spans, timings, status, and
   token counts are present, and that prompt, response, and tool-content fields
   and the marker are absent from telemetry. Exercise delegation too, so tool
   argument/result exclusion is checked. Include `AppGenAIContent` when present:
   it can contain tool schemas even with message capture disabled. Check that
   `InputMessages`, `OutputMessages`, `SystemInstructions`, `ToolCallArguments`,
   and `ToolCallResult` are empty, rather than assuming any row means a leak or
   that a protected table means content exclusion.
4. Open **hosted-agents-dev > Agents > Traces** in Foundry. Allow several minutes
   for new traces to arrive. The Application Insights **Performance** and
   **Transaction search** views expose the underlying telemetry too.
5. Run a full Terraform plan and require no differences. Remove temporary
   deployment permissions after completing the rollout.

Telemetry starts with new activity; this does not reconstruct past agent runs.
Storage and retention incur Azure Monitor charges. The component requests 30-day
retention; the existing workspace's retention, caps, and policies still apply.
Consult [tracing setup](https://learn.microsoft.com/azure/foundry/observability/how-to/trace-agent-setup)
and [Entra ingestion](https://learn.microsoft.com/azure/foundry/observability/how-to/trace-ingestion-entra-authentication).

## Offline validation

```powershell
terraform init -backend=false
terraform fmt -check -recursive
terraform validate
terraform test
```

The mock-provider tests check private access, Entra authentication, scoped
publishers, and opt-in connection creation. Live telemetry and content exclusion
must also be verified after deployment.
