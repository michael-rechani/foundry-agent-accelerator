#!/bin/bash
# Runs once as root from cloud-init. Installs the tools validate.yml needs and the
# runner binary. It does not register the runner: that needs a token you generate
# in GitHub, so register-runner.sh does it later and the token never touches
# Terraform, cloud-init, or the VM's disk.
set -euo pipefail

# shellcheck source=/dev/null
. /etc/runner/provision.env

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y --no-install-recommends \
  build-essential ca-certificates curl docker.io gh git jq unattended-upgrades unzip

# PowerShell: validate.yml runs several Terraform checks with `shell: pwsh`.
snap install powershell --classic
ln -sf /snap/bin/pwsh /usr/local/bin/pwsh

# Non-root runner account. It can use Docker because validate.yml runs one job in a
# container, which makes it root-equivalent on this VM. See the runbook's risk notes.
id runner >/dev/null 2>&1 || useradd --create-home --shell /bin/bash runner
usermod -aG docker runner
systemctl enable --now docker

install -d -o runner -g runner /opt/actions-runner
archive="actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
curl -fsSL -o "/tmp/${archive}" \
  "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${archive}"
echo "${RUNNER_SHA256}  /tmp/${archive}" | sha256sum --check --strict
tar -xzf "/tmp/${archive}" -C /opt/actions-runner
rm -f "/tmp/${archive}"
chown -R runner:runner /opt/actions-runner
/opt/actions-runner/bin/installdependencies.sh

# OS updates: security and regular updates install on their own timers.
systemctl enable --now apt-daily.timer apt-daily-upgrade.timer unattended-upgrades

# Idle shutdown only runs when configured; it also waits for registration.
if [ "${IDLE_SHUTDOWN_MINUTES}" -gt 0 ]; then
  systemctl daemon-reload
  systemctl enable --now runner-idle.timer
fi

touch /var/lib/runner-provisioned
