"""The release floor has to order dev10 after dev9.

``boneio-migrate-v2`` refuses a manifest whose release is older than the
highest one the device has already accepted, which is what stops an attacker
presenting a whole older package tree — every signature in it genuinely valid —
to replay a migration this device never applied.

It compared the pre-release suffix as text, so ``"dev10" < "dev9"`` and a
controller that had reached 1.6.0.dev9 refused 1.6.0.dev10 and everything after
it. The floor is only consulted when a migration is applied, so a release
carrying none never triggered it and the fault went unseen from dev10 to
dev14.
"""

from __future__ import annotations

from pathlib import Path

import pytest

HELPER = (
    Path(__file__).resolve().parents[3]
    / "boneio"
    / "migrations"
    / "assets"
    / "helpers"
    / "boneio-migrate-v2"
)


@pytest.fixture(scope="module")
def version_key():
    """The helper's own comparison, taken from the file that ships.

    Read out of the asset rather than imported: this file is installed to
    /usr/sbin and run as root by sudo, so it is not an importable module, and a
    reimplementation here would pass while the shipped helper still refused.
    """
    namespace: dict = {}
    source = HELPER.read_text()
    head, _, _ = source.partition("def _raise_floor")
    exec(compile(head, str(HELPER), "exec"), namespace)  # noqa: S102
    return namespace["_version_key"]


class TestAgainstAFloorOfDev9:
    """What a device that has accepted 1.6.0.dev9 will take next."""

    FLOOR = "1.6.0.dev9"

    def accepted(self, version_key, release: str) -> bool:
        return not version_key(release) < version_key(self.FLOOR)

    @pytest.mark.parametrize(
        "release",
        [
            "1.6.0.dev9",
            "1.6.0.dev10",
            "1.6.0.dev11",
            "1.6.0.dev20",
            "1.6.0.dev100",
            "1.6.0.rc1",
            "1.6.0",
            "1.6.1.dev1",
            "1.7.0",
        ],
    )
    def test_it_accepts_everything_from_dev9_onwards(self, version_key, release):
        assert self.accepted(version_key, release)

    @pytest.mark.parametrize("release", ["1.6.0.dev8", "1.6.0.dev1", "1.5.18", "1.5.0"])
    def test_it_still_refuses_a_real_downgrade(self, version_key, release):
        # The protection has to keep working. A key that accepted everything
        # would pass the test above and lose the property the floor exists for.
        assert not self.accepted(version_key, release)


class TestOrdering:
    """The whole series, in the order a person would write it down."""

    def test_the_dev_series_sorts_by_number(self, version_key):
        series = ["1.6.0.dev2", "1.6.0.dev10", "1.6.0.dev9", "1.6.0.dev20"]
        assert sorted(series, key=version_key) == [
            "1.6.0.dev2",
            "1.6.0.dev9",
            "1.6.0.dev10",
            "1.6.0.dev20",
        ]

    def test_a_pre_release_sorts_below_its_own_release(self, version_key):
        assert version_key("1.6.0.dev1") < version_key("1.6.0")
        assert version_key("1.6.0.rc1") < version_key("1.6.0")

    def test_dev_sorts_below_rc(self, version_key):
        assert version_key("1.6.0.dev20") < version_key("1.6.0.rc1")

    def test_numbers_are_compared_before_the_suffix(self, version_key):
        # This is what lets a stuck device accept the release that repairs it:
        # the old, broken key agreed on this much, so 1.6.1.devN gets through
        # where 1.6.0.dev11 does not.
        assert version_key("1.6.0.dev99") < version_key("1.6.1.dev1")


class TestTheRepairIsInstallable:
    """The migration that replaces the helper has to be able to land."""

    def test_it_validates_before_overwriting_the_migration_channel(self):
        from boneio.migrations.versions import v1_6_16_release_floor_ordering as migration

        actions = migration.plan()
        # /usr/sbin/boneio-migrate-v2 is the only way this device migrates. A
        # helper that will not compile has to be refused before it is written,
        # because afterwards there is nothing left to fix it with.
        assert all(action.validate == "python" for action in actions)

    def test_it_refreshes_the_pristine_copy_too(self):
        from boneio.migrations.versions import v1_6_16_release_floor_ordering as migration

        # boneio-helpers-heal.service restores from the trusted directory, so
        # leaving the old helper there puts the broken comparison back at the
        # next boot.
        destinations = [action.dst for action in migration.plan()]
        assert destinations == [
            "/usr/lib/boneio/trusted/boneio-migrate-v2",
            "/usr/sbin/boneio-migrate-v2",
        ]
