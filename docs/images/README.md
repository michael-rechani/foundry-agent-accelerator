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

Edit [the diagram template](foundry-runtime-architecture.template.svg), then run:

```powershell
./docs/images/build-architecture.ps1
```

The build embeds the original SVG bytes as image data in
[the rendered diagram](foundry-runtime-architecture.svg). It remains
self-contained when GitHub displays it as an image, with no external asset or
network dependency. Keep the source icons, template, and generated image together.

Azure resource groups, VNets, integration subnets, private endpoints, and PaaS
services are distinct concepts. APIM's public gateway is not drawn inside its
outbound integration subnet; Foundry is a managed service accessed through
private endpoints, not a VM inside the workload VNet. This is a logical diagram,
not an exhaustive subnet or resource inventory. Dashed connectors identify the
API route that has not been published; operational status belongs in the
[delivery notes](../status.md), not a snapshot banner on the artwork.