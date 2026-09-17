"""Retry libyaml installation for devices with a false v1.5.2 applied flag.

v1.5.2 could be falsely marked as applied when all optional actions
failed (bug fixed in the boneio-migrate helper).  This migration
repeats the same libyaml install so that affected devices get a
second attempt automatically.

See also: ``v1_5_2_libyaml.py`` for the original migration.
"""

from __future__ import annotations

from pathlib import Path

from boneio.migrations.actions import AptInstall, MigrationAction, PipInstallWheel

VERSION = "1.5.3"
DESCRIPTION = "Retry libyaml install (fix false v1.5.2 applied flag)"
REQUIRES_ROOT = True

ASSETS_DIR = Path(__file__).parent.parent / "assets"
WHEELS_SUBDIR = "wheels"

# Expression evaluated by the target interpreter to detect the C backend
_LIBYAML_CHECK = "__import__('yaml').__with_libyaml__"


def _bundled_wheels() -> tuple[str, ...]:
    """Every PyYAML wheel shipped in the migration assets.

    Deliberately not filtered by the running interpreter. This plan is frozen
    and signed on a build machine, then executed on a controller: a wheel
    chosen here would carry CI's Python tag and architecture, and the device
    would be handed something it cannot install — with a valid signature over
    it. The device picks from this list using its own tags.

    Returns:
        Wheel paths relative to the assets directory, sorted for determinism.
    """
    wheels_dir = ASSETS_DIR / WHEELS_SUBDIR
    if not wheels_dir.is_dir():
        return ()
    names = sorted(
        path.name
        for path in wheels_dir.iterdir()
        if path.suffix == ".whl" and path.name.lower().startswith("pyyaml-")
    )
    return tuple(f"{WHEELS_SUBDIR}/{name}" for name in names)


def plan() -> list[MigrationAction]:
    """Return the ordered list of migration actions.

    Unconditional on purpose. The previous version probed the build machine —
    it returned an empty list whenever *that* machine already had libyaml — so
    freezing it produced a signed no-op for exactly the devices that needed the
    work. Whether anything is installed is now decided on the device by
    ``skip_if``.

    Returns:
        List of :class:`MigrationAction` to apply in order.
    """
    return [
        # Runtime library the wheel links against; usually already present.
        AptInstall(packages=["libyaml-0-2"], optional=True),
        PipInstallWheel(
            wheel_candidates=_bundled_wheels(),
            python="@venv",
            run_as="@service_user",
            skip_if=_LIBYAML_CHECK,
            verify=_LIBYAML_CHECK,
            optional=True,
        ),
    ]
