"""Install the signing migration helper alongside the one that cannot be trusted.

The helper this migration is applied *by* accepts a whole plan over stdin from
the unprivileged application: the actions, the asset digests, and a
``validate_cmd`` string it runs as root. Holding the ``boneio`` account is
therefore equivalent to holding root, through a completely legitimate call —
CVE-2026-77055.

This installs the replacement. It does **not** remove the old helper, and it
deliberately installs the new one at its own path:

  * The pivot is the only step with no way back. ``py_compile`` catches a syntax
    error but not a wrong ``openssl`` invocation, a missing trust anchor or an
    interpreter that moved. Overwriting ``/usr/sbin/boneio-migrate`` and getting
    any of that wrong would leave a controller whose migration channel is dead
    and whose only repair needs somebody physically present.
  * So the runner asks ``boneio-migrate-v2 --selftest`` afterwards, and only a
    zero from that lets the next migration retire the old helper. A device where
    the selftest fails keeps working exactly as before — it reports the hardening
    as unfinished and retries on the next start.

The trust anchors go to /etc/boneio, outside the application's reach, and the
pristine copy under /usr/lib/boneio/trusted is what
``boneio-helpers-heal.service`` restores from. Recovery therefore never needs
the ``boneio`` account: the password for that account is shared across
controllers, and a recovery path that reinstalls the *public key* would let an
attacker re-pin their own anchor and sign every future "trusted" plan — a
persistence that would survive this entire exercise. There is no sudo rule for
reinstalling the helpers, on purpose.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.5.applied`` and
restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import (
    InstallFile,
    MigrationAction,
    SetFilePermissions,
    SystemctlDaemonReload,
    SystemctlEnable,
)

VERSION = "1.6.5"
DESCRIPTION = "Install the signature-verifying migration helper (CVE-2026-77055)"
REQUIRES_ROOT = True

#: Root-owned master copies. boneio-helpers-heal.service restores the installed
#: helpers from here, so this directory — not the pip package — is the thing a
#: device's privileged surface depends on.
TRUSTED_DIR = "/usr/lib/boneio/trusted"
PINNED_DIR = "/etc/boneio"

#: (asset, destination, mode) for the pristine copy. Everything the heal unit
#: needs, and nothing else.
_PRISTINE = (
    ("helpers/boneio-migrate-v2", "boneio-migrate-v2", 0o755),
    ("helpers/boneio-containers", "boneio-containers", 0o755),
    ("helpers/boneio-system", "boneio-system", 0o755),
    ("helpers/boneio-helpers-heal", "boneio-helpers-heal", 0o755),
    ("sudoers/boneio-helpers", "sudoers-boneio-helpers", 0o440),
    ("migrations.pem", "migrations.pem", 0o444),
    ("migrations-recovery.pem", "migrations-recovery.pem", 0o444),
    # The compose templates. boneio-containers copies the compose file from
    # here instead of the application writing it, which is what stops whoever
    # can write that file from starting a container as root with the host
    # filesystem mounted.
    ("docker/nodered/docker-compose.yaml", "docker-compose.yaml", 0o644),
    ("docker/nodered/docker-compose-cloud.yaml", "docker-compose-cloud.yaml", 0o644),
)


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    The order matters: anchors and helpers are in place before the sudoers
    fragment that names them, so an interrupted run never leaves a rule
    pointing at a binary that is not there.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    actions: list[MigrationAction] = []

    # 1. The pristine copy, which is what recovery reads from.
    for asset, name, mode in _PRISTINE:
        actions.append(
            InstallFile(
                src=asset,
                dst=f"{TRUSTED_DIR}/{name}",
                mode=mode,
                owner="root",
                group="root",
            )
        )

    # 2. The trust anchors. Two of them: re-pinning a key needs a migration
    #    signed by a key the device already trusts, so with a single anchor a
    #    lost release key would mean this device can never accept a signed
    #    migration again. The recovery anchor signs no release; the helper
    #    restricts what a plan carrying its signature may do.
    for name in ("migrations.pem", "migrations-recovery.pem"):
        actions.append(
            InstallFile(
                src=name,
                dst=f"{PINNED_DIR}/{name}",
                mode=0o444,
                owner="root",
                group="root",
            )
        )

    # 3. The helpers, at their own paths. /usr/sbin/boneio-migrate is left
    #    exactly as it is — see the module docstring.
    actions.extend([
        InstallFile(
            src="helpers/boneio-migrate-v2",
            dst="/usr/sbin/boneio-migrate-v2",
            mode=0o755,
            owner="root",
            group="root",
            # Both spellings: the legacy helper reads validate_cmd, v2 reads
            # the named validator and refuses to run a command string.
            validate_cmd="python3 -m py_compile",
            validate="python",
        ),
        InstallFile(
            src="helpers/boneio-containers",
            dst="/usr/sbin/boneio-containers",
            mode=0o755,
            owner="root",
            group="root",
            # Both spellings: the legacy helper reads validate_cmd, v2 reads
            # the named validator and refuses to run a command string.
            validate_cmd="python3 -m py_compile",
            validate="python",
        ),
        InstallFile(
            src="helpers/boneio-helpers-heal",
            dst="/usr/sbin/boneio-helpers-heal",
            mode=0o755,
            owner="root",
            group="root",
            # Both spellings: the legacy helper reads validate_cmd, v2 reads
            # the named validator and refuses to run a command string.
            validate_cmd="python3 -m py_compile",
            validate="python",
        ),
    ])

    # 4. NOPASSWD for the two helpers that take a closed vocabulary. The old
    #    rule for boneio-migrate stays until the retirement migration removes
    #    it, because until then the old helper is the only way to migrate.
    actions.append(
        InstallFile(
            src="sudoers/boneio-helpers",
            dst="/etc/sudoers.d/boneio-helpers",
            mode=0o440,
            owner="root",
            group="root",
            validate_cmd="visudo -cf",
            validate="sudoers",
        )
    )

    # 5. Self-heal, so a helper that goes missing comes back at boot from the
    #    pristine copy rather than through an elevation the application holds.
    actions.extend([
        InstallFile(
            src="systemd/boneio-helpers-heal.service",
            dst="/etc/systemd/system/boneio-helpers-heal.service",
            mode=0o644,
            owner="root",
            group="root",
            on_change=SystemctlDaemonReload(),
        ),
        SystemctlEnable(unit="boneio-helpers-heal.service"),
    ])

    # 6. Take the compose file away from the application. `docker compose up`
    #    reads it, so whoever can write it can start a container as root with
    #    the host filesystem mounted — the file is the vector, not the command
    #    line, which is why a sudoers rule on `docker compose` would not have
    #    helped. boneio-containers refuses to run at all unless this holds.
    actions.append(
        SetFilePermissions(
            path="/home/boneio/docker/nodered/docker-compose.yaml",
            mode=0o644,
            owner="root",
            group="root",
        )
    )

    return actions
