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
import shutil
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


def test_the_last_overlay_line_is_reported(helper, uenv, capsys):
    """For a key assigned twice U-Boot uses the last value, as the kernel check does."""
    uenv.write_text(
        uenv.read_text(encoding="utf-8") + "uboot_overlay_addr1=BONEIO-BLACK-PINS-v1.0.dtbo\n",
        encoding="utf-8",
    )
    assert helper.main(["overlay-get"]) == 0
    assert json.loads(capsys.readouterr().out)["overlay"] == "BONEIO-BLACK-PINS-v1.0.dtbo"


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


def test_no_password_ever_reaches_an_argument_list(helper):
    """The helper does handle one secret — the broker password — and reads it
    from stdin on purpose.

    What must never happen is a password in argv: the process table is readable
    by every local account, which is exactly what `mosquitto_passwd -b <file>
    <user> <password>` exposed. Checked against the syntax tree rather than the
    prose, because the module explains at length why those paths went.
    """
    import ast

    tree = ast.parse(HELPER.read_text(encoding="utf-8"))
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    # `sudo -S` is how a password gets piped to sudo; -b is the form of
    # mosquitto_passwd that takes it as an argument.
    assert "-S" not in literals
    assert "-b" not in literals, "the batch form puts the password in argv"

    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "getpass" not in names

    # Every argv this module builds is a list of constants plus validated
    # values; a password may only travel as `input=`.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "run"):
            continue
        argv = node.args[0] if node.args else None
        if isinstance(argv, (ast.List, ast.Tuple)):
            rendered = ast.unparse(argv)
            assert "password" not in rendered.lower(), (
                f"a password-shaped value is in an argument list: {rendered[:80]}"
            )


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


# --------------------------------------------------------- bus-off recovery


def test_a_controller_can_be_restarted_out_of_bus_off(helper, ran):
    """A CAN controller that has counted too many errors stops transmitting.

    The kernel's primitive for that is `type can restart`, which clears the
    state without touching the configured bitrate — so a recovery does not have
    to know what the bus is running at.
    """
    assert helper.main(["can-restart", "can0"]) == 0
    assert ran == [["ip", "link", "set", "can0", "type", "can", "restart"]]


@pytest.mark.parametrize("interface", ["can2", "eth0", "", "can0;id", "../can0"])
def test_a_restart_is_refused_for_anything_but_a_can_interface(helper, ran, interface):
    assert helper.main(["can-restart", interface]) == 1
    assert ran == []


def test_recovery_needs_no_wider_grant_than_setup(helper):
    """Both verbs touch the same three interfaces and nothing else.

    This is what lets the `ip link set can0 *` rule go: the operations CAN
    actually needs — bring up, take down, restart out of bus-off — are all
    named, so nothing is left that requires an open argument list.
    """
    assert "can-restart" in helper.VERBS
    assert set(helper.CAN_INTERFACES) == {"can0", "can1", "vcan0"}


# ------------------------------------------------------------- broker passwords


@pytest.fixture
def passwd(tmp_path, helper, monkeypatch):
    """A broker password file the helper will accept."""
    path = tmp_path / "passwd"
    path.write_text("boneio:$7$existing\n", encoding="utf-8")
    os.chmod(path, 0o640)
    monkeypatch.setattr(helper, "MOSQUITTO_PASSWD", path)
    monkeypatch.setattr(helper, "_assert_root", lambda: None)
    monkeypatch.setattr(helper, "_restore_passwd_permissions", lambda: None)
    return path


def _feed(monkeypatch, text: str) -> None:
    class _Stdin:
        def read(self) -> str:
            return text

    monkeypatch.setattr("sys.stdin", _Stdin())


def test_the_password_is_read_from_stdin_not_the_argument_list(
    helper, passwd, monkeypatch
):
    """The rule this replaces put the new password in the process table.

    `mosquitto_passwd -b <file> <user> <password>` is readable by every local
    account for as long as it runs, and by anything sampling ps.
    """
    import subprocess as sp

    seen = {}

    def _fake(argv, input=None, **kwargs):
        seen["argv"] = list(argv)
        seen["input"] = input
        return sp.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(sp, "run", _fake)
    _feed(monkeypatch, "hunter2\n")

    assert helper.main(["mqtt-password", "boneio"]) == 0
    assert "hunter2" not in " ".join(seen["argv"]), "the password reached argv"
    assert "-b" not in seen["argv"], "the batch form takes the password as an argument"
    assert seen["input"] == "hunter2\nhunter2\n"


@pytest.mark.parametrize("account", ["root", "admin", "", "boneio2", "../boneio"])
def test_only_the_managed_accounts_can_be_given_a_password(
    helper, passwd, monkeypatch, account
):
    """Otherwise this becomes a way to add a broker login nobody asked for."""
    _feed(monkeypatch, "hunter2\n")
    assert helper.main(["mqtt-password", account]) == 1


def test_every_account_the_sudoers_rule_allowed_is_still_accepted(helper):
    assert set(helper.MQTT_ACCOUNTS) == {"boneio", "homeassistant", "mqtt"}


@pytest.mark.parametrize("password", ["", "\n", "two\nlines\n"])
def test_an_unusable_password_is_refused(helper, passwd, monkeypatch, password):
    _feed(monkeypatch, password)
    assert helper.main(["mqtt-password", "boneio"]) == 1


