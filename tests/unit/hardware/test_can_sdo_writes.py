"""The CANopen client connects and handles SDO writes with the real canopen API.

`connect()` used to register its SDO handlers with `sdo.add_callback()`, which
canopen-asyncio has never had, so it raised on every start and CAN never came
up. These tests run the real `LocalNode` (and a python-can virtual bus for
`connect()`), not a mock of it, so an API that does not exist fails here.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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
