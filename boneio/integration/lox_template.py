"""Lox Config Template Generator.

Generates a configuration template for importing into Lox Config software.
The template describes all BoneIO outputs, covers, and sensors as
Virtual UDP Input/Output commands that the Miniserver can use.

The output is an XML file compatible with Lox Config's import mechanism.
"""

from __future__ import annotations

import logging
import uuid
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from boneio.core.manager.manager import Manager

_LOGGER = logging.getLogger(__name__)


def _uuid() -> str:
    """Generate a Loxone-style UUID (lowercase with dashes)."""
    return str(uuid.uuid4())


def generate_lox_template(manager: Manager) -> str:
    """Generate Lox Config XML template from current BoneIO configuration.

    Creates Virtual UDP Output commands (Miniserver → BoneIO) for controlling
    outputs and covers, and Virtual UDP Input commands (BoneIO → Miniserver)
    for receiving state feedback.

    The generated XML can be imported into Lox Config to quickly set up
    communication between a Lox Miniserver and this BoneIO device.

    Args:
        manager: Active Manager instance with initialized outputs/covers.

    Returns:
        XML string ready to be saved as a .xml template file.
    """
    serial = manager.config_helper.serial_no or "boneio"
    device_name = manager.config_helper.name or serial
    topic_prefix = manager.config_helper.topic_prefix or f"boneio/{serial}"

    # Get Lox UDP config (host/ports) from running config
    lox_config = _get_lox_config(manager)
    boneio_ip = lox_config.get("boneio_ip", "0.0.0.0")
    listen_port = lox_config.get("listen_port", 4445)  # BoneIO listens on this
    send_port = lox_config.get("send_port", 4444)  # BoneIO sends to this

    root = ET.Element("LoxConfig")
    root.set("version", "1.0")
    root.set("generator", f"boneio-{serial}")

    # ===========================================================
    # Virtual UDP Output (Miniserver → BoneIO)
    # Miniserver sends commands to BoneIO's listen_port
    # ===========================================================
    vout = ET.SubElement(root, "VirtualOutput")
    vout.set("Title", f"boneIO {device_name}")
    vout.set("Address", f"dev/udp/{boneio_ip}/{listen_port}")
    vout.set("UUID", _uuid())

    # --- Output commands ---
    outputs = manager.outputs.get_all_outputs()
    for output_id, output in outputs.items():
        if output.output_type in ("none", "cover"):
            continue

        cmd = ET.SubElement(vout, "VirtualOutputCommand")
        cmd.set("Title", f"{output.name}")
        cmd.set("UUID", _uuid())
        # BoneIO Lox UDP format: "device_id=ON" / "device_id=OFF"
        cmd.set("CmdOn", f"{output_id}=ON")
        cmd.set("CmdOff", f"{output_id}=OFF")

    # --- Output group commands ---
    output_groups = manager.outputs.get_all_output_groups()
    for group_id, group in output_groups.items():
        cmd = ET.SubElement(vout, "VirtualOutputCommand")
        cmd.set("Title", f"Group: {getattr(group, 'name', group_id)}")
        cmd.set("UUID", _uuid())
        cmd.set("CmdOn", f"{group_id}=ON")
        cmd.set("CmdOff", f"{group_id}=OFF")

    # --- Cover commands ---
    covers = manager.covers.get_all_covers()
    for cover_id, cover in covers.items():
        # Open command
        cmd_open = ET.SubElement(vout, "VirtualOutputCommand")
        cmd_open.set("Title", f"Cover {cover.name} Open")
        cmd_open.set("UUID", _uuid())
        cmd_open.set("CmdOn", f"{cover_id}=OPEN")
        cmd_open.set("CmdOff", f"{cover_id}=STOP")

        # Close command
        cmd_close = ET.SubElement(vout, "VirtualOutputCommand")
        cmd_close.set("Title", f"Cover {cover.name} Close")
        cmd_close.set("UUID", _uuid())
        cmd_close.set("CmdOn", f"{cover_id}=CLOSE")
        cmd_close.set("CmdOff", f"{cover_id}=STOP")

    # ===========================================================
    # Virtual UDP Input (BoneIO → Miniserver)
    # BoneIO sends state updates to Miniserver's send_port
    # ===========================================================
    vin = ET.SubElement(root, "VirtualInput")
    vin.set("Title", f"boneIO {device_name} Status")
    vin.set("Address", f"dev/udp/{boneio_ip}/{send_port}")
    vin.set("UUID", _uuid())

    # --- Output state feedback ---
    for output_id, output in outputs.items():
        if output.output_type in ("none", "cover"):
            continue

        vi_cmd = ET.SubElement(vin, "VirtualInputCommand")
        vi_cmd.set("Title", f"{output.name}")
        vi_cmd.set("UUID", _uuid())
        # Recognition pattern: "output_id=\v"
        # \v captures the value (ON/OFF → 1/0 in Loxone)
        vi_cmd.set("CmdRecognition", f"{output_id}=\\v")
        vi_cmd.set("Type", "Digital")

    # --- Cover state feedback ---
    for cover_id, cover in covers.items():
        vi_cmd = ET.SubElement(vin, "VirtualInputCommand")
        vi_cmd.set("Title", f"Cover {cover.name} Position")
        vi_cmd.set("UUID", _uuid())
        vi_cmd.set("CmdRecognition", f"{cover_id}=\\v")
        vi_cmd.set("Type", "Analog")

    # Pretty-print
    ET.indent(root, space="  ")
    xml_str = ET.tostring(root, encoding="unicode", xml_declaration=True)
    return xml_str


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
        config = manager.config_helper.reload_config()
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
