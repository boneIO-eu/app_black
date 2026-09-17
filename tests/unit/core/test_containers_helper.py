"""Tests for boneio-containers, the privileged container helper.

It exists so the ``boneio`` account can leave the ``docker`` group, which is
root-equivalent. The two properties worth guarding are that no caller value
reaches docker, and that compose is never run against a file the caller could
have written — because the compose file, not the argument list, is the vector.
"""

from __future__ import annotations

import json
import os
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HELPER = REPO_ROOT / "boneio" / "migrations" / "assets" / "helpers" / "boneio-containers"


@pytest.fixture(scope="module")
def helper():
    """The helper loaded as a module (it has no .py extension)."""
    return SourceFileLoader("boneio_containers", str(HELPER)).load_module()


@pytest.fixture
def project(tmp_path, helper, monkeypatch):
    """A compose project and pristine copy the helper will accept."""
    project_dir = tmp_path / "docker" / "nodered"
    trusted = tmp_path / "trusted"
    project_dir.mkdir(parents=True)
    trusted.mkdir()

    compose = project_dir / "docker-compose.yaml"
    compose.write_text("services:\n  node-red:\n    image: nodered\n")
    os.chmod(compose, 0o644)
    (trusted / "docker-compose.yaml").write_text("services:\n  plain: {}\n")
    (trusted / "docker-compose-cloud.yaml").write_text(
        "services:\n  caddy:\n    environment:\n      DOMAIN: ${DOMAIN}\n"
    )
    for name in ("docker-compose.yaml", "docker-compose-cloud.yaml"):
        os.chmod(trusted / name, 0o644)

    monkeypatch.setattr(helper, "PROJECT_DIR", project_dir)
    monkeypatch.setattr(helper, "COMPOSE_FILE", compose)
    monkeypatch.setattr(helper, "TRUSTED_DIR", trusted)
    monkeypatch.setattr(helper, "COMPOSE_TEMPLATE", trusted / "docker-compose.yaml")
    monkeypatch.setattr(
        helper, "COMPOSE_CLOUD_TEMPLATE", trusted / "docker-compose-cloud.yaml"
    )
    monkeypatch.setattr(helper, "_assert_root", lambda: None)
    # The suite is not root, so nothing on disk is root-owned; ownership itself
    # is covered separately.
    monkeypatch.setattr(
        helper, "_root_owned",
        lambda path: (
            os.path.isfile(path)
            and not os.path.islink(path)
            and not path.lstat().st_mode & 0o022
        ),
    )
    return project_dir


@pytest.fixture
def ran(helper, monkeypatch):
    """Record what would have been executed instead of running docker."""
    calls: list[list[str]] = []

    def _fake(argv, timeout=120):
        calls.append(list(argv))
        return 0

    monkeypatch.setattr(helper, "_run", _fake)
    return calls


# ------------------------------------------------------------------- the verbs


def test_every_verb_the_app_needs_is_available(helper):
    """The inventory of docker calls in the application, as verbs."""
    for verb in (
        "status", "start-nodered", "stop-nodered", "restart-caddy",
        "reload-caddy", "pull-nodered", "logs-caddy", "logs-nodered",
        "apply-cloud-template", "remove-cloud-template",
    ):
        assert verb in helper.ALL_VERBS, f"{verb} is missing from the verb list"


def test_an_unknown_verb_is_refused(helper, project, ran):
    assert helper.main(["definitely-not-a-verb"]) == 1
    assert ran == []


@pytest.mark.parametrize("extra", ["evil", "--privileged", "/etc/shadow"])
def test_a_verb_cannot_be_given_an_extra_argument(helper, project, ran, extra):
    """Otherwise the argument is one step from reaching docker."""
    assert helper.main(["restart-caddy", extra]) == 1
    assert ran == []


def test_no_verb_passes_caller_data_to_docker(helper):
    """Every fixed verb expands to a constant command."""
    for verb in set(helper.VERBS) | set(helper.DAEMON_VERBS):
        argv = helper._argv_for(verb)
        assert argv[0] == "docker", verb
        assert all(isinstance(part, str) for part in argv), verb


def test_list_verbs_is_machine_readable(helper, capsys):
    assert helper.main(["--list-verbs"]) == 0
    assert json.loads(capsys.readouterr().out) == helper.ALL_VERBS


