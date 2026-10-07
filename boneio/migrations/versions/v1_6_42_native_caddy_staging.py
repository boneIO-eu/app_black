"""Stage the packaged Caddy on every controller; nothing switches to it yet.

Everything the move from the Caddy container to Debian's ``caddy`` package
needs goes in place here, so that the switch itself — started from the panel,
run by ``boneio-containers proxy-switch-start`` — installs one package and
swaps one compose file instead of carrying files of its own:

  * the Caddy apt repository: its signing key, a pin to the 2.11 series, and the
    source list, in that order — a source list without its key makes every
    ``apt-get update`` fail, the pin keeps a later series out;
  * the starting page the packaged Caddy serves while the panel comes up;
  * ``proxy-config``, the root generator that writes the Caddyfile from what
    boneIO already keeps, and the ``caddy.service`` drop-in that runs it;
  * the compose file without the Caddy container, in the pristine copy where
    ``boneio-containers`` takes compose files from;
  * ``boneio-system`` and ``boneio-containers`` with the verbs that install the
    package, drive it and switch over, and ``boneio-proxy-recover.service``,
    which puts the container back at boot when a switch was cut short;
  * ``boneio-helpers-heal``, which now restores the generator at boot as it
    does the helpers;
  * Caddy among the origins automatic updates take, with the 2.11 pin still
    holding. The panel's switch for automatic updates covers it as well.

Nothing here touches the running Caddy container. The drop-in carries
``ConditionPathExists=/etc/boneio/proxy-native`` and only the switch creates
that marker, so the package's postinst cannot start a stock Caddy on a
controller that has not switched. The recovery unit costs nothing on a healthy
boot: its ``ExecCondition`` greps a switch record that does not exist, and a
condition that exits non-zero skips the unit rather than failing it.

The repository key is "Caddy Web Server <contact@caddyserver.com>",
fingerprint ``65760C51EDEA2017CEA2CA15155B6D79CA56EA34``, checked against the
repository's signed InRelease.

A failed action stops the run without marking the migration applied, but
what came before it stays in place until the retry on the next start, which
may be a long time if the failure repeats. So every prefix of this plan is a
state a controller can be left in. ``boneio-system`` goes first for that
reason: the panel's system update runs ``apt-get update``
through it, and the version before this one fails the whole update when one
source does, as an unreachable Caddy repository would. Helpers and the
generator go to the pristine copy first, so ``boneio-helpers-heal.service``
does not put the old ones back, and are compiled before they are written
(``validate="python"``). The sudoers rule from 1.6.5 already covers both
helpers.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.42.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import (
    InstallFile,
    MigrationAction,
    SystemctlDaemonReload,
    SystemctlEnable,
)

VERSION = "1.6.42"
DESCRIPTION = "Stage the packaged Caddy, not switched on yet"
REQUIRES_ROOT = True

_TRUSTED_DIR = "/usr/lib/boneio/trusted"


def _executable(src: str, *dsts: str) -> list[InstallFile]:
    """Install a root script to each destination, compiled before it is written."""
    return [
        InstallFile(
            src=src, dst=dst, mode=0o755, owner="root", group="root", validate="python",
        )
        for dst in dsts
    ]


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        # Before the source list: the update the panel runs goes through this
        # helper, and only this version carries on when the Caddy repository
        # cannot be reached.
        *_executable(
            "helpers/boneio-system", f"{_TRUSTED_DIR}/boneio-system", "/usr/sbin/boneio-system"
        ),
        InstallFile(
            src="apt/caddy-stable-archive-keyring.gpg",
            dst="/usr/share/keyrings/caddy-stable-archive-keyring.gpg",
            mode=0o644,
        ),
        InstallFile(src="apt/caddy-pin.pref", dst="/etc/apt/preferences.d/caddy", mode=0o644),
        InstallFile(
            src="apt/caddy-stable.list",
            dst="/etc/apt/sources.list.d/caddy-stable.list",
            mode=0o644,
        ),
        InstallFile(src="caddy/502.html", dst="/usr/share/boneio/proxy/502.html", mode=0o644),
        *_executable(
            "helpers/boneio-proxy-config",
            f"{_TRUSTED_DIR}/boneio-proxy-config",
            "/usr/lib/boneio/proxy-config",
        ),
        InstallFile(
            src="systemd/caddy-boneio.conf",
            dst="/etc/systemd/system/caddy.service.d/boneio.conf",
            mode=0o644,
        ),
        SystemctlDaemonReload(),
        InstallFile(
            src="docker/nodered/docker-compose-native-proxy.yaml",
            dst=f"{_TRUSTED_DIR}/docker-compose-native-proxy.yaml",
            mode=0o644,
        ),
        *_executable(
            "helpers/boneio-containers",
            f"{_TRUSTED_DIR}/boneio-containers",
            "/usr/sbin/boneio-containers",
        ),
        InstallFile(
            src="systemd/boneio-proxy-recover.service",
            dst="/etc/systemd/system/boneio-proxy-recover.service",
            mode=0o644,
        ),
        SystemctlDaemonReload(),
        SystemctlEnable(unit="boneio-proxy-recover.service"),
        InstallFile(src="apt/53boneio-caddy", dst="/etc/apt/apt.conf.d/53boneio-caddy", mode=0o644),
        # Last, after the generator's pristine copy: from here on the self-heal
        # restores /usr/lib/boneio/proxy-config at boot as well.
        *_executable(
            "helpers/boneio-helpers-heal",
            f"{_TRUSTED_DIR}/boneio-helpers-heal",
            "/usr/sbin/boneio-helpers-heal",
        ),
    ]
