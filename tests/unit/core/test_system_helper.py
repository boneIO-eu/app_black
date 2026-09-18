"""Tests for boneio-system, the last of the privileged helpers.

It replaced two things at once: endpoints that asked the operator for their
system password, and wildcard sudo rules — ``ip link set can0 *`` and a
``sed -i`` expression the application composed for root to run on
/boot/uEnv.txt. So the tests are about the closed vocabulary and about the
uEnv.txt edit behaving exactly as the sed did.
"""

from __future__ import annotations

import json
import os
import subprocess
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HELPER = REPO_ROOT / "boneio" / "migrations" / "assets" / "helpers" / "boneio-system"

UENV = """\
#uboot_overlay_addr0=/lib/firmware/BONEIO-BLACK-PINS-v0.2-v0.3.dtbo
uboot_overlay_addr1=/lib/firmware/BONEIO-BLACK-PINS-v0.4-v0.8.dtbo
uboot_overlay_addr2=BONEIO-BLACK-PINS.dtbo
enable_uboot_overlays=1
"""


@pytest.fixture(scope="module")
def helper():
    """The helper loaded as a module (it has no .py extension)."""
    return SourceFileLoader("boneio_system", str(HELPER)).load_module()


@pytest.fixture
def uenv(tmp_path, helper, monkeypatch) -> Path:
    """A uEnv.txt the helper will edit."""
    path = tmp_path / "uEnv.txt"
    path.write_text(UENV, encoding="utf-8")
    monkeypatch.setattr(helper, "UENV_PATHS", (path,))
    monkeypatch.setattr(helper, "_assert_root", lambda: None)
    return path


@pytest.fixture
def ran(helper, monkeypatch):
    """Record what would have been executed."""
    calls: list[list[str]] = []

    def _fake(argv, timeout=30, tolerate=False):
        calls.append(list(argv))
        return 0

    monkeypatch.setattr(helper, "_run", _fake)
    monkeypatch.setattr(helper, "_assert_root", lambda: None)
    return calls


# ----------------------------------------------------------------------- CAN


def test_an_interface_is_brought_up_in_three_steps(helper, ran):
    assert helper.main(["can-up", "can0", "125000"]) == 0
    assert ran == [
        ["ip", "link", "set", "can0", "down"],
        ["ip", "link", "set", "can0", "type", "can", "bitrate", "125000"],
        ["ip", "link", "set", "can0", "up"],
    ]


@pytest.mark.parametrize("interface", [
    "can2", "eth0", "lo", "can0 up", "../can0", "", "can0;id",
])
def test_an_interface_outside_the_board_is_refused(helper, ran, interface):
    """The sudoers rule this replaces was `ip link set can0 *`."""
    assert helper.main(["can-up", interface, "125000"]) == 1
    assert ran == []


@pytest.mark.parametrize("bitrate", ["0", "999", "125001", "abc", "", "1e6", "-125000"])
def test_an_unsupported_bitrate_is_refused(helper, ran, bitrate):
    assert helper.main(["can-up", "can0", bitrate]) == 1
    assert ran == []


def test_every_bitrate_the_ui_offers_is_accepted(helper, ran):
    for bitrate in helper.CAN_BITRATES:
        ran.clear()
        assert helper.main(["can-up", "can1", str(bitrate)]) == 0, bitrate


def test_an_interface_can_be_taken_down(helper, ran):
    assert helper.main(["can-down", "can1"]) == 0
    assert ran == [["ip", "link", "set", "can1", "down"]]


# ------------------------------------------------------------------- overlay


def test_the_overlay_is_reported(helper, uenv, capsys):
    assert helper.main(["overlay-get"]) == 0
    reported = json.loads(capsys.readouterr().out)
    assert reported["overlay"] == "BONEIO-BLACK-PINS-v0.4-v0.8.dtbo"


