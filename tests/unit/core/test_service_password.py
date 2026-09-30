"""The boneio login password: set once from the wizard, then only with the current one.

Part of F-04. `boneio` carries a password-gated ``(ALL:ALL) ALL``, so its
password is the root password, and boneio-system runs as root without a
password for anyone holding that account. An operation that set the password
whenever asked would be boneio -> root in two steps: set it, then sudo with it.

So these tests are mostly about refusals. The operation is allowed where it
grants nothing new — the account locked from the factory, still on the shipped
"Black", or with no password at all — and nowhere the owner has chosen one.
Changing a chosen one is passwd: it wants the current password, and counts the
wrong ones where the caller cannot reset the count.
"""

from __future__ import annotations

import io
import json
import subprocess
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HELPER = REPO_ROOT / "boneio" / "migrations" / "assets" / "helpers" / "boneio-system"


def _hash(password: str) -> str:
    """A real sha512-crypt hash, so the libcrypt check is exercised for real."""
    return subprocess.run(
        ["openssl", "passwd", "-6", password], capture_output=True, text=True, check=True
    ).stdout.strip()


# Computed here, at import. The device fixture replaces subprocess.run inside
# the helper, and the helper's subprocess is this process's subprocess module —
# a hash made inside a test would come from the fake and be empty.
SHIPPED_HASH = _hash("Black")
OWNER_HASH = _hash("korkociag-na-szafie")


@pytest.fixture(scope="module")
def helper():
    return SourceFileLoader("boneio_system_pw", str(HELPER)).load_module()


@pytest.fixture
def device(tmp_path, helper, monkeypatch):
    """A shadow file, a flag location and a recorded chpasswd."""
    shadow = tmp_path / "shadow"
    flag = tmp_path / "var" / "service-password.set"
    attempts = tmp_path / "var" / "service-password-change.json"
    monkeypatch.setattr(helper, "SHADOW", shadow)
    monkeypatch.setattr(helper, "SERVICE_PASSWORD_FLAG", flag)
    monkeypatch.setattr(helper, "SERVICE_PASSWORD_ATTEMPTS", attempts)
    monkeypatch.setattr(helper, "_assert_root", lambda: None)
    sleeps: list[float] = []
    monkeypatch.setattr(helper.time, "sleep", sleeps.append)

    calls: list[dict] = []

    def fake_run(argv, **kwargs):
        calls.append({"argv": list(argv), "input": kwargs.get("input")})
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(helper.subprocess, "run", fake_run)

    class Device:
        def __init__(self):
            self.shadow, self.flag, self.calls = shadow, flag, calls
            self.attempts, self.sleeps = attempts, sleeps

        def account(self, field: str) -> None:
            shadow.write_text(
                f"root:*:19000:0:99999:7:::\nboneio:{field}:19000:0:99999:7:::\n",
                encoding="utf-8",
            )

        def stdin(self, text: str) -> None:
            monkeypatch.setattr(helper.sys, "stdin", io.StringIO(text))

    return Device()


class TestState:
    """Reading the account, which changes nothing."""

    @pytest.mark.parametrize("field", ["!", "!$6$abc$def", "*"])
    def test_a_locked_account(self, helper, device, field):
        device.account(field)
        assert helper._service_password_state() == "locked"

    def test_no_password_at_all(self, helper, device):
        device.account("")
        assert helper._service_password_state() == "empty"

    def test_the_shipped_password_is_recognised(self, helper, device):
        device.account(SHIPPED_HASH)
        assert helper._service_password_state() == "shipped"

    def test_a_password_the_owner_chose(self, helper, device):
        device.account(OWNER_HASH)
        assert helper._service_password_state() == "set"

    def test_a_missing_account_is_refused(self, helper, device):
        device.shadow.write_text("root:*:19000:0:99999:7:::\n", encoding="utf-8")
        with pytest.raises(helper.Refused):
            helper._service_password_state()


