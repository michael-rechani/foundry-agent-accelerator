#!/bin/bash
# Deallocates this VM after it has been idle for IDLE_SHUTDOWN_MINUTES. Deallocating
# stops compute charges; an in-guest shutdown would not. It authenticates with the
# VM's managed identity, which can deallocate only this VM. No credentials are stored.
set -euo pipefail
set +x

# shellcheck source=/dev/null
. /etc/runner/provision.env

# Never deallocate before the runner is registered, or while a job or update runs.
[ -f /opt/actions-runner/.runner ] || exit 0

state=/run/runner-idle-since
if pgrep -f 'Runner\.Worker' >/dev/null || pgrep -x unattended-upgr >/dev/null || pgrep -x apt-get >/dev/null; then
  rm -f "${state}"
  exit 0
fi

now=$(date +%s)
if [ ! -f "${state}" ]; then
  echo "${now}" >"${state}"
  exit 0
fi

since=$(cat "${state}")
if [ $((now - since)) -lt $((IDLE_SHUTDOWN_MINUTES * 60)) ]; then
  exit 0
fi

imds=http://169.254.169.254/metadata
meta=$(curl -fsS -H Metadata:true --noproxy '*' "${imds}/instance/compute?api-version=2021-02-01")
subscription=$(jq -r .subscriptionId <<<"${meta}")
group=$(jq -r .resourceGroupName <<<"${meta}")
vm=$(jq -r .name <<<"${meta}")
token=$(curl -fsS -H Metadata:true --noproxy '*' \
  "${imds}/identity/oauth2/token?api-version=2018-02-01&resource=https://management.azure.com/" |
  jq -r .access_token)

logger -t runner-idle "Idle for ${IDLE_SHUTDOWN_MINUTES} minutes; deallocating ${vm}."
curl -fsS -X POST -H "Authorization: Bearer ${token}" -H 'Content-Length: 0' \
  "https://management.azure.com/subscriptions/${subscription}/resourceGroups/${group}/providers/Microsoft.Compute/virtualMachines/${vm}/deallocate?api-version=2024-07-01" \
  >/dev/null
