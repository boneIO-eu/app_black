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
    etc = tmp_path / "etc-boneio"
    etc.mkdir()
    monkeypatch.setattr(helper, "NATIVE_MARKER", etc / "proxy-native")
    monkeypatch.setattr(helper, "CLOUD_MARKER", etc / "proxy-cloud")
    monkeypatch.setattr(helper, "PROXY_LOCK", tmp_path / "boneio-proxy.lock")
    monkeypatch.setattr(helper, "CADDY_DATA", tmp_path / "caddy-data")
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


@pytest.mark.parametrize("argument", ["0", "99999", "-1", "10; id", "abc", "1e3", "²", "٣"])
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


# ---------------------------------------------------------------------- Caddy
#
# Which Caddy runs is the release's decision, carried in a root-owned template.
# So the tests are about the caller having no say, and about the one line.

PINNED = "caddy:2.11.4-alpine@sha256:" + "a" * 64


@pytest.fixture
def pinned(project, helper):
    """A template that pins Caddy, as a release installs it."""
    template = helper.COMPOSE_TEMPLATE
    template.write_text(f"services:\n  caddy:\n    image: {PINNED}\n")
    os.chmod(template, 0o644)
    return template


def test_the_state_reports_pinned_and_configured(helper, pinned, capsys):
    assert helper.main(["caddy-image-state"]) == 0
    state = json.loads(capsys.readouterr().out)
    assert state == {"pinned": PINNED, "configured": "caddy:2-alpine", "update_available": True}


def test_apply_changes_only_the_caddy_line_then_pulls_and_recreates_caddy(
    helper, pinned, project, ran
):
    compose = project / "docker-compose.yaml"
    before = compose.read_text().splitlines()
    assert helper.main(["caddy-image-apply"]) == 0
    after = compose.read_text().splitlines()
    changed = [(a, b) for a, b in zip(before, after) if a != b]
    assert changed == [("    image: caddy:2-alpine", f"    image: {PINNED}")]
    assert ran == [
        ["docker", "compose", "-f", str(compose), "pull", "caddy"],
        ["docker", "compose", "-f", str(compose), "up", "-d", "caddy"],
    ]


@pytest.mark.parametrize("argument", ["caddy:latest", "2.11.4-alpine", "x"])
def test_the_caller_cannot_choose_the_caddy_image(helper, pinned, project, ran, argument):
    assert helper.main(["caddy-image-apply", argument]) == 1
    assert ran == []
    assert "caddy:2-alpine" in (project / "docker-compose.yaml").read_text()


@pytest.mark.parametrize("image", [
    "caddy:latest; rm -rf /",
    "caddy:2-alpine@sha256:short",
    "evil/caddy:2",
    "caddy:",
])
def test_a_template_pinning_something_odd_is_refused(helper, project, ran, image):
    template = helper.COMPOSE_TEMPLATE
    template.write_text(f"services:\n  caddy:\n    image: {image}\n")
    assert helper.main(["caddy-image-apply"]) == 1
    assert ran == []


def test_a_template_the_application_could_write_is_refused(helper, pinned, project, ran):
    os.chmod(pinned, 0o666)
    assert helper.main(["caddy-image-apply"]) == 1
    assert ran == []


def test_the_shipped_templates_pin_caddy_by_digest(helper):
    """caddy:2-alpine meant something different on every controller."""
    for name in ("docker-compose.yaml", "docker-compose-cloud.yaml"):
        text = (REPO_ROOT / "boneio" / "migrations" / "assets" / "docker" / "nodered" / name).read_text()
        match = helper._CADDY_IMAGE_RE.search(text)
        assert match, name
        assert "@sha256:" in match.group("image"), name
        assert helper._PINNED_CADDY_RE.match(match.group("image")), name
    package = (REPO_ROOT / "boneio" / "core" / "cloud" / "data" / "docker-compose.yaml").read_text()
    assert helper._CADDY_IMAGE_RE.search(package).group("image") == match.group("image")


@pytest.mark.parametrize(("verb", "timeout"), [
    ("pull-nodered", 900), ("pull", 900), ("restart-caddy", 120),
])
def test_an_image_pull_gets_minutes_not_the_default(helper, project, monkeypatch, verb, timeout):
    """A Node-RED pull on a BeagleBone outlasts 120 s and was cut off."""
    seen: list[int] = []
    monkeypatch.setattr(helper, "_run", lambda argv, timeout=120: seen.append(timeout) or 0)
    assert helper.main([verb]) == 0
    assert seen == [timeout]


