"""The CANopen client connects and handles SDO writes with the real canopen API.

`connect()` used to register its SDO handlers with `sdo.add_callback()`, which
canopen-asyncio has never had, so it raised on every start and CAN never came
up. These tests run the real `LocalNode` (and a python-can virtual bus for
`connect()`), not a mock of it, so an API that does not exist fails here.

Once CAN came up, a bus nobody acknowledges went bus-off every few seconds and
the monitor restarted it every time; the last class covers the backoff.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

canopen = pytest.importorskip("canopen_asyncio")

from boneio.hardware.can import client as client_module  # noqa: E402
from boneio.hardware.can.client import (  # noqa: E402
    SDO_CONFIG_PAYLOAD_INDEX,
    SDO_CONFIG_TRIGGER_INDEX,
    SDO_NODE_ID_INDEX,
    CANopenClient,
)


def _client_with_local_node() -> CANopenClient:
    client = CANopenClient(channel="vcan_test", node_id=5)
    client._local_node = canopen.LocalNode(5, client._create_object_dictionary())
    client._setup_sdo_callbacks()
    return client


class TestSdoWrites:
    def test_node_id_write_reaches_the_callback(self):
        client = _client_with_local_node()
        on_node_id = MagicMock()
        client.add_sdo_node_id_callback(on_node_id)

        client._local_node.set_data(SDO_NODE_ID_INDEX, 0, (42).to_bytes(1, "little"))

        on_node_id.assert_called_once_with(42)

    @pytest.mark.parametrize("index", [SDO_CONFIG_PAYLOAD_INDEX, SDO_CONFIG_TRIGGER_INDEX])
    def test_config_push_is_refused_with_an_sdo_abort(self, index):
        """Unsigned configuration must not reach the config callback."""
        client = _client_with_local_node()
        on_config = MagicMock()
        client.add_sdo_config_callback(on_config)

        with pytest.raises(canopen.SdoAbortedError):
            client._local_node.set_data(index, 0, b"\x01")

        on_config.assert_not_called()
        assert index not in client._local_node.data_store


class TestConnect:
    async def test_connect_succeeds_on_a_virtual_bus(self):
        pytest.importorskip("can")
        client = CANopenClient(channel="boneio_test_bus", node_id=5)

        with patch.object(client_module, "DEFAULT_INTERFACE", "virtual"):
            connected = await client.connect()
        try:
            assert connected is True
            assert client.is_connected
        finally:
            await client.disconnect()


class TestBusOffBackoff:
    """An unacknowledged bus goes bus-off again seconds after every restart."""

    def _manager(self):
        from boneio.core.manager.canopen import CANopenManager

        manager = object.__new__(CANopenManager)
        manager._channel = "can0"
        manager._bitrate = 125000
        manager._bus_off_restarts = 0
        manager._last_bus_off_restart = 0.0
        manager._next_bus_off_restart = 0.0
        return manager

    async def test_restarts_back_off_while_the_bus_stays_off(self):
        manager = self._manager()
        restart = AsyncMock(return_value=True)

        with patch("boneio.hardware.can.interface.restart_can_interface", restart):
            for second in range(0, 40):
                await manager._handle_bus_state("BUS-OFF", 1000.0 + second)

        # 2s, 4s, 8s, 16s, 32s apart: restarts at +0, +2, +6, +14, +30
        assert restart.await_count == 5

    async def test_count_resets_once_the_bus_is_healthy(self):
        manager = self._manager()
        restart = AsyncMock(return_value=True)

        with patch("boneio.hardware.can.interface.restart_can_interface", restart):
            await manager._handle_bus_state("BUS-OFF", 1000.0)
            await manager._handle_bus_state("ERROR-ACTIVE", 1030.0)
            assert manager._bus_off_restarts == 1
            await manager._handle_bus_state("ERROR-ACTIVE", 1061.0)

        assert manager._bus_off_restarts == 0
