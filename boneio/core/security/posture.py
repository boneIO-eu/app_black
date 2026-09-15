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

#: The password the factory image writes for every MQTT account. Published in
#: the setup script and identical on every controller ever shipped, which is
#: what makes it worth naming here rather than treating as a secret.
DEFAULT_MQTT_PASSWORD = "boneio123"

#: What the panel sends when config.yaml says nothing about framing. It lives
#: here, beside the other shipped defaults the checks know about, and the
#: header builder imports it — so the check and the header cannot disagree
#: about what an unconfigured device actually does. See
#: :mod:`boneio.webui.security_headers` for why this value and not another.
DEFAULT_FRAME_ANCESTORS = "'self'"


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
) -> Posture:
    """Work out what is still unlocked.

    Args:
        config: Parsed configuration, or None when it cannot be read.
        is_provisioned: Whether an administrator account exists.
        anonymous_allowed: Whether the anonymous opt-out is set.
        auth_required: Whether requests currently need a token.
        cloud_active: Whether cloud registration is serving a real certificate.

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
            settings_section="system:mqtt-passwords",
        )
    )

    web = config.get("web") if isinstance(config.get("web"), dict) else {}
    legacy_auth = web.get("auth") if isinstance(web.get("auth"), dict) else {}
    has_legacy = bool(legacy_auth.get("username") or legacy_auth.get("password"))
    checks.append(
        Check(
            id="legacy_web_auth",
            title="Old credentials in config.yaml",
            severity=Severity.WARNING,
            state=State.FAILED if has_legacy else State.OK,
            detail=(
                "config.yaml still holds the pre-1.6 web.auth block, with the "
                "password in clear text. It is no longer read."
                if has_legacy
                else "No credentials are stored in config.yaml."
            ),
            remedy="Delete the web.auth username and password from config.yaml.",
            settings_section="web",
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
    frame_ancestors = security.get("frame_ancestors") or DEFAULT_FRAME_ANCESTORS
    unrestricted = "*" in str(frame_ancestors).split()
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
                "Replace * with 'self', adding your Home Assistant address if a "
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
