"""What is still unlocked on this controller, in one place.

Three things need to answer the same question — the Security section in the
panel, the prompt after an update, and a Home Assistant sensor — and if each
worked it out for itself they would disagree within a release. They all read
this instead.

Each check reports a state rather than a fix. A check that cannot tell is
``UNKNOWN`` and says so; claiming "secure" for something nobody measured is
worse than admitting the gap, because it is the claim people act on.

Severities are about consequence, not effort:

``CRITICAL``
    Someone on the network can take the device over right now.
``WARNING``
    A credential or a channel is exposed, but taking it needs a position on
    the network or a second step.
``INFO``
    Worth knowing and worth improving, not a way in by itself.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from boneio.core.security import framing

#: The password the factory image writes for every MQTT account. Published in
#: the setup script and identical on every controller ever shipped, which is
#: what makes it worth naming here rather than treating as a secret.
DEFAULT_MQTT_PASSWORD = "boneio123"

#: Re-exported so callers that only care about the checks need one import.
DEFAULT_FRAME_ANCESTORS = framing.DEFAULT_FRAME_ANCESTORS


class Severity(StrEnum):
    """How much a failed check costs."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class State(StrEnum):
    """The outcome of one check."""

    OK = "ok"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Check:
    """One security property and where this controller stands on it."""

    id: str
    title: str
    severity: Severity
    state: State
    detail: str
    remedy: str = ""
    #: Where in the panel this is fixed, when it can be fixed there. A bare
    #: name is a Settings section; ``system:<anchor>`` is the System page.
    #: None means there is no control — the remedy is a file or a shell.
    settings_section: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialise for the API.

        Returns:
            JSON-safe dictionary.
        """
        return {
            "id": self.id,
            "title": self.title,
            "severity": str(self.severity),
            "state": str(self.state),
            "detail": self.detail,
            "remedy": self.remedy,
            "settings_section": self.settings_section,
        }


@dataclass
class Posture:
    """Every check, and a summary of the ones that failed."""

    checks: list[Check] = field(default_factory=list)

    @property
    def failed(self) -> list[Check]:
        """Checks that are not OK, worst first."""
        order = {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.INFO: 2}
        return sorted(
            (c for c in self.checks if c.state is State.FAILED),
            key=lambda c: order[c.severity],
        )

    @property
    def worst(self) -> Severity | None:
        """Severity of the most serious failure, or None when all is well."""
        failures = self.failed
        return failures[0].severity if failures else None

    @property
    def actionable(self) -> list[Check]:
        """Failures worth interrupting someone about, worst first.

        INFO is excluded deliberately. A self-signed certificate is the
        designed default and cloud registration is a choice, not a fix; if
        those counted, every controller would wear a permanent red badge, and
        a badge that is always red is a badge nobody reads. They still appear
        in the panel, under their own heading.
        """
        return [c for c in self.failed if c.severity is not Severity.INFO]

    def count(self, severity: Severity) -> int:
        """How many failures of one severity.

        Args:
            severity: Severity to count.

        Returns:
            Number of failed checks at that severity.
        """
        return sum(1 for c in self.failed if c.severity is severity)

    def to_dict(self) -> dict[str, Any]:
        """Serialise for the API.

        Returns:
            JSON-safe dictionary with the checks and a summary.
        """
        return {
            "checks": [c.to_dict() for c in self.checks],
            "summary": {
                "failed": len(self.failed),
                # What the badge counts and what the prompt fires on.
                "actionable": len(self.actionable),
                "critical": self.count(Severity.CRITICAL),
                "warning": self.count(Severity.WARNING),
                "info": self.count(Severity.INFO),
                "worst": str(self.worst) if self.worst else None,
            },
        }


def _legacy_web_auth(config: dict) -> bool:
    """Whether a pre-1.6 ``web.auth`` credential is still in the file.

    Accounts moved to a hashed store in 1.6, and the block is no longer read.
    Startup copies it across rather than deleting it, because rewriting
    somebody's configuration during an upgrade is not a surprise worth
    springing on a controller in a cabinet — so the password stays in plain
    text until it is taken out deliberately.

    Args:
        config: Parsed configuration.

    Returns:
        True when a username or password is still present under ``web.auth``.
    """
    web = config.get("web")
    if not isinstance(web, dict):
        return False
    auth = web.get("auth")
    if not isinstance(auth, dict):
        return False
    return bool(auth.get("password") or auth.get("username"))


def _web_exposure(config: dict) -> str:
    """How much of the network the panel's own port answers on.

    Args:
        config: Parsed configuration.

    Returns:
        ``"proxy"`` when it is limited to the loopback and the Docker bridges,
        ``"all"`` otherwise.
    """
    web = config.get("web")
    if not isinstance(web, dict):
        return "all"
    return "proxy" if web.get("expose") == "proxy" else "all"


def _mqtt_password(config: dict) -> str | None:
    """The configured MQTT password, if there is one.

    Args:
        config: Parsed configuration.

    Returns:
        The password, or None when MQTT is not configured.
    """
    mqtt = config.get("mqtt")
    if not isinstance(mqtt, dict):
        return None
    password = mqtt.get("password")
    return password if isinstance(password, str) else None


def evaluate(
    config: dict | None,
    *,
    is_provisioned: bool,
    anonymous_allowed: bool,
    auth_required: bool,
    cloud_active: bool,
    proxy_serving: bool | None = None,
) -> Posture:
    """Work out what is still unlocked.

    Args:
        config: Parsed configuration, or None when it cannot be read.
        is_provisioned: Whether an administrator account exists.
        anonymous_allowed: Whether the anonymous opt-out is set.
        auth_required: Whether requests currently need a token.
        cloud_active: Whether cloud registration is serving a real certificate.
        proxy_serving: Whether the reverse proxy is answering for this
            panel right now. None when nobody looked.

    Returns:
        The full set of checks.
    """
    config = config or {}
    checks: list[Check] = []

    checks.append(
        Check(
            id="admin_account",
            title="Administrator account",
            severity=Severity.CRITICAL,
            state=State.OK if is_provisioned else State.FAILED,
            detail=(
                "An administrator account exists."
                if is_provisioned
                else "This device has no account. Whoever reaches the first-run "
                "wizard first takes control of it."
            ),
            remedy="Finish the first-run wizard, or run: boneio accounts add <name> --role admin",
            settings_section="accounts",
        )
    )

    anonymous_in_effect = anonymous_allowed and not auth_required
    checks.append(
        Check(
            id="anonymous_access",
            title="Unauthenticated access",
            severity=Severity.CRITICAL,
            state=State.FAILED if anonymous_in_effect else State.OK,
            detail=(
                "Anyone on the network can read the configuration, switch "
                "outputs and reboot this device without a password."
                if anonymous_in_effect
                else "Requests need to be signed in."
            ),
            remedy="Create an account, and remove allow_anonymous from web.auth in config.yaml.",
            settings_section="web",
        )
    )

    behind_proxy = _web_exposure(config) == "proxy"
    checks.append(
        Check(
            id="web_exposed_in_clear",
            title="Panel served in the clear",
            # Three states, not two. Telling somebody to move the panel behind
            # a proxy that is not serving it is advice we would then refuse to
            # carry out, and they would find that out by clicking. Where the
            # proxy is not answering this drops to advice and points at the
            # proxy instead of at the panel.
            severity=Severity.WARNING if proxy_serving is not False else Severity.INFO,
            state=State.OK if behind_proxy else State.FAILED,
            detail=(
                "The panel is reachable only through the encrypted proxy."
                if behind_proxy
                else (
                    "The panel answers on its own port on every network "
                    "interface, without TLS. Anyone who can see the traffic "
                    "sees the login form, the token it hands back, and a "
                    "configuration that carries passwords."
                    if proxy_serving is not False
                    else "The panel answers on its own port on every network "
                    "interface, without TLS — and the proxy that would replace "
                    "it is not serving this panel, so closing that port now "
                    "would leave the device reachable on nothing."
                )
            ),
            remedy=(
                "Move it behind the proxy. It then answers over HTTPS and "
                "through an SSH tunnel, and not on the local network in the "
                "clear."
                if proxy_serving is not False
                else "Get the proxy serving this panel first — check that "
                "HTTPS answers on its port — and this becomes one click."
            ),
            settings_section="security",
        )
    )

    mqtt_password = _mqtt_password(config)
    if mqtt_password is None:
        mqtt_state, mqtt_detail = State.OK, "No MQTT broker is configured."
    elif mqtt_password == DEFAULT_MQTT_PASSWORD:
        mqtt_state, mqtt_detail = (
            State.FAILED,
            "The broker still uses the password every boneIO ships with, which "
            "is published and identical on every device.",
        )
    else:
        mqtt_state, mqtt_detail = State.OK, "The broker password has been changed."
    checks.append(
        Check(
            id="mqtt_password",
            title="MQTT broker password",
            severity=Severity.CRITICAL,
            state=mqtt_state,
            detail=mqtt_detail,
            remedy="Set a new broker password, then update Home Assistant with it.",
            settings_section="mosquitto",
        )
    )

    web = config.get("web") if isinstance(config.get("web"), dict) else {}
    has_legacy = _legacy_web_auth(config)
    checks.append(
        Check(
            id="legacy_web_auth",
            title="Old credentials in config.yaml",
            severity=Severity.WARNING,
            state=State.FAILED if has_legacy else State.OK,
            detail=(
                "config.yaml still holds the pre-1.6 web.auth block, with the "
                "password in clear text. Nothing reads it any more — the "
                "account was copied into the hashed store when this device was "
                "upgraded — but it is still a password, and it is in every "
                "backup and diagnostic bundle taken since."
                if has_legacy
                else "No credentials are stored in config.yaml."
            ),
            remedy=(
                "Remove it from the Security section, which keeps a copy of "
                "config.yaml first. If that password is one you use anywhere "
                "else, change it there too."
            ),
            settings_section="security",
        )
    )

    checks.append(
        Check(
            id="certificate",
            title="HTTPS certificate",
            severity=Severity.INFO,
            state=State.OK if cloud_active else State.FAILED,
            detail=(
                "Served with a certificate browsers trust."
                if cloud_active
                else "Served with a self-signed certificate, so browsers warn "
                "on every visit and people learn to click through the warning."
            ),
            remedy="Enable boneIO Cloud registration to get a trusted certificate.",
            settings_section="web",
        )
    )

    security = web.get("security") if isinstance(web.get("security"), dict) else {}
    frame_tokens = framing.effective(security.get("frame_ancestors"))
    frame_ancestors = framing.to_csp(frame_tokens)
    unrestricted = framing.is_unrestricted(frame_tokens)
    checks.append(
        Check(
            id="frame_ancestors",
            title="Embedding in other sites",
            severity=Severity.WARNING,
            state=State.FAILED if unrestricted else State.OK,
            detail=(
                "Any site may embed this panel in a frame, which is what "
                "clickjacking needs."
                if unrestricted
                else f"Only {frame_ancestors} may embed this panel."
            ),
            remedy=(
                "Replace * with self, adding your Home Assistant address if a "
                "dashboard frames this device directly."
            ),
            settings_section="security",
        )
    )

    if os.environ.get("BONEIO_DEV"):
        checks.append(
            Check(
                id="dev_mode",
                title="Development mode",
                severity=Severity.WARNING,
                state=State.FAILED,
                detail=(
                    "BONEIO_DEV is set: development routes are mounted and CORS "
                    "accepts local dev servers."
                ),
                remedy="Unset BONEIO_DEV on any device that is not a development board.",
            )
        )

    return Posture(checks=checks)


def evaluate_config(
    config: dict | None,
    *,
    user_store: Any = None,
    cloud_active: bool = False,
) -> Posture:
    """Evaluate the posture from the configuration and the account store alone.

    :func:`evaluate` takes the running web server's own view of who is signed
    in, which is the right source inside a request. The Home Assistant sensor
    is published by the manager, which must not reach into the web layer, so
    this derives the same three facts from the files instead. Both derivations
    are pure functions of the config and ``users.json``, and a test pins them
    to the same answer.

    Args:
        config: Parsed configuration, or None when it cannot be read.
        user_store: Account store, or None when it cannot be opened.
        cloud_active: Whether cloud registration is serving a real certificate.

    Returns:
        The full set of checks.
    """
    config = config or {}

    provisioned = True  # never claim an unreadable store means "no admin"
    if user_store is not None:
        try:
            provisioned = bool(user_store.is_provisioned())
        except Exception:  # noqa: BLE001
            provisioned = True

    web = config.get("web") if isinstance(config.get("web"), dict) else {}
    auth = web.get("auth") if isinstance(web.get("auth"), dict) else {}

    anonymous_allowed = bool(auth.get("allow_anonymous"))
    auth_required = provisioned or bool(auth.get("username") and auth.get("password"))

    return evaluate(
        config,
        is_provisioned=provisioned,
        anonymous_allowed=anonymous_allowed,
        auth_required=auth_required,
        cloud_active=cloud_active,
    )
