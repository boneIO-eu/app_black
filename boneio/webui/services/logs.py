"""Log service for BoneIO Web UI."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

from boneio.models.logs import LogEntry

_LOGGER = logging.getLogger(__name__)


def clean_ansi(text: str) -> str:
    """
    Remove ANSI escape sequences from text.
    
    Args:
        text: Text containing ANSI codes.
        
    Returns:
        Clean text without ANSI codes.
    """
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)


def decode_ascii_list(ascii_list: list) -> str:
    """
    Decode a list of ASCII codes into a string and clean ANSI codes.
    
    Args:
        ascii_list: List of ASCII code integers.
        
    Returns:
        Decoded and cleaned string.
    """
    try:
        text = ''.join(chr(code) for code in ascii_list)
        return clean_ansi(text)
    except Exception as e:
        _LOGGER.error(f"Error decoding ASCII list: {e}")
        return str(ascii_list)


def parse_systemd_log_entry(entry: dict) -> dict:
    """
    Parse a systemd journal log entry.
    
    Args:
        entry: Raw journal entry dictionary.
        
    Returns:
        Parsed entry with decoded MESSAGE field.
    """
    if isinstance(entry.get('MESSAGE'), list):
        try:
            decoded_msg = decode_ascii_list(entry['MESSAGE'])
            
            try:
                json_msg = json.loads(decoded_msg)
                if isinstance(json_msg.get('MESSAGE'), list):
                    json_msg['MESSAGE'] = decode_ascii_list(json_msg['MESSAGE'])
                entry['MESSAGE'] = json_msg.get('MESSAGE', decoded_msg)
            except json.JSONDecodeError:
                entry['MESSAGE'] = decoded_msg
            except Exception as e:
                _LOGGER.debug(f"Error parsing nested message: {e}")
                entry['MESSAGE'] = decoded_msg
                
        except Exception as e:
            _LOGGER.error(f"Error parsing message: {e}")
            entry['MESSAGE'] = "Can't decode message"
    
    for ts_field in ('__REALTIME_TIMESTAMP', '__MONOTONIC_TIMESTAMP'):
        if ts_field in entry:
            try:
                entry[ts_field] = int(entry[ts_field])
            except (TypeError, ValueError):
                pass
    
    return entry


def strip_ansi_codes(text: str) -> str:
    """
    Remove ANSI color codes from text.
    
    Args:
        text: Text with potential ANSI codes.
        
    Returns:
        Clean text.
    """
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)


async def get_systemd_logs(since: str = "-15m") -> list[LogEntry]:
    """
    Get logs from journalctl for boneio service.
    
    Args:
        since: Time specification for log retrieval (e.g., "-15m", "-1h").
        
    Returns:
        List of LogEntry objects.
    """
    cmd = [
        "journalctl",
        "-u", "boneio",
        "--no-pager",
        "--no-hostname",
        "--output=json",
        "--output-fields=MESSAGE,__REALTIME_TIMESTAMP,PRIORITY",
        "--no-tail",
        "--since", since
    ]
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await process.communicate()
    if stderr:
        _LOGGER.error(f"Error getting systemd logs: {stderr.decode()}")
    if not stdout.strip():
        return []
    raw_log = json.loads(b'[' + stdout.replace(b'\n', b',')[:-1] + b']')

    log_entries = []
    for log in raw_log:
        if isinstance(log.get('MESSAGE'), list):
            try:
                message_bytes = bytes(log['MESSAGE'])
                message = message_bytes.decode('utf-8', errors='ignore')
                message = strip_ansi_codes(message)
            except Exception as e:
                message = f"Error decoding message: {e}"
        else:
            message = log.get('MESSAGE') or ''
        log_entries.append(
            LogEntry(
                timestamp=str(log.get("__REALTIME_TIMESTAMP") or ""),
                message=message,
                level=str(log.get("PRIORITY") or ""),
            )
        )

    return log_entries


def get_standalone_logs(since: str, limit: int) -> list[LogEntry]:
    """
    Get logs from log file when running standalone (not as systemd service).
    
    Args:
        since: Time specification for filtering logs.
        limit: Maximum number of log entries to return.
        
    Returns:
        List of LogEntry objects.
    """
    log_file = Path("/tmp/boneio.log")
    if not log_file.exists():
        return []

    since_time = None
    if since:
        if since[-1] in ["h", "d"]:
            amount = int(since[:-1])
            unit = since[-1]
            delta = timedelta(hours=amount) if unit == "h" else timedelta(days=amount)
            since_time = datetime.now() - delta
        else:
            try:
                since_time = datetime.fromisoformat(since)
            except ValueError:
                since_time = None

    log_entries = []
    try:
        with open(log_file) as f:
            lines = f.readlines()[-limit:]
            for line in lines:
                try:
                    parts = line.split(" ", 3)
                    if len(parts) >= 4:
                        timestamp_str = f"{parts[0]} {parts[1]}"
                        level = parts[2]
                        message = parts[3].strip()

                        level_map = {
                            "DEBUG": "7",
                            "INFO": "6",
                            "WARNING": "4",
                            "ERROR": "3",
                            "CRITICAL": "2",
                        }

                        if since_time:
                            try:
                                log_time = datetime.strptime(
                                    timestamp_str, "%Y-%m-%d %H:%M:%S"
                                )
                                if log_time < since_time:
                                    continue
                            except ValueError:
                                continue

                        log_entries.append(
                            LogEntry(
                                timestamp=timestamp_str,
                                message=message,
                                level=level_map.get(level.upper(), "6"),
                            )
                        )
                except (IndexError, ValueError):
                    continue
    except Exception as e:
        _LOGGER.warning(f"Error reading log file: {e}")
        return []

    return log_entries


def is_running_as_service() -> bool:
    """
    Check if running as a systemd service.
    
    Returns:
        True if running under systemd.
    """
    try:
        with open("/proc/1/comm") as f:
            return "systemd" in f.read()
    except Exception:
        return False