# ------------------------------------------------------------ packaged Caddy
#
# With /etc/boneio/proxy-native present, Caddy is the apt package under
# systemd. The verbs keep their names so the application does not change, and
# none of them may reach compose: there is no caddy service there any more.

CERT = b"-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"


@pytest.fixture
def native(project, helper):
    """The marker the switch leaves behind."""
    helper.NATIVE_MARKER.touch()
    return helper.NATIVE_MARKER


@pytest.fixture
def asked(helper, monkeypatch):
    """Answers for what the native verbs ask the system, and a record of it."""
    answers = {
        "systemctl": (0, "active\n"),
        "dpkg-query": (0, "installed 2.10.2-1"),
        "apt-cache": (
            0, "caddy:\n  Installed: 2.10.2-1\n  Candidate: 2.10.3-1\n  Version table:\n"
        ),
        "docker": (0, ""),
    }
    calls: list[list[str]] = []

    def _fake(argv, timeout=30):
        calls.append(list(argv))
        return answers[argv[0]]

    monkeypatch.setattr(helper, "_capture", _fake)
    return answers, calls


@pytest.mark.parametrize(("verb", "action"), [
    ("start-caddy", "start"), ("restart-caddy", "restart"), ("reload-caddy", "reload"),
])
def test_native_lifecycle_verbs_drive_the_unit(helper, native, ran, verb, action):
    assert helper.main([verb]) == 0
    assert ran == [["systemctl", action, "caddy"]]


def test_native_caddy_log_comes_from_the_journal(helper, native, ran):
    assert helper.main(["logs-caddy", "50"]) == 0
    assert ran == [["journalctl", "-u", "caddy", "-n", "50", "--no-pager", "-o", "short-iso"]]


def test_native_caddy_log_still_checks_the_line_count(helper, native, ran):
    assert helper.main(["logs-caddy", "10; id"]) == 1
    assert ran == []


def test_native_cloud_template_sets_the_marker_and_reloads(helper, native, project, ran):
    before = (project / "docker-compose.yaml").read_bytes()
    assert helper.main(["apply-cloud-template"]) == 0
    assert helper.CLOUD_MARKER.is_file()
    assert helper.CLOUD_MARKER.stat().st_mode & 0o777 == 0o644
    assert ran == [["systemctl", "reload", "caddy"]]
    assert (project / "docker-compose.yaml").read_bytes() == before


def test_native_cloud_template_still_takes_no_argument(helper, native, ran):
    assert helper.main(["apply-cloud-template", "boneio.example.com"]) == 1
    assert not helper.CLOUD_MARKER.exists()
    assert ran == []


def test_native_cloud_template_removal_clears_the_marker_and_reloads(helper, native, ran):
    helper.CLOUD_MARKER.touch()
    assert helper.main(["remove-cloud-template"]) == 0
    assert not helper.CLOUD_MARKER.exists()
    assert ran == [["systemctl", "reload", "caddy"]]


def test_native_cloud_template_removal_without_a_marker_is_fine(helper, native, ran):
    assert helper.main(["remove-cloud-template"]) == 0
    assert ran == [["systemctl", "reload", "caddy"]]