def test_a_symlinked_password_file_is_refused(helper, tmp_path, monkeypatch):
    """Otherwise the write follows it to any file root can reach."""
    target = tmp_path / "elsewhere"
    target.write_text("x\n", encoding="utf-8")
    link = tmp_path / "passwd"
    link.symlink_to(target)
    monkeypatch.setattr(helper, "MOSQUITTO_PASSWD", link)
    monkeypatch.setattr(helper, "_assert_root", lambda: None)
    _feed(monkeypatch, "hunter2\n")
    assert helper.main(["mqtt-password", "boneio"]) == 1


def test_the_permissions_are_restored_after_a_write(helper, tmp_path, monkeypatch):
    """mosquitto_passwd rewrites the file with a mode of its own.

    It shipped 0644 and was seen at 0704, which let any local account take the
    hashes for an offline crack (F-11).
    """
    import subprocess as sp

    path = tmp_path / "passwd"
    path.write_text("boneio:$7$existing\n", encoding="utf-8")
    monkeypatch.setattr(helper, "MOSQUITTO_PASSWD", path)
    monkeypatch.setattr(helper, "_assert_root", lambda: None)
    monkeypatch.setattr(
        sp, "run", lambda argv, **k: sp.CompletedProcess(argv, 0, stdout="", stderr="")
    )
    _feed(monkeypatch, "hunter2\n")

    os.chmod(path, 0o704)
    helper.main(["mqtt-password", "boneio"])
    assert path.stat().st_mode & 0o777 == helper.MOSQUITTO_PASSWD_MODE
    assert helper.MOSQUITTO_PASSWD_MODE & 0o040, "the broker must still be able to read it"
    assert helper.MOSQUITTO_PASSWD_MODE & 0o007 == 0, "world still has access"


# ----------------------------------------------------------------- OS updates
#
# apt run as root with caller-chosen arguments is a root shell, so the tests
# are mostly about what the caller cannot say: a mode outside the closed set,
# the executor outside its own unit, and a kernel upgrade that would boot
# without the boneIO pinmux.

APT_SIMULATION = """\
Reading package lists...
Inst libssl3t64 [3.5.1-1] (3.5.4-1~deb13u1 Debian-Security:13/stable [armhf])
Inst linux-image-6.18.60-bone56 (1bookworm Beagle:13/stable [armhf])
Conf libssl3t64 (3.5.4-1~deb13u1 Debian-Security:13/stable [armhf])
"""


#: Captured from a controller (apt-get on Debian 13, LC_ALL=C), cut to the end.
APT_ASSUME_NO = """\
4 upgraded, 3 newly installed, 0 to remove and 0 not upgraded.
Need to get 44.4 MB of archives.
After this operation, 59.0 MB of additional disk space will be used.
Do you want to continue? [Y/n] N
Abort.
"""


def test_apts_sizes_are_read_from_its_no_answer(helper):
    # 44.4 MB and 59.0 MB are decimal; the device's free space is in MiB.
    assert helper._apt_space_needed(APT_ASSUME_NO) == (43, 57)


def test_partly_downloaded_counts_what_is_still_to_come(helper):
    text = (
        "Need to get 12.3 MB/44.4 MB of archives.\n"
        "After this operation, 3072 kB disk space will be freed.\n"
    )
    assert helper._apt_space_needed(text) == (12, -2)


def test_small_sizes_and_none_at_all(helper):
    assert helper._apt_space_needed("Need to get 1308 B of archives.\n") == (1, 0)
    assert helper._apt_space_needed("0 upgraded, 0 newly installed.\n") is None


def test_the_requirement_counts_downloads_growth_and_a_margin(helper):
    assert helper._os_update_required_mb(400, 250) == 400 + 250 + helper.OS_UPDATE_MARGIN_MB
    # Shrinking packages still need their downloads; small upgrades the floor.
    assert helper._os_update_required_mb(400, -50) == 400 + helper.OS_UPDATE_MARGIN_MB
    assert helper._os_update_required_mb(2, 1) == helper.OS_UPDATE_MIN_FREE_MB


def test_the_simulation_is_parsed_into_packages(helper):
    assert helper._os_update_list(APT_SIMULATION) == [
        {"name": "libssl3t64", "from": "3.5.1-1", "to": "3.5.4-1~deb13u1"},
        {"name": "linux-image-6.18.60-bone56", "from": None, "to": "1bookworm"},
    ]


@pytest.mark.parametrize("mode", [
    "", "install", "upgrade -o APT::Update::Pre-Invoke=sh", "../upgrade", "UPGRADE",
])
def test_an_unknown_update_mode_is_refused(helper, ran, monkeypatch, mode):
    monkeypatch.setattr(helper, "_os_update_unit_active", lambda: False)
    assert helper.main(["os-update-start", mode]) == 1
    assert ran == []


def test_an_update_starts_in_its_own_unit_with_a_fixed_command(helper, ran, monkeypatch):
    """Outside boneio.service: an upgrade that restarts boneIO must not kill dpkg."""
    monkeypatch.setattr(helper, "_os_update_unit_active", lambda: False)
    assert helper.main(["os-update-start", "upgrade"]) == 0
    assert len(ran) == 1
    argv = ran[0]
    assert argv[:3] == ["systemd-run", "--unit", "boneio-os-update.service"]
    assert argv[-3:] == ["/usr/sbin/boneio-system", "os-update-run", "upgrade"]


def test_a_second_update_is_refused_while_one_runs(helper, ran, monkeypatch):
    monkeypatch.setattr(helper, "_os_update_unit_active", lambda: True)
    assert helper.main(["os-update-start", "check"]) == 1
    assert ran == []


