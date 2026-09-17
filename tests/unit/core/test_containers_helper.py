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
    compose.write_text(
        "services:\n"
        "  node-red:\n"
        "    image: nodered/node-red:4.1.2-22-minimal\n"
        "    restart: unless-stopped\n"
        "  caddy:\n"
        "    image: caddy:2-alpine\n"
    )
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


# -------------------------------------------------------- the compose template


def test_the_cloud_template_takes_no_argument(helper, project):
    """The template needs no parameter, so accepting one would only open a path
    for caller data to reach the file `docker compose up` executes."""
    before = (project / "docker-compose.yaml").read_text()
    assert helper.main(["apply-cloud-template", "boneio.example.com"]) == 1
    assert (project / "docker-compose.yaml").read_text() == before


def test_applying_the_cloud_template_copies_the_trusted_file(helper, project):
    assert helper.main(["apply-cloud-template"]) == 0
    assert (project / "docker-compose.yaml").read_text() == \
        helper.COMPOSE_CLOUD_TEMPLATE.read_text()


def test_applying_a_template_leaves_a_file_others_cannot_write(helper, project):
    helper.main(["apply-cloud-template"])
    mode = (project / "docker-compose.yaml").lstat().st_mode
    assert not mode & 0o022, "the installed compose file is writable by others"


def test_removing_the_cloud_template_restores_the_plain_one(helper, project):
    helper.main(["apply-cloud-template"])
    assert helper.main(["remove-cloud-template"]) == 0
    assert "plain" in (project / "docker-compose.yaml").read_text()


def test_a_template_that_is_not_root_owned_is_refused(helper, project):
    os.chmod(helper.COMPOSE_CLOUD_TEMPLATE, 0o666)
    before = (project / "docker-compose.yaml").read_text()
    assert helper.main(["apply-cloud-template"]) == 1
    assert (project / "docker-compose.yaml").read_text() == before


# ------------------------------------------------------------------ selftest


def test_selftest_reports_an_untrusted_compose_file(helper, project):
    os.chmod(project / "docker-compose.yaml", 0o666)
    assert helper.selftest() == 1


def test_selftest_reports_a_missing_template(helper, project):
    helper.COMPOSE_TEMPLATE.unlink()
    assert helper.selftest() == 1


# ---------------------------------------------------------- customised files


def test_a_hand_edited_compose_file_is_backed_up(helper, project):
    """Hand-editing is being taken away; what was written must not vanish."""
    compose = project / "docker-compose.yaml"
    compose.write_text("services:\n  mine:\n    image: something-i-wrote\n")

    assert helper.main(["apply-cloud-template"]) == 0
    backup = compose.with_suffix(".yaml.bak")
    assert backup.exists()
    assert "something-i-wrote" in backup.read_text()


def test_one_of_our_own_templates_is_not_backed_up(helper, project):
    """The template it came from is already the backup."""
    compose = project / "docker-compose.yaml"
    compose.write_text(helper.COMPOSE_TEMPLATE.read_text())

    helper.main(["apply-cloud-template"])
    assert not compose.with_suffix(".yaml.bak").exists()


def test_an_existing_backup_is_not_overwritten(helper, project):
    """A second switch must not bury the first backup."""
    compose = project / "docker-compose.yaml"
    backup = compose.with_suffix(".yaml.bak")
    backup.write_text("the original\n")
    compose.write_text("services:\n  mine: {}\n")

    helper.main(["apply-cloud-template"])
    assert backup.read_text() == "the original\n"


# ------------------------------------------------------- the node-red image tag


def test_the_image_tag_can_be_changed(helper, project):
    assert helper.main(["set-nodered-image", "4.2.0-22-minimal"]) == 0
    assert "nodered/node-red:4.2.0-22-minimal" in \
        (project / "docker-compose.yaml").read_text()


def test_changing_the_tag_touches_nothing_else(helper, project):
    """The application used to rewrite the whole file to change one tag."""
    compose = project / "docker-compose.yaml"
    before = compose.read_text().splitlines()
    helper.main(["set-nodered-image", "4.2.0-22-minimal"])
    after = compose.read_text().splitlines()

    assert len(before) == len(after)
    changed = [
        (b, a) for b, a in zip(before, after) if b != a
    ]
    assert len(changed) == 1
    assert "nodered/node-red" in changed[0][0]
    assert "caddy:2-alpine" in "\n".join(after), "the caddy image was disturbed"


@pytest.mark.parametrize("tag", [
    "",
    "-leading",
    "tag with space",
    "tag\nservices:\n  evil:\n    privileged: true",
    "$(id)",
    "../../etc/passwd",
    "a" * 200,
])
def test_an_implausible_tag_is_refused(helper, project, tag):
    """Validated before it reaches the file `docker compose up` executes."""
    compose = project / "docker-compose.yaml"
    before = compose.read_text()
    assert helper.main(["set-nodered-image", tag]) == 1
    assert compose.read_text() == before


def test_setting_the_same_tag_is_a_no_op(helper, project):
    compose = project / "docker-compose.yaml"
    before = compose.read_text()
    assert helper.main(["set-nodered-image", "4.1.2-22-minimal"]) == 0
    assert compose.read_text() == before


def test_a_compose_file_without_the_image_line_is_refused(helper, project):
    """Better than guessing which line was meant."""
    compose = project / "docker-compose.yaml"
    compose.write_text("services:\n  node-red:\n    build: .\n")
    assert helper.main(["set-nodered-image", "4.2.0"]) == 1


def test_setting_the_tag_needs_a_root_owned_compose_file(helper, project):
    compose = project / "docker-compose.yaml"
    os.chmod(compose, 0o666)
    assert helper.main(["set-nodered-image", "4.2.0"]) == 2


# ---------------------------------------------------------- container log access


def test_a_container_log_needs_a_container_that_exists(helper, project, monkeypatch):
    """A regex alone would still admit anything shaped like a name."""
    import subprocess as sp

    monkeypatch.setattr(
        sp, "run",
        lambda argv, **k: sp.CompletedProcess(argv, 0, stdout="nodered-caddy-1\n", stderr=""),
    )
    assert helper.main(["logs-container", "not-a-real-container"]) == 1


@pytest.mark.parametrize("name", ["", "-rm", "name with space", "$(id)", "../etc"])
def test_a_malformed_container_name_is_refused(helper, project, name):
    assert helper.main(["logs-container", name]) == 1


def test_names_is_a_read_only_verb(helper):
    assert "names" in helper.READ_ONLY_VERBS
    assert "names" in helper.DAEMON_VERBS