class TestInit:
    """The one-shot."""

    @pytest.mark.parametrize("field", ["!", SHIPPED_HASH, ""])
    def test_allowed_where_it_grants_nothing_new(self, helper, device, field):
        device.account(field)
        device.stdin("nowe-haslo-wlasciciela\n")

        assert helper._service_password_init() == 0

        chpasswd = device.calls[0]
        assert chpasswd["argv"] == ["chpasswd"]
        assert chpasswd["input"] == "boneio:nowe-haslo-wlasciciela\n"
        assert device.flag.exists()

    def test_the_password_never_reaches_the_argument_list(self, helper, device):
        # ps shows argv to every local account for as long as a command runs.
        device.account("!")
        device.stdin("nowe-haslo-wlasciciela\n")
        helper._service_password_init()
        for call in device.calls:
            assert not any("nowe-haslo" in part for part in call["argv"])

    def test_refused_where_the_owner_chose_one(self, helper, device):
        # The whole point. Replacing a chosen password is boneio -> root.
        device.account(OWNER_HASH)
        device.stdin("napastnik\n")
        with pytest.raises(helper.Refused, match="owner"):
            helper._service_password_init()
        assert device.calls == []

    def test_refused_a_second_time_even_if_relocked(self, helper, device):
        # Locking the account again by hand must not re-arm it.
        device.account("!")
        device.flag.parent.mkdir(parents=True)
        device.flag.write_text("set\n")
        device.stdin("napastnik\n")
        with pytest.raises(helper.Refused, match="already been set"):
            helper._service_password_init()
        assert device.calls == []

    @pytest.mark.parametrize(
        "given",
        ["", "\n", "dwie\nlinie\n", "x" * 1025 + "\n"],
        ids=["empty", "just-newline", "line-break", "too-long"],
    )
    def test_unusable_passwords_are_refused(self, helper, device, given):
        device.account("!")
        device.stdin(given)
        with pytest.raises(helper.Refused):
            helper._service_password_init()
        assert not device.flag.exists()

    def test_a_refusal_through_main_is_exit_1(self, helper, device):
        device.account(OWNER_HASH)
        device.stdin("napastnik\n")
        assert helper.main(["service-password-init"]) == 1

    def test_both_operations_are_in_the_vocabulary(self, helper):
        assert "service-password-state" in helper.VERBS
        assert "service-password-init" in helper.VERBS