def test_the_executor_refuses_outside_its_unit(helper, monkeypatch, tmp_path):
    """Run straight from boneio.service it would die with boneIO mid-upgrade."""
    monkeypatch.setattr(helper, "_assert_root", lambda: None)
    monkeypatch.setattr(helper, "_in_update_unit", lambda: False)
    monkeypatch.setattr(helper, "OS_UPDATE_STATE", tmp_path / "state.json")

    def _no_subprocess(*args, **kwargs):
        raise AssertionError("nothing may run outside the unit")

    monkeypatch.setattr(helper.subprocess, "run", _no_subprocess)
    assert helper.main(["os-update-run", "upgrade"]) == 1
    assert not (tmp_path / "state.json").exists()


@pytest.fixture
def os_update(helper, monkeypatch, tmp_path):
    """An executor inside its unit, with apt faked and state in tmp_path."""
    monkeypatch.setattr(helper, "_assert_root", lambda: None)
    monkeypatch.setattr(helper, "_in_update_unit", lambda: True)
    monkeypatch.setattr(helper, "OS_UPDATE_STATE", tmp_path / "state.json")
    monkeypatch.setattr(helper, "OS_UPDATE_LOG", tmp_path / "update.log")
    # Never the build machine's own apt cache.
    monkeypatch.setattr(helper, "APT_ARCHIVES", tmp_path / "no-archives")
    monkeypatch.setattr(
        helper, "_kernel_check",
        lambda repair=False: {"status": "ok", "kernel": "k", "running": "k", "message": None},
    )
    calls: list[list[str]] = []

    monkeypatch.setattr(helper.shutil, "disk_usage", _disk(10_000))

    def _fake(argv, log, timeout):
        calls.append(list(argv))
        if "--assume-no" in argv:
            log.write(APT_ASSUME_NO)
            return 1, APT_ASSUME_NO
        out = APT_SIMULATION if "-s" in argv else ""
        log.write(out)
        return 0, out

    monkeypatch.setattr(helper, "_stream", _fake)
    return calls


def test_a_check_changes_nothing_on_the_system(helper, os_update, tmp_path):
    assert helper.main(["os-update-run", "check"]) == 0
    commands = os_update
    assert not any("-y" in argv for argv in commands)
    assert not any(argv[0] == "dpkg" for argv in commands)
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["result"] == "success"
    assert [p["name"] for p in state["packages"]] == [
        "libssl3t64", "linux-image-6.18.60-bone56",
    ]


def test_an_upgrade_keeps_local_configuration_and_a_clean_environment(
    helper, os_update, tmp_path
):
    assert helper.main(["os-update-run", "upgrade"]) == 0
    commands = os_update
    assert ["dpkg", "--configure", "-a"] in commands
    upgrade = next(argv for argv in commands if "dist-upgrade" in argv and "-y" in argv)
    # Migrations install mosquitto, sshd and journald settings; the
    # distribution's defaults must not come back with a package upgrade.
    assert "Dpkg::Options::=--force-confold" in upgrade
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["reboot_recommended"] is True


def _disk(free_mb: int):
    mb = 1024 * 1024
    return lambda path: shutil._ntuple_diskusage(10**10, 10**10 - free_mb * mb, free_mb * mb)


def _big_upgrade(download: str, growth: str) -> str:
    return (
        f"Need to get {download} of archives.\n"
        f"After this operation, {growth} of additional disk space will be used.\n"
        "Abort.\n"
    )


def test_an_upgrade_bigger_than_the_room_is_refused_before_it_starts(
    helper, os_update, monkeypatch, tmp_path
):
    # 300 MB free used to be enough to start a year's worth of packages, which
    # then filled / to zero halfway through and failed with rc=100.
    monkeypatch.setattr(helper.shutil, "disk_usage", _disk(300))
    streamed = helper._stream

    def _year_old(argv, log, timeout):
        if "--assume-no" in argv:
            out = _big_upgrade("180 MB", "150 MB")
            os_update.append(list(argv))
            return 1, out
        return streamed(argv, log, timeout)

    monkeypatch.setattr(helper, "_stream", _year_old)
    assert helper.main(["os-update-run", "upgrade"]) == 1
    assert not any("-y" in argv and "dist-upgrade" in argv for argv in os_update)
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["result"] == "failed"
    assert state["required_mb"] == 172 + 144 + helper.OS_UPDATE_MARGIN_MB
    assert "300 MB free" in state["message"]
    assert "172 MB to download" in state["message"]


def test_a_full_device_is_still_repaired_before_anything_is_measured(
    helper, os_update, monkeypatch, tmp_path
):
    # Left at 0 MB by a failed run: dpkg must get to finish its work, even
    # though the upgrade proper will be refused.
    monkeypatch.setattr(helper.shutil, "disk_usage", _disk(0))
    assert helper.main(["os-update-run", "upgrade"]) == 1
    assert ["dpkg", "--configure", "-a"] in os_update
    assert not any("-y" in argv and "dist-upgrade" in argv for argv in os_update)


def test_the_apt_cache_is_cleared_before_an_upgrade(helper, os_update, monkeypatch, tmp_path):
    archives = tmp_path / "archives"
    archives.mkdir()
    (archives / "linux-image.deb").write_bytes(b"x" * 1024 * 1024 * 3)
    monkeypatch.setattr(helper, "APT_ARCHIVES", archives)
    assert helper.main(["os-update-run", "upgrade"]) == 0
    assert os_update[0] == ["apt-get", "clean"]
    assert os_update.index(["dpkg", "--configure", "-a"]) == 1


