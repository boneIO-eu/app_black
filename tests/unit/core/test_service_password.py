"""The boneio login password: set once, from the wizard, and never again by the app.

Part of F-04. `boneio` carries a password-gated ``(ALL:ALL) ALL``, so its
password is the root password, and boneio-system runs as root without a
password for anyone holding that account. An operation that set the password
whenever asked would be boneio -> root in two steps: set it, then sudo with it.

So these tests are mostly about refusals. The operation is allowed where it
grants nothing new — the account locked from the factory, still on the shipped
"Black", or with no password at all — and nowhere the owner has chosen one.
"""

from __future__ import annotations

import io
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
    monkeypatch.setattr(helper, "SHADOW", shadow)
    monkeypatch.setattr(helper, "SERVICE_PASSWORD_FLAG", flag)
    monkeypatch.setattr(helper, "_assert_root", lambda: None)

    calls: list[dict] = []

    def fake_run(argv, **kwargs):
        calls.append({"argv": list(argv), "input": kwargs.get("input")})
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(helper.subprocess, "run", fake_run)

    class Device:
        def __init__(self):
            self.shadow, self.flag, self.calls = shadow, flag, calls

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

    def test_there_is_no_button_for_it(self):
        # On purpose: a panel operation that set this password whenever asked
        # would be a way from the service account to root.
        assert self._check("shipped").settings_section is None
