"""Lox Config Template Generator.

Generates XML configuration templates for importing into Lox Config software.
The templates describe all BoneIO outputs, covers, and sensors as
Virtual UDP Input/Output commands that the Miniserver can use.

Two separate templates are generated:
- VirtualOut: Miniserver → BoneIO (sending commands)
- VirtualInUdp: BoneIO → Miniserver (receiving state feedback)

The output XML files are compatible with Lox Config's import mechanism
and use the correct element names, attributes, and structure required
by Loxone.
"""

from __future__ import annotations

import logging
import uuid
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from boneio.core.manager.manager import Manager

_LOGGER = logging.getLogger(__name__)

# Loxone template type constants
_TEMPLATE_TYPE_INPUT = "1"   # VirtualInUdp
_TEMPLATE_TYPE_OUTPUT = "3"  # VirtualOut (UDP)
_MIN_VERSION = "17000331"    # Minimum Lox Config version


def _uuid() -> str:
    """Generate a Loxone-style UUID (lowercase with dashes)."""
    return str(uuid.uuid4())


def generate_lox_template(manager: Manager) -> str:
    """Generate Lox Config XML template from current BoneIO configuration.

    Creates two XML documents concatenated together:
    - VirtualOut: Commands Miniserver sends to BoneIO (ON/OFF, OPEN/CLOSE)
    - VirtualInUdp: State feedback BoneIO sends to Miniserver

    The generated XML can be imported into Lox Config to quickly set up
    communication between a Lox Miniserver and this BoneIO device.

    Args:
        manager: Active Manager instance with initialized outputs/covers.

    Returns:
        XML string ready to be saved as a .xml template file.
    """
    serial = manager.config_helper.serial_no or "boneio"
    device_name = manager.config_helper.name or serial

    # Get Lox UDP config (host/ports) from running config
    lox_config = _get_lox_config(manager)
    boneio_ip = lox_config.get("boneio_ip", "0.0.0.0")
    listen_port = lox_config.get("listen_port", 4445)  # BoneIO listens on this
    send_port = lox_config.get("send_port", 4444)  # BoneIO sends to this

    # ===========================================================
    # VirtualOut (Miniserver → BoneIO)
    # Miniserver sends commands to BoneIO's listen_port
    # ===========================================================
    vout = ET.Element("VirtualOut")
    vout.set("Title", f"boneIO {device_name}")
    vout.set("Comment", f"BoneIO {serial} output control")
    vout.set("Address", f"/dev/udp/{boneio_ip}/{listen_port}")
    vout.set("CmdInit", "")
    vout.set("CloseAfterSend", "true")
    vout.set("CmdSep", ";")
    vout.set("HintText", "")

    # Info element with template type (required for Lox Config import)
    info_out = ET.SubElement(vout, "Info")
    info_out.set("templateType", _TEMPLATE_TYPE_OUTPUT)
    info_out.set("minVersion", _MIN_VERSION)

    # --- Output commands ---
    outputs = manager.outputs.get_all_outputs()
    for output_id, output in outputs.items():
        if output.output_type in ("none", "cover"):
            continue

        cmd = ET.SubElement(vout, "VirtualOutCmd")
        cmd.set("Title", f"{output.name}")
        cmd.set("Comment", "")
        cmd.set("CmdOnMethod", "GET")
        cmd.set("CmdOffMethod", "GET")
        cmd.set("CmdOn", f"{output_id}=ON")
        cmd.set("CmdOnHTTP", "")
        cmd.set("CmdOnPost", "")
        cmd.set("CmdOff", f"{output_id}=OFF")
        cmd.set("CmdOffHTTP", "")
        cmd.set("CmdOffPost", "")
        cmd.set("CmdAnswer", "")
        cmd.set("Analog", "false")
        cmd.set("Repeat", "0")
        cmd.set("RepeatRate", "0")
        cmd.set("HintText", "")

    # --- Output group commands ---
    output_groups = manager.outputs.get_all_output_groups()
    for group_id, group in output_groups.items():
        cmd = ET.SubElement(vout, "VirtualOutCmd")
        cmd.set("Title", f"Group: {getattr(group, 'name', group_id)}")
        cmd.set("Comment", "")
        cmd.set("CmdOnMethod", "GET")
        cmd.set("CmdOffMethod", "GET")
        cmd.set("CmdOn", f"{group_id}=ON")
        cmd.set("CmdOnHTTP", "")
        cmd.set("CmdOnPost", "")
        cmd.set("CmdOff", f"{group_id}=OFF")
        cmd.set("CmdOffHTTP", "")
        cmd.set("CmdOffPost", "")
        cmd.set("CmdAnswer", "")
        cmd.set("Analog", "false")
        cmd.set("Repeat", "0")
        cmd.set("RepeatRate", "0")
        cmd.set("HintText", "")

    # --- Cover commands ---
    covers = manager.covers.get_all_covers()
    for cover_id, cover in covers.items():
        # Open command
        cmd_open = ET.SubElement(vout, "VirtualOutCmd")
        cmd_open.set("Title", f"{cover.name} Open")
        cmd_open.set("Comment", "")
        cmd_open.set("CmdOnMethod", "GET")
        cmd_open.set("CmdOffMethod", "GET")
        cmd_open.set("CmdOn", f"{cover_id}=OPEN")
        cmd_open.set("CmdOnHTTP", "")
        cmd_open.set("CmdOnPost", "")
        cmd_open.set("CmdOff", f"{cover_id}=STOP")
        cmd_open.set("CmdOffHTTP", "")
        cmd_open.set("CmdOffPost", "")
        cmd_open.set("CmdAnswer", "")
        cmd_open.set("Analog", "false")
        cmd_open.set("Repeat", "0")
        cmd_open.set("RepeatRate", "0")
        cmd_open.set("HintText", "")

        # Close command
        cmd_close = ET.SubElement(vout, "VirtualOutCmd")
        cmd_close.set("Title", f"{cover.name} Close")
        cmd_close.set("Comment", "")
        cmd_close.set("CmdOnMethod", "GET")
        cmd_close.set("CmdOffMethod", "GET")
        cmd_close.set("CmdOn", f"{cover_id}=CLOSE")
        cmd_close.set("CmdOnHTTP", "")
        cmd_close.set("CmdOnPost", "")
        cmd_close.set("CmdOff", f"{cover_id}=STOP")
        cmd_close.set("CmdOffHTTP", "")
        cmd_close.set("CmdOffPost", "")
        cmd_close.set("CmdAnswer", "")
        cmd_close.set("Analog", "false")
        cmd_close.set("Repeat", "0")
        cmd_close.set("RepeatRate", "0")
        cmd_close.set("HintText", "")

    # ===========================================================
    # VirtualInUdp (BoneIO → Miniserver)
    # BoneIO sends state updates to Miniserver's send_port
    # Miniserver listens for these on its own UDP port
    # ===========================================================
    vin = ET.Element("VirtualInUdp")
    vin.set("Title", f"boneIO {device_name} Status")
    vin.set("Comment", f"BoneIO {serial} state feedback")
    vin.set("Address", "")
    vin.set("Port", str(send_port))
    vin.set("HintText", "")

    # Info element with template type
    info_in = ET.SubElement(vin, "Info")
    info_in.set("templateType", _TEMPLATE_TYPE_INPUT)
    info_in.set("minVersion", _MIN_VERSION)

    # --- Output state feedback ---
    for output_id, output in outputs.items():
        if output.output_type in ("none", "cover"):
            continue

        vi_cmd = ET.SubElement(vin, "VirtualInUdpCmd")
        vi_cmd.set("Title", f"{output.name}")
        vi_cmd.set("Comment", "")
        vi_cmd.set("Address", boneio_ip)
        # Check pattern: backslash before device_id tells Loxone it's literal
        vi_cmd.set("Check", f"\\{output_id}=\\v")
        vi_cmd.set("Signed", "true")
        vi_cmd.set("Analog", "false")
        vi_cmd.set("SourceValLow", "0")
        vi_cmd.set("DestValLow", "0")
        vi_cmd.set("SourceValHigh", "100")
        vi_cmd.set("DestValHigh", "100")
        vi_cmd.set("DefVal", "0")
        vi_cmd.set("MinVal", "0")
        vi_cmd.set("MaxVal", "1")
        vi_cmd.set("Unit", "")
        vi_cmd.set("HintText", "")

    # --- Cover state feedback (position 0-100) ---
    for cover_id, cover in covers.items():
        vi_cmd = ET.SubElement(vin, "VirtualInUdpCmd")
        vi_cmd.set("Title", f"{cover.name} Position")
        vi_cmd.set("Comment", "")
        vi_cmd.set("Address", boneio_ip)
        vi_cmd.set("Check", f"\\{cover_id}=\\v")
        vi_cmd.set("Signed", "true")
        vi_cmd.set("Analog", "true")
        vi_cmd.set("SourceValLow", "0")
        vi_cmd.set("DestValLow", "0")
        vi_cmd.set("SourceValHigh", "100")
        vi_cmd.set("DestValHigh", "100")
        vi_cmd.set("DefVal", "0")
        vi_cmd.set("MinVal", "0")
        vi_cmd.set("MaxVal", "100")
        vi_cmd.set("Unit", "%")
        vi_cmd.set("HintText", "")

    # --- Input (event/binary_sensor) state feedback ---
    if manager.inputs:
        all_inputs = manager.inputs.get_all_inputs()
        for input_id, input_obj in all_inputs.items():
            vi_cmd = ET.SubElement(vin, "VirtualInUdpCmd")
            vi_cmd.set("Title", f"Input {getattr(input_obj, 'name', input_id)}")
            vi_cmd.set("Comment", "")
            vi_cmd.set("Address", boneio_ip)
            vi_cmd.set("Check", f"\\{input_id}=\\v")
            vi_cmd.set("Signed", "true")
            vi_cmd.set("Analog", "false")
            vi_cmd.set("SourceValLow", "0")
            vi_cmd.set("DestValLow", "0")
            vi_cmd.set("SourceValHigh", "100")
            vi_cmd.set("DestValHigh", "100")
            vi_cmd.set("DefVal", "0")
            vi_cmd.set("MinVal", "0")
            vi_cmd.set("MaxVal", "1")
            vi_cmd.set("Unit", "")
            vi_cmd.set("HintText", "")

    # Generate XML with declaration — two separate documents
    vout_str = _element_to_xml(vout)
    vin_str = _element_to_xml(vin)

    # Combine both as separate XML documents
    return vout_str + "\n\n" + vin_str


