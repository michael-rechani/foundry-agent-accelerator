#!/usr/bin/env bash
set -euo pipefail

app="$(az containerapp show --name "$LAB_CONTAINER_APP" --resource-group "$AZURE_RESOURCE_GROUP" \
  --query '{id:id,revisionMode:properties.configuration.activeRevisionsMode,latest:properties.latestRevisionName,ready:properties.latestReadyRevisionName,containers:properties.template.containers[].{name:name,image:image}}' \
  --output json)"
revisions="$(az containerapp revision list --name "$LAB_CONTAINER_APP" --resource-group "$AZURE_RESOURCE_GROUP" \
  --query '[].{id:id,name:name,active:properties.active,state:properties.runningState,containers:properties.template.containers[].{name:name,image:image}}' \
  --output json)"
registry="$(az acr show --name "$LAB_REGISTRY" --query loginServer --output tsv)"
jq -n --argjson app "$app" --argjson revisions "$revisions" --arg registry "$registry" \
  '{app:$app,revisions:$revisions,registry:$registry}' |
  python3 .github/scripts/check_lab_image_release.py --live "$@"
