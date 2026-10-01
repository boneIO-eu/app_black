"""Virtual switches go to Home Assistant with the rest of the discovery.

Only a reload of the virtual_switch section announced them, so after a restart
the discovery cleanup found their retained configs missing from the cache and
removed them, and they stayed gone until the next reload.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from boneio.core.manager.manager import Manager

SUBSYSTEMS = (
    "outputs inputs covers sensors modbus display update_manager "
    "security_alert templates irrigation"
).split()


def test_virtual_switches_are_announced_with_the_rest():
    fake = SimpleNamespace(
        **{name: SimpleNamespace(send_ha_autodiscovery=AsyncMock()) for name in SUBSYSTEMS},
        virtual_switches=SimpleNamespace(publish_discovery=MagicMock()),
    )

    asyncio.run(Manager.send_all_ha_autodiscovery(fake))

    fake.virtual_switches.publish_discovery.assert_called_once_with()
