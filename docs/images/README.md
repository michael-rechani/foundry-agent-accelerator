# Architecture artwork

[Home](../../README.md) / [Docs](../README.md) / Architecture artwork

Use this guide when you edit or rebuild the architecture diagrams, Lab
screenshots, or README tour. The source files, exported SVGs, and Azure icons
are part of the documentation contract, so update them together and keep the
images readable at README width and on mobile.

## At a glance

| Artwork type | Source of truth | Rebuild command |
| --- | --- | --- |
| Detailed draw.io diagrams | `.drawio` files such as `lab-components.drawio` | `./docs/images/build-flow-diagrams.ps1 -DrawioPath "C:\Program Files\draw.io\draw.io.exe"` |
| High-level overview diagrams | `.template.svg` files such as `foundry-overview.template.svg` | `./docs/images/build-architecture.ps1` |
| Azure service icons | Unmodified SVG files in `azure-icons/` | Copied unchanged from the official Azure Architecture Center icon set. |
| Lab screenshots | Playwright tests in `workbench/frontend/tests/` | `npm test -- --project=desktop` in `workbench/frontend/`, then `./docs/images/refresh-screenshots.ps1` from the repo root |
| README and scenario tours | The twelve screenshots in `screenshots/` | `./docs/images/build-tour.ps1`, then `./docs/images/build-tour.ps1 -Tour scenarios` |

## Azure icons in architecture diagrams