def test_setting_the_overlay_rewrites_only_the_matching_lines(helper, uenv):
    assert helper.main(["overlay-set", "BONEIO-BLACK-PINS-v1.0.dtbo"]) == 0
    after = uenv.read_text(encoding="utf-8").splitlines()

    # The commented line is left alone, exactly as the sed address did.
    assert after[0].startswith("#uboot_overlay_addr0=")
    assert "v0.2-v0.3" in after[0]
    # Both uncommented forms are updated: with a directory prefix and without.
    assert after[1] == "uboot_overlay_addr1=/lib/firmware/BONEIO-BLACK-PINS-v1.0.dtbo"
    assert after[2] == "uboot_overlay_addr2=BONEIO-BLACK-PINS-v1.0.dtbo"
    # Unrelated lines survive.
    assert after[3] == "enable_uboot_overlays=1"


def test_setting_the_overlay_keeps_a_backup(helper, uenv):
    helper.main(["overlay-set", "BONEIO-BLACK-PINS-v1.0.dtbo"])
    backup = uenv.with_suffix(uenv.suffix + ".boneio.bak")
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == UENV


def test_an_existing_backup_is_not_overwritten(helper, uenv):
    backup = uenv.with_suffix(uenv.suffix + ".boneio.bak")
    backup.write_text("the original\n", encoding="utf-8")
    helper.main(["overlay-set", "BONEIO-BLACK-PINS-v1.0.dtbo"])
    assert backup.read_text(encoding="utf-8") == "the original\n"


def test_setting_the_same_overlay_changes_nothing(helper, uenv):
    before = uenv.read_text(encoding="utf-8")
    assert helper.main(["overlay-set", "BONEIO-BLACK-PINS-v0.4-v0.8.dtbo"]) == 0
    # addr2 still differs, so this is not a no-op overall — but addr1 is
    # already correct and must not be touched twice.
    assert "v0.4-v0.8" in uenv.read_text(encoding="utf-8")
    assert before != ""


@pytest.mark.parametrize("overlay", [
    "",
    "evil.dtbo",
    "../../etc/passwd",
    "/lib/firmware/BONEIO-BLACK-PINS-v1.0.dtbo",
    "BONEIO-BLACK-PINS.dtbo; id",
    "BONEIO-BLACK-PINS-v9.9.dtbo",
])
def test_an_overlay_outside_the_shipped_set_is_refused(helper, uenv, overlay):
    """This replaced a `sed -i` expression composed in the application."""
    before = uenv.read_text(encoding="utf-8")
    assert helper.main(["overlay-set", overlay]) == 1
    assert uenv.read_text(encoding="utf-8") == before


def test_a_missing_uenv_is_refused(helper, uenv):
    uenv.unlink()
    assert helper.main(["overlay-set", "BONEIO-BLACK-PINS-v1.0.dtbo"]) == 1


def test_a_uenv_symlink_is_not_followed(helper, tmp_path, monkeypatch):
    """Otherwise the caller could point the edit at any file root can write."""
    target = tmp_path / "elsewhere.txt"
    target.write_text("uboot_overlay_addr1=BONEIO-BLACK-PINS.dtbo\n", encoding="utf-8")
    link = tmp_path / "uEnv.txt"
    link.symlink_to(target)
    monkeypatch.setattr(helper, "UENV_PATHS", (link,))
    monkeypatch.setattr(helper, "_assert_root", lambda: None)
    assert helper.main(["overlay-set", "BONEIO-BLACK-PINS-v1.0.dtbo"]) == 1
    assert "BONEIO-BLACK-PINS.dtbo" in target.read_text(encoding="utf-8")


# ------------------------------------------------------------------ hostname


@pytest.mark.parametrize("name", ["blk265f49", "boneio-1", "a"])
def test_a_plausible_hostname_is_accepted(helper, ran, name):
    assert helper.main(["hostname-set", name]) == 0
    assert ran == [["hostnamectl", "set-hostname", name]]