def _element_to_xml(element: ET.Element) -> str:
    """Convert an XML element to a pretty-printed string with XML declaration.

    Args:
        element: XML element to serialize.

    Returns:
        Formatted XML string with declaration.
    """
    ET.indent(element, space="\t")
    xml_str = ET.tostring(element, encoding="unicode", xml_declaration=False)
    return f'<?xml version="1.0" encoding="utf-8"?>\n{xml_str}'


def generate_lox_summary(manager: Manager) -> dict[str, Any]:
    """Generate a JSON summary of all available Lox UDP commands.

    This is useful for documentation and debugging — shows exactly
    which commands BoneIO will accept and which status messages it sends.

    Args:
        manager: Active Manager instance.

    Returns:
        Dictionary with 'commands' and 'status' sections.
    """
    serial = manager.config_helper.serial_no or "boneio"
    device_name = manager.config_helper.name or serial

    commands: list[dict[str, str]] = []
    status_messages: list[dict[str, str]] = []

    # Outputs
    outputs = manager.outputs.get_all_outputs()
    for output_id, output in outputs.items():
        if output.output_type in ("none", "cover"):
            continue
        commands.append({
            "entity": output_id,
            "name": output.name,
            "type": output.output_type,
            "cmd_on": f"{output_id}=ON",
            "cmd_off": f"{output_id}=OFF",
        })
        status_messages.append({
            "entity": output_id,
            "name": output.name,
            "type": output.output_type,
            "format": f"{output_id}=ON|OFF",
        })

    # Output groups
    output_groups = manager.outputs.get_all_output_groups()
    for group_id, group in output_groups.items():
        name = getattr(group, "name", group_id)
        commands.append({
            "entity": group_id,
            "name": name,
            "type": "group",
            "cmd_on": f"{group_id}=ON",
            "cmd_off": f"{group_id}=OFF",
        })

    # Covers
    covers = manager.covers.get_all_covers()
    for cover_id, cover in covers.items():
        commands.append({
            "entity": cover_id,
            "name": cover.name,
            "type": "cover",
            "cmd_on": f"{cover_id}=OPEN",
            "cmd_off": f"{cover_id}=CLOSE",
            "cmd_stop": f"{cover_id}=STOP",
        })
        status_messages.append({
            "entity": cover_id,
            "name": cover.name,
            "type": "cover",
            "format": f"{cover_id}=0..100",
        })

    return {
        "device_name": device_name,
        "serial": serial,
        "output_count": len(outputs),
        "cover_count": len(covers),
        "group_count": len(output_groups),
        "commands": commands,
        "status_messages": status_messages,
    }


def _get_lox_config(manager: Manager) -> dict[str, Any]:
    """Extract Lox UDP config from manager's config helper.

    Args:
        manager: Active Manager instance.

    Returns:
        Dictionary with lox_udp configuration values.
    """
    try:
        config = manager.config_helper.get_config()
        lox = config.get("lox_udp", {})
        return {
            "boneio_ip": lox.get("host", "0.0.0.0"),
            "send_port": lox.get("send_port", 4444),
            "listen_port": lox.get("listen_port", 4445),
        }
    except Exception as e:
        _LOGGER.warning("Could not read lox_udp config: %s", e)
        return {
            "boneio_ip": "0.0.0.0",
            "send_port": 4444,
            "listen_port": 4445,
        }
