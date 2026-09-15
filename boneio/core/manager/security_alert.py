"""Publish this controller's security posture to Home Assistant.

The panel shows the same checks, but the panel is a place people visit after
something goes wrong. A device that has been sitting on a shelf with the
factory MQTT password does not produce a visit — it produces nothing at all,
which is indistinguishable from being fine. On the Home Assistant dashboard it
is a red diagnostic entity next to the other diagnostics, and it can raise an
automation.

One entity, not one per check: the set of checks grows between releases, and
entities that appear and disappear leave orphans in the HA registry that only
the user can clear. The failures ride on the attributes topic instead.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from boneio.core.security.posture import Posture, Severity, evaluate_config

_LOGGER = logging.getLogger(__name__)


def _open_user_store(config_file_path: str):
    """Open the account store that lives beside config.yaml.

    Args:
        config_file_path: Path to config.yaml.

    Returns:
        A ``UserStore``, or None when it cannot be opened.
    """
    try:
        from boneio.core.auth.store import UserStore

        return UserStore(Path(config_file_path).parent / "users.json")
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Could not open the account store: %s", err)
        return None


def build_payloads(posture: Posture) -> tuple[str, str]:
    """Render the state and attributes payloads for one posture.

    Args:
        posture: The evaluated posture.

    Returns:
        Tuple of ``(state_payload, attributes_payload)``, both JSON.
    """
    failures = posture.failed
    # ON tracks the actionable findings, not the advice. A problem sensor that
    # is ON on every controller ever shipped would be automated around within
    # a week, which is the same as not having it.
    state = json.dumps({"state": "ON" if posture.actionable else "OFF"})

    attributes = {
        "failed": len(failures),
        "actionable": len(posture.actionable),
        "critical": posture.count(Severity.CRITICAL),
        "warning": posture.count(Severity.WARNING),
        "info": posture.count(Severity.INFO),
        "worst": str(posture.worst) if posture.worst else "none",
        # Human-readable, because this is what an HA notification will carry.
        "summary": (
            "; ".join(f"{c.title}: {c.detail}" for c in failures[:5])
            if failures
            else "No security recommendations outstanding"
        ),
        # Machine-readable, for anyone templating against it.
        "recommendations": [
            {
                "id": c.id,
                "title": c.title,
                "severity": str(c.severity),
                "remedy": c.remedy,
            }
            for c in failures
        ],
    }
    return state, json.dumps(attributes)


class SecurityAlertPublisher:
    """Keeps the Home Assistant security entity in step with the device.

    Args:
        manager: The boneIO manager, used for its MQTT and discovery helpers.
    """

    def __init__(self, manager) -> None:
        self._manager = manager

    def _load_config(self) -> dict:
        """Read config.yaml.

        The manager holds its configuration as exploded constructor arguments,
        not as the document, and the checks need the document — the MQTT
        password among them. Read through the normal loader so ``!secret`` is
        resolved: a shipped default moved into secrets.yaml is still a shipped
        default.

        Returns:
            The parsed configuration, or an empty dict when it cannot be read.
        """
        try:
            from boneio.core.config.yaml_util import load_yaml_file

            loaded = load_yaml_file(self._manager._config_file_path)
            return loaded if isinstance(loaded, dict) else {}
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Could not read the configuration: %s", err)
            return {}

    def _evaluate(self) -> Posture:
        """Evaluate the current posture.

        Returns:
            The posture. Never raises; an unreadable device still reports.
        """
        config = self._load_config()

        cloud_active = False
        try:
            cloud_reg = getattr(self._manager._config_helper, "_cloud_reg", None)
            if cloud_reg is not None:
                cloud_active = bool(cloud_reg.is_cloud_config_active())
        except Exception:  # noqa: BLE001
            cloud_active = False

        return evaluate_config(
            config,
            user_store=_open_user_store(self._manager._config_file_path),
            cloud_active=cloud_active,
        )

    async def send_ha_autodiscovery(self) -> None:
        """Register the security binary_sensor and publish its first state."""
        from boneio.integration.homeassistant import (
            ha_security_alert_availability_message,
        )

        try:
            msg = ha_security_alert_availability_message(
                config_helper=self._manager._config_helper
            )
            self._manager.publish_ha_discovery(
                id="security_alert",
                ha_type="binary_sensor",
                payload=msg,
            )
        except Exception as err:  # noqa: BLE001 - discovery must not stop startup
            _LOGGER.warning("Could not register the security entity: %s", err)
            # Still publish: the entity may already exist from a previous run,
            # and a stale retained state is worse than a corrected one.

        await self.publish_state()

    async def publish_state(self) -> None:
        """Publish the current posture.

        Retained, so Home Assistant shows the state of a device that is
        offline rather than an empty entity — a controller that has been
        unplugged is exactly the one nobody has hardened.
        """
        try:
            posture = self._evaluate()
            state_payload, attr_payload = build_payloads(posture)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Could not evaluate the security posture: %s", err)
            return

        topic = self._manager._topic_prefix
        self._manager.send_message(
            topic=f"{topic}/security/state", payload=state_payload, retain=True
        )
        self._manager.send_message(
            topic=f"{topic}/security/attributes", payload=attr_payload, retain=True
        )

        actionable = posture.actionable
        if actionable:
            _LOGGER.info(
                "Security: %d recommendation(s) outstanding, worst %s",
                len(actionable),
                posture.worst,
            )
        else:
            _LOGGER.debug("Security: nothing outstanding")
