"""Device tree overlay locations and applied-state detection.

Single source of truth for *where* boneIO overlay ``.dtbo`` files must live and
*whether* an overlay actually took effect. This knowledge used to be duplicated
in ``boneio.migrations.runner`` and ``boneio.webui.routes.system``, and both
copies carried the same defect: they only ever looked at
``/boot/dtbs/$uname_r/overlays/``.

Two directories matter, for different consumers:

``/boot/dtbs/$uname_r/``
    U-Boot resolves bare filenames from ``uEnv.txt`` here, e.g.
    ``uboot_overlay_addr0=BONEIO-BLACK-PINS-v1.0.dtbo``. **This is the only
    path that decides whether the overlay is actually applied at boot.**

``/boot/dtbs/$uname_r/overlays/``
    Used by kernel/userspace overlay tooling.

Stock BeagleBoard overlays (``BB-ADC-00A0.dtbo`` and friends) ship in both.
Installing only into ``overlays/`` makes U-Boot log

    uboot_overlays: unable to find [mmc 0:3 BONEIO-BLACK-PINS-v1.0.dtbo]

and continue with the stock BeagleBone pinmux. Nothing in userspace reports an
error, so file-presence checks against ``overlays/`` report success while the
board silently runs unconfigured pins.

The authoritative answer to "is an overlay applied" is therefore not the
filesystem at all but ``/proc/device-tree/chosen/overlays/``, which the kernel
populates from what U-Boot actually merged into the device tree.
"""

from __future__ import annotations

import logging
import os
import platform
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

OVERLAY_GLOB = "BONEIO-BLACK-PINS*.dtbo"
"""Glob matching every boneIO pin overlay binary."""

DT_CHOSEN_OVERLAYS = Path("/proc/device-tree/chosen/overlays")
"""Kernel-reported list of overlays merged into the live device tree."""

DTBS_ROOT = Path("/boot/dtbs")
"""Root of the per-kernel device tree blob directories."""

SHIPPED_OVERLAYS_DIR = Path("/usr/lib/boneio/overlays")
"""Overlays boneIO installs through migrations; every copy under
:data:`DTBS_ROOT` of the same name must match. Kept in step with
``SHIPPED_OVERLAYS_DIR`` in boneio-system, which does the copying."""


def kernel_release() -> str:
    """Return the running kernel release, or an empty string if unavailable."""
    try:
        return platform.uname().release
    except Exception:  # pragma: no cover - platform call is effectively safe
        return ""


def overlay_dirs_for_kernel(kernel_version: str) -> tuple[Path, Path]:
    """Return both overlay destinations for a kernel version.

    Args:
        kernel_version: Kernel release string, e.g. ``6.18.45-bone48``.

    Returns:
        Tuple of ``(uboot_dir, tooling_dir)``. ``uboot_dir`` is the directory
        U-Boot reads; ``tooling_dir`` is its ``overlays/`` subdirectory.
    """
    base = DTBS_ROOT / kernel_version
    return base, base / "overlays"


def missing_overlay_dirs(kernel_version: str) -> list[Path]:
    """Return the overlay destinations that lack boneIO overlays.

    Args:
        kernel_version: Kernel release string.

    Returns:
        List of directories (possibly empty) that need to be populated. An
        empty list means both destinations already hold overlays.
    """
    uboot_dir, tooling_dir = overlay_dirs_for_kernel(kernel_version)
    # No DTB directory for this kernel means the kernel package is not
    # installed here; there is nothing for us to repair.
    if not uboot_dir.is_dir():
        return []

    missing: list[Path] = []
    for directory in (uboot_dir, tooling_dir):
        # glob() on a non-existent directory yields nothing rather than raising,
        # which is the behaviour we want for a not-yet-created overlays/ dir.
        if not any(directory.glob(OVERLAY_GLOB)):
            missing.append(directory)
    return missing


def stale_overlay_copies() -> list[Path]:
    """Return the copies under /boot/dtbs that differ from boneIO's shipped one.

    The image copied overlays into every kernel's directory once and nothing
    updated them after, so a corrected overlay installed into
    :data:`SHIPPED_OVERLAYS_DIR` changes nothing until each copy is replaced.
    Every kernel counts, not only the running one: the kernel postinst hook
    seeds a new kernel from an old kernel's copies.

    Returns:
        Sorted list of stale copies, empty when every copy matches or nothing
        is shipped.
    """
    stale: list[Path] = []
    for shipped in sorted(SHIPPED_OVERLAYS_DIR.glob(OVERLAY_GLOB)):
        try:
            content = shipped.read_bytes()
        except OSError as exc:
            _LOGGER.debug("Cannot read %s: %s", shipped, exc)
            continue
        for pattern in (f"*/{shipped.name}", f"*/overlays/{shipped.name}"):
            for copy in DTBS_ROOT.glob(pattern):
                try:
                    if copy.read_bytes() != content:
                        stale.append(copy)
                except OSError as exc:
                    _LOGGER.debug("Cannot read %s: %s", copy, exc)
    return sorted(stale)


def applied_overlay_names() -> list[str]:
    """Return the overlay names the kernel reports as merged into the DT.

    Reads ``/proc/device-tree/chosen/overlays/``. Entries are named after the
    overlay that produced them, e.g. ``BB-ADC-00A0.kernel``.

    Returns:
        List of entry names, or an empty list if the node is absent (which
        happens when U-Boot merged no overlays at all).
    """
    if not DT_CHOSEN_OVERLAYS.is_dir():
        return []
    try:
        # 'name' is a property of the node itself, not an applied overlay.
        return sorted(e for e in os.listdir(DT_CHOSEN_OVERLAYS) if e != "name")
    except OSError as exc:
        _LOGGER.debug("Cannot read %s: %s", DT_CHOSEN_OVERLAYS, exc)
        return []


def is_boneio_overlay_applied() -> bool:
    """Return whether a boneIO pin overlay is live in the device tree.

    This is the authoritative check. File presence under ``/boot/dtbs`` proves
    nothing about what U-Boot actually loaded.
    """
    return any(name.startswith("BONEIO-BLACK-PINS") for name in applied_overlay_names())
