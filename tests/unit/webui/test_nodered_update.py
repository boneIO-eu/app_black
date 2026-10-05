"""A Node-RED update offers only what can run here, and undoes itself on failure.

Node-RED 5 publishes no arm/v7 image, which is what a BeagleBone is. The check
offered 5.x anyway; the update then rewrote the compose file, failed the pull,
and left the file naming an image that does not exist. The panel reported 5.x
while the editor, still on the old container, said 4.1.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from boneio.core import containers
from boneio.webui.routes import nodered


def _tag(name: str, *platforms: tuple[str, str | None]) -> dict:
    return {"name": name, "platforms": [list(p) for p in platforms]}


ARM = ("arm", "v7")
ARM64 = ("arm64", None)
AMD64 = ("amd64", None)

TAGS = [
    _tag("latest-22-minimal", AMD64, ARM, ARM64),
    _tag("5.0.7-minimal", AMD64, ARM64),
    _tag("5.0.7-24-minimal", AMD64, ARM64),
    _tag("4.1.15-22-minimal", AMD64, ARM, ARM64),
    _tag("4.1.15-20-minimal", AMD64, ARM, ARM64),
    _tag("4.1.15-22", AMD64, ARM, ARM64),
    _tag("4.1.14-22-minimal", AMD64, ARM, ARM64),
]


@pytest.fixture
def installed(monkeypatch):
    """Set the installed version and the tag list Docker Hub returns."""

    def install(version: str, machine: str = "armv7l", tags: list[dict] = TAGS):
        monkeypatch.setattr(nodered, "_get_installed_version", lambda: version)
        monkeypatch.setattr(nodered.platform, "machine", lambda: machine)

        async def fetch():
            return tags

        monkeypatch.setattr(nodered, "_fetch_docker_hub_tags_async", fetch)

    return install


class TestTheCheck:
    async def test_a_beaglebone_is_not_offered_node_red_5(self, installed):
        installed("4.1.2-22-minimal")
        result = await nodered.check_update()
        assert result.latest_version == "4.1.15-22-minimal"
        assert result.update_available

    async def test_a_machine_with_an_image_for_it_is(self, installed):
        installed("5.0.6-24-minimal", machine="x86_64",
                  tags=[_tag("5.0.7-24-minimal", AMD64, ARM64)])
        result = await nodered.check_update()
        assert result.latest_version == "5.0.7-24-minimal"

    async def test_the_node_major_is_kept(self, installed):
        installed("4.1.2-20-minimal")
        result = await nodered.check_update()
        assert result.latest_version == "4.1.15-20-minimal"

    async def test_the_full_image_is_not_swapped_for_minimal(self, installed):
        installed("4.1.2-22")
        result = await nodered.check_update()
        assert result.latest_version == "4.1.15-22"

    async def test_nothing_newer_that_runs_here_is_no_update(self, installed):
        installed("4.1.15-22-minimal")
        result = await nodered.check_update()
        assert not result.update_available
        assert result.latest_version == "4.1.15-22-minimal"

    async def test_an_unversioned_tag_is_left_alone(self, installed):
        installed("latest-22-minimal")
        result = await nodered.check_update()
        assert not result.update_available


class TestTheInstalledVersion:
    def test_the_running_container_wins_over_the_compose_file(self, monkeypatch):
        monkeypatch.setattr(nodered, "_get_current_image_version", lambda: "5.0.7-minimal")
        monkeypatch.setattr(
            containers, "service_status",
            lambda service, timeout=30: {
                "State": "running", "Image": "nodered/node-red:4.1.2-22-minimal",
            },
        )
        monkeypatch.setitem(nodered._STATUS_CACHE, "checked_at", 0.0)
        assert nodered._get_installed_version() == "4.1.2-22-minimal"

    def test_a_stopped_container_falls_back_to_the_compose_file(self, monkeypatch):
        monkeypatch.setattr(nodered, "_get_current_image_version", lambda: "4.1.2-22-minimal")
        monkeypatch.setattr(containers, "service_status", lambda service, timeout=30: None)
        monkeypatch.setitem(nodered._STATUS_CACHE, "checked_at", 0.0)
        assert nodered._get_installed_version() == "4.1.2-22-minimal"


class _Tasks:
    """Stands in for BackgroundTasks; keeps the task to run it here."""

    def __init__(self):
        self.task = None

    def add_task(self, task):
        self.task = task


@pytest.fixture
def helper(monkeypatch, tmp_path):
    """Record the helper calls an update makes; *fail* names the one that fails."""
    compose = tmp_path / "docker-compose.yaml"
    compose.write_text("services:\n  node-red:\n    image: nodered/node-red:4.1.2-22-minimal\n")
    monkeypatch.setattr(nodered, "COMPOSE_FILE_PATH", str(compose))

    calls: list[tuple[str, str | None]] = []
    state = {"fail": None}

    def verb(name):
        def call(*args, **kwargs):
            calls.append((name, args[0] if args else None))
            ok = state["fail"] != name
            return containers.Result(0 if ok else 1, "", "" if ok else f"{name} broke", True)
        return call

    monkeypatch.setattr(containers, "set_nodered_image", verb("set"))
    monkeypatch.setattr(containers, "pull_nodered", verb("pull"))
    monkeypatch.setattr(containers, "start_nodered", verb("up"))

    async def no_backup():
        return None

    monkeypatch.setattr(nodered, "create_backup", no_backup)

    async def fetch():
        return [{"name": "4.1.15-22-minimal", "size_here": state["image_bytes"]}]

    monkeypatch.setattr(nodered, "_fetch_docker_hub_tags_async", fetch)
    monkeypatch.setattr(
        nodered.shutil, "disk_usage",
        lambda path: SimpleNamespace(free=state["free_mb"] << 20),
    )
    state.update(image_bytes=112 << 20, free_mb=25_000)
    nodered._reset_update_status()
    return calls, state


async def _update(target: str = "4.1.15-22-minimal") -> None:
    tasks = _Tasks()
    await nodered.perform_update(tasks, target_version=target)
    await tasks.task()


class TestTheUpdate:
    async def test_a_failed_pull_puts_the_old_tag_back(self, helper):
        calls, state = helper
        state["fail"] = "pull"
        await _update()
        assert calls == [
            ("set", "4.1.15-22-minimal"),
            ("pull", None),
            ("set", "4.1.2-22-minimal"),
        ]
        assert nodered._update_status["status"] == "error"

    async def test_a_failed_start_also_brings_the_old_container_back(self, helper):
        calls, state = helper
        state["fail"] = "up"
        await _update()
        assert calls[-2:] == [("set", "4.1.2-22-minimal"), ("up", None)]
        assert nodered._update_status["status"] == "error"

    async def test_a_good_update_is_not_undone(self, helper):
        calls, _ = helper
        await _update()
        assert calls == [("set", "4.1.15-22-minimal"), ("pull", None), ("up", None)]
        assert nodered._update_status["status"] == "success"

    async def test_too_little_room_stops_it_before_anything_changes(self, helper):
        calls, state = helper
        state["free_mb"] = 400  # a 112 MB image needs 548 MB
        await _update()
        assert calls == []
        assert nodered._update_status["status"] == "error"
        assert "needs 548 MB free, 400 MB available" in nodered._update_status["error"]

    async def test_an_unknown_size_still_asks_for_the_minimum(self, helper):
        calls, state = helper
        state.update(image_bytes=None, free_mb=499)
        await _update()
        assert calls == []


def test_the_size_is_taken_for_this_machine(monkeypatch):
    monkeypatch.setattr(nodered.platform, "machine", lambda: "armv7l")
    images = [
        {"architecture": "amd64", "variant": None, "size": 1},
        {"architecture": "arm", "variant": "v7", "size": 2},
    ]
    assert nodered._size_here(images) == 2
