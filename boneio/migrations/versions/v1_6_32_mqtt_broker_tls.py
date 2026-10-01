"""Reinstall boneio-system: the broker on the controller can serve TLS.

boneio-system gains four verbs for Mosquitto:

  - ``mqtt-tls-state`` — which of the managed shapes
    /etc/mosquitto/conf.d/boneio.conf is in, and whether a certificate is
    installed. The file is mosquitto's and unreadable to boneio, hence a verb;
  - ``mqtt-tls-cert`` — the broker's chain and key on stdin, never as
    arguments. Only PEM certificates and one unencrypted key are accepted,
    and OpenSSL has to load them as a pair before anything is written. The key
    lands in /etc/mosquitto/certs as ``root:mosquitto 0640``;
  - ``mqtt-tls-cert-remove`` — only while TLS is off;
  - ``mqtt-tls-mode off|optional|required`` — rewrites boneio.conf in one of
    three fixed shapes: ``off`` is byte for byte what 1.3.0 installs,
    ``optional`` adds a TLS listener on 8883, ``required`` also moves plain
    1883 to 127.0.0.1 so boneIO keeps its own connection over loopback.

Every change that touches the broker restarts it and waits for 1883 on
loopback (and 8883 with TLS) to answer. If they do not, the previous files are
put back and the broker restarted on them: a broker that does not come up
takes Home Assistant and boneIO's own connection with it, on a device that
may be in a cabinet. A boneio.conf in none of the managed shapes is somebody's
hand edit, and the verbs refuse to touch it.

The panel's routes also check what they can first — the certificate, the CA
that signed it, and that TLS-only would not cut boneIO off its own broker —
and offer the card only once ``--list-verbs`` names these verbs.

8883/tcp joins the staged firewall rules beside 1883, for the same reason
1.6.3 added 22 and 8443: whoever turns ufw on later must not lose the port the
panel told Home Assistant to use.

Pristine copy first, as in 1.6.22, so ``boneio-helpers-heal.service`` does not
put the old helper back. ``validate="python"`` because a helper that does not
compile would take CAN, the overlay, the hostname, NTP, the broker passwords
and system updates down with it. The sudoers rule from 1.6.8 already covers the
helper.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.32.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction, UfwAllow

VERSION = "1.6.32"
DESCRIPTION = "TLS for the broker on the controller, managed from the panel"
REQUIRES_ROOT = True

_TRUSTED_DIR = "/usr/lib/boneio/trusted"


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        *(
            InstallFile(
                src="helpers/boneio-system", dst=dst, mode=0o755,
                owner="root", group="root", validate="python",
            )
            for dst in (f"{_TRUSTED_DIR}/boneio-system", "/usr/sbin/boneio-system")
        ),
        UfwAllow(port=8883, proto="tcp", comment="MQTT over TLS"),
    ]
