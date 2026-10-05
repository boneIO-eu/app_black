"""The Disk section: the helper measures and cleans fixed places, the route adds the rest."""

from __future__ import annotations

import json
import subprocess
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import SimpleNamespace

import pytest

HELPER = Path(__file__).resolve().parents[3] / "boneio" / "migrations" / "assets" / "helpers" / "boneio-system"


@pytest.fixture(scope="module")
def helper():
    return SourceFileLoader("boneio_system_disk", str(HELPER)).load_module()


@pytest.fixture
def ran(helper, monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr(helper, "_run", lambda argv, timeout=30, tolerate=False: calls.append(argv) or 0)
    monkeypatch.setattr(helper, "_assert_root", lambda: None)
    return calls


@pytest.mark.parametrize(("target", "argv"), [
    ("docker", ["docker", "image", "prune", "-a", "-f"]),
    ("apt", ["apt-get", "clean"]),
])
def test_a_named_clean_up_runs_its_fixed_command(helper, ran, target, argv):
    assert helper.main(["disk-clean", target]) == 0
    assert ran == [argv]


@pytest.mark.parametrize("args", [["disk-clean", "/etc"], ["disk-clean"], ["disk-clean", "apt", "x"]])
def test_anything_else_is_refused(helper, ran, args):
    assert helper.main(args) == 1
    assert ran == []


def test_images_are_reported_in_bytes_with_whether_they_are_used(helper, monkeypatch, capsys):
    monkeypatch.setattr(helper, "_assert_root", lambda: None)
    out = {
        ("image", "ls"): "sha256:new\nsha256:old\n",
        ("ps", "-aq"): "c1\n",
        ("inspect", "--format"): "sha256:new\n",
        ("image", "inspect"): 'sha256:new 300000000 ["nodered/node-red:4.1.15-22-minimal"]\n'
                              'sha256:old 290000000 ["nodered/node-red:4.1.2-22-minimal"]\n',
    }

    def fake_run(argv, **kwargs):
        if argv[0] == "du":
            return SimpleNamespace(returncode=0, stdout=f"1234\t{argv[-1]}\n", stderr="")
        return SimpleNamespace(returncode=0, stdout=out[tuple(argv[1:3])], stderr="")

    monkeypatch.setattr(helper.subprocess, "run", fake_run)
    assert helper.main(["disk-usage"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["images"] == [
        {"tags": ["nodered/node-red:4.1.15-22-minimal"], "size": 300000000, "in_use": True},
        {"tags": ["nodered/node-red:4.1.2-22-minimal"], "size": 290000000, "in_use": False},
    ]
    assert report["journal"] == report["apt_cache"] == 1234


def test_no_docker_is_no_images_not_a_failure(helper, monkeypatch, capsys):
    monkeypatch.setattr(helper, "_assert_root", lambda: None)

    def fake_run(argv, **kwargs):
        if argv[0] == "docker":
            raise FileNotFoundError("docker")
        return SimpleNamespace(returncode=0, stdout="0\t/x\n", stderr="")

    monkeypatch.setattr(helper.subprocess, "run", fake_run)
    assert helper.main(["disk-usage"]) == 0
    assert json.loads(capsys.readouterr().out)["images"] is None


# ------------------------------------------------------------------- the route


async def test_the_route_adds_the_filesystem_and_the_backups(monkeypatch, tmp_path):
    from boneio.core import system_ops
    from boneio.webui.routes import diagnostics

    (tmp_path / "a.tar.gz").write_bytes(b"x" * 10)
    (tmp_path / "a.tar.gz.sha256").write_bytes(b"y" * 5)
    monkeypatch.setattr(diagnostics, "NODERED_BACKUP_DIR", str(tmp_path))
    monkeypatch.setattr(system_ops, "helper_supports", lambda verb: True)
    monkeypatch.setattr(
        system_ops, "disk_usage",
        lambda: system_ops.Result(0, json.dumps({"images": [], "journal": 1, "apt_cache": 2}), ""),
    )
    disk = await diagnostics.get_disk()
    assert disk["nodered_backups"] == {"size": 15, "count": 2}
    assert disk["root"]["total"] > 0
    assert disk["journal"] == 1 and disk["supported"]


async def test_an_old_helper_says_which_migration_is_missing(monkeypatch):
    from boneio.core import system_ops
    from boneio.webui.routes import diagnostics

    monkeypatch.setattr(system_ops, "helper_supports", lambda verb: False)
    disk = await diagnostics.get_disk()
    assert not disk["supported"] and "1.6.40" in disk["message"]
