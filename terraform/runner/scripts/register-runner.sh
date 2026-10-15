#!/bin/bash
# Registers this VM as a repository runner and installs it as a systemd service
# that runs as the non-root "runner" user. Run it as root through Azure Run Command.
#
# RUNNER_TOKEN is the registration token you generate in GitHub under
# Settings > Actions > Runners > New self-hosted runner. It arrives as an
# environment variable from a Run Command protected parameter, is handed to the
# runner through the environment (never an argument), and is never written to disk
# or printed.
set -euo pipefail
set +x

: "${RUNNER_TOKEN:?RUNNER_TOKEN must be passed as a protected parameter}"

# shellcheck source=/dev/null
. /etc/runner/provision.env

if [ ! -f /var/lib/runner-provisioned ]; then
  echo "Provisioning hasn't finished. Check /var/log/cloud-init-output.log." >&2
  exit 1
fi

cd /opt/actions-runner

if [ -f .runner ]; then
  echo "This runner is already registered. Remove it in GitHub and delete /opt/actions-runner/.runner first." >&2
  exit 1
fi

ACTIONS_RUNNER_INPUT_TOKEN="${RUNNER_TOKEN}" \
  runuser -u runner --preserve-environment -- ./config.sh \
    --unattended \
    --url "https://github.com/${GITHUB_REPOSITORY}" \
    --name "$(hostname)" \
    --labels lab-runner \
    --work _work \
    --replace
unset RUNNER_TOKEN

./svc.sh install runner
./svc.sh start
./svc.sh status | head -n 5