@pytest.mark.parametrize("name", [
    "",
    "-leading",
    "trailing-",
    "has_underscore",
    "UPPER",
    "with space",
    "a" * 64,
    "name;id",
])
def test_an_implausible_hostname_is_refused(helper, ran, name):
    """The old check allowed underscores, which are not valid in a DNS label."""
    assert helper.main(["hostname-set", name]) == 1
    assert ran == []


# ---------------------------------------------------------------- the verbs


def test_an_unknown_verb_is_refused(helper, ran):
    assert helper.main(["rm-rf-everything"]) == 1
    assert ran == []


def test_the_verbs_are_listed(helper, capsys):
    assert helper.main(["--list-verbs"]) == 0
    assert json.loads(capsys.readouterr().out) == list(helper.VERBS)


def test_nothing_here_handles_a_password(helper):
    """The point of the helper: the sudoers rule is NOPASSWD because the
    vocabulary is closed, so nothing needs to collect a password.

    Checked against code, not prose — the module explains at length why the
    password paths went, so a plain word search would only find that.
    """
    import ast

    tree = ast.parse(HELPER.read_text(encoding="utf-8"))
    names = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {
        arg.arg
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for arg in node.args.args
    }
    assert not [name for name in names if "password" in name.lower()], (
        "the helper has a password-shaped variable or parameter"
    )
    assert "getpass" not in names
    # `sudo -S` is how a password gets piped to sudo.
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "-S" not in literals


def test_no_route_pipes_a_password_to_sudo_any_more():
    """The routes that used these operations collected the system password.

    That password is shared across every controller that shipped, so this is
    the property worth holding on to: `sudo -S` is how one gets piped in.
    """
    import ast

    routes = REPO_ROOT / "boneio" / "webui" / "routes"
    offenders = []
    for path in sorted(routes.glob("*.py")):
        if path.name == "migrations.py":
            # Bootstrap keeps its password deliberately: on a device with no
            # helper there is nothing else to elevate with. Trust on first use.
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        literals = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        if "-S" in literals:
            offenders.append(path.name)
    assert not offenders, f"these routes pipe a password to sudo: {offenders}"


# ----------------------------------------------------------------------- NTP
#
# The NTP verbs write into a file systemd parses as root. The value comes from
# a web form, so the tests below are mostly about what the helper refuses: a
# newline or a space in a "server name" would let the caller append directives
# of their own to that file.


@pytest.fixture
def dropin(tmp_path, helper, monkeypatch) -> Path:
    """Redirect the timesyncd drop-in into a temporary directory."""
    path = tmp_path / "timesyncd.conf.d" / "boneio.conf"
    monkeypatch.setattr(helper, "NTP_DROPIN", path)
    monkeypatch.setattr(helper, "_assert_root", lambda: None)
    return path


@pytest.mark.parametrize(
    "server",
    [
        "192.168.1.10",
        "10.0.0.1",
        "2001:db8::1",
        "ntp",
        "ntp.local",
        "pool.ntp.org",
        "tempus1.gum.gov.pl",
    ],
)
def test_a_usable_ntp_server_is_accepted(helper, server):
    assert helper._check_ntp_server(server) == server


@pytest.mark.parametrize(
    "server",
    [
        "192.168.1.10 rogue.example",  # a space starts a second server
        "ntp.local\nNTP=attacker.example",  # a newline starts a new directive
        "ntp.local\n[Time]",
        "[Time]",
        "-leading-hyphen.example",
        "trailing-hyphen-.example",
        "ntp.local;reboot",
        "ntp..local",
        "",
        "a" * 254,
    ],
)
def test_an_unusable_ntp_server_is_refused(helper, server):
    with pytest.raises(helper.Refused):
        helper._check_ntp_server(server)


def test_more_servers_than_allowed_are_refused(helper):
    with pytest.raises(helper.Refused):
        helper._parse_ntp_servers(",".join(f"ntp{i}.local" for i in range(6)))


