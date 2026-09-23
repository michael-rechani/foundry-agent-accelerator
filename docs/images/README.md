# Architecture artwork

[Home](../../README.md) / [Docs](../README.md) / Architecture artwork

Use this guide when you edit or rebuild the architecture diagrams. The source
files, exported SVGs, and Azure icons are part of the documentation contract, so
update them together and keep the diagrams readable at README width and on
mobile.

## At a glance

| Artwork type | Source of truth | Rebuild command |
| --- | --- | --- |
| Detailed draw.io diagrams | `.drawio` files such as `lab-components.drawio` | `./docs/images/build-flow-diagrams.ps1 -DrawioPath "C:\Program Files\draw.io\draw.io.exe"` |
| High-level overview diagrams | `.template.svg` files such as `foundry-overview.template.svg` | `./docs/images/build-architecture.ps1` |
| Azure service icons | Unmodified SVG files in `azure-icons/` | Copied unchanged from the official Azure Architecture Center icon set. |

## Azure icons in architecture diagrams

The architecture diagrams use unmodified Microsoft Azure service icons from the
official [Azure Architecture Center icon set](https://learn.microsoft.com/azure/architecture/icons/),
release V24. The selected SVGs in `azure-icons/` are copied unchanged from
[Microsoft's distribution](https://arch-center.azureedge.net/icons/Azure_Public_Service_Icons_V24.zip).

Microsoft permits these icons in architectural diagrams, training materials, and
documentation, and reserves other rights. Do not crop, recolor, distort, rotate,
or repurpose product icons to represent custom applications. Product names
accompany their icons; custom review agents use plain labeled shapes inside the
Foundry Agent Service boundary.

## Detailed draw.io diagrams

The deeper architecture views are native, editable draw.io documents. Shapes,
labels, boundaries, and connectors remain editable; these are not flattened
screenshots imported into draw.io. Official icon bytes are embedded unchanged.

| View | Editable source | GitHub-readable export |
| --- | --- | --- |
| Lab components and dependencies | [lab-components.drawio](lab-components.drawio) | [lab-components.svg](lab-components.svg) |
| Chat request, delegation, and save | [lab-request-flow.drawio](lab-request-flow.drawio) | [lab-request-flow.svg](lab-request-flow.svg) |
| Review persistence and recovery | [review-lifecycle.drawio](review-lifecycle.drawio) | [review-lifecycle.svg](review-lifecycle.svg) |

Open a source in draw.io Desktop, or choose **File > Open from > Device** in
[diagrams.net](https://app.diagrams.net/). Edit the source, then export with
draw.io Desktop (verified with version 31.4.4):

```powershell
./docs/images/build-flow-diagrams.ps1 -DrawioPath "C:\Program Files\draw.io\draw.io.exe"
```

The script checks native XML references, embeds any `azure-icons/...` image
references, and exports SVGs containing both the artwork and an editable diagram
copy. It rejects external image dependencies. The standalone `.drawio` file is
the source of truth; do not maintain a separate edited copy inside the SVG. Use
`-PreviewDirectory <temporary-directory>` for PNG inspection copies, and
`-Names lab-components` to rebuild one view. Commit sources and SVG exports
together, not temporary previews or downloaded tools.

The root README leads with the agent-collaboration view and links to the
platform overview. Detailed diagrams belong in the
[architecture guide](../architecture.md) and
[review workflow](../review-workflow.md), with full-size links for zooming on
small screens. Each view labels its requests, results, and persistence paths;
color alone does not identify a trust boundary or prove success. Product icons
identify Microsoft services; plain shapes identify custom code. Label optional
paths and execution boundaries explicitly rather than relying on color alone.

## High-level overview artwork

Use the four views for different questions rather than putting every component
in one diagram:

| View | Purpose | Editable source |
| --- | --- | --- |
| [Agent collaboration](agent-collaboration.svg) | Coordinator requests, specialist results, and human review. | [SVG template](agent-collaboration.template.svg) |
| [Lab infrastructure](foundry-overview.svg) | Default request paths and application-owned records; optional Azure API Management (APIM) stays outside the flow. | [SVG template](foundry-overview.template.svg) |
| [Operations and security](foundry-operations.svg) | Independent telemetry, image-publishing, and state paths, plus secret ownership. | [SVG template](foundry-operations.template.svg) |
| [Terraform deployment](foundry-deployment.svg) | Platform and Lab resource ownership, existing prerequisites, and separate release workflows. | [SVG template](foundry-deployment.template.svg) |

Edit the [agent-collaboration view](agent-collaboration.template.svg),
[runtime overview](foundry-overview.template.svg),
[operations diagram](foundry-operations.template.svg), or
[deployment view](foundry-deployment.template.svg), then run:

```powershell
./docs/images/build-architecture.ps1
```

The build embeds any referenced icons as their original SVG bytes. The
[rendered agent flow](agent-collaboration.svg),
[rendered overview](foundry-overview.svg),
[rendered operations diagram](foundry-operations.svg), and
[rendered deployment view](foundry-deployment.svg) remain self-contained when
GitHub displays them, with no external asset or network dependency. Keep source
icons, templates, and generated images together.

The collaboration view shows the default review profile. Its two coordinator
boxes are stages of one agent, not separate agents. Blue arrows carry requests;
green arrows return results. Arrow labels and text explain the distinction
without relying on color. Keep the one-specialist default,
clarification/failure behavior, and human-review boundary aligned with the
implementation. The official Foundry icon labels the service boundary; the
custom agents use plain cards.

The infrastructure view separates agent calls from record reads and writes. Its
dashed record path is not an automatic transcript-save step. Keep explicit chat
saves distinct from server-persisted review drafts and results. The operations
rows are independent paths, not sequential tasks or network boundaries. Preserve
the existing-backend requirement and the distinction between Entra
authentication and a specific managed identity.

The deployment view shows ownership, not another runtime flow. The Lab
references platform resources; it does not take ownership of the whole platform
state. Build artifacts and agent versions remain release-workflow outputs. Keep
optional alert delivery distinct from agent-triggered email, and do not depict
an enterprise landing zone or gateway as deployed by default.

These are logical diagrams, not an exhaustive subnet or resource inventory.
Component boxes do not place managed services inside virtual networks. The
overview focuses on runtime calls; the operations view covers monitoring,
private state access, and security boundaries. APIM is optional. Keep secret
ownership and private connectivity boundaries visible without adding
deployment-history notes.

## Visual review checklist

- Check each image at README width and on mobile.
- Keep labels short and avoid crossing text with connectors.
- Do not reduce type to fit more detail.
- Use labels and callouts, not color alone, to explain requests, results,
  persistence paths, optional paths, and execution boundaries.
