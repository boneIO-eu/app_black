"""BoneIO 1.6.3 — stage the firewall rules whose absence was a trap.

``setup_boneio.sh`` has always staged ``ufw allow`` rules for 1883, 8090 and
8091, and has never run ``ufw enable``. So the device ships unfiltered, and the
rule list is a plan rather than a state.

The trap was what the plan left out. Neither 22 nor 8443 was in it, so the
first person to act on the apparent intent and run ``ufw enable`` would lose
SSH and the TLS panel in the same second, keeping only the two plain-HTTP
ports — locking themselves out of a device that is often on a DIN rail in a
cabinet.

This adds the two missing rules. It deliberately does **not** enable the
firewall: turning default-deny on unattended, over the network, is how a
remote controller becomes a brick. The rules simply stop being a loaded gun for
whoever turns it on later.
"""

from __future__ import annotations

from boneio.migrations.actions import MigrationAction, UfwAllow

VERSION = "1.6.3"
DESCRIPTION = "Allow SSH and the TLS panel in the staged firewall rules (F-10)"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions for version 1.6.3.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        UfwAllow(port=22, proto="tcp", comment="SSH - do not lock the operator out"),
        UfwAllow(port=8443, proto="tcp", comment="boneIO panel over TLS"),
    ]
