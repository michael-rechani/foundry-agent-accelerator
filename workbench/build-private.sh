#!/usr/bin/env bash
set -euo pipefail
umask 077
work=$(mktemp -d)
trap 'docker logout "$registry" >/dev/null 2>&1 || true; rm -rf "$work"' EXIT
registry='__REGISTRY__.azurecr.io'
tag='__TAG__'
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq docker.io unzip curl python3 >/dev/null
systemctl start docker
printf '%s' '__ARCHIVE__' | base64 --decode > "$work/source.zip"
printf '%s  %s\n' '__HASH__' "$work/source.zip" | sha256sum --check --status
unzip -q "$work/source.zip" -d "$work/source"
find "$work/source" -type d -exec chmod 755 {} +
find "$work/source" -type f -exec chmod 644 {} +
getent ahostsv4 "$registry" | awk '{print $1}' | sort -u | grep -Eq '^10\.(42|43)\.'
access_token=$(curl --fail --silent --show-error --noproxy '*' -H Metadata:true 'http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https%3A%2F%2Fmanagement.azure.com%2F' | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
refresh_token=$(curl --fail --silent --show-error "https://$registry/oauth2/exchange" --data-urlencode 'grant_type=access_token' --data-urlencode "service=$registry" --data-urlencode 'tenant=__TENANT__' --data-urlencode "access_token=$access_token" | python3 -c 'import json,sys; print(json.load(sys.stdin)["refresh_token"])')
unset access_token
printf '%s' "$refresh_token" | docker login "$registry" --username 00000000-0000-0000-0000-000000000000 --password-stdin >/dev/null
unset refresh_token
docker build --pull --tag "$registry/workbench:$tag" "$work/source" > "$work/build.log" 2>&1 || { tail -n 30 "$work/build.log"; exit 1; }
docker run --rm --entrypoint python "$registry/workbench:$tag" -c 'import app, history; from pathlib import Path; assert Path("agents.json").read_text(); assert Path("static/index.html").read_text()'
docker push "$registry/workbench:$tag" > "$work/push.log" 2>&1 || { tail -n 20 "$work/push.log"; exit 1; }
docker image inspect "$registry/workbench:$tag" --format '{{index .RepoDigests 0}}'
docker image rm "$registry/workbench:$tag" >/dev/null
docker pull "$registry/workbench:$tag" > /dev/null
printf 'PRIVATE_BUILD_PUSH_AND_PULL_VERIFIED=True\n'