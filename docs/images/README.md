# Architecture artwork

The diagram uses unmodified Microsoft Azure service icons from the official
[Azure Architecture Center icon set](https://learn.microsoft.com/azure/architecture/icons/),
release V24. The selected SVGs in `azure-icons/` are copied unchanged from
[Microsoft's distribution](https://arch-center.azureedge.net/icons/Azure_Public_Service_Icons_V24.zip).

Microsoft permits these icons in architectural diagrams, training materials,
and documentation, and reserves other rights. Do not crop, recolor, distort,
rotate, or repurpose product icons to represent custom applications. Product
names accompany their icons; custom review agents use plain labeled shapes
inside the Foundry Agent Service boundary.

Edit the [runtime overview](foundry-overview.template.svg) or
[operations diagram](foundry-operations.template.svg), then run:

```powershell
./docs/images/build-architecture.ps1
```

The build embeds the original SVG bytes as image data in the
[rendered overview](foundry-overview.svg) and
[rendered operations diagram](foundry-operations.svg). Both remain self-contained
when GitHub displays them, with no external asset or network dependency. Keep
source icons, templates, and generated images together.

These are logical diagrams, not an exhaustive subnet or resource inventory.
Component boxes do not place managed services inside VNets. The overview focuses
on runtime calls; the operations view covers monitoring, private state access,
and security boundaries. APIM publication and platform credential migration remain
explicitly incomplete. Detailed evidence belongs in [delivery status](../status.md).

Check both images at README width and on mobile after editing. Keep labels short,
avoid crossing text with connectors, and do not reduce type to fit more detail.