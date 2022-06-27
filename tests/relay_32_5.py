import asyncio
import logging

from boneio.helper import load_config_from_file
from boneio.manager import Manager

_LOGGER = logging.getLogger(__name__)

from boneio.const import LM75, MCP23017, MCP_TEMP_9808, OUTPUT


async def test_32_5():
    _config = load_config_from_file("./32_5_config.yaml")
    if not _config:
        _LOGGER.info("Missing file.")
        return
    manager = Manager(
        send_message=lambda topic, payload: None,
        relay_pins=_config.get(OUTPUT, []),
        sensors={
            LM75: _config.get(LM75),
            MCP_TEMP_9808: _config.get(MCP_TEMP_9808),
        },
        mcp23017=_config.get(MCP23017, []),
        ha_discovery=False,
    )
    await asyncio.sleep(1)
    for key, value in manager.output.items():
        print(
            f"State of \33[42m{key} MCP {value.mcp_id} pin: {value.pin_id}\033[0m is {value.is_active}. Toggle it."
        )
        value.toggle()
        print("It should be on. Sleeping for 2 secs.")
        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(test_32_5())