The architecture diagrams use unmodified Microsoft Azure service icons from the
official [Azure Architecture Center icon set](https://learn.microsoft.com/azure/architecture/icons/),
release V24. The selected SVGs in `azure-icons/` are copied unchanged from
[Microsoft's distribution](https://arch-center.azureedge.net/icons/Azure_Public_Service_Icons_V24.zip),
which Microsoft updates in place; they match its July 2026 update. When you add
an icon, copy it from the current download under a short lowercase name, such
as `private-endpoints.svg`, and delete icons that no template or draw.io source
references.

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
copy. It rejects external image dependencies. Exports use the light theme only,
so GitHub shows the light artwork in both themes. These diagrams have no dark
variant yet: their SVGs come from draw.io Desktop, not the template build, so
the overview color map does not apply, and a dark export would need its own
draw.io Desktop pass and visual review. The script also removes
the PNG copies of text labels that draw.io adds for viewers without HTML text
support; browsers render the text directly, and the SVGs stay under 100 KB.
The standalone `.drawio` file is the source of truth; do not maintain a separate
edited copy inside the SVG. Use
`-PreviewDirectory <temporary-directory>` for PNG inspection copies, and
`-Names lab-components` to rebuild one view. Commit sources and SVG exports
together, not temporary previews or downloaded tools.

The root README opens with the [README tour](#readme-tour), an animated view of
**Explore demos**, **Create agent**, **Chat**, and **Document reviews** in light or
dark to match the reader's GitHub theme. A second tour presents the three
fictional customer stories. It shows the release journey,
agent-collaboration view, and Azure architecture view under "How it works",
and links to the architecture guide for the platform overview. The Azure
architecture view is wide, so the README pairs it with a full-size link. Detailed diagrams belong in the
[architecture guide](../architecture.md) and
[review workflow](../review-workflow.md), with full-size links for zooming on
small screens. Each view labels its requests, results, and persistence paths;
color alone does not identify a trust boundary or prove success. Product icons
identify Microsoft services; plain shapes identify custom code. Label optional
paths and execution boundaries explicitly rather than relying on color alone.

## High-level overview artwork

Use the six views for different questions rather than putting every component
in one diagram:

| View | Purpose | Editable source |
| --- | --- | --- |
| [Agent release journey](agent-release-journey.svg) | Customer-facing explanation of the separate foundation and agent-release workflows, their configuration handoff, and human approval boundaries. | [SVG template](agent-release-journey.template.svg) |
| [Azure architecture](azure-architecture.svg) | One-page network map: the subscription and resource group, the admin and workload networks with their default subnets, a private endpoint for each service, and seven numbered request steps. | [SVG template](azure-architecture.template.svg) |
| [Agent collaboration](agent-collaboration.svg) | Coordinator requests, specialist results, and human review. | [SVG template](agent-collaboration.template.svg) |
| [Lab infrastructure](foundry-overview.svg) | Default request paths and application-owned records; optional Azure API Management (APIM) stays outside the flow. | [SVG template](foundry-overview.template.svg) |
| [Operations and security](foundry-operations.svg) | Independent telemetry, image-publishing, and state paths, plus secret ownership. | [SVG template](foundry-operations.template.svg) |
| [Terraform deployment](foundry-deployment.svg) | Platform, Lab, Bastion, and agent monitoring resource ownership, existing prerequisites, and separate release workflows. | [SVG template](foundry-deployment.template.svg) |

Edit the [Azure architecture view](azure-architecture.template.svg),
[agent-collaboration view](agent-collaboration.template.svg),
[runtime overview](foundry-overview.template.svg),
[operations diagram](foundry-operations.template.svg), or
[deployment view](foundry-deployment.template.svg), or
[agent release journey](agent-release-journey.template.svg), then run:

```powershell
./docs/images/build-architecture.ps1
```

The build embeds any referenced icons as their original SVG bytes. It writes a
light `<name>.svg` and a dark `<name>-dark.svg` from each template; see
[Dark variants](#dark-variants). The
[rendered Azure architecture](azure-architecture.svg),
[rendered agent flow](agent-collaboration.svg),
[rendered overview](foundry-overview.svg),
[rendered operations diagram](foundry-operations.svg), and
[rendered deployment view](foundry-deployment.svg) remain self-contained when
GitHub displays them, as do their dark variants, with no external asset or
network dependency. Keep source icons, templates, and generated images together.

The Azure architecture view is the one-picture network map. It borrows the
layered layout of the Azure Architecture Center reference diagrams: dashed
boundaries for the subscription and resource group, blue panels for the two
virtual networks, and white subnet boxes labeled with their Terraform names and
default address ranges. Only what is deployed into a virtual network sits inside
one: Azure Bastion and the jumpbox in the admin network, and in the workload
network the Lab's internal Container Apps environment, the agent subnet
delegated to Foundry, and one private endpoint for each service. Foundry, data
services, and shared services sit outside the networks, each linked to its
private endpoint.

Numbered badges 1 to 7 follow one request and match the steps in the root
README and the SVG description. Solid blue arrows are requests, dashed green
arrows are data reads and writes, and plain gray lines are private endpoint
connections outside the numbered steps. Warm dashed cards mark optional
resources. The legend repeats each cue in words. Don't draw what Terraform
doesn't create, such as network security groups or a firewall, and don't add
paths the view omits on purpose, such as Lab logs, which reach Azure Monitor
through diagnostic settings rather than its private endpoint. Model names are
examples; deployments are configurable. Keep optional API Management and its
subnet out of this view. When a subnet or address default changes in Terraform,
update the view.

The collaboration view shows the Lab's default setup: **Application and case
helper** with the **Application checker** and **Case notes summarizer**
specialists. Its numbered steps match the root README. Steps 2 and 3 are stages
of one coordinator agent, not separate agents. Blue arrows carry requests;
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

The deployment view shows ownership, not another runtime flow. The Lab,
Bastion, and agent monitoring roots reference platform resources; none of them
takes ownership of the platform state. Build artifacts and agent versions remain
release-workflow outputs. Keep
optional alert delivery distinct from agent-triggered email, and do not depict
an enterprise landing zone or gateway as deployed by default.

These are logical diagrams, not a resource inventory. Only the Azure
architecture view shows subnets. Component boxes do not place managed services
inside virtual networks. The
overview focuses on runtime calls; the operations view covers monitoring,
private state access, and security boundaries. APIM is optional. Keep secret
ownership and private connectivity boundaries visible without adding
deployment-history notes.

## Dark variants

GitHub shows the `-dark` overview diagrams to readers who use a dark theme.
Both variants come from the same template, so do not edit either SVG by hand.
Edit the template, rebuild, and commit the template and both outputs together.

The build swaps colors in the template markup before it embeds the icons, so
the icon bytes are identical in both variants. The `<title>` and `<desc>` text
is never changed. `$darkPalette` in `build-architecture.ps1` is the single
light-to-dark color map. The build fails if a template uses a hex color that
the map does not cover, so add each new color to the map before you use it.
Colors match as whole tokens, ignoring case; `#fff` and `#ffffff` are separate
entries.

White has two roles. A white rectangle with no border, `stroke="none"`, or a
dashed border is part of the canvas: the background, label masks, and grouping
boundaries such as the Azure subscription. Other white fills are cards, which
use a raised surface so they stand out from the dark canvas.

| Role | Light | Dark |
| --- | --- | --- |
| Canvas, label masks, dashed boundaries | `#fff` | `#0d1117` |
| Cards | `#fff` | `#1f252e` |
| Subtle panels | `#f5f7fa` | `#161b22` |
| Blue-tinted panels | `#f3f8fc` | `#0f2438` |
| Green-tinted panels | `#edf7f4` | `#0e2723` |
| Warm-tinted panels | `#fffaf0` | `#2a2313` |
| Yellow notes | `#fff4ce` | `#3b300d` |
| Primary text | `#242424` | `#e6edf3` |
| Secondary text and bullets | `#4d5b69` | `#a9b4c0` |
| Tool names | `#334e68` | `#b8c9da` |
| Request arrows and accent borders | `#0078d4` | `#4aa8ff` |
| Result arrows and green borders | `#00786a` | `#3cc3ae` |
| Blue panel borders | `#8abce0` | `#4278a6` |
| Card and boundary borders | `#8da6bb` | `#6b7c8e` |
| Panel borders | `#aebdcb` | `#637484` |
| Subtle panel borders | `#cdd9e2` | `#5d6d7e` |
| Warm panel borders | `#b59e59` | `#a08845` |

Keep text at a WCAG contrast ratio of at least 4.5:1, and arrows and borders at
least 3:1, against every background they sit on. Update this table when you
change the map.

Icons stay unmodified in both variants. The current icons remain visible on the
dark surfaces, so the dark variants add no backing tiles. If a new icon becomes
hard to see, add a neutral light rounded tile behind every icon in that dark
diagram through the build; do not recolor the icon.

Embed both variants with a `<picture>` element. Paths are relative to the
Markdown file. Keep the alt text on the `<img>`, and leave a blank line before
and after the block so the surrounding Markdown still renders:

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/agent-collaboration-dark.svg">
  <img alt="Default agent collaboration: ..." src="docs/images/agent-collaboration.svg">
</picture>
```

Full-size and template links keep pointing to the light SVG and the template.
The draw.io diagrams stay light-only for now; see
[Detailed draw.io diagrams](#detailed-drawio-diagrams).

## Lab screenshots

The screenshots in `screenshots/` come from the Lab's browser tests. The tests
replace the backend with mocked API responses, so the images show real UI
layout but not live model answers or saved records. Each image carries the
**ILLUSTRATIVE UI TEST** watermark in its lower-right corner; keep it visible
and say "illustrative" in the caption and alt text wherever you use one.

| Screenshot | Shows | Test output | Used in |
| --- | --- | --- | --- |
| [lab-chat-start.png](screenshots/lab-chat-start.png) | An empty **Chat** with the default agent's guide and example tasks | `demo-starters.png` | [README tour](#readme-tour), [demo guide](../demos.md#a-short-demonstration) |
| [lab-chat-start-dark.png](screenshots/lab-chat-start-dark.png) | The same **Chat** with the **System** theme and a dark color scheme | `demo-starters-dark.png` | [README tour](#readme-tour) for readers using GitHub's dark theme |
| [lab-document-review.png](screenshots/lab-document-review.png) | A **Document reviews** record with a gap, a supported item, and its quoted source | `review-findings.png` | [README tour](#readme-tour), [review workflow](../review-workflow.md#workflow) |
| [lab-document-review-dark.png](screenshots/lab-document-review-dark.png) | The same review with the **System** theme and a dark color scheme | `review-findings-dark.png` | [README tour](#readme-tour) for readers using GitHub's dark theme |
| [lab-create-agent.png](screenshots/lab-create-agent.png) | The **Create agent** page with its templates in two groups and the full sidebar | `creation-start.png` | [README tour](#readme-tour) and its full-size link, [agent creation](../agent-creation.md#what-a-participant-can-do) |
| [lab-create-agent-dark.png](screenshots/lab-create-agent-dark.png) | The same page in the **Dark** theme with the Foundry accent and one template selected | `creation-start-dark.png` | [README tour](#readme-tour) for readers using GitHub's dark theme |
| [lab-demo-application.png](screenshots/lab-demo-application.png) / [dark](screenshots/lab-demo-application-dark.png) | Application completeness story in **Explore demos** | `demo-application.png` / `demo-application-dark.png` | README and scenario tours, [showcase](../showcase.md) |
| [lab-demo-invoice.png](screenshots/lab-demo-invoice.png) / [dark](screenshots/lab-demo-invoice-dark.png) | Supplier invoice story with clearly illustrative findings | `demo-invoice.png` / `demo-invoice-dark.png` | Scenario tour and showcase |
| [lab-demo-casework.png](screenshots/lab-demo-casework.png) / [dark](screenshots/lab-demo-casework-dark.png) | Casework story preserving facts, disagreements, and human decisions | `demo-casework.png` / `demo-casework-dark.png` | Scenario tour and showcase |

To refresh them, run the desktop browser tests, then the asset refresh script:

```powershell
cd workbench/frontend
npm ci
npx playwright install chromium
npm test -- --project=desktop
cd ../..
./docs/images/refresh-screenshots.ps1
```

The tests write 1440 x 1000 PNGs under `test-results/`, which Git ignores.
The refresh script requires exactly one desktop result per source and validates
every PNG before replacing the documentation images. It also rebuilds both
tours. Do not crop out the watermark or substitute mobile screenshots.

## README tour

The root README opens with [lab-tour.svg](lab-tour.svg), or
[lab-tour-dark.svg](lab-tour-dark.svg) for readers using GitHub's dark theme.
Each tour crossfades between four Lab screenshots, about four seconds each,
and loops:

| Step | Light frame | Dark frame |
| --- | --- | --- |
| 1 · Explore demos | `lab-demo-application.png` | `lab-demo-application-dark.png` |
| 2 · Create an agent | `lab-create-agent.png` | `lab-create-agent-dark.png` |
| 3 · Chat with it | `lab-chat-start.png` | `lab-chat-start-dark.png` |
| 4 · Review documents | `lab-document-review.png` | `lab-document-review-dark.png` |

[scenario-tour.svg](scenario-tour.svg) and its [dark variant](scenario-tour-dark.svg)
use the application, invoice, and casework screenshots as three separate
customer stories. They share the same accessible frame and reduced-motion behavior.

A minimal window bar above the frames names the current step and shows a
progress bar, so nothing covers the screenshots or their watermark. Both SVGs
are generated, so do not edit them by hand. The frames are copies of the
screenshots, so after you refresh any of the twelve, rebuild both tours and commit
the screenshots and SVGs together:

```powershell
./docs/images/build-tour.ps1
./docs/images/build-tour.ps1 -Tour scenarios
```

The build embeds each PNG unchanged as base64 data and animates with CSS only.
The SVGs have no scripts or external references, because GitHub shows README
SVGs as images. The build fails if a screenshot is missing or is not 1440 x 1000
desktop test output, and reruns give byte-identical files. Keep each SVG under
about 1.3 MB, and do not recompress the frames as JPEG,
which blurs the watermark and UI text.

For readers who turn on reduced motion in their operating system, the SVGs'
`prefers-reduced-motion: reduce` rules stop every animation and show only the
first frame, **Explore demos** (or the application story), with its step label. The SVG `<title>` and
`<desc>` say that the tour is an illustrative UI test with mocked APIs, and the
README alt text describes the full sequence.

## Visual review checklist

- Check each image at README width and on mobile.
- Check the overview diagrams in both GitHub themes. Render the light and
  `-dark` SVGs and confirm that text, arrows, notes, icons, and card edges stay
  visible in each.
- Refresh each `-dark` screenshot together with its light screenshot so the two
  README tour variants show the same UI.
- After you refresh any tour screenshot, rebuild the tour with
  `./docs/images/build-tour.ps1`, then check a paused frame, a mid-fade state,
  and the reduced-motion first frame in both variants.
- Keep labels short and avoid crossing text with connectors.
- Do not reduce type to fit more detail.
- Use labels and callouts, not color alone, to explain requests, results,
  persistence paths, optional paths, and execution boundaries.

## Related content

- [Architecture](../architecture.md)
- [Docs](../README.md)
- [Home](../../README.md)