def test_a_known_verb_runs_the_expected_command(helper, project, ran):
    assert helper.main(["restart-caddy"]) == 0
    assert ran == [helper._argv_for("restart-caddy")]


# --------------------------------------------------------- the compose file


def test_a_non_root_owned_compose_file_stops_every_write_verb(
    helper, project, ran
):
    """The file is the vector: `compose up` reads it and can mount the host."""
    os.chmod(project / "docker-compose.yaml", 0o666)
    assert helper.main(["up"]) == 2
    assert ran == []


def test_a_missing_compose_file_stops_every_write_verb(helper, project, ran):
    (project / "docker-compose.yaml").unlink()
    assert helper.main(["start-nodered"]) == 2
    assert ran == []


def test_a_compose_symlink_is_refused(helper, project, ran, tmp_path):
    """A symlink would let the caller point compose anywhere."""
    compose = project / "docker-compose.yaml"
    compose.unlink()
    elsewhere = tmp_path / "attacker.yaml"
    elsewhere.write_text("services: {}\n")
    compose.symlink_to(elsewhere)
    assert helper.main(["up"]) == 2
    assert ran == []


def test_read_only_verbs_still_work_with_an_untrusted_compose_file(
    helper, project, ran
):
    """Refusing these would leave the UI unable to say what is wrong."""
    os.chmod(project / "docker-compose.yaml", 0o666)
    assert helper.main(["status"]) == 0
    assert ran == [helper._argv_for("status")]


# ------------------------------------------------------------------ log tails


def test_a_log_tail_accepts_a_sane_line_count(helper, project, ran):
    assert helper.main(["logs-caddy", "50"]) == 0
    assert "50" in ran[0]


def test_a_log_tail_defaults_without_an_argument(helper, project, ran):
    assert helper.main(["logs-nodered"]) == 0
    assert "200" in ran[0]


@pytest.mark.parametrize("argument", ["0", "99999", "-1", "10; id", "abc", "1e3"])
def test_a_bad_log_line_count_is_refused(helper, project, ran, argument):
    assert helper.main(["logs-caddy", argument]) == 1
    assert ran == []


# ---------------------------------------------------------------- the domain


@pytest.mark.parametrize("domain", [
    "boneio.example.com",
    "a.io",
    "my-device.cloud.boneio.eu",
])
def test_a_plausible_domain_is_accepted(helper, project, domain):
    assert helper.main(["apply-cloud-template", domain]) == 0
    written = (project / "docker-compose.yaml").read_text()
    assert domain in written
    assert "${DOMAIN}" not in written


@pytest.mark.parametrize("domain", [
    "",
    "no-dot",
    "-leading.example.com",
    "trailing-.example.com",
    "with space.example.com",
    "x.example.com\nservices:\n  evil:\n    privileged: true",
    "$(id).example.com",
    "../../etc/passwd",
    "a" * 300 + ".com",
])
def test_an_implausible_domain_is_refused(helper, project, domain):
    """Validated before it can reach the template, so no YAML can be smuggled."""
    before = (project / "docker-compose.yaml").read_text()
    assert helper.main(["apply-cloud-template", domain]) == 1
    assert (project / "docker-compose.yaml").read_text() == before


def test_applying_a_template_leaves_a_root_owned_file(helper, project):
    helper.main(["apply-cloud-template", "boneio.example.com"])
    mode = (project / "docker-compose.yaml").lstat().st_mode
    assert not mode & 0o022, "the installed compose file is writable by others"


def test_removing_the_cloud_template_restores_the_plain_one(helper, project):
    helper.main(["apply-cloud-template", "boneio.example.com"])
    assert helper.main(["remove-cloud-template"]) == 0
    assert "plain" in (project / "docker-compose.yaml").read_text()


def test_a_template_that_is_not_root_owned_is_refused(helper, project):
    os.chmod(helper.COMPOSE_CLOUD_TEMPLATE, 0o666)
    before = (project / "docker-compose.yaml").read_text()
    assert helper.main(["apply-cloud-template", "boneio.example.com"]) == 1
    assert (project / "docker-compose.yaml").read_text() == before


# ------------------------------------------------------------------ selftest


def test_selftest_reports_an_untrusted_compose_file(helper, project):
    os.chmod(project / "docker-compose.yaml", 0o666)
    assert helper.selftest() == 1


def test_selftest_reports_a_missing_template(helper, project):
    helper.COMPOSE_TEMPLATE.unlink()
    assert helper.selftest() == 1