def test_native_image_state_reports_the_package(helper, native, asked, capsys):
    """The template pins no Caddy any more; that must not make this refuse."""
    assert helper.main(["caddy-image-state"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "mode": "native", "installed": "2.10.2-1", "candidate": "2.10.3-1",
    }


def test_native_image_state_without_the_package(helper, native, asked, capsys):
    answers, _ = asked
    answers["dpkg-query"] = (1, "")
    answers["apt-cache"] = (0, "caddy:\n  Installed: (none)\n  Candidate: (none)\n")
    assert helper.main(["caddy-image-state"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "mode": "native", "installed": None, "candidate": None,
    }


def test_native_image_state_ignores_a_removed_package(helper, native, asked, capsys):
    """``rc``: removed, configuration kept — dpkg still knows a version."""
    answers, _ = asked
    answers["dpkg-query"] = (0, "config-files 2.10.2-1")
    assert helper.main(["caddy-image-state"]) == 0
    assert json.loads(capsys.readouterr().out)["installed"] is None


def test_native_dispatch_does_not_fall_through_to_the_root_ca(
    helper, native, capsysbinary
):
    """A Caddy verb the native mode does not handle is refused, not the CA."""
    _root_native(helper).parent.mkdir(parents=True)
    _root_native(helper).write_bytes(CERT)
    with pytest.raises(helper.Refused):
        helper._native_caddy("some-future-caddy-verb", None)
    assert capsysbinary.readouterr().out == b""


def test_native_image_apply_is_refused(helper, native, ran, caplog):
    assert helper.main(["caddy-image-apply"]) == 1
    assert ran == []
    assert "Caddy is pinned by boneIO; it updates with boneIO" in caplog.text


# --------------------------------------------------------------- root CA


def _root_in_container(helper) -> Path:
    return helper.PROJECT_DIR / "caddy/data/caddy/pki/authorities/local/root.crt"


def _root_native(helper) -> Path:
    return helper.CADDY_DATA / "pki/authorities/local/root.crt"


@pytest.mark.parametrize("mode", ["container", "native"])
def test_the_root_ca_is_printed_in_both_modes(helper, project, capsysbinary, mode):
    if mode == "native":
        helper.NATIVE_MARKER.touch()
        path = _root_native(helper)
    else:
        path = _root_in_container(helper)
    path.parent.mkdir(parents=True)
    path.write_bytes(CERT)
    assert helper.main(["caddy-root-ca"]) == 0
    assert capsysbinary.readouterr().out == CERT


def test_native_root_ca_is_read_from_caddys_data_not_the_export(helper, native, capsysbinary):
    """The export lags until Caddy's second start; its own copy does not."""
    assert helper.main(["caddy-root-ca"]) == 1
    _root_native(helper).parent.mkdir(parents=True)
    _root_native(helper).write_bytes(CERT)
    assert helper.main(["caddy-root-ca"]) == 0


def test_a_root_ca_symlink_is_not_followed(helper, project, tmp_path, capsysbinary):
    secret = tmp_path / "secret.pem"
    secret.write_bytes(CERT)
    path = _root_in_container(helper)
    path.parent.mkdir(parents=True)
    path.symlink_to(secret)
    assert helper.main(["caddy-root-ca"]) == 1
    assert capsysbinary.readouterr().out == b""


def test_a_root_ca_directory_symlink_is_not_followed(helper, project, tmp_path, capsysbinary):
    """O_NOFOLLOW on the last component alone would let this through."""
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "local").mkdir(parents=True)
    (elsewhere / "local" / "root.crt").write_bytes(CERT)
    path = _root_in_container(helper)
    path.parent.parent.mkdir(parents=True)
    path.parent.symlink_to(elsewhere / "local")
    assert helper.main(["caddy-root-ca"]) == 1
    assert capsysbinary.readouterr().out == b""


@pytest.mark.parametrize("content", [
    b"root:x:0:0:root:/root:/bin/bash\n",
    CERT + b"-----BEGIN PRIVATE KEY-----\nMIIE\n-----END PRIVATE KEY-----\n",
    CERT + b"A" * (64 * 1024),
])
def test_a_root_ca_that_is_not_just_a_certificate_is_refused(
    helper, project, capsysbinary, content
):
    path = _root_in_container(helper)
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    assert helper.main(["caddy-root-ca"]) == 1
    assert capsysbinary.readouterr().out == b""


def test_the_root_ca_takes_no_argument(helper, project):
    assert helper.main(["caddy-root-ca", "/etc/shadow"]) == 1


def test_the_root_ca_is_listed_and_read_only(helper):
    assert "caddy-root-ca" in helper.ALL_VERBS
    assert "caddy-root-ca" in helper.READ_ONLY_VERBS


# ------------------------------------------------- the app sees a "caddy" anyway


def _app_result(out: str):
    from boneio.core.containers import Result

    return Result(returncode=0, stdout=out, stderr="", via_helper=True)


@pytest.mark.parametrize("docker_out", [
    '{"Service": "node-red", "Name": "nodered-node-red-1", "State": "running"}\n',
    '[{"Service": "node-red", "Name": "nodered-node-red-1", "State": "running"}]\n',
    "",
])
def test_native_status_lists_a_virtual_caddy(helper, native, asked, capsys, docker_out):
    """containers.service_status("caddy") matches on Service, as for compose."""
    answers, _ = asked
    answers["docker"] = (0, docker_out)
    assert helper.main(["status"]) == 0
    items = _app_result(capsys.readouterr().out).json()
    items = items if isinstance(items, list) else [items]
    by_service = {item.get("Service"): item for item in items}
    assert by_service["caddy"]["State"] == "running"
    if docker_out:
        assert by_service["node-red"]["State"] == "running"


def test_native_status_reports_a_stopped_caddy(helper, native, asked, capsys):
    answers, _ = asked
    answers["systemctl"] = (3, "failed\n")
    assert helper.main(["status"]) == 0
    caddy = _app_result(capsys.readouterr().out).json()
    assert caddy["State"] != "running"
    assert "failed" in caddy["Status"]


def test_native_ps_and_names_list_caddy(helper, native, asked, capsys):
    answers, _ = asked
    answers["docker"] = (0, "nodered-node-red-1\n")
    assert helper.main(["names"]) == 0
    assert capsys.readouterr().out.split() == ["nodered-node-red-1", "caddy"]
    answers["docker"] = (0, '{"Names": "nodered-node-red-1", "State": "running"}\n')
    assert helper.main(["ps"]) == 0
    names = [i["Names"] for i in _app_result(capsys.readouterr().out).json()]
    assert names == ["nodered-node-red-1", "caddy"]


def test_container_status_has_no_virtual_caddy(helper, project, ran):
    assert helper.main(["status"]) == 0
    assert ran == [helper._argv_for("status")]


def test_native_caddy_container_log_comes_from_the_journal(helper, native, ran):
    """Diagnostics asks for a log of every name ``names`` returned."""
    assert helper.main(["logs-container", "caddy"]) == 0
    assert ran == [["journalctl", "-u", "caddy", "-n", "200", "--no-pager", "-o", "short-iso"]]


CADDY_VERBS = [
    ["start-caddy"], ["restart-caddy"], ["reload-caddy"], ["logs-caddy", "20"],
    ["apply-cloud-template"], ["remove-cloud-template"], ["caddy-image-state"],
    ["caddy-image-apply"], ["caddy-root-ca"], ["logs-container", "caddy"],
]


@pytest.mark.parametrize("argv", CADDY_VERBS, ids=lambda a: a[0])
def test_native_mode_never_touches_compose_for_caddy(
    helper, native, project, asked, monkeypatch, argv
):
    _, calls = asked
    monkeypatch.setattr(helper, "_run", lambda a, timeout=120: calls.append(list(a)) or 0)
    monkeypatch.setattr(
        helper.subprocess, "run",
        lambda a, **k: calls.append(list(a)) or helper.subprocess.CompletedProcess(a, 0, "", ""),
    )
    before = (project / "docker-compose.yaml").read_bytes()
    helper.main(argv)
    assert not [c for c in calls if c[0] == "docker"], calls
    assert (project / "docker-compose.yaml").read_bytes() == before


# ------------------------------------------------------------------ the lock


@pytest.fixture
def held_lock(helper, project, monkeypatch):
    """The switch holding the proxy lock (a second open file description
    conflicts exactly as another process would)."""
    import fcntl

    monkeypatch.setattr(helper, "PROXY_LOCK_TIMEOUT", 0.1)
    fd = os.open(helper.PROXY_LOCK, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    yield fd
    os.close(fd)


@pytest.mark.parametrize("mode", ["container", "native"])
@pytest.mark.parametrize("argv", CADDY_VERBS[:-1] + [["up"], ["down"], ["set-nodered-image", "4.2.0"]], ids=lambda a: a[0])
def test_caddy_verbs_wait_for_the_switch_lock(
    helper, held_lock, asked, ran, caplog, mode, argv
):
    if mode == "native":
        helper.NATIVE_MARKER.touch()
    assert helper.main(argv) == 1
    assert ran == []
    assert "boneio-proxy.lock" in caplog.text


def test_the_lock_is_released_after_a_verb(helper, native, ran):
    assert helper.main(["reload-caddy"]) == 0
    assert helper.main(["reload-caddy"]) == 0
    assert len(ran) == 2


@pytest.mark.parametrize("verb", ["status", "ps", "names", "pull"])
def test_status_and_pull_do_not_wait_for_the_lock(helper, held_lock, ran, verb):
    """The switch holds it through an apt install; the UI must still answer."""
    assert helper.main([verb]) == 0


def test_the_lock_lives_where_only_root_can_create_it(helper):
    """/run/lock is world-writable: anyone could create it first and hold it."""
    assert str(helper.PROXY_LOCK) == "/run/boneio-proxy.lock"


def test_the_lock_wait_is_shorter_than_the_apps_timeout(helper):
    assert helper.PROXY_LOCK_TIMEOUT < 30


def test_a_symlinked_lock_file_is_refused(helper, project, ran, tmp_path):
    """Root must not create or lock a file a link points to."""
    target = tmp_path / "planted"
    helper.PROXY_LOCK.symlink_to(target)
    assert helper.main(["reload-caddy"]) == 1
    assert ran == []
    assert not target.exists()


def test_selftest_in_native_mode_wants_the_packaged_caddy(helper, native, monkeypatch, caplog):
    monkeypatch.setattr(
        helper.shutil, "which", lambda name: None if name == "caddy" else f"/usr/bin/{name}"
    )
    assert helper.selftest() == 1
    assert "caddy" in caplog.text
