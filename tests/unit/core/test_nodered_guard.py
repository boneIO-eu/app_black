"""After an update Node-RED still runs the settings it started with.

A controller flashed from a dev29 image ran the editor open; the migration
that puts the real settings.js back cannot restart the container, and an
update restarts boneIO only. So boneIO looks, and restarts Node-RED once when
the running editor wants no login while the file on disk asks for one.
"""

from types import SimpleNamespace

import pytest

from boneio.core import nodered_guard as guard

SECURE = 'module.exports = { adminAuth: { type: "credentials" } };\n'
STUB = 'module.exports = { httpAdminRoot: "/nodered" };\n'


@pytest.fixture
def settings(tmp_path):
    path = tmp_path / "settings.js"
    path.write_text(SECURE)
    return path


class Restart:
    def __init__(self, ok=True):
        self.calls = 0
        self.ok = ok

    def __call__(self):
        self.calls += 1
        return SimpleNamespace(ok=self.ok, stderr="" if self.ok else "boom", stdout="")


async def _run(answers, settings, restart, attempts=3):
    replies = iter(answers)
    return await guard.ensure_admin_auth(
        8443,
        first_check_after=0,
        retry_every=0,
        attempts=attempts,
        probe_fn=lambda _port: next(replies),
        settings_path=settings,
        restart=restart,
    )


@pytest.mark.asyncio
async def test_an_open_editor_with_secure_settings_is_restarted_once(settings):
    restart = Restart()
    assert await _run([guard.OPEN], settings, restart) == "restarted"
    assert restart.calls == 1


@pytest.mark.asyncio
async def test_a_protected_editor_is_left_alone(settings):
    restart = Restart()
    assert await _run([guard.PROTECTED], settings, restart) == guard.PROTECTED
    assert restart.calls == 0


@pytest.mark.asyncio
async def test_no_answer_is_not_a_reason_to_restart(settings):
    # Node-RED switched off, still starting, or the proxy being recreated.
    restart = Restart()
    answers = [guard.UNKNOWN] * 3
    assert await _run(answers, settings, restart) == guard.UNKNOWN
    assert restart.calls == 0


@pytest.mark.asyncio
async def test_it_keeps_looking_until_the_editor_answers(settings):
    restart = Restart()
    answers = [guard.UNKNOWN, guard.UNKNOWN, guard.OPEN]
    assert await _run(answers, settings, restart) == "restarted"


@pytest.mark.asyncio
async def test_settings_without_a_login_are_reported_not_restarted(settings):
    # A restart would bring the same open editor back.
    settings.write_text(STUB)
    restart = Restart()
    assert await _run([guard.OPEN], settings, restart) == guard.OPEN
    assert restart.calls == 0


@pytest.mark.asyncio
async def test_a_failed_restart_is_reported(settings):
    assert await _run([guard.OPEN], settings, Restart(ok=False)) == "restart_failed"


def test_the_probe_reads_the_login_type(monkeypatch):
    class Response:
        def __init__(self, body):
            self.body = body

        def read(self, _n):
            return self.body

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    monkeypatch.setattr(guard.urllib.request, "urlopen", lambda *_a, **_k: Response(b"{}"))
    assert guard.probe(8443) == guard.OPEN
    monkeypatch.setattr(
        guard.urllib.request, "urlopen",
        lambda *_a, **_k: Response(b'{"type":"credentials","prompts":[]}'),
    )
    assert guard.probe(8443) == guard.PROTECTED
    monkeypatch.setattr(guard.urllib.request, "urlopen", lambda *_a, **_k: Response(b"<html>502"))
    assert guard.probe(8443) == guard.UNKNOWN


def test_the_probe_treats_a_refused_connection_as_unknown(monkeypatch):
    def refuse(*_a, **_k):
        raise ConnectionRefusedError

    monkeypatch.setattr(guard.urllib.request, "urlopen", refuse)
    assert guard.probe(8443) == guard.UNKNOWN


def test_the_shipped_settings_require_a_login():
    from pathlib import Path

    shipped = Path(guard.__file__).parents[1] / "migrations/assets/docker/nodered/node-red/settings.js"
    assert guard.settings_require_login(shipped)
