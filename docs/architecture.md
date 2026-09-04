# Architecture

[Overview](../README.md) / Architecture

![Private review-agent architecture and planned APIM entry point](images/foundry-runtime-architecture.svg)

The diagram uses [official Microsoft Azure architecture icons](images/README.md)
with separate resource-group, virtual-network, subnet, and managed-service
boundaries. Custom review agents are labeled components, not Microsoft products.

## Trust boundaries

| Boundary | Current implementation | Publication requirement |
| --- | --- | --- |
| Client to APIM | Public Standard v2 gateway; no review API | Validate Entra issuer, audience, and authorized caller claims; do not equate authentication with permission |
| APIM to Foundry | VNet integration, peering, private DNS, managed identity role | Exact backend path, managed-identity policy, request limits, and correlation IDs |
| Coordinator to specialists | Named Foundry endpoints with managed identity | New deployment must prove both tool executions |
| Administration to private data plane | Private jumpbox and project-scoped deployment identity | Inventory before mutation; serialize deployment per agent |
| Terraform to Azure | ARM resource provisioning | Protect backend state, saved plans, and credential history |

The workload and management networks may be in different regions. APIM's
integration subnet is in the management network and must be in APIM's region.
Outbound VNet integration does not make the public gateway private.

## Review request

This is the **target** request flow. The APIM API and policy steps remain
unpublished. The timeout and success-receipt behavior is in the hardened local
coordinator, not the recorded v1 deployment.

```mermaid
sequenceDiagram
    autonumber
    actor Client
    participant Gateway as APIM (API pending)
    participant Coordinator as Review coordinator
    participant Specialist as Application or case specialist
    Client->>Gateway: Review request + Entra bearer token
    alt Caller is not authorized
        Gateway-->>Client: Reject before contacting Foundry
    else Authorized request within limits
        Gateway->>Coordinator: Responses request using gateway managed identity
        Coordinator->>Coordinator: Select tool; acquire concurrency slot
        Coordinator->>Specialist: Full supplied request via managed identity
        alt Completed nonempty specialist response
            Specialist-->>Coordinator: Evidence-grounded findings
            Coordinator->>Coordinator: Emit structured successful tool result
            Coordinator-->>Gateway: Review response
            Gateway-->>Client: Result + correlation ID
        else Deadline or specialist failure
            Coordinator->>Coordinator: Cancel local request; release slot
            Note over Coordinator,Specialist: Remote work may continue after local cancellation
            Coordinator-->>Gateway: Review could not be completed
            Gateway-->>Client: Failure response under published API contract
        end
    end
```

The exact APIM error contract remains to be defined. A tool timeout must not be
presented as a completed review, even if the agent returns explanatory text.
Ambiguous requests can result in a clarifying question without a specialist call.

## Delivery is separate from runtime

Terraform provisions the platform; a private deployment runner uploads agent
code and manages version routing. CI uses local tests and mocked HTTP, without
creating Azure resources. The cost calculator is an analysis tool, not an agent
dependency. Redis and semantic caching are intentionally absent.

See [delivery status](status.md) for remaining gates and
[private deployment](private-deployment.md) for the operational sequence.