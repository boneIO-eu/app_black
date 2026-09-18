"""Tell a freshly flashed controller from one that has been in service.

The first-run wizard has two steps that are only appropriate on a blank
device. The import step offers to restore a configuration, which on a device
that already has one reads as "yours is gone". The devices step is worse than
misleading: it replaces the whole ``event`` section, so a controller with fifty
configured inputs loses them to a wizard its owner opened only to create an
account.

So the question has to be answered before those steps are offered, and the two
ways of getting it wrong are not equally bad:

  * Treating an upgraded device as fresh costs the owner their configuration.
  * Treating a fresh device as upgraded costs them a step in a wizard; they
    can still import and bind inputs from the normal interface afterwards.

This module is therefore written to answer "is it fresh" and to say no when it
cannot tell. Freshness has to be demonstrated, not assumed.

The demonstration is that the configuration is still the factory one. The image
copies a variant out of ``~/.cache/boneio_configs/<variant>/`` verbatim, and
per-device work touches only ``mqtt.yaml`` (the broker password), so a
controller nobody has configured yet still has a ``config.yaml`` byte-identical
to its template.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

#: Where the image leaves the per-variant templates it seeded the device from.
FACTORY_TEMPLATE_DIR = Path.home() / ".cache" / "boneio_configs"


def _digest(path: Path) -> bytes | None:
    """Read a file for comparison.

    Args:
        path: File to read.

    Returns:
        Its contents, or None when it cannot be read.
    """
    try:
        return path.read_bytes()
    except OSError:
        return None


def looks_factory_fresh(
    config_path: str | os.PathLike[str],
    template_dir: str | os.PathLike[str] | None = None,
) -> bool:
    """Whether this device still carries an untouched factory configuration.

    Args:
        config_path: The device's ``config.yaml``.
        template_dir: Where the per-variant templates live. Defaults to
            :data:`FACTORY_TEMPLATE_DIR`.

    Returns:
        True only when freshness can be positively shown: there is no
        configuration at all, or the configuration is identical to one of the
        templates the image ships. False whenever the answer is not certain.
    """
    config = Path(config_path)
    current = _digest(config)
    if current is None:
        # Nothing to lose, and nothing that an import could overwrite.
        _LOGGER.debug("No configuration at %s — treating the device as fresh", config)
        return True

    root = Path(template_dir) if template_dir is not None else FACTORY_TEMPLATE_DIR
    try:
        variants = sorted(p for p in root.iterdir() if p.is_dir())
    except OSError:
        # No templates to compare against: the honest answer is "cannot tell",
        # and the safe reading of that is "assume it has been configured".
        _LOGGER.debug("No factory templates under %s — assuming configured", root)
        return False

    for variant in variants:
        if current == _digest(variant / "config.yaml"):
            _LOGGER.debug("Configuration matches the %s template", variant.name)
            return True

    return False


def was_configured_before(
    config_path: str | os.PathLike[str],
    had_legacy_auth: bool = False,
    template_dir: str | os.PathLike[str] | None = None,
) -> bool:
    """Whether the wizard should skip the steps that assume a blank device.

    Args:
        config_path: The device's ``config.yaml``.
        had_legacy_auth: Whether a pre-1.6 ``web.auth`` block was found. It
            proves the device is not fresh, but its absence proves nothing —
            most 1.5.x controllers never had web authentication at all, which
            is exactly the case this used to get wrong.
        template_dir: Passed through to :func:`looks_factory_fresh`.

    Returns:
        True when the device already has a configuration of its own.
    """
    if had_legacy_auth:
        return True
    return not looks_factory_fresh(config_path, template_dir)