def test_a_failed_upgrade_leaves_no_downloads_behind(helper, os_update, monkeypatch, tmp_path):
    streamed = helper._stream

    def _runs_out_of_room(argv, log, timeout):
        if "-y" in argv and "dist-upgrade" in argv:
            os_update.append(list(argv))
            return 100, "E: No space left on device\n"
        return streamed(argv, log, timeout)

    cleaned: list[list[str]] = []
    monkeypatch.setattr(helper, "_stream", _runs_out_of_room)
    monkeypatch.setattr(
        helper.subprocess, "run",
        lambda argv, **kw: cleaned.append(list(argv)) or subprocess.CompletedProcess(argv, 0),
    )
    assert helper.main(["os-update-run", "upgrade"]) == 1
    assert cleaned == [["apt-get", "clean"]]
    state = json.loads((tmp_path / "state.json").read_text())
    assert "dist-upgrade failed (rc=100)" in state["message"]


def test_a_check_measures_what_the_upgrade_will_need(helper, os_update, tmp_path):
    assert helper.main(["os-update-run", "check"]) == 0
    state = json.loads((tmp_path / "state.json").read_text())
    assert (state["download_mb"], state["growth_mb"]) == (43, 57)
    assert state["required_mb"] == helper.OS_UPDATE_MIN_FREE_MB


def test_the_state_reports_what_clearing_the_cache_would_free(helper, monkeypatch, tmp_path, capsys):
    archives = tmp_path / "archives"
    (archives / "partial").mkdir(parents=True)
    (archives / "a.deb").write_bytes(b"x" * 1024 * 1024 * 2)
    (archives / "partial" / "b.deb").write_bytes(b"x" * 1024 * 1024)
    (archives / "lock").write_bytes(b"x" * 1024 * 1024 * 5)
    monkeypatch.setattr(helper, "APT_ARCHIVES", archives)
    assert helper._apt_cache_mb() == 3


def test_a_failed_step_is_recorded(helper, os_update, monkeypatch, tmp_path):
    def _fails(argv, log, timeout):
        log.write("E: no network\n")
        return 100, "E: no network\n"

    monkeypatch.setattr(helper, "_stream", _fails)
    assert helper.main(["os-update-run", "check"]) == 1
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["result"] == "failed"
    assert "update failed" in state["message"]
    assert "no network" in (tmp_path / "update.log").read_text()


# ------------------------------------------------------- kernel after upgrade


@pytest.fixture
def boot(helper, monkeypatch, tmp_path):
    """A /boot with a running kernel that has the overlay, and a new one."""
    root = tmp_path / "boot"
    for kernel in ("6.18.52-bone54", "6.18.60-bone56"):
        (root / "dtbs" / kernel / "overlays").mkdir(parents=True)
        (root / f"vmlinuz-{kernel}").write_text("k")
        (root / f"initrd.img-{kernel}").write_text("i")
    (root / "dtbs" / "6.18.52-bone54" / "BONEIO-BLACK-PINS-v1.0.dtbo").write_text("dtbo")
    uenv = root / "uEnv.txt"
    uenv.write_text(
        "uname_r=6.18.60-bone56\nenable_uboot_overlays=1\n"
        "uboot_overlay_addr0=BONEIO-BLACK-PINS-v1.0.dtbo\n"
    )
    monkeypatch.setattr(helper, "BOOT_DIR", root)
    monkeypatch.setattr(helper, "UENV_PATHS", (uenv,))
    monkeypatch.setattr(helper, "DT_CHOSEN_OVERLAYS", tmp_path / "chosen-overlays")
    monkeypatch.setattr(
        helper.os, "uname", lambda: os.uname_result(("Linux", "h", "6.18.52-bone54", "", "armv7l"))
    )
    return root


def test_a_new_kernel_without_the_overlay_is_a_problem(helper, boot):
    """U-Boot would boot the stock pinmux, silently."""
    report = helper._kernel_check(repair=False)
    assert report["status"] == "problem"
    assert "BONEIO-BLACK-PINS-v1.0.dtbo" in report["message"]
    assert not (boot / "dtbs" / "6.18.60-bone56" / "BONEIO-BLACK-PINS-v1.0.dtbo").exists()


def test_the_overlay_is_copied_to_the_new_kernel(helper, boot):
    report = helper._kernel_check(repair=True)
    assert report["status"] == "repaired"
    new = boot / "dtbs" / "6.18.60-bone56"
    assert (new / "BONEIO-BLACK-PINS-v1.0.dtbo").read_text() == "dtbo"
    assert (new / "overlays" / "BONEIO-BLACK-PINS-v1.0.dtbo").read_text() == "dtbo"
    assert helper._kernel_check()["status"] == "ok"


def test_a_missing_initrd_is_a_problem(helper, boot):
    (boot / "initrd.img-6.18.60-bone56").unlink()
    assert helper._kernel_check(repair=True)["status"] == "problem"


def test_an_overlay_the_board_does_not_ship_is_not_copied(helper, boot):
    uenv = boot / "uEnv.txt"
    uenv.write_text(uenv.read_text().replace("v1.0.dtbo", "v9.dtbo"))
    (boot / "dtbs" / "6.18.52-bone54" / "BONEIO-BLACK-PINS-v9.dtbo").write_text("x")
    report = helper._kernel_check(repair=True)
    assert report["status"] == "problem"
    assert not (boot / "dtbs" / "6.18.60-bone56" / "BONEIO-BLACK-PINS-v9.dtbo").exists()


