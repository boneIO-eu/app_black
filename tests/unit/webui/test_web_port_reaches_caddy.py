"""The panel's port has to arrive at Caddy, or moving it strands the device.

Caddy's Caddyfile is generated when its container starts, from ``WEB_PORT``.
Before this, the upstream was hardcoded at 8090, so changing ``web.port`` left
Caddy proxying to a port nothing was listening on — and with ``web.expose`` set
to ``proxy``, which a 1.6 image now ships, the application was not listening on
the LAN either. The device answered on nothing but the loopback, the USB gadget
link and an SSH tunnel.

These tests cover the two halves that can each fail silently: the ``.env`` the
port is written to, and the shipped assets that have to read it.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from boneio.core import containers
from boneio.webui.routes import config_core
from boneio.webui.routes.config_core import _apply_web_port_change

ASSETS = Path(containers.__file__).resolve().parents[2] / "boneio" / "migrations" / "assets"
DOCKER_ASSETS = ASSETS / "docker" / "nodered"


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    """Point the compose project's .env at a temporary directory."""
    path = tmp_path / "docker" / "nodered" / ".env"
    monkeypatch.setattr(containers, "ENV_FILE", path)
    return path


class TestTheEnvFile:
    """Writing one variable without disturbing the file around it."""

    def test_it_is_created_when_absent(self, env_file):
        assert containers.set_project_env("WEB_PORT", "8095")
        assert env_file.read_text() == "WEB_PORT=8095\n"

    def test_it_keeps_what_the_operator_put_there(self, env_file):
        env_file.parent.mkdir(parents=True)
        env_file.write_text("# theirs\nHTTPS_PORT=9443\nWEB_PORT=8090\nHOSTNAME=kotek\n")

        assert containers.set_project_env("WEB_PORT", "8095")

        assert env_file.read_text() == (
            "# theirs\nHTTPS_PORT=9443\nWEB_PORT=8095\nHOSTNAME=kotek\n"
        )

    def test_a_later_duplicate_goes_too(self, env_file):
        # Compose reads the first assignment, but a later one overrides it, so
        # leaving the second behind would keep the old port in force.
        env_file.parent.mkdir(parents=True)
        env_file.write_text("WEB_PORT=8090\nX=1\nexport WEB_PORT = 7777\n")

        assert containers.set_project_env("WEB_PORT", "8095")

        assert env_file.read_text() == "WEB_PORT=8095\nX=1\n"

    def test_it_leaves_no_temporary_file_behind(self, env_file):
        assert containers.set_project_env("WEB_PORT", "8095")
        assert [p.name for p in env_file.parent.iterdir()] == [".env"]

    def test_an_unwritable_directory_is_reported_not_raised(self, env_file, monkeypatch):
        def refuse(*args, **kwargs):
            raise OSError("read-only file system")

        monkeypatch.setattr(containers.os, "fdopen", refuse)
        monkeypatch.setattr(Path, "mkdir", lambda *a, **k: None)

        assert containers.set_project_env("WEB_PORT", "8095") is False


class TestTheShippedAssets:
    """The generated Caddyfile and the templates that feed it."""

    def test_no_asset_hardcodes_the_panel_port(self):
        offenders = [
            path.relative_to(ASSETS)
            for path in ASSETS.rglob("*")
            if path.is_file()
            and path.suffix in {".sh", ".yaml", ".yml"}
            and "host.docker.internal:8090" in path.read_text(errors="ignore")
        ]
        assert offenders == []

    def test_the_init_script_reads_the_variable(self):
        script = (DOCKER_ASSETS / "caddy" / "init-certs.sh").read_text()
        assert "host.docker.internal:${WEB_PORT:-8090}" in script

    @pytest.mark.parametrize(
        "template", ["docker-compose.yaml", "docker-compose-cloud.yaml"]
    )
    def test_both_templates_pass_the_ports_in(self, template):
        body = (DOCKER_ASSETS / template).read_text()
        # Without WEB_PORT the init script's default applies and .env is read
        # and then ignored, which looks exactly like the change having worked.
        assert "WEB_PORT=${WEB_PORT:-8090}" in body
        # PUBLIC_HTTPS_PORT had been referenced by the redirect since it was
        # written, and supplied by neither template.
        assert "PUBLIC_HTTPS_PORT=${HTTPS_PORT:-8443}" in body

    def test_the_migration_refreshes_the_trusted_templates(self):
        # boneio-containers copies the compose from /usr/lib/boneio/trusted, so
        # a stale copy there restores the old file the next time cloud mode is
        # switched, undoing this without a trace.
        from boneio.migrations.versions import v1_6_15_web_port_reaches_caddy as migration

        destinations = {action.dst for action in migration.plan()}
        assert "/usr/lib/boneio/trusted/docker-compose.yaml" in destinations
        assert "/usr/lib/boneio/trusted/docker-compose-cloud.yaml" in destinations


class TestApplyingAPortChange:
    """What the save path does once the new port is stored."""

    @pytest.fixture
    def spy(self, monkeypatch):
        """Record the calls, without touching a device."""
        calls: list[str] = []

        class Outcome:
            ok = True
            error = None

        def env(name, value):
            calls.append(f"env:{name}={value}")
            return True

        monkeypatch.setattr(config_core.containers, "set_project_env", env)
        for verb in ("apply_cloud_template", "remove_cloud_template", "start_caddy"):
            monkeypatch.setattr(
                config_core.containers,
                verb,
                lambda v=verb: (calls.append(v), Outcome())[1],
            )
        return calls

    def test_nothing_happens_when_the_port_did_not_move(self, spy):
        outcome = asyncio.run(
            _apply_web_port_change({"port": 8090}, {"port": 8090, "expose": "proxy"})
        )
        assert outcome is None
        assert spy == []

    def test_a_moved_port_is_written_and_the_proxy_brought_up(self, spy):
        outcome = asyncio.run(
            _apply_web_port_change({"port": 8090}, {"port": 8095})
        )
        # up -d, not restart: a container's environment is fixed at creation,
        # so a restart would keep the old port and report success.
        assert spy == ["env:WEB_PORT=8095", "remove_cloud_template", "start_caddy"]
        assert "8095" in outcome

    def test_a_cloud_device_keeps_its_own_template(self, spy):
        asyncio.run(
            _apply_web_port_change(
                {"port": 8090}, {"port": 8095, "cloud": {"enabled": True}}
            )
        )
        assert "apply_cloud_template" in spy
        assert "remove_cloud_template" not in spy

    def test_a_failure_is_reported_rather_than_raised(self, monkeypatch):
        # The port is already saved by this point. A 500 here would say nothing
        # was written, which is worse than saying the proxy is behind.
        monkeypatch.setattr(
            config_core.containers, "set_project_env", lambda *a: False
        )
        outcome = asyncio.run(_apply_web_port_change({"port": 8090}, {"port": 8095}))
        assert "8095" in outcome
