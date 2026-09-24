"""Remove PackageKit and AppStream, which slow every apt run and serve nothing.

The BeagleBoard base image carries them for Cockpit's software page. On a
boneIO controller they cost on every package operation:

* ``/etc/apt/apt.conf.d/20packagekit`` pings the PackageKit daemon over D-Bus
  after every ``apt update`` and every dpkg run, with a 4 s timeout. Starting
  ``packagekitd`` on a BeagleBone takes longer than that, so the panel's system
  update log ended in ``Error: Timeout was reached`` — alarming, and wrong: every
  repository had answered. The daemon it starts then sits in the ~480 MB of RAM.
* ``/etc/apt/apt.conf.d/50appstream`` downloads DEP-11 component metadata and
  rebuilds the AppStream cache on every ``apt update``: time and traffic for a
  software catalogue a controller never shows anyone.

Nothing boneIO runs uses either. Cockpit itself stays; only its PackageKit page
goes (``cockpit-packagekit``), and boneIO disables Cockpit's socket anyway.

``apt_purge`` refuses when apt would remove anything beyond this list, so a
device where something else happens to depend on these keeps them and says so
in the migration log rather than losing a package nobody named. The libraries
they pull in (glib's tools, gstreamer, libxmlb, libstemmer) are left for
``apt-get autoremove`` — the panel's system update runs it — instead of being
removed here by name.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.20.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import AptPurge, MigrationAction

VERSION = "1.6.20"
DESCRIPTION = "Remove PackageKit and AppStream"
REQUIRES_ROOT = True

#: Also in setup_boneio.sh, step 3 — keep the two lists the same.
PACKAGES = [
    "cockpit-packagekit",
    "packagekit-tools",
    "packagekit",
    "libpackagekit-glib2-18",
    "appstream",
    "libappstream5",
]


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [AptPurge(packages=PACKAGES)]