def test_the_state_asks_for_a_reboot_after_a_kernel_upgrade(
    helper, boot, monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(helper, "OS_UPDATE_STATE", tmp_path / "none.json")
    monkeypatch.setattr(helper, "REBOOT_REQUIRED", tmp_path / "reboot-required")
    monkeypatch.setattr(helper, "_os_update_unit_active", lambda: False)
    monkeypatch.setattr(helper, "_assert_root", lambda: None)
    assert helper.main(["os-update-state"]) == 0
    state = json.loads(capsys.readouterr().out)
    assert state["reboot_required"] is True
    assert state["kernel"]["kernel"] == "6.18.60-bone56"
    assert state["running"] is False


def _path_form(boot):
    """The overlay written as a path into the running kernel's directory —
    what the dev controller carries: /boot/dtbs/<old>/overlays/<name>."""
    uenv = boot / "uEnv.txt"
    uenv.write_text(uenv.read_text().replace(
        "uboot_overlay_addr0=BONEIO-BLACK-PINS-v1.0.dtbo",
        "uboot_overlay_addr0=/boot/dtbs/6.18.52-bone54/overlays/BONEIO-BLACK-PINS-v1.0.dtbo",
    ))
    (boot / "dtbs" / "6.18.52-bone54" / "overlays" / "BONEIO-BLACK-PINS-v1.0.dtbo").write_text("dtbo")
    return uenv


def test_a_path_to_the_old_kernel_is_not_reported_as_fine(helper, boot):
    """U-Boot reads that exact path; the new kernel's copy is irrelevant to it."""
    _path_form(boot)
    (boot / "dtbs" / "6.18.60-bone56" / "BONEIO-BLACK-PINS-v1.0.dtbo").write_text("dtbo")
    report = helper._kernel_check(repair=False)
    assert report["status"] == "ok"
    assert "/boot/dtbs/6.18.52-bone54/overlays/" in report["message"]


def test_a_path_that_no_longer_exists_is_a_problem(helper, boot):
    _path_form(boot)
    (boot / "dtbs" / "6.18.52-bone54" / "overlays" / "BONEIO-BLACK-PINS-v1.0.dtbo").unlink()
    (boot / "dtbs" / "6.18.60-bone56" / "BONEIO-BLACK-PINS-v1.0.dtbo").write_text("dtbo")
    assert helper._kernel_check(repair=False)["status"] == "problem"


def test_repair_switches_a_path_to_the_bare_name(helper, boot):
    """So the overlay follows every later kernel, and survives the old one's removal."""
    uenv = _path_form(boot)
    report = helper._kernel_check(repair=True)
    assert report["status"] == "repaired"
    assert "uboot_overlay_addr0=BONEIO-BLACK-PINS-v1.0.dtbo\n" in uenv.read_text()
    assert (boot / "uEnv.txt.boneio.bak").exists()
    assert (boot / "dtbs" / "6.18.60-bone56" / "BONEIO-BLACK-PINS-v1.0.dtbo").is_file()
    assert helper._kernel_check(repair=False) == {
        "status": "ok", "kernel": "6.18.60-bone56", "running": "6.18.52-bone54", "message": None,
    }


def test_the_overlay_is_copied_from_the_overlays_subdirectory(helper, boot):
    """Early installs put the .dtbo only under overlays/."""
    old = boot / "dtbs" / "6.18.52-bone54"
    (old / "BONEIO-BLACK-PINS-v1.0.dtbo").rename(old / "overlays" / "BONEIO-BLACK-PINS-v1.0.dtbo")
    assert helper._kernel_check(repair=True)["status"] == "repaired"
    assert (boot / "dtbs" / "6.18.60-bone56" / "BONEIO-BLACK-PINS-v1.0.dtbo").is_file()


# An old image that never had a second kernel: 6.18.2-bone12 boots and runs,
# and the legacy overlay sits only under its overlays/ directory.

OLD = "6.18.2-bone12"
LEGACY = "BONEIO-BLACK-PINS.dtbo"


@pytest.fixture
def old_image(helper, monkeypatch, tmp_path):
    root = tmp_path / "old-boot"
    (root / "dtbs" / OLD / "overlays").mkdir(parents=True)
    (root / f"vmlinuz-{OLD}").write_text("k")
    (root / f"initrd.img-{OLD}").write_text("i")
    (root / "dtbs" / OLD / "overlays" / LEGACY).write_text("dtbo")
    uenv = root / "uEnv.txt"
    uenv.write_text(
        f"uname_r={OLD}\nenable_uboot_overlays=1\n"
        f"uboot_overlay_addr0=/boot/dtbs/{OLD}/overlays/{LEGACY}\n"
    )
    monkeypatch.setattr(helper, "BOOT_DIR", root)
    monkeypatch.setattr(helper, "UENV_PATHS", (uenv,))
    monkeypatch.setattr(helper, "DT_CHOSEN_OVERLAYS", tmp_path / "chosen-overlays")
    monkeypatch.setattr(helper, "_boot_time", lambda: uenv.stat().st_mtime + 60)
    monkeypatch.setattr(
        helper.os, "uname", lambda: os.uname_result(("Linux", "h", OLD, "", "armv7l"))
    )
    return root


def _bare_name(boot):
    uenv = boot / "uEnv.txt"
    uenv.write_text(f"uname_r={OLD}\nenable_uboot_overlays=1\nuboot_overlay_addr0={LEGACY}\n")
    return uenv


def _overlay_live(tmp_path, entry="BONEIO-BLACK-PINS.kernel"):
    (tmp_path / "chosen-overlays").mkdir(exist_ok=True)
    (tmp_path / "chosen-overlays" / entry).write_text("")


def test_a_path_into_the_own_overlays_directory_is_not_a_problem(helper, old_image):
    """The report from the field: U-Boot reads the written path, which exists;
    the empty kernel directory beside it does not matter to it."""
    report = helper._kernel_check(repair=False)
    assert report["status"] == "ok"
    assert f"/boot/dtbs/{OLD}/overlays/" in report["message"]


def test_repair_copies_from_the_own_overlays_directory(helper, old_image):
    """No other kernel to copy from: the boot kernel's overlays/ is the source."""
    report = helper._kernel_check(repair=True)
    assert report["status"] == "repaired"
    assert (old_image / "dtbs" / OLD / LEGACY).read_text() == "dtbo"
    assert f"uboot_overlay_addr0={LEGACY}\n" in (old_image / "uEnv.txt").read_text()
    assert helper._kernel_check(repair=False)["message"] is None


def test_a_bare_name_missing_from_the_kernel_directory_is_a_problem(helper, old_image):
    _bare_name(old_image)
    report = helper._kernel_check(repair=False)
    assert report["status"] == "problem"
    assert f"{LEGACY} is missing from /boot/dtbs/{OLD}/" in report["message"]


def test_repair_of_a_bare_name_copies_from_the_own_overlays_directory(helper, old_image):
    _bare_name(old_image)
    assert helper._kernel_check(repair=True)["status"] == "repaired"
    assert (old_image / "dtbs" / OLD / LEGACY).is_file()
    assert helper._kernel_check(repair=False)["status"] == "ok"


def test_a_boot_that_worked_is_not_a_problem_when_nothing_changed(helper, old_image, tmp_path):
    """Same kernel, uEnv.txt untouched, the overlay live: the next boot finds
    it wherever this one did, even where the check does not look."""
    _bare_name(old_image)
    _overlay_live(tmp_path)
    report = helper._kernel_check(repair=False)
    assert report["status"] == "ok"
    assert "missing" in report["message"]


def test_a_uenv_changed_since_boot_is_still_a_problem(helper, old_image, monkeypatch, tmp_path):
    uenv = _bare_name(old_image)
    _overlay_live(tmp_path)
    monkeypatch.setattr(helper, "_boot_time", lambda: uenv.stat().st_mtime - 60)
    assert helper._kernel_check(repair=False)["status"] == "problem"


def test_a_new_kernel_is_a_problem_even_with_the_overlay_live(helper, boot, tmp_path):
    """The live device tree says nothing about a kernel that has not booted."""
    _overlay_live(tmp_path, "BONEIO-BLACK-PINS-v1.0.kernel")
    assert helper._kernel_check(repair=False)["status"] == "problem"


def test_the_last_overlay_line_is_the_one_checked(helper, old_image):
    """U-Boot imports uEnv.txt as an environment, so the last line wins."""
    uenv = old_image / "uEnv.txt"
    (old_image / "dtbs" / OLD / "BONEIO-BLACK-PINS-v1.0.dtbo").write_text("dtbo")
    uenv.write_text(
        f"uname_r={OLD}\nenable_uboot_overlays=1\n"
        "uboot_overlay_addr0=BONEIO-BLACK-PINS-v0.2-v0.3.dtbo\n"
        "uboot_overlay_addr0=BONEIO-BLACK-PINS-v1.0.dtbo\n"
    )
    assert helper._kernel_check(repair=False) == {
        "status": "ok", "kernel": OLD, "running": OLD, "message": None,
    }


def test_every_overlay_key_is_checked(helper, old_image):
    """addr0 and addr1 are both loaded; a missing second one is still a problem."""
    (old_image / "dtbs" / OLD / "BONEIO-BLACK-PINS-v1.0.dtbo").write_text("dtbo")
    (old_image / "uEnv.txt").write_text(
        f"uname_r={OLD}\nenable_uboot_overlays=1\n"
        "uboot_overlay_addr0=BONEIO-BLACK-PINS-v1.0.dtbo\n"
        f"uboot_overlay_addr1={LEGACY}\n"
    )
    report = helper._kernel_check(repair=False)
    assert report["status"] == "problem"
    assert LEGACY in report["message"]


# overlay-repair: what boneIO's startup check asks for. Nobody is watching,
# so files only; uEnv.txt stays as it is.


def _repair(helper, monkeypatch, capsys, *argv):
    monkeypatch.setattr(helper, "_assert_root", lambda: None)
    rc = helper.main(["overlay-repair", *argv])
    out = capsys.readouterr().out
    return rc, (json.loads(out) if out else None)


def test_overlay_repair_copies_but_leaves_uenv_alone(helper, old_image, monkeypatch, capsys):
    uenv = (old_image / "uEnv.txt").read_text()
    rc, report = _repair(helper, monkeypatch, capsys)
    assert rc == 0
    assert report["status"] == "repaired"
    assert (old_image / "dtbs" / OLD / LEGACY).read_text() == "dtbo"
    assert (old_image / "uEnv.txt").read_text() == uenv


def test_overlay_repair_fills_the_overlays_directory_from_the_boot_file(
    helper, old_image, monkeypatch, capsys
):
    """Otherwise the startup check finds overlays/ empty and asks on every boot."""
    _bare_name(old_image)
    (old_image / "dtbs" / OLD / "overlays" / LEGACY).unlink()
    (old_image / "dtbs" / OLD / LEGACY).write_text("boot copy")
    rc, report = _repair(helper, monkeypatch, capsys)
    assert (rc, report["status"]) == (0, "repaired")
    assert (old_image / "dtbs" / OLD / "overlays" / LEGACY).read_text() == "boot copy"
    assert _repair(helper, monkeypatch, capsys)[1]["status"] == "ok"


def test_the_update_repair_does_not_touch_the_overlays_directory(helper, old_image):
    """The system update's repair is unchanged by the startup mode."""
    _bare_name(old_image)
    (old_image / "dtbs" / OLD / "overlays" / LEGACY).unlink()
    (old_image / "dtbs" / OLD / LEGACY).write_text("boot copy")
    assert helper._kernel_check(repair=True)["status"] == "ok"
    assert not (old_image / "dtbs" / OLD / "overlays" / LEGACY).exists()


def test_overlay_repair_does_not_call_a_dead_path_repaired(
    helper, old_image, monkeypatch, capsys
):
    """uEnv.txt points into a removed kernel: copying beside it fixes nothing,
    and only the uEnv.txt edit it must not make would."""
    uenv = old_image / "uEnv.txt"
    uenv.write_text(uenv.read_text().replace(f"/boot/dtbs/{OLD}/", "/boot/dtbs/6.1.0-gone/"))
    rc, report = _repair(helper, monkeypatch, capsys)
    assert (rc, report["status"]) == (1, "problem")
    assert "/boot/dtbs/6.1.0-gone/overlays/" in report["message"]
    assert (old_image / "dtbs" / OLD / LEGACY).is_file()
    assert "6.1.0-gone" in uenv.read_text()


def test_overlay_repair_reports_a_problem_with_a_failing_status(
    helper, old_image, monkeypatch, capsys
):
    _bare_name(old_image)
    (old_image / "dtbs" / OLD / "overlays" / LEGACY).unlink()
    rc, report = _repair(helper, monkeypatch, capsys)
    assert rc == 1
    assert report["status"] == "problem"


@pytest.mark.parametrize("argv", [["x"], ["x", "y"], ["--force"]])
def test_overlay_repair_takes_no_arguments(helper, old_image, monkeypatch, capsys, argv):
    rc, report = _repair(helper, monkeypatch, capsys, *argv)
    assert (rc, report) == (1, None)
    assert not (old_image / "dtbs" / OLD / LEGACY).exists()


# A corrected overlay boneIO ships replaces every kernel's copy of that name.

V02 = "BONEIO-BLACK-PINS-v0.2-v0.3.dtbo"


@pytest.fixture
def shipped(helper, boot, monkeypatch, tmp_path) -> Path:
    """The v0.2-v0.3 overlay shipped, and an older copy in both kernels."""
    directory = tmp_path / "shipped-overlays"
    directory.mkdir()
    (directory / V02).write_bytes(b"fixed")
    monkeypatch.setattr(helper, "SHIPPED_OVERLAYS_DIR", directory)
    for kernel in ("6.18.52-bone54", "6.18.60-bone56"):
        for sub in ("", "overlays"):
            (boot / "dtbs" / kernel / sub / V02).write_bytes(b"old")
    return directory


def test_a_shipped_overlay_replaces_every_kernels_copy(helper, boot, shipped):
    report = helper._kernel_check(repair=True, unattended=True)
    assert report["status"] == "repaired"
    assert f"{V02} replaced with the version boneIO ships in 4 place(s)" in report["message"]
    for kernel in ("6.18.52-bone54", "6.18.60-bone56"):
        for sub in ("", "overlays"):
            copy = boot / "dtbs" / kernel / sub / V02
            assert copy.read_bytes() == b"fixed"
            assert copy.stat().st_mode & 0o777 == 0o644
    assert not list((boot / "dtbs").rglob("*.tmp"))


def test_the_system_update_repair_replaces_them_too(helper, boot, shipped):
    helper._kernel_check(repair=True)
    assert (boot / "dtbs" / "6.18.60-bone56" / V02).read_bytes() == b"fixed"


def test_a_matching_copy_is_left_alone(helper, boot, shipped):
    helper._kernel_check(repair=True, unattended=True)
    report = helper._kernel_check(repair=True, unattended=True)
    assert "boneIO ships" not in (report["message"] or "")


def test_the_check_alone_replaces_nothing(helper, boot, shipped):
    helper._kernel_check(repair=False)
    assert (boot / "dtbs" / "6.18.60-bone56" / V02).read_bytes() == b"old"


def test_a_shipped_overlay_is_not_spread_where_there_was_no_copy(helper, boot, shipped):
    """Which kernel lacks the overlay uEnv.txt loads is the kernel check's call."""
    (boot / "dtbs" / "6.18.52-bone54" / "overlays" / V02).unlink()
    helper._kernel_check(repair=True, unattended=True)
    assert not (boot / "dtbs" / "6.18.52-bone54" / "overlays" / V02).exists()


def test_a_shipped_file_outside_the_board_set_is_ignored(helper, boot, shipped):
    (shipped / "BONEIO-BLACK-PINS-v9.dtbo").write_bytes(b"fixed")
    (boot / "dtbs" / "6.18.52-bone54" / "BONEIO-BLACK-PINS-v9.dtbo").write_bytes(b"old")
    helper._kernel_check(repair=True, unattended=True)
    assert (boot / "dtbs" / "6.18.52-bone54" / "BONEIO-BLACK-PINS-v9.dtbo").read_bytes() == b"old"


def test_the_shipped_overlay_is_the_source_for_a_missing_one(helper, boot, shipped):
    """The overlay uEnv.txt loads, missing from the boot kernel: the shipped
    version is copied in, not the stale one from the running kernel."""
    uenv = boot / "uEnv.txt"
    uenv.write_text(uenv.read_text().replace("v1.0.dtbo", "v0.2-v0.3.dtbo"))
    for sub in ("", "overlays"):
        (boot / "dtbs" / "6.18.60-bone56" / sub / V02).unlink()
    report = helper._kernel_check(repair=True, unattended=True)
    assert report["status"] == "repaired"
    for sub in ("", "overlays"):
        assert (boot / "dtbs" / "6.18.60-bone56" / sub / V02).read_bytes() == b"fixed"


def test_apt_output_reaches_the_log_while_the_step_runs(helper, tmp_path):
    """Written only at the end, a 30-minute configure looked hung in the panel."""
    log_path = tmp_path / "update.log"
    with log_path.open("w", encoding="utf-8") as log:
        rc, out = helper._stream(
            ["sh", "-c", "echo one; echo two >&2; exit 3"], log, timeout=30
        )
    assert rc == 3
    assert out.splitlines() == ["one", "two"]
    assert log_path.read_text().splitlines() == ["one", "two"]


def test_the_apt_environment_is_the_only_environment(helper, tmp_path, monkeypatch):
    monkeypatch.setenv("APT_CONFIG", "/tmp/evil.conf")
    with (tmp_path / "log").open("w") as log:
        _, out = helper._stream(["sh", "-c", "env"], log, timeout=30)
    assert "APT_CONFIG" not in out
    assert "NEEDRESTART_MODE=l" in out


def test_a_step_that_hangs_is_killed(helper, tmp_path):
    with (tmp_path / "log").open("w") as log:
        rc, _ = helper._stream(["sleep", "30"], log, timeout=1)
    assert rc != 0


# --------------------------------------------------- automatic security updates


@pytest.fixture
def periodic(helper, monkeypatch, tmp_path):
    path = tmp_path / "52boneio-periodic"
    path.write_text('APT::Periodic::Unattended-Upgrade "1";\n')
    monkeypatch.setattr(helper, "AUTOUPDATE_PERIODIC", path)
    monkeypatch.setattr(helper, "AUTOUPDATE_LOG", tmp_path / "unattended-upgrades.log")
    monkeypatch.setattr(helper, "_autoupdate_state", lambda: {"enabled": None})
    return path


def test_switching_off_writes_the_template_and_stops_the_timers(helper, ran, periodic):
    assert helper.main(["os-autoupdate-set", "off"]) == 0
    text = periodic.read_text()
    assert 'APT::Periodic::Unattended-Upgrade "0";' in text
    assert 'APT::Periodic::Update-Package-Lists "0";' in text
    assert ran == [
        ["systemctl", "disable", "--now", "apt-daily.timer"],
        ["systemctl", "disable", "--now", "apt-daily-upgrade.timer"],
    ]


def test_switching_on_enables_the_timers(helper, ran, periodic):
    helper.main(["os-autoupdate-set", "off"])
    ran.clear()
    assert helper.main(["os-autoupdate-set", "on"]) == 0
    assert 'APT::Periodic::Unattended-Upgrade "1";' in periodic.read_text()
    assert ran[0] == ["systemctl", "enable", "--now", "apt-daily.timer"]


@pytest.mark.parametrize("argument", ["", "1", "true", 'on"; APT::Evil "1', "ON"])
def test_only_on_or_off_is_accepted(helper, ran, periodic, argument):
    before = periodic.read_text()
    assert helper.main(["os-autoupdate-set", argument]) == 1
    assert periodic.read_text() == before
    assert ran == []


def test_the_switch_needs_the_migration(helper, ran, periodic):
    """Without 52boneio-unattended beside it, 'on' would mean Debian's defaults."""
    periodic.unlink()
    assert helper.main(["os-autoupdate-set", "on"]) == 1
    assert not periodic.exists()


def test_the_last_automatic_run_is_read_from_its_log(helper, monkeypatch, tmp_path):
    log = tmp_path / "unattended-upgrades.log"
    log.write_text(
        "2026-09-24 06:10:01,100 INFO Starting unattended upgrades script\n"
        "2026-09-24 06:10:40,200 INFO Packages that will be upgraded: libssl3t64 openssl\n"
        "2026-09-25 06:12:03,300 INFO Starting unattended upgrades script\n"
        "2026-09-25 06:12:30,400 INFO No packages found that can be upgraded unattended\n"
    )
    monkeypatch.setattr(helper, "AUTOUPDATE_LOG", log)
    monkeypatch.setattr(helper, "AUTOUPDATE_PERIODIC", tmp_path / "missing")
    state = helper._autoupdate_state()
    assert state["last_run"] == "2026-09-25 06:12:03"
    assert state["last_packages"] == ["libssl3t64", "openssl"]
    assert state["last_packages_at"] == "2026-09-24 06:10:40"
    assert state["enabled"] is False


def test_the_shipped_unattended_config_takes_security_fixes_only():
    conf = (REPO_ROOT / "boneio" / "migrations" / "assets" / "apt" / "52boneio-unattended").read_text()
    code = "\n".join(line for line in conf.splitlines() if not line.strip().startswith("//"))
    assert "#clear Unattended-Upgrade::Origins-Pattern;" in code
    patterns = [line.strip() for line in code.splitlines() if line.strip().startswith('"origin=')]
    assert patterns and all("label=Debian-Security" in p for p in patterns)
    assert 'Unattended-Upgrade::Automatic-Reboot "false";' in code
