"""Tests for boneio.core.utils.overlay.

Covers the defect that made overlay detection unreliable: only the
``overlays/`` subdirectory was ever inspected, while U-Boot resolves bare
filenames from ``/boot/dtbs/$uname_r/``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from boneio.core.utils import overlay as overlay_util

OVERLAY_NAME = "BONEIO-BLACK-PINS-v1.0.dtbo"


@pytest.fixture
def dtbs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the module at a temporary /boot/dtbs tree."""
    root = tmp_path / "dtbs"
    root.mkdir()
    monkeypatch.setattr(overlay_util, "DTBS_ROOT", root)
    return root


def _make_kernel(root: Path, version: str, *, in_uboot: bool, in_overlays: bool) -> None:
    """Create a kernel DTB dir, optionally seeding each overlay destination."""
    base = root / version
    (base / "overlays").mkdir(parents=True)
    if in_uboot:
        (base / OVERLAY_NAME).write_bytes(b"\xd0\x0d\xfe\xed")
    if in_overlays:
        (base / "overlays" / OVERLAY_NAME).write_bytes(b"\xd0\x0d\xfe\xed")


class TestMissingOverlayDirs:
    def test_both_present_reports_nothing_missing(self, dtbs: Path) -> None:
        _make_kernel(dtbs, "6.1.0-test", in_uboot=True, in_overlays=True)
        assert overlay_util.missing_overlay_dirs("6.1.0-test") == []

    def test_only_overlays_subdir_reports_uboot_path_missing(self, dtbs: Path) -> None:
        """The regression under test.

        The old check looked solely at overlays/, called this state healthy, and
        left U-Boot unable to find the overlay.
        """
        _make_kernel(dtbs, "6.1.0-test", in_uboot=False, in_overlays=True)
        missing = overlay_util.missing_overlay_dirs("6.1.0-test")
        assert missing == [dtbs / "6.1.0-test"]

    def test_only_uboot_path_reports_overlays_missing(self, dtbs: Path) -> None:
        _make_kernel(dtbs, "6.1.0-test", in_uboot=True, in_overlays=False)
        missing = overlay_util.missing_overlay_dirs("6.1.0-test")
        assert missing == [dtbs / "6.1.0-test" / "overlays"]

    def test_neither_present_reports_both(self, dtbs: Path) -> None:
        _make_kernel(dtbs, "6.1.0-test", in_uboot=False, in_overlays=False)
        missing = overlay_util.missing_overlay_dirs("6.1.0-test")
        assert missing == [
            dtbs / "6.1.0-test",
            dtbs / "6.1.0-test" / "overlays",
        ]

    def test_unknown_kernel_dir_is_not_reported(self, dtbs: Path) -> None:
        """A kernel with no DTB dir at all is not our problem to repair."""
        assert overlay_util.missing_overlay_dirs("9.9.9-absent") == []


class TestFindOverlaySource:
    def test_finds_source_in_overlays_subdir(self, dtbs: Path) -> None:
        _make_kernel(dtbs, "6.0.0-old", in_uboot=False, in_overlays=True)
        assert overlay_util.find_overlay_source() == dtbs / "6.0.0-old" / "overlays"

    def test_finds_source_in_uboot_path(self, dtbs: Path) -> None:
        _make_kernel(dtbs, "6.0.0-old", in_uboot=True, in_overlays=False)
        assert overlay_util.find_overlay_source() == dtbs / "6.0.0-old"

    def test_prefers_newest_kernel(self, dtbs: Path) -> None:
        _make_kernel(dtbs, "6.0.0-old", in_uboot=True, in_overlays=True)
        _make_kernel(dtbs, "6.9.0-new", in_uboot=True, in_overlays=True)
        assert overlay_util.find_overlay_source() == dtbs / "6.9.0-new"

    def test_excludes_repair_destinations(self, dtbs: Path) -> None:
        """A destination being repaired must not be chosen as its own source."""
        _make_kernel(dtbs, "6.9.0-new", in_uboot=False, in_overlays=True)
        _make_kernel(dtbs, "6.0.0-old", in_uboot=True, in_overlays=True)
        src = overlay_util.find_overlay_source(
            exclude=(dtbs / "6.9.0-new", dtbs / "6.9.0-new" / "overlays")
        )
        assert src == dtbs / "6.0.0-old"

    def test_returns_none_when_no_overlays_anywhere(self, dtbs: Path) -> None:
        _make_kernel(dtbs, "6.0.0-old", in_uboot=False, in_overlays=False)
        assert overlay_util.find_overlay_source() is None

    def test_returns_none_when_dtbs_root_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(overlay_util, "DTBS_ROOT", tmp_path / "nope")
        assert overlay_util.find_overlay_source() is None


class TestAppliedState:
    def test_no_chosen_overlays_node_means_not_applied(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """U-Boot merging no overlays leaves the node absent entirely."""
        monkeypatch.setattr(overlay_util, "DT_CHOSEN_OVERLAYS", tmp_path / "absent")
        assert overlay_util.applied_overlay_names() == []
        assert overlay_util.is_boneio_overlay_applied() is False

    def test_stock_overlays_only_means_boneio_not_applied(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The exact state observed on the field controller."""
        node = tmp_path / "overlays"
        node.mkdir()
        (node / "BB-ADC-00A0.kernel").write_text("")
        (node / "BB-BONE-eMMC1-01-00A0.kernel").write_text("")
        (node / "name").write_text("")
        monkeypatch.setattr(overlay_util, "DT_CHOSEN_OVERLAYS", node)

        assert overlay_util.applied_overlay_names() == [
            "BB-ADC-00A0.kernel",
            "BB-BONE-eMMC1-01-00A0.kernel",
        ]
        assert overlay_util.is_boneio_overlay_applied() is False

    def test_boneio_overlay_detected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        node = tmp_path / "overlays"
        node.mkdir()
        (node / "BB-ADC-00A0.kernel").write_text("")
        (node / "BONEIO-BLACK-PINS-v1.0.kernel").write_text("")
        (node / "name").write_text("")
        monkeypatch.setattr(overlay_util, "DT_CHOSEN_OVERLAYS", node)

        assert overlay_util.is_boneio_overlay_applied() is True

    def test_name_property_is_not_treated_as_an_overlay(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        node = tmp_path / "overlays"
        node.mkdir()
        (node / "name").write_text("")
        monkeypatch.setattr(overlay_util, "DT_CHOSEN_OVERLAYS", node)
        assert overlay_util.applied_overlay_names() == []


class TestOverlayDirsForKernel:
    def test_returns_uboot_path_first(self, dtbs: Path) -> None:
        uboot_dir, tooling_dir = overlay_util.overlay_dirs_for_kernel("6.1.0-test")
        assert uboot_dir == dtbs / "6.1.0-test"
        assert tooling_dir == dtbs / "6.1.0-test" / "overlays"
