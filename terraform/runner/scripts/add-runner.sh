#!/bin/bash
# Adds one more runner on this VM so jobs run in parallel. Run it as root through
# Azure Run Command, after the first runner is registered. This script is not
# baked into cloud-init, so using it never changes the VM's Terraform plan.
#
# RUNNER_TOKEN: a registration token from GitHub, passed as a Run Command
#   protected parameter. It is never written to disk or printed.
# RUNNER_INSTANCE: a number of 2 or more. Instance N lives in /opt/actions-runner-N
#   and is named "<hostname>-N".
set -euo pipefail
set +x

: "${RUNNER_TOKEN:?RUNNER_TOKEN must be passed as a protected parameter}"
instance="${RUNNER_INSTANCE:?RUNNER_INSTANCE must be passed as a parameter}"
case "${instance}" in
  '' | *[!0-9]* | 0 | 1) echo "RUNNER_INSTANCE must be a number of 2 or more." >&2; exit 1 ;;
esac

# shellcheck source=/dev/null
. /etc/runner/provision.env

if [ ! -f /opt/actions-runner/.runner ]; then
  echo "Register the first runner with register-runner before adding another." >&2
  exit 1
fi

dir="/opt/actions-runner-${instance}"
name="$(hostname)-${instance}"

if [ ! -d "${dir}" ]; then
  install -d -o runner -g runner "${dir}"
  tar -C /opt/actions-runner \
    --exclude=./_work --exclude=./_diag --exclude=./.runner \
    --exclude=./.credentials --exclude=./.credentials_rsaparams --exclude=./.service \
    -cf - . | tar -C "${dir}" -xf -
  chown -R runner:runner "${dir}"
fi

cd "${dir}"

if [ -f .runner ]; then
  echo "This runner is already registered. Remove it in GitHub and delete ${dir}/.runner first." >&2
  exit 1
fi

ACTIONS_RUNNER_INPUT_TOKEN="${RUNNER_TOKEN}" \
  runuser -u runner --preserve-environment -- ./config.sh \
    --unattended \
    --url "https://github.com/${GITHUB_REPOSITORY}" \
    --name "${name}" \
    --labels lab-runner \
    --work _work \
    --replace
unset RUNNER_TOKEN

./svc.sh install runner
./svc.sh start
./svc.sh status | head -n 5