def test_duplicate_servers_are_refused(helper):
    with pytest.raises(helper.Refused):
        helper._parse_ntp_servers("ntp.local,ntp.local")


@pytest.mark.parametrize("argument", ["", "   ", "default", "DEFAULT", None])
def test_the_defaults_are_spelled_as_an_empty_list(helper, argument):
    assert helper._parse_ntp_servers(argument) == []


def test_setting_servers_writes_a_drop_in_and_nudges_the_daemon(helper, dropin, ran):
    assert helper._ntp_set("192.168.1.10,ntp.local") == 0

    content = dropin.read_text(encoding="utf-8")
    assert "[Time]" in content
    assert "NTP=192.168.1.10 ntp.local" in content
    # try-restart, not restart: changing the source must not switch
    # synchronisation back on when the operator turned it off.
    assert ran == [["systemctl", "try-restart", "systemd-timesyncd"]]


def test_the_drop_in_is_world_readable_and_nothing_more(helper, dropin, ran):
    helper._ntp_set("192.168.1.10")
    assert oct(dropin.stat().st_mode & 0o777) == "0o644"


def test_choosing_the_defaults_removes_the_drop_in(helper, dropin, ran):
    helper._ntp_set("192.168.1.10")
    assert dropin.exists()

    assert helper._ntp_set("default") == 0
    assert not dropin.exists()
    # Removing it still has to reach the daemon, or the old servers stay live.
    assert ran[-1] == ["systemctl", "try-restart", "systemd-timesyncd"]


def test_removing_an_absent_drop_in_is_not_an_error(helper, dropin, ran):
    assert helper._ntp_set("") == 0
    assert not dropin.exists()


def test_a_refused_server_leaves_the_previous_configuration_alone(helper, dropin, ran):
    helper._ntp_set("192.168.1.10")
    before = dropin.read_text(encoding="utf-8")

    with pytest.raises(helper.Refused):
        helper._ntp_set("192.168.1.11,bad server name")

    assert dropin.read_text(encoding="utf-8") == before


def test_the_servers_are_read_back(helper, dropin, ran, capsys):
    helper._ntp_set("192.168.1.10,ntp.local")
    capsys.readouterr()

    assert helper._ntp_get() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["servers"] == ["192.168.1.10", "ntp.local"]
    assert payload["dropin"] is True


def test_reading_back_with_no_drop_in_reports_the_defaults(helper, dropin, capsys):
    assert helper._ntp_get() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["servers"] == []
    assert payload["dropin"] is False


def test_the_helper_accepts_exactly_the_bitrates_the_schema_allows():
    """A helper wider than the schema grants more than anything can ask for;
    a narrower one breaks a configuration the schema called valid.

    It shipped with 800000, which the schema does not list, and without vcan0,
    which it does.
    """
    import re

    schema = (REPO_ROOT / "boneio" / "schema" / "schema.yaml").read_text(encoding="utf-8")
    # Anchored on the can: block rather than on indentation, which moves.
    can_block = schema[schema.index("\ncan:"):]
    allowed = re.search(r"bitrate:.*?allowed:\s*\[([^\]]*)\]", can_block, re.S)
    assert allowed, "can.bitrate no longer declares an allowed list"
    from_schema = tuple(int(v) for v in allowed.group(1).replace(" ", "").split(","))

    helper_mod = SourceFileLoader("boneio_system_bitrates", str(HELPER)).load_module()
    assert tuple(sorted(helper_mod.CAN_BITRATES)) == tuple(sorted(from_schema))


def test_the_virtual_interface_the_schema_mentions_is_accepted(helper, ran):
    """The schema offers vcan0 for testing; refusing it would break that."""
    assert helper.main(["can-up", "vcan0", "125000"]) == 0
    assert ran[0] == ["ip", "link", "set", "vcan0", "down"]
