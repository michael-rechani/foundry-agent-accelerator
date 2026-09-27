# Architecture artwork

[Home](../../README.md) / [Docs](../README.md) / Architecture artwork

Use this guide when you edit or rebuild the architecture diagrams, Lab
screenshots, or README tour. The templates, generated SVGs, and Azure icons
are part of the documentation contract, so update them together and keep the
images readable at README width and on mobile.

## At a glance

| Artwork type | Source of truth | Rebuild command |
| --- | --- | --- |
| Diagrams | `.template.svg` files such as `azure-architecture.template.svg` | `./docs/images/build-architecture.ps1` |
| Azure service icons | Unmodified SVG files in `azure-icons/` | Copied unchanged from the official Azure Architecture Center icon set. |
| Lab screenshots | Playwright tests in `workbench/frontend/tests/` | `npm test -- --project=desktop` in `workbench/frontend/`, then `./docs/images/refresh-screenshots.ps1` from the repo root |
| README and scenario tours | The twelve screenshots in `screenshots/` | `./docs/images/build-tour.ps1`, then `./docs/images/build-tour.ps1 -Tour scenarios` |

## Diagrams

Each diagram answers one question, so no single picture has to show every
component:

| Diagram | What it shows | Where it appears | Source |
| --- | --- | --- | --- |
| [Agent release journey](agent-release-journey.svg) | The private foundation and agent releases as two connected workflows, their configuration handoff, and the decisions people approve. | [README](../../README.md#one-foundation-two-connected-workflows), [showcase](../showcase.md) | [Template](agent-release-journey.template.svg) |
| [Azure architecture](azure-architecture.svg) | One-page network map: the subscription and resource group, the admin and workload networks with their default subnets, a private endpoint for each service, and seven numbered request steps. | [README](../../README.md#what-runs-in-azure) | [Template](azure-architecture.template.svg) |
| [Agent collaboration](agent-collaboration.svg) | The coordinator's requests to specialists, their results, and the person who checks the answer. | [README](../../README.md#agents-working-together), [architecture guide](../architecture.md#agent-collaboration) | [Template](agent-collaboration.template.svg) |
| [Orchestration pattern](orchestration-pattern.svg) | How the coordinator compares with the five patterns in Microsoft's agent orchestration guide: handoff is the closest match, with one difference. | [Architecture guide](../architecture.md#orchestration-pattern) | [Template](orchestration-pattern.template.svg) |
| [How the Lab handles a request](foundry-overview.svg) | The Lab's request path, the records it saves, and optional Azure API Management (APIM) outside the default flow. | [Architecture guide](../architecture.md#implementation-overview) | [Template](foundry-overview.template.svg) |
| [Lab components](lab-components.svg) | What runs in the browser, the Lab's internal container app, Microsoft Foundry, and the data store, and how they connect. | [Architecture guide](../architecture.md#component-interactions) | [Template](lab-components.template.svg) |
| [Chat request flow](lab-request-flow.svg) | One chat request in sequence: admission, specialist delegation, receipts, and the separate save to shared history. | [Architecture guide](../architecture.md#chat-and-delegation) | [Template](lab-request-flow.template.svg) |
| [Review lifecycle](review-lifecycle.svg) | What a document review saves before it runs, how results are checked, and how clarification resumes. | [Review workflow](../review-workflow.md#execution-and-persistence) | [Template](review-lifecycle.template.svg) |
| [Operations](foundry-operations.svg) | Independent telemetry, image-publishing, and state paths, plus secret ownership. | [Architecture guide](../architecture.md#operations) | [Template](foundry-operations.template.svg) |
| [Terraform deployment](foundry-deployment.svg) | Which Terraform root owns what, what must exist first, and the separate release workflows. | [Extension guide](../architecture-assessment.md#terraform-first-deployment) | [Template](foundry-deployment.template.svg) |

Edit a template, then rebuild every diagram, or only the ones you changed:

```powershell
./docs/images/build-architecture.ps1
./docs/images/build-architecture.ps1 -Name agent-collaboration
```

The build picks up every `*.template.svg` file in this folder. It writes a
light `<name>.svg` and a dark `<name>-dark.svg` from each template (see
[Dark variants](#dark-variants)) and embeds the referenced icons as their
original SVG bytes. The generated SVGs are self-contained when GitHub displays
them, with no external asset or network dependency, so don't edit them by
hand. Commit each template with both of its outputs.

The **docs** check in the Validate workflow reruns the build and fails if any
committed SVG differs from its template's output. It also checks every relative
link, image path, and heading anchor in the repository's Markdown. Run the same
link check locally before you push:

```powershell
python .github/scripts/check_markdown_links.py
```

These are logical diagrams, not a resource inventory. Only the Azure
architecture view shows subnets; elsewhere, boxes don't place managed services
inside virtual networks.

## Diagram style

All ten diagrams follow the same rules, so the set reads as one family. They
borrow the layered layout of the
[Azure Architecture Center](https://learn.microsoft.com/azure/architecture/browse/)
reference diagrams, simplified for a workshop audience: official icons,
restrained color, generous spacing, and labeled flows.

- **Canvas:** 1600 pixels wide, so every diagram scales by the same amount at
  README width. The height fits the content.
- **Header:** a 34 px title and a 21 px subtitle that states the main idea.
  When a diagram has numbered steps, the subtitle says what they follow.
- **Type:** 20 px semibold names; 18 px details, captions, and arrow labels;
  17 px monospace for paths, endpoints, and tool names; 18 px uppercase labels
  for boundaries. Don't go smaller; add height or cut words instead.
- **Boundaries and panels:**
  - Dashed outlines group things that share a scope, such as the subscription,
    a phase, or the roots that read platform resources.
  - Blue panels hold Azure services and networks.
  - Green panels hold data.
  - Gray panels hold people, the browser, and tooling.
  - Warm dashed cards mark optional resources.
  - Yellow boxes hold caveats.
- **Cards:** white with a thin border. A 2 px blue border marks the focal item.
  Microsoft services carry their official icon and product name. Custom agents
  and custom code use plain cards, sometimes with a monospace name. Name
  third-party tools such as Terraform and Docker in text; don't use their logos.
- **Arrows:** solid blue for requests, solid green for results, dashed green
  for data reads and writes, and plain gray for connections with no direction,
  such as a private endpoint and its service. Arrows don't cross, and their
  labels sit clear of borders.
- **Numbered badges:** blue circles on requests and green circles on data
  steps, numbered in the order of one story. The steps beside the diagram and
  the SVG description use the same numbers.
- **Legend:** a bottom row repeats, in words, only the cues that diagram uses,
  with one short caveat on the right.
- **Color:** only the colors in the [dark-variant map](#dark-variants). No
  gradients, shadows, transparency, or animation.
- **Accessibility:** the `<title>` names the diagram and the `<desc>` describes
  every box, path, and step in prose. Labels, not color alone, carry meaning.

### Keep each diagram accurate

The Azure architecture view is the one-picture network map. Only what is
deployed into a virtual network sits inside one: Azure Bastion and the jumpbox
in the admin network, and in the workload network the Lab's internal Container
Apps environment, the agent subnet delegated to Foundry, and one private
endpoint for each service. Foundry, data services, and shared services sit
outside the networks, each linked to its private endpoint. Step 6 starts at
Foundry Agent Service and runs through the agent subnet, because agents reach
their data from there. Badges 1 to 7 follow one request and match the steps in
the root README. Don't draw what Terraform doesn't create, such as network
security groups or a firewall, and don't add paths the view omits on purpose,
such as Lab logs, which reach Azure Monitor through diagnostic settings rather
than its private endpoint. Model names are examples; deployments are
configurable. Keep optional API Management and its subnet out of this view.
When a subnet or address default changes in Terraform, update the view.

The collaboration view shows the Lab's default setup: **Application and case
helper** with the **Application checker** and **Case notes summarizer**
specialists. Its numbered steps match the root README. Steps 2 and 3 are stages
of one coordinator agent, not separate agents. Keep the one-specialist default,
clarification and failure behavior, and human-review boundary aligned with the
implementation.

The orchestration-pattern view compares the default coordinator with the five
patterns in Microsoft's
[AI agent orchestration patterns](https://learn.microsoft.com/azure/architecture/ai-ml/guide/ai-agent-design-patterns)
guide. Keep its message precise: handoff is the *closest* match, not an exact
one, because specialists are tools and control stays with the coordinator. It
uses plain shapes rather than icons, because the patterns are concepts, not
products. Gray arrows show generic pattern flow and dashed gray arrows show
routes not taken; the blue request and green result arrows belong to the
coordinator. Each pattern also has a text status, so color is not the only
signal. The schematics are redrawn, not copied; keep the CC BY 4.0 attribution
in the diagram, its description, and the architecture guide caption.

The Lab request view separates agent calls from record saves. Chat is saved
only when someone asks; review drafts and results are saved by the server.
Neither is an automatic transcript save. Keep optional APIM outside the default
flow.

The component map and the chat request flow show the Lab's own code as plain
cards: the FastAPI request boundary, its routes, and `FoundryGateway`. The
platform's Storage, Cosmos DB, and Azure AI Search backing services are distinct
from the Lab's application records. In the request flow, saving to shared
history is a separate user action, and limits match the values in
`workbench/app.py`.

The review lifecycle shows that a review is saved before it runs, that results
must pass fail-closed checks before the final write, and how clarification
resumes a run. Keep its endpoints, status codes, and steps aligned with
`workbench/review_runs.py` and the [review workflow](../review-workflow.md).

The operations lanes are independent paths, not sequential tasks or network
boundaries. Optional agent traces come from Foundry, not the Lab. Preserve the
existing-backend requirement and the distinction between Entra authentication
and a specific managed identity.

The deployment view shows ownership, not another runtime flow. The Lab,
Bastion, and agent monitoring roots reference platform resources; none of them
takes ownership of the platform state. Build artifacts and agent versions remain
release-workflow outputs. Keep optional alert delivery distinct from
agent-triggered email, and don't depict an enterprise landing zone or gateway
as deployed by default.

## Azure icons in architecture diagrams

The diagrams use unmodified Microsoft Azure service icons from the
official [Azure Architecture Center icon set](https://learn.microsoft.com/azure/architecture/icons/),
release V24. The selected SVGs in `azure-icons/` are copied unchanged from
[Microsoft's distribution](https://arch-center.azureedge.net/icons/Azure_Public_Service_Icons_V24.zip),
which Microsoft updates in place; they match its July 2026 update. When you add
an icon, copy it from the current download under a short lowercase name, such
as `private-endpoints.svg`, and delete icons that no template references.

Microsoft permits these icons in architectural diagrams, training materials, and
documentation, and reserves other rights. Do not crop, recolor, distort, rotate,
or repurpose product icons to represent custom applications. Product names
accompany their icons; custom review agents use plain labeled cards inside the
Foundry Agent Service boundary. Don't use the Azure logo as a service icon.

## Dark variants

GitHub shows the `-dark` diagrams to readers who use a dark theme.
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

Every diagram and screenshot embed uses this pattern. Full-size and template
links keep pointing to the light SVG and the template.

## Lab screenshots

The screenshots in `screenshots/` come from the Lab's browser tests. The tests
replace the backend with mocked API responses, so the images show real UI
layout but not live model answers or saved records. Each image carries the
**ILLUSTRATIVE UI TEST** watermark in its lower-right corner; keep it visible
and say "illustrative" in the caption and alt text wherever you use one.

| Screenshot | Shows | Test output | Used in |
| --- | --- | --- | --- |
| [lab-chat-start.png](screenshots/lab-chat-start.png) | An empty **Chat** with the default agent's guide and example tasks | `demo-starters.png` | [README tour](#readme-tour), [demo guide](../demos.md#a-short-demonstration) |
| [lab-chat-start-dark.png](screenshots/lab-chat-start-dark.png) | The same **Chat** with the **System** theme and a dark color scheme | `demo-starters-dark.png` | Everywhere the light image appears, for readers using GitHub's dark theme |
| [lab-document-review.png](screenshots/lab-document-review.png) | A **Document reviews** record with a gap, a supported item, and its quoted source | `review-findings.png` | [README tour](#readme-tour), [review workflow](../review-workflow.md#workflow) |
| [lab-document-review-dark.png](screenshots/lab-document-review-dark.png) | The same review with the **System** theme and a dark color scheme | `review-findings-dark.png` | Everywhere the light image appears, for readers using GitHub's dark theme |
| [lab-create-agent.png](screenshots/lab-create-agent.png) | The **Create agent** page with its templates in two groups and the full sidebar | `creation-start.png` | [README tour](#readme-tour) and its full-size link, [agent creation](../agent-creation.md#what-a-participant-can-do) |
| [lab-create-agent-dark.png](screenshots/lab-create-agent-dark.png) | The same page in the **Dark** theme with the Foundry accent and one template selected | `creation-start-dark.png` | Everywhere the light image appears, for readers using GitHub's dark theme |
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
customer stories. The root README links to them from its story table rather
than embedding them, because their first frame repeats the Lab tour's. They
share the same accessible frame and reduced-motion behavior.

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
- Check every diagram in both GitHub themes. Render the light and `-dark` SVGs
  and confirm that text, arrows, notes, icons, and card edges stay visible in
  each.
- Confirm that each diagram follows the [diagram style](#diagram-style): gaps
  wide enough for arrow labels, no crossings, labels clear of borders, and
  numbered badges that match the steps in the surrounding page.
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
