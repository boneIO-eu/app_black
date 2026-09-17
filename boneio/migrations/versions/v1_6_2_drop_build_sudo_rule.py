"""BoneIO 1.6.2 — take away the sudo rule the image build left behind.

``build_image_usb.sh`` writes ``boneio ALL=(ALL) NOPASSWD: ALL`` to
``/etc/sudoers.d/boneio-setup`` so the unattended setup can run as root, and
until 1.6.2 nothing removed it afterwards. Every image built that way shipped
with the service account holding full root with no credential at all — not a
password, not a narrow command list. Anything that manages to run code as
``boneio``, including the web app itself, is already root (F-04, part of
CVE-2026-77055).

The image scripts now drop the file when they seal an image. That only helps
units built from now on, which is why this repairs the controllers already in
the field — exactly the gap the audit script was written to show.

Removing it does not take away anything the product uses. The panel's own
privileged operations either have their own narrow NOPASSWD rules
(``/etc/sudoers.d/boneio``, ``boneio-timedatectl``, ``boneio-migrate``) or
prompt for the user's password and run ``sudo -S``. Both keep working, because
``boneio`` remains a member of the sudo group.
"""

from __future__ import annotations

from boneio.migrations.actions import MigrationAction, RemoveFile

VERSION = "1.6.2"
DESCRIPTION = "Remove the build-time NOPASSWD: ALL sudo rule (F-04)"
REQUIRES_ROOT = True


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions for version 1.6.2.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        # A no-op where the file was never written, so this is safe on a device
        # provisioned by hand or by a future image that never creates it.
        RemoveFile(path="/etc/sudoers.d/boneio-setup"),
    ]
