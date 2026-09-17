"""Tests for the application's side of the container helper.

The property that matters here is that the helper is used whenever it is
available, and that the one operation which used to mean "write the compose
file" cannot fall back to doing that.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from boneio.core import containers


@pytest.fixture(autouse=True)
def _clear_cache():
    """The availability answer is cached per process."""
    containers._helper_available = None
    yield
    containers._helper_available = None


@pytest.fixture
def with_helper(monkeypatch):
    """A device where boneio-containers is installed and callable."""
    monkeypatch.setattr("os.path.isfile", lambda path: True)
    monkeypatch.setattr("os.access", lambda path, mode: True)
    calls: list[list[str]] = []

    def _run(argv, **kwargs):
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)
    return calls


@pytest.fixture
def without_helper(monkeypatch):
    """A device that has not applied the trust-transition migration yet."""
    monkeypatch.setattr("os.path.isfile", lambda path: False)
    calls: list[list[str]] = []

    def _run(argv, **kwargs):
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)
    return calls


# ------------------------------------------------------------- which path


def test_the_helper_is_used_when_available(with_helper):
    containers.restart_caddy()
    assert with_helper[-1] == ["sudo", "-n", containers.HELPER_PATH, "restart-caddy"]


def test_docker_is_used_directly_when_the_helper_is_absent(without_helper):
    """The transition, not a loophole: this device is as it is today."""
    result = containers.restart_caddy()
    assert result.via_helper is False
    assert without_helper[-1][:2] == ["docker", "compose"]


def test_availability_is_only_probed_once(with_helper):
    containers.status()
    containers.status()
    probes = [c for c in with_helper if "--list-verbs" in c]
    assert len(probes) == 1


def test_a_helper_that_refuses_to_list_verbs_is_not_used(monkeypatch):
    monkeypatch.setattr("os.path.isfile", lambda path: True)
    monkeypatch.setattr("os.access", lambda path, mode: True)
    monkeypatch.setattr(
        subprocess, "run",
        lambda argv, **k: subprocess.CompletedProcess(argv, 1, stdout="", stderr="no"),
    )
    assert containers.helper_available() is False


def test_a_helper_that_cannot_be_executed_is_not_used(monkeypatch):
    monkeypatch.setattr("os.path.isfile", lambda path: True)
    monkeypatch.setattr("os.access", lambda path, mode: True)

    def _explode(*args, **kwargs):
        raise OSError("no sudo")

    monkeypatch.setattr(subprocess, "run", _explode)
    assert containers.helper_available() is False


# ------------------------------------------------------- the compose file


def test_the_cloud_template_cannot_be_applied_without_the_helper(without_helper):
    """The fallback used to be "write the compose file from the application".

    That file is what `docker compose up` executes, so writing it was
    equivalent to being able to run a container as root. There is deliberately
    no fallback for it.
    """
    result = containers.apply_cloud_template()
    assert result.ok is False
    assert "not installed" in result.stderr
    assert not any("compose" in " ".join(c) for c in without_helper)


def test_the_cloud_template_goes_through_the_helper(with_helper):
    containers.apply_cloud_template()
    assert with_helper[-1] == [
        "sudo", "-n", containers.HELPER_PATH, "apply-cloud-template",
    ]


def test_removing_the_cloud_template_also_needs_the_helper(without_helper):
    assert containers.remove_cloud_template().ok is False


# ---------------------------------------------------------------- parity


def test_every_verb_has_a_fallback_or_is_helper_only(with_helper):
    """Otherwise a verb would silently do nothing on a pre-migration device."""
    from importlib.machinery import SourceFileLoader
    from pathlib import Path

    helper_path = (
        Path(containers.__file__).resolve().parents[1]
        / "migrations" / "assets" / "helpers" / "boneio-containers"
    )
    helper = SourceFileLoader("boneio_containers_ref", str(helper_path)).load_module()

    covered = (
        set(containers._FALLBACK)
        | set(containers._LOG_VERBS)
        | containers._HELPER_ONLY
        | containers._PARAMETERISED
    )
    missing = set(helper.ALL_VERBS) - covered
    assert not missing, f"verbs with no application-side handling: {sorted(missing)}"


def test_an_unknown_verb_is_a_programming_error(without_helper):
    with pytest.raises(ValueError, match="unknown container verb"):
        containers.run("rm-rf-everything")


# ---------------------------------------------------------------- results


def test_line_delimited_json_is_parsed(monkeypatch, with_helper):
    """Docker emits one JSON object per line for `ps --format json`."""
    monkeypatch.setattr(
        subprocess, "run",
        lambda argv, **k: subprocess.CompletedProcess(
            argv, 0, stdout='{"Name":"caddy"}\n{"Name":"node-red"}\n', stderr=""
        ),
    )
    parsed = containers.status().json()
    assert [item["Name"] for item in parsed] == ["caddy", "node-red"]


def test_a_single_json_document_is_parsed(monkeypatch, with_helper):
    monkeypatch.setattr(
        subprocess, "run",
        lambda argv, **k: subprocess.CompletedProcess(
            argv, 0, stdout=json.dumps([{"Name": "caddy"}]), stderr=""
        ),
    )
    assert containers.status().json() == [{"Name": "caddy"}]


def test_non_json_output_is_not_a_crash(monkeypatch, with_helper):
    monkeypatch.setattr(
        subprocess, "run",
        lambda argv, **k: subprocess.CompletedProcess(
            argv, 0, stdout="Cannot connect to the Docker daemon", stderr=""
        ),
    )
    assert containers.status().json() is None


def test_a_timeout_is_a_failure_not_an_exception(monkeypatch, with_helper):
    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="docker", timeout=1)

    monkeypatch.setattr(subprocess, "run", _timeout)
    result = containers.restart_caddy()
    assert result.ok is False
    assert "timed out" in result.stderr


def test_logs_take_a_line_count(with_helper):
    containers.logs(containers.NODERED_SERVICE, lines=50)
    assert with_helper[-1][-2:] == ["logs-nodered", "50"]


def test_logs_for_an_unknown_service_is_a_programming_error(with_helper):
    with pytest.raises(ValueError, match="no log verb"):
        containers.logs("postgres")


# -------------------------------------------------------- one service at a time


def test_a_single_service_is_picked_out_of_the_project(monkeypatch, with_helper):
    monkeypatch.setattr(
        subprocess, "run",
        lambda argv, **k: subprocess.CompletedProcess(
            argv, 0,
            stdout='{"Service":"caddy","State":"running"}\n'
                   '{"Service":"node-red","State":"exited"}\n',
            stderr="",
        ),
    )
    assert containers.service_status("caddy")["State"] == "running"
    assert containers.service_status("node-red")["State"] == "exited"


def test_a_service_that_is_not_there_is_none(monkeypatch, with_helper):
    monkeypatch.setattr(
        subprocess, "run",
        lambda argv, **k: subprocess.CompletedProcess(
            argv, 0, stdout='{"Service":"caddy","State":"running"}', stderr=""
        ),
    )
    assert containers.service_status("node-red") is None


def test_unreadable_status_is_none_not_a_crash(monkeypatch, with_helper):
    monkeypatch.setattr(
        subprocess, "run",
        lambda argv, **k: subprocess.CompletedProcess(
            argv, 1, stdout="Cannot connect to the Docker daemon", stderr="boom"
        ),
    )
    assert containers.service_status("caddy") is None


# ------------------------------------------------------- nobody else talks to docker


def test_only_this_module_invokes_docker():  # noqa: C901
    """The point of the exercise, as a property of the tree.

    If another module grows a `docker` call it bypasses the helper, and on a
    device where the account has left the docker group it simply stops working —
    silently, in whatever feature that module serves.
    """
    import re
    from pathlib import Path

    root = Path(containers.__file__).resolve().parents[1]
    allowed = {
        root / "core" / "containers.py",
        # The helper itself, which is what actually runs docker as root.
        root / "migrations" / "assets" / "helpers" / "boneio-containers",
    }
    offenders = []
    for path in root.rglob("*.py"):
        if path in allowed or "frontend-dist" in str(path):
            continue
        # An invocation puts "docker" first in an argument list. A bare
        # "docker" also appears as a filesystem path, a systemd unit name and
        # a shutil.which() probe — none of which goes near the daemon.
        invocation = re.compile(r"""[\[\(]\s*["']docker["']""")
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
        ):
            if "which(" in line:
                continue
            if invocation.search(line):
                offenders.append(f"{path.relative_to(root)}:{number}: {line.strip()}")
                break
    assert not offenders, (
        "these modules invoke docker directly instead of going through "
        f"boneio.core.containers: {offenders}"
    )


def test_container_names_are_read_from_docker(monkeypatch, with_helper):
    """Compose prefixes names with the project, so they cannot be guessed."""
    monkeypatch.setattr(
        subprocess, "run",
        lambda argv, **k: subprocess.CompletedProcess(
            argv, 0, stdout="nodered-caddy-1\nnodered-node-red-1\n", stderr=""
        ),
    )
    assert containers.container_names() == ["nodered-caddy-1", "nodered-node-red-1"]


def test_unavailable_docker_gives_no_names_rather_than_an_error(
    monkeypatch, with_helper
):
    monkeypatch.setattr(
        subprocess, "run",
        lambda argv, **k: subprocess.CompletedProcess(argv, 1, stdout="", stderr="no"),
    )
    assert containers.container_names() == []


def test_container_logs_pass_the_name_to_the_helper(with_helper):
    containers.container_logs("nodered-caddy-1")
    assert with_helper[-1][-2:] == ["logs-container", "nodered-caddy-1"]


def test_container_logs_need_a_name(without_helper):
    with pytest.raises(ValueError, match="needs a container name"):
        containers.run("logs-container")
