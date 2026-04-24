#!/bin/bash
# install-helper.sh — install boneio-migrate helper and sudoers entry.
# Called by MigrationRunner.bootstrap_install() via: sudo -S bash install-helper.sh <src> <sudoers_src>
# Must be run as root.

set -e

HELPER_SRC="${1:?Usage: $0 <helper_src> <sudoers_src>}"
SUDOERS_SRC="${2:?Usage: $0 <helper_src> <sudoers_src>}"

HELPER_DST="/usr/sbin/boneio-migrate"
SUDOERS_DST="/etc/sudoers.d/boneio-migrate"
APPLIED_DIR="/var/lib/boneio/migrations.d"
LOG_FILE="/var/log/boneio-migrate.log"

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: Must be run as root" >&2
    exit 1
fi

# Install helper script
install -m 0755 -o root -g root "${HELPER_SRC}" "${HELPER_DST}"

# Install sudoers fragment (validate first)
install -m 0440 -o root -g root "${SUDOERS_SRC}" "${SUDOERS_DST}.tmp"
if ! visudo -cf "${SUDOERS_DST}.tmp"; then
    rm -f "${SUDOERS_DST}.tmp"
    echo "ERROR: sudoers validation failed" >&2
    exit 1
fi
mv "${SUDOERS_DST}.tmp" "${SUDOERS_DST}"

# Create runtime directories
mkdir -p "${APPLIED_DIR}"
chown -R root:root "${APPLIED_DIR}"
chmod 0755 "${APPLIED_DIR}"

# Create log file with correct permissions
touch "${LOG_FILE}"
chmod 0644 "${LOG_FILE}"
chown root:root "${LOG_FILE}"

echo "boneio-migrate helper installed successfully."
