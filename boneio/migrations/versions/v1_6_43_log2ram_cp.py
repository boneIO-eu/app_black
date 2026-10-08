"""Let log2ram copy the logs with cp instead of rsync.

At every start log2ram fills the RAM disk from /var/hdd.log with
``rsync -aXv --sparse --inplace --no-whole-file``. On an SD card that takes
about a second per megabyte of journal, so with a 20 MB journal log2ram ends
at ~49.5 s after the kernel starts. It is ordered before sysinit.target, so
every service waits for it. With ``USE_RSYNC=false`` log2ram uses
``cp -rfup --sparse=always`` and ends at ~32 s (17 s earlier). Measured on an
SD card with the packaged Caddy, the Caddy page answers ~30 s earlier (~103 s
to ~73 s, because Caddy waits for sysinit) and the panel ~7 s earlier (~112 s
to ~105 s, boneIO's own start then dominates). When syncing back to disk
cp copies a changed file whole, but journal files are capped at 2 MB
(``SystemMaxFileSize=2M``), so the extra SD wear is negligible.

log2ram sources /etc/log2ram.conf, which ships only a commented
``#USE_RSYNC=false``, so the new line takes effect at the next boot. If
/etc/log2ram.conf is missing (log2ram not installed) the line creates a
harmless file and the migration still succeeds.

To run it again: ``rm /var/lib/boneio/migrations.d/1.6.43.applied``.
"""

from __future__ import annotations

from boneio.migrations.actions import AppendLineIfMissing, MigrationAction

VERSION = "1.6.43"
DESCRIPTION = "log2ram copies the logs with cp, not rsync"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions."""
    return [AppendLineIfMissing(path="/etc/log2ram.conf", line="USE_RSYNC=false")]
