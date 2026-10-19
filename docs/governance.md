# Agent governance and risk map

[Home](../README.md) / [Docs](README.md) / Agent governance

This guide maps the sample's controls to the
[OWASP Top 10 for Agentic Applications 2026](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/)
(ASI01 to ASI10), lists the gaps, and consolidates the known limitations. Use it
to decide what to fix before real data or production use.

This is a self-assessment of a sample, not a certification, audit, or
production-readiness claim. It describes what the repository does today. It
doesn't add controls.

**In this guide:**
[How to read it](#how-to-read-it) · [Risk map](#risk-map) ·
[Traceability](#traceability) · [Known limitations](#known-limitations) ·
[Supply-chain checks](#supply-chain-checks) · [Closing gaps](#closing-gaps) ·
[References](#references)

## How to read it

Governance here means three questions, in order:

1. **Is this action allowed?** What stops an agent from doing something it
   shouldn't, whatever its prompt says?
2. **Who did it?** Which identity acted, and with what access?
3. **Can you show what happened?** What record exists, and how far can you
   trust it?

A prompt instruction is a request to a model, not a control. The risk map
therefore separates **enforced** controls (network, identity, code, Terraform,
CI) from **model-level** controls (instructions the model might not follow).

| Status | Meaning |
| --- | --- |
| **Covered** | An enforced control exists and a test or check protects it. |
| **Partly covered** | A control exists, but it's model-level, process-local, or untested live. |
| **Gap** | No control today. |

## Risk map

| Risk | Controls today | Status | Gap or next step |
| --- | --- | --- | --- |
| **ASI01 Agent goal hijack** | Instructions treat supplied evidence, criteria, and retrieved passages as untrusted data ([coordinator instructions](../hosted-agents/review-coordinator-agent/instructions.md), [review schema](../workbench/reviews.py)). The structured review requires exact-quote citations. Offline cases such as `application-untrusted-instructions` and `case-untrusted-instructions` check the expected behavior ([test cases](evaluation-test-cases.md)). A person makes every decision. | Partly covered | These are model-level controls. No Foundry guardrail or Prompt Shields policy is configured in this repository, and the live injection results aren't recorded ([demo handoff](demo-handoff.md#what-needs-further-validation)). |
| **ASI02 Tool misuse** | The coordinator can call only the specialists in its profile, with timeouts and concurrency limits, and receipts correlate each call to its expected target ([architecture](architecture.md#chat-and-delegation)). Created agents have no tools, or two simulated read-only lookups ([agent creation](agent-creation.md#configuration-ownership)). Knowledge search is flag-gated and read-only ([design](knowledge-retrieval.md)). | Partly covered | There's no declarative per-call policy such as allow, deny, or require approval. Foundry's hosted Search tool can't enforce a field allowlist ([knowledge retrieval](knowledge-retrieval.md)). |
| **ASI03 Identity and privilege abuse** | Managed identity everywhere, local key authentication disabled, container-scoped Cosmos DB role, and a [role-by-role reference](permissions.md). The Lab accepts traffic only from the private network and checks origin on every data API ([request guard](../workbench/request_guard.py)). | Partly covered | The Lab has no sign-in, so every caller shares one identity and one set of records. The Search roles are write-capable and shared by every agent in the project ([permissions](permissions.md)). Per-agent identity and least-privilege roles are listed as future work in the [production considerations](../terraform/README.md#separately-scoped-production-considerations). |
| **ASI04 Agentic supply chain** | Actions pinned by commit SHA. The Lab image is pinned by digest. Gitleaks scans every commit, `pip-audit` runs on Python dependencies, CodeQL default setup scans Python, TypeScript, and Actions, and Dependabot proposes monthly updates ([validate workflow](../.github/workflows/validate.yml), [dependabot](../.github/dependabot.yml)). OpenSSF Scorecard scores the repository weekly. | Partly covered | The agent hosting package is a preview build and is upgraded by hand. There's no SBOM or build-provenance attestation. Agent templates and add-ons are checked by manifest, not signed. |
| **ASI05 Unexpected code execution** | No agent has a shell or code tool. The code interpreter add-on is planned, not available ([add-on package format](addon-package-format.md)). The Lab image runs as non-root. | Covered today | Enabling the code interpreter add-on is a new risk. Review it against this table first. |
| **ASI06 Memory and context poisoning** | Foundry calls use `store=false`. Follow-ups reuse a chat's Foundry session for up to 10 minutes. Chats save only when the user saves them. Retrieved passages carry an untrusted header and are paraphrased and cited ([architecture](architecture.md#chat-and-delegation)). | Partly covered | Saved history is shared, not per-user, and clients can submit transcript data, so saved receipts are marked unverified ([conversations](lab-conversations.md)). Poisoned content in shared history could reach another user. Owner-scoped history is a publication requirement. |
| **ASI07 Insecure inter-agent communication** | One coordinator and two specialists, called as tools by named Foundry endpoint with managed identity. There are no specialist-to-specialist calls. The wrapper accepts only a completed, nonempty response ([architecture](architecture.md#agent-collaboration)). | Partly covered | Messages aren't signed, and the call relies on Foundry's transport and identity. Profile-based bindings need per-tool target checks ([trust boundaries](architecture.md#trust-boundaries)). |
| **ASI08 Cascading failures** | Four shared agent slots, 20 starts per minute, per-model request and token budgets, bounded deadlines, and no automatic model retry. A failed or timed-out call is reported as incomplete, never replaced ([failure and capacity boundaries](architecture.md#failure-and-capacity-boundaries)). | Partly covered | The limits are process-local and need one worker and one replica. There's no circuit breaker or shared admission control. |
| **ASI09 Human-agent trust exploitation** | Agents don't approve, deny, rank, or act. Reviews report **Met**, **Not demonstrated**, or **Unclear**, end with a human-review notice, and keep missing evidence distinct from noncompliance ([review workflow](review-workflow.md#execution-and-trust)). A library agent isn't **Reviewed** until a person signs off its recorded answers ([scorecards](library-scorecards.md)). | Partly covered | Confident, well-cited output can still be wrong, and nothing measures reviewer over-reliance. If any agent gains an action tool, add an approval step bound to that action. |
| **ASI10 Rogue agents** | Only curated and operator-created agents appear. Creation is off until an operator turns it on. The Lab calls named agent endpoints, not a browser-chosen model ([agent creation](agent-creation.md)). | Partly covered | There's no runtime behavior monitoring or kill switch beyond an operator deleting or rolling back an agent version. Optional [agent monitoring](../terraform/monitoring/README.md) records metadata-only traces. |

## Traceability

The OWASP list doesn't include an audit requirement, but regulators and
incident responders ask for one.

| Record | What it shows | What it doesn't |
| --- | --- | --- |
| Lab request metadata in Log Analytics | That a request happened, when, and how it ended. | Prompt or answer content. |
| Optional agent traces in Application Insights | Metadata-only agent and tool activity. | Content, and it's off unless monitoring is deployed. |
| Specialist receipts | That a configured specialist call completed for this answer. | That the finding is true. |
| Saved conversations and review results | What a person chose to save, and the checks run at the time. | Anything tamper-evident. Clients can submit transcript data, and history is shared and editable. |

There's no immutable, tamper-evident audit ledger and no end-user identity to
attribute actions to ([review workflow](review-workflow.md)). Both are needed
before confidential data.

## Known limitations

The same limits appear across the guides. This list collects them.

- **No sign-in.** The private network is the only access control. Everyone with
  access shares saved records ([README](../README.md#scope-and-limitations),
  [SECURITY](../SECURITY.md#known-limitations)).
- **Model-level controls can fail.** Instructions to treat evidence as
  untrusted lower the risk but don't remove it. OWASP's own guidance says
  prompt injection has no known fool-proof prevention.
- **Offline tests don't show live behavior.** Mocked checks don't establish
  model behavior, cloud connectivity, or RBAC ([demo handoff](demo-handoff.md)).
- **Limits are process-local.** Request limits assume one worker and one
  replica ([architecture](architecture.md#failure-and-capacity-boundaries)).
- **Simulated data.** Template lookups return sample, read-only data and don't
  touch customer systems.
- **Sample, not product.** This isn't an official Microsoft product and has no
  support commitment.

## Supply-chain checks

| Check | Where | Notes |
| --- | --- | --- |
| Credential scan | `secrets` job in [validate](../.github/workflows/validate.yml) | Scans every commit with Gitleaks. See [credentials](credentials.md). |
| Python dependency audit | `python` job in [validate](../.github/workflows/validate.yml) | `pip-audit` on the combined install. |
| Static analysis | CodeQL default setup in the repository's security settings | Python, JavaScript and TypeScript, and Actions, scanned weekly and on changes. It isn't a workflow file, so it's configured in repository settings. |
| Dependency updates | [Dependabot](../.github/dependabot.yml) | Monthly, one grouped pull request per ecosystem. |
| Repository practices | [Scorecard workflow](../.github/workflows/scorecard.yml) | Weekly OpenSSF Scorecard. Results appear in the Security tab. |

## Closing gaps

Work that needs a decision, billable calls, or infrastructure is tracked as
GitHub issues rather than listed here. The main candidates, in order:

1. Record live prompt-injection results, then add adversarial cases for the
   coordinator and each template.
2. Configure and test a Foundry guardrail policy for the model deployments.
3. Add owner-scoped history and sign-in, then per-agent identities with
   least-privilege roles.
4. Decide on a tamper-evident audit record before any confidential data.
5. Add a per-call tool policy only if agents gain action tools.

## References

- [OWASP Top 10 for Agentic Applications 2026](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/)
- [Microsoft Agent Governance Toolkit](https://github.com/microsoft/agent-governance-toolkit):
  a public-preview runtime governance toolkit. This guide borrows its
  risk-to-control mapping approach. The repository doesn't depend on it.
- [AI Red Teaming Agent in Foundry](https://learn.microsoft.com/azure/ai-foundry/concepts/ai-red-teaming-agent)
- [Architecture](architecture.md#trust-boundaries) and
  [permissions](permissions.md)