class TestChange:
    """passwd, as root: the current password or nothing.

    Allowed only where it grants nothing that knowing the current password does
    not — that person can sudo already. What it must not be is a way to set the
    password without it, or a guessing oracle cheaper than sudo.
    """

    @staticmethod
    def _change(helper, device, capsys, current, new="nowe-haslo-ssh"):
        device.stdin(f"{current}\n{new}\n")
        rc = helper._service_password_change()
        return rc, json.loads(capsys.readouterr().out.strip().splitlines()[-1])

    def _chpasswd_calls(self, device):
        return [c for c in device.calls if c["argv"] == ["chpasswd"]]

    @pytest.mark.parametrize(
        ("field", "current"),
        [(OWNER_HASH, "korkociag-na-szafie"), (SHIPPED_HASH, "Black")],
        ids=["set", "shipped"],
    )
    def test_the_right_current_password_changes_it(self, helper, device, capsys, field, current):
        device.account(field)
        rc, out = self._change(helper, device, capsys, current)

        assert (rc, out) == (0, {"result": "changed"})
        assert self._chpasswd_calls(device)[0]["input"] == "boneio:nowe-haslo-ssh\n"
        assert json.loads(device.attempts.read_text()) == []

    def test_a_change_arms_the_one_shot_flag(self, helper, device, capsys):
        # Relocking the account afterwards must not let the wizard set it again.
        device.account(SHIPPED_HASH)
        self._change(helper, device, capsys, "Black")
        assert device.flag.exists()

    def test_a_wrong_current_password_changes_nothing(self, helper, device, capsys):
        device.account(OWNER_HASH)
        rc, out = self._change(helper, device, capsys, "zgadywane")

        assert rc == 1
        assert out == {"result": "wrong_password", "attempts_left": 4}
        assert self._chpasswd_calls(device) == []
        assert device.sleeps == [helper.SERVICE_PASSWORD_FAIL_DELAY]
        assert len(json.loads(device.attempts.read_text())) == 1

    def test_the_fifth_wrong_password_shuts_it_even_to_the_right_one(
        self, helper, device, capsys
    ):
        device.account(OWNER_HASH)
        lefts = [self._change(helper, device, capsys, f"proba-{i}")[1]["attempts_left"] for i in range(5)]
        assert lefts == [4, 3, 2, 1, 0]

        rc, out = self._change(helper, device, capsys, "korkociag-na-szafie")
        assert rc == 1
        assert out["result"] == "throttled"
        assert 0 < out["retry_after"] <= helper.SERVICE_PASSWORD_WINDOW + 1
        assert self._chpasswd_calls(device) == []

    def test_old_failures_age_out(self, helper, device, capsys):
        device.account(OWNER_HASH)
        device.attempts.parent.mkdir(parents=True, exist_ok=True)
        long_ago = helper.time.time() - helper.SERVICE_PASSWORD_WINDOW - 60
        device.attempts.write_text(json.dumps([long_ago] * 5))

        rc, out = self._change(helper, device, capsys, "korkociag-na-szafie")
        assert (rc, out) == (0, {"result": "changed"})

    def test_a_timestamp_from_the_future_does_not_hold_it_shut(self, helper, device, capsys):
        # The clock was set back: forget those, rather than lock for hours.
        device.account(OWNER_HASH)
        device.attempts.parent.mkdir(parents=True, exist_ok=True)
        device.attempts.write_text(json.dumps([helper.time.time() + 86400] * 5))

        rc, _ = self._change(helper, device, capsys, "korkociag-na-szafie")
        assert rc == 0

    def test_success_clears_the_count(self, helper, device, capsys):
        device.account(OWNER_HASH)
        self._change(helper, device, capsys, "zle-1")
        self._change(helper, device, capsys, "zle-2")
        self._change(helper, device, capsys, "korkociag-na-szafie")
        assert json.loads(device.attempts.read_text()) == []

    def test_the_attempt_is_counted_before_the_check(self, helper, device, capsys, monkeypatch):
        # A caller killed mid-check, or racing another, still pays for the try.
        device.account(OWNER_HASH)
        real = helper._crypt_matches

        def interrupted(password, stored):
            if password == helper.SHIPPED_PASSWORD:
                return real(password, stored)
            raise KeyboardInterrupt

        monkeypatch.setattr(helper, "_crypt_matches", interrupted)
        device.stdin("zgadywane\nnowe-haslo-ssh\n")
        with pytest.raises(KeyboardInterrupt):
            helper._service_password_change()
        assert len(json.loads(device.attempts.read_text())) == 1

    def test_the_attempts_file_is_root_only(self, helper, device, capsys):
        device.account(OWNER_HASH)
        self._change(helper, device, capsys, "zgadywane")
        assert device.attempts.stat().st_mode & 0o777 == 0o600

    @pytest.mark.parametrize(
        ("field", "state"), [("!", "locked"), ("*", "locked"), ("", "empty")]
    )
    def test_refused_where_there_is_no_password_to_know(
        self, helper, device, capsys, field, state
    ):
        # Those belong to service-password-init, once. Here they would be a
        # way to set the password without knowing one.
        device.account(field)
        rc, out = self._change(helper, device, capsys, "cokolwiek")
        assert (rc, out) == (1, {"result": "refused", "state": state})
        assert self._chpasswd_calls(device) == []
        assert json.loads(device.attempts.read_text() or "[]") == []

    def test_refused_when_nothing_can_check_the_password(
        self, helper, device, capsys, monkeypatch
    ):
        device.account(OWNER_HASH)
        monkeypatch.setattr(helper, "_crypt_matches", lambda password, stored: None)
        rc, out = self._change(helper, device, capsys, "korkociag-na-szafie")
        assert (rc, out) == (1, {"result": "refused", "state": "unknown"})
        assert self._chpasswd_calls(device) == []

    @pytest.mark.parametrize(
        "given",
        [
            "tylko-jedna-linia\n",
            "raz\ndwa\ntrzy\n",
            "\nnowe-haslo-ssh\n",
            "korkociag-na-szafie\n\n",
            "korkociag-na-szafie\nkrotkie\n",
            "korkociag-na-szafie\nz\rpowrotem-karetki\n",
            "korkociag-na-szafie\n" + "x" * 1025 + "\n",
        ],
        ids=["one-line", "three-lines", "no-current", "no-new", "new-too-short",
             "carriage-return", "too-long"],
    )
    def test_unusable_input_is_refused_before_anything_is_counted(
        self, helper, device, given
    ):
        device.account(OWNER_HASH)
        device.stdin(given)
        with pytest.raises(helper.Refused):
            helper._service_password_change()
        assert self._chpasswd_calls(device) == []
        assert not device.attempts.exists()

    def test_neither_password_reaches_the_argument_list(self, helper, device, capsys):
        device.account(OWNER_HASH)
        self._change(helper, device, capsys, "korkociag-na-szafie", "nowe-haslo-ssh")
        for call in device.calls:
            assert not any("korkociag" in part or "nowe-haslo" in part for part in call["argv"])

    def test_through_main(self, helper, device, capsys):
        device.account(OWNER_HASH)
        device.stdin("zgadywane\nnowe-haslo-ssh\n")
        assert helper.main(["service-password-change"]) == 1
        device.stdin("korkociag-na-szafie\nnowe-haslo-ssh\n")
        assert helper.main(["service-password-change"]) == 0

    @pytest.mark.parametrize("extra", [["root"], ["root", "x"]])
    def test_it_takes_no_account_name(self, helper, device, extra):
        # Fixed to boneio. Quietly ignoring a name would read as if the caller
        # could pick one.
        device.account(OWNER_HASH)
        device.stdin("korkociag-na-szafie\nnowe-haslo-ssh\n")
        assert helper.main(["service-password-change", *extra]) == 1
        assert self._chpasswd_calls(device) == []

    def test_it_is_in_the_vocabulary(self, helper):
        assert "service-password-change" in helper.VERBS


