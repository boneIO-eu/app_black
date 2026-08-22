"""Tests that the GitHub releases fetch does not stall the event loop.

The blocking ``requests.get()`` inside ``_fetch_github_releases`` was called
directly from three coroutines. On a BeagleBone Black that froze the whole
application — MQTT, GPIO handling and the web server — for 23.3 s during
startup, and again on every periodic check.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from boneio.webui.routes import update as update_routes


@pytest.fixture(autouse=True)
def _clear_cache():
    """Reset the module-level releases cache around each test."""
    update_routes._GITHUB_RELEASES_CACHE["data"] = None
    update_routes._GITHUB_RELEASES_CACHE["fetched_at"] = 0.0
    yield
    update_routes._GITHUB_RELEASES_CACHE["data"] = None
    update_routes._GITHUB_RELEASES_CACHE["fetched_at"] = 0.0


@pytest.mark.asyncio
async def test_slow_fetch_does_not_block_the_event_loop(monkeypatch) -> None:
    """A slow network call must not prevent other tasks from running."""
    blocking_duration = 0.4

    def slow_fetch(repo="boneIO-eu/app_black"):
        time.sleep(blocking_duration)  # stands in for DNS + TLS + JSON parse
        return [{"tag_name": "v1.5.0", "prerelease": False, "published_at": "x"}], None

    monkeypatch.setattr(update_routes, "_fetch_github_releases", slow_fetch)

    ticks = 0

    async def heartbeat() -> None:
        """Represents MQTT/GPIO work that must keep running."""
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.02)

    beat = asyncio.create_task(heartbeat())
    try:
        releases, error = await update_routes._fetch_github_releases_async()
    finally:
        beat.cancel()
        await asyncio.gather(beat, return_exceptions=True)

    assert error is None
    assert releases and releases[0]["tag_name"] == "v1.5.0"
    # Blocking the loop would have left ticks at 1. Allow generous slack for
    # slow CI, but require clear evidence of concurrency.
    assert ticks > 5, f"event loop appears blocked (ticks={ticks})"


@pytest.mark.asyncio
async def test_cache_hit_is_answered_without_a_thread(monkeypatch) -> None:
    """Cached results short-circuit before to_thread, avoiding pointless churn."""
    update_routes._GITHUB_RELEASES_CACHE["data"] = [{"tag_name": "v1.4.0"}]
    update_routes._GITHUB_RELEASES_CACHE["fetched_at"] = time.monotonic()

    def explode(repo="boneIO-eu/app_black"):
        raise AssertionError("must not be called on a cache hit")

    monkeypatch.setattr(update_routes, "_fetch_github_releases", explode)

    releases, error = await update_routes._fetch_github_releases_async()

    assert error is None
    assert releases == [{"tag_name": "v1.4.0"}]


@pytest.mark.asyncio
async def test_errors_propagate_from_the_worker_thread(monkeypatch) -> None:
    """Failure handling is unchanged by the thread hop."""

    def failing_fetch(repo="boneIO-eu/app_black"):
        return None, "GitHub API request failed: boom"

    monkeypatch.setattr(update_routes, "_fetch_github_releases", failing_fetch)

    releases, error = await update_routes._fetch_github_releases_async()

    assert releases is None
    assert error == "GitHub API request failed: boom"
