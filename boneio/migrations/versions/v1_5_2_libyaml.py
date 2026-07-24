"""Switch PyYAML to the libyaml (C) backend for faster config handling.

PyYAML installed from an sdist on armhf silently falls back to its
pure-Python parser, which needs several seconds to parse the boneIO schema
on a BeagleBone Black. This migration installs a prebuilt PyYAML wheel
(bundled in the migration assets, built with libyaml) into the boneIO
virtualenv, giving roughly a 10x speed-up of YAML parsing.

Both actions are marked optional: on a device without the matching wheel,
without network for ``libyaml-0-2`` or with a failing pip, the migration
logs a warning and completes so that later migrations are not blocked. The
application keeps working with the pure-Python parser in that case.

To retry the migration on a device, delete
``/var/lib/boneio/migrations.d/1.5.2.applied`` and restart boneIO.
"""

from __future__ import annotations

import getpass
import logging
import sys
import sysconfig
from pathlib import Path

from boneio.migrations.actions import AptInstall, MigrationAction, PipInstallWheel

_LOGGER = logging.getLogger(__name__)

VERSION = "1.5.2"
DESCRIPTION = "Install libyaml-backed PyYAML for faster YAML parsing"
REQUIRES_ROOT = True

ASSETS_DIR = Path(__file__).parent.parent / "assets"
WHEELS_SUBDIR = "wheels"

# Expression evaluated by the target interpreter to detect the C backend
_LIBYAML_CHECK = "__import__('yaml').__with_libyaml__"


def _wheel_glob() -> str:
    """Build the wheel filename pattern for the running interpreter.

    Uses a case-insensitive prefix because pip normalises the project
    name to lowercase (``pyyaml-*``) while the canonical PyPI name is
    ``PyYAML``.

    Returns:
        A glob pattern such as ``[Pp][Yy][Yy][Aa][Mm][Ll]-*-cp313-*linux_armv7l*.whl``.
    """
    py_tag = f"cp{sys.version_info.major}{sys.version_info.minor}"
    platform_tag = sysconfig.get_platform().replace("-", "_").replace(".", "_")
    # Case-insensitive prefix: matches both "PyYAML" and "pyyaml"
    ci_prefix = "[Pp][Yy][Yy][Aa][Mm][Ll]"
    return f"{ci_prefix}-*-{py_tag}-*{platform_tag}*.whl"


def _find_wheel() -> str | None:
    """Locate a bundled PyYAML wheel matching this interpreter.

    Returns:
        Path of the wheel relative to the assets directory, or None when no
        matching wheel is shipped for this Python version / architecture.
    """
    wheels_dir = ASSETS_DIR / WHEELS_SUBDIR
    if not wheels_dir.is_dir():
        return None
    matches = sorted(wheels_dir.glob(_wheel_glob()))
    if not matches:
        return None
    return f"{WHEELS_SUBDIR}/{matches[0].name}"


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    Returns:
        List of :class:`MigrationAction` to apply in order. Empty when the
        C backend is already active or no matching wheel is bundled.
    """
    try:
        import yaml

        if yaml.__with_libyaml__:
            _LOGGER.debug("PyYAML already uses libyaml, nothing to do.")
            return []
    except ImportError:
        return []

    wheel = _find_wheel()
    if wheel is None:
        _LOGGER.warning(
            "No bundled PyYAML wheel matching %s — keeping the pure-Python parser.",
            _wheel_glob(),
        )
        return []

    return [
        # Runtime library the wheel links against; usually already present.
        AptInstall(packages=["libyaml-0-2"], optional=True),
        PipInstallWheel(
            wheel=wheel,
            python=sys.executable,
            run_as=getpass.getuser(),
            skip_if=_LIBYAML_CHECK,
            verify=_LIBYAML_CHECK,
            optional=True,
        ),
    ]