class TestPostureCheck:
    """What the security section says about it."""

    @staticmethod
    def _check(state):
        from boneio.core.security.posture import evaluate

        posture = evaluate(
            {},
            is_provisioned=True,
            anonymous_allowed=False,
            auth_required=True,
            cloud_active=False,
            service_password=state,
        )
        return next(c for c in posture.checks if c.id == "ssh_password")

    @pytest.mark.parametrize("state", ["shipped", "empty"])
    def test_a_shared_or_missing_password_is_critical(self, state):
        check = self._check(state)
        assert check.state == "failed"
        assert check.severity == "critical"
        assert "passwd" in check.remedy

    @pytest.mark.parametrize("state", ["locked", "set"])
    def test_locked_or_chosen_is_fine(self, state):
        assert self._check(state).state == "ok"

    @pytest.mark.parametrize("state", [None, "unknown"])
    def test_not_being_able_to_ask_is_not_a_pass(self, state):
        # A missing helper must not read as a clean bill of health.
        assert self._check(state).state == "unknown"

    def test_the_shipped_password_points_at_the_accounts_card(self):
        # The card changes it given the current password, and the shipped one
        # is public, so it grants nothing sudo with "Black" did not.
        check = self._check("shipped")
        assert check.settings_section == "accounts"
        assert "Accounts" in check.remedy

    def test_no_password_at_all_has_no_button(self):
        # Nothing to check it against: a panel operation that set it anyway
        # would be a way from the service account to root.
        check = self._check("empty")
        assert check.settings_section is None
        assert check.variant == "empty"
        assert "Accounts" not in check.remedy
