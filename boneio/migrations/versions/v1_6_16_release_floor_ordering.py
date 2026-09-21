"""Reinstall the migration helper, whose release comparison read dev10 as older than dev9.

``_version_key`` in ``boneio-migrate-v2`` compared a release's pre-release
suffix as text. ``"dev10" < "dev9"`` is true of strings, so a device whose
release floor had reached 1.6.0.dev9 read 1.6.0.dev10 as an attempt to go
backwards and refused the manifest — and with it dev11, dev12 and every
remaining release of the 1.6.0 dev series. Any floor from dev2 upwards refuses
every two-digit dev release.

The floor is consulted only when a migration is actually applied, which is why
this stayed invisible: dev10 shipped no new migration, so nothing asked. It
surfaced the first time a release carried one, on a real controller.

The awkward part is that the fix lives in the helper, the helper is replaced by
a migration, and the migration is refused by the helper being replaced. The way
out is in the comparison itself: the numeric part is compared before the
suffix, so a release whose numbers are higher is accepted even by the broken
key. Releasing this as 1.6.1.devN — rather than as another 1.6.0.devN — is
therefore not cosmetic. It is what lets a device that is already stuck accept
the manifest carrying its own repair.

``validate="python"`` is not decoration here either. This overwrites the only
path by which the device can migrate at all, so a helper that will not compile
must be refused before it is installed rather than discovered afterwards, when
nothing is left to fix it with. The pristine copy under /usr/lib/boneio/trusted
is updated with it, because ``boneio-helpers-heal.service`` restores from there
and would otherwise put the broken comparison back at the next boot.

A device that has never accepted a release above dev9 needs nothing special —
its floor is lower, so the old key already let this through.

To retry on a device, delete ``/var/lib/boneio/migrations.d/1.6.16.applied``
and restart boneIO.
"""

from __future__ import annotations

from boneio.migrations.actions import InstallFile, MigrationAction

VERSION = "1.6.16"
DESCRIPTION = "Fix the release-floor comparison in the migration helper"
REQUIRES_ROOT = True

_TRUSTED_DIR = "/usr/lib/boneio/trusted"


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    The pristine copy goes first. If the run were interrupted between the two,
    a device would be left with the corrected helper in /usr/sbin and the old
    one in the trusted directory, and the heal unit would undo the repair at
    the next boot without saying anything.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        InstallFile(
            src="helpers/boneio-migrate-v2",
            dst=f"{_TRUSTED_DIR}/boneio-migrate-v2",
            mode=0o755,
            owner="root",
            group="root",
            validate="python",
        ),
        InstallFile(
            src="helpers/boneio-migrate-v2",
            dst="/usr/sbin/boneio-migrate-v2",
            mode=0o755,
            owner="root",
            group="root",
            validate="python",
        ),
    ]
