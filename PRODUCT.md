# Foundry Agent Accelerator

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Customer demo leads and workshop participants come first. Developers and
operators reuse the agent code, private infrastructure, and release tooling.

## Product Purpose

Help a participant explore one practical agent task, inspect its evidence,
understand its limitations, and identify what a person must decide next.

## Positioning

A customer-facing demonstration experience backed by reusable Microsoft
Foundry hosted agents and Terraform/Azure Verified Modules infrastructure.
This repository is a sample, not an official Microsoft product or a
production-ready business application.

## Operating Context

The private Azure deployment supports model calls and shared saved records.
Local preview supports exploration without model execution or persistence.
Browser-test artwork uses explicitly labeled mocked APIs, not live results.

## Capabilities and Constraints

- Create agents from reviewed templates only after explicit operator and cost
  confirmation. Preparing a setup is not publication.
- Chat with configured agents; review supplied documents against criteria.
- Keep fictional inputs, expected findings, and actual model responses distinct.
- Never imply customer-system connectivity: template lookups are simulated
  and read-only. People make business, clinical, payment, and eligibility decisions.
- Shared records have no per-user authorization boundary. Private networking
  does not make records private to a participant.
- Preserve resource names, catalog IDs, routes, Terraform state, and operator
  configuration when changing display branding.

## Brand Commitments

Use **Foundry Agent Accelerator** for the repository, **Foundry Agent Lab** for
the browser experience, and **Microsoft Foundry** for the underlying service. Retain the existing light/dark themes, optional accents,
framed walkthroughs, and evidence-led voice. Show practical work, not invented
benchmarks, customer endorsements, or production claims.

## Evidence on Hand

The repository includes fictional scenarios in `docs/demo-inputs/`, reviewed
templates in `workbench/agent_templates.py`, simulated lookup records in
`workbench/agent_runtime/demo_tools.py`, and editable architecture artwork in
`docs/images/`. Expected findings are examples to check, not measured outcomes.

## Product Principles

- Start with a recognizable customer task, not infrastructure terminology.
- Make evidence, uncertainty, and the human decision visible.
- Keep exploration separate from resource creation and paid execution.
- Reuse one foundation while releasing and verifying agents independently.
