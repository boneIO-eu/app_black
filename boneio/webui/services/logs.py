"""Log service for BoneIO Web UI."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
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
            with contextlib.suppress(TypeError, ValueError):
                entry[ts_field] = int(entry[ts_field])
    
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


def _timestamp_to_journalctl(ts: str) -> str:
    """Convert a microsecond or ISO timestamp to journalctl-compatible format.
    
    Args:
        ts: Timestamp string (microseconds or ISO format).
        
    Returns:
        Date string in 'YYYY-MM-DD HH:MM:SS' format.
    """
    try:
        us = int(ts)
        return datetime.fromtimestamp(us / 1_000_000).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError, OSError):
        return ts


async def _run_journalctl(
    service_name: str,
    limit: int = 200,
    before: str | None = None,
    priority: str | None = None,
    since: str | None = None,
    until: str | None = None,
    grep: str | None = None,
) -> bytes | None:
    """Run journalctl for a specific service name with cursor-based pagination.
    
    Args:
        service_name: Systemd unit name (e.g., 'BoneIO', 'boneio').
        limit: Maximum number of entries to return.
        before: Microsecond timestamp cursor — return entries older than this.
        priority: journalctl priority filter (e.g. '3' for err, '0..4' for range).
        since: Start of date range filter (ISO or microsecond timestamp).
        until: End of date range filter (ISO or microsecond timestamp).
        grep: Text search filter (case-insensitive regex passed to journalctl --grep).
        
    Returns:
        stdout bytes if logs found, None otherwise.
    """
    cmd = [
        "journalctl",
        "-u", service_name,
        "--no-pager",
        "--no-hostname",
        "--output=json",
        "--output-fields=MESSAGE,__REALTIME_TIMESTAMP,PRIORITY",
        "--reverse",
        "-n", str(limit),
    ]
    if priority:
        cmd.extend(["--priority", priority])
    if grep:
        cmd.extend(["--grep", grep, "--case-sensitive=no"])
    # Date range takes precedence over cursor-based 'before'
    if since:
        cmd.extend(["--since", _timestamp_to_journalctl(since)])
    if until:
        cmd.extend(["--until", _timestamp_to_journalctl(until)])
    elif before:
        # Subtract 1 second to avoid returning the same boundary entry
        try:
            before_us = int(before)
            before_dt = datetime.fromtimestamp(before_us / 1_000_000) - timedelta(seconds=1)
            before_str = before_dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError, OSError):
            before_str = before
        cmd.extend(["--until", before_str])
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if stderr:
            _LOGGER.debug("journalctl stderr for %s: %s", service_name, stderr.decode().strip())
        if stdout and stdout.strip():
            return stdout
    except Exception as e:
        _LOGGER.debug("Error running journalctl for %s: %s", service_name, e)
    return None


async def get_systemd_logs(
    limit: int = 200,
    before: str | None = None,
    priority: str | None = None,
    since: str | None = None,
    until: str | None = None,
    grep: str | None = None,
) -> tuple[list[LogEntry], bool]:
    """
    Get logs from journalctl for boneio service with cursor-based pagination.
    
    Tries multiple service name variants (BoneIO, boneio) since
    the systemd unit name is case-sensitive.
    
    Args:
        limit: Maximum number of entries to return.
        before: Microsecond timestamp cursor — return entries older than this.
        priority: journalctl priority filter (e.g. '3' for err, '0..4' for range).
        since: Start of date range filter.
        until: End of date range filter.
        grep: Text search filter (case-insensitive).
        
    Returns:
        Tuple of (list of LogEntry objects, has_more flag).
    """
    # Fetch one extra to detect if there are more entries
    fetch_limit = limit + 1
    
    # Try multiple service names — systemd unit name is case-sensitive
    service_names = ["BoneIO", "boneio"]
    
    for service_name in service_names:
        stdout = await _run_journalctl(
            service_name, fetch_limit, before, priority, since, until, grep
        )
        if stdout:
            break
    else:
        _LOGGER.warning("No logs found for any boneio service variant: %s", service_names)
        return [], False
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

    # --reverse gives newest first, we want chronological order
    log_entries.reverse()

    has_more = len(log_entries) > limit
    if has_more:
        # Remove the extra entry (oldest one, now first after reverse)
        log_entries = log_entries[1:]

    return log_entries, has_more


def _parse_standalone_timestamp(ts: str) -> datetime | None:
    """Parse a timestamp string from standalone log file or API parameter.
    
    Args:
        ts: Timestamp string in ISO or 'YYYY-MM-DD HH:MM:SS' format.
        
    Returns:
        datetime object or None if parsing fails.
    """
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        pass
    try:
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def get_standalone_logs(
    limit: int = 200,
    before: str | None = None,
    since: str | None = None,
    until: str | None = None,
    grep: str | None = None,
) -> tuple[list[LogEntry], bool]:
    """
    Get logs from log file when running standalone (not as systemd service).
    
    Uses cursor-based pagination. Returns the last `limit` entries
    that are older than `before` timestamp, optionally filtered by date range
    and text search.
    
    Args:
        limit: Maximum number of log entries to return.
        before: Timestamp cursor — return entries older than this.
        since: Start of date range filter.
        until: End of date range filter.
        grep: Text search filter (case-insensitive substring match).
        
    Returns:
        Tuple of (list of LogEntry objects, has_more flag).
    """
    log_file = Path("/tmp/boneio.log")
    if not log_file.exists():
        return [], False

    before_time = _parse_standalone_timestamp(before) if before else None
    since_time = _parse_standalone_timestamp(since) if since else None
    until_time = _parse_standalone_timestamp(until) if until else None
    grep_lower = grep.lower() if grep else None

    level_map = {
        "DEBUG": "7",
        "INFO": "6",
        "WARNING": "4",
        "ERROR": "3",
        "CRITICAL": "2",
    }

    all_entries = []
    try:
        with open(log_file) as f:
            for line in f:
                try:
                    parts = line.split(" ", 3)
                    if len(parts) >= 4:
                        timestamp_str = f"{parts[0]} {parts[1]}"
                        level = parts[2]
                        message = parts[3].strip()

                        try:
                            log_time = datetime.strptime(
                                timestamp_str, "%Y-%m-%d %H:%M:%S"
                            )
                        except ValueError:
                            continue

                        if before_time and log_time >= before_time:
                            continue
                        if since_time and log_time < since_time:
                            continue
                        if until_time and log_time > until_time:
                            continue
                        if grep_lower and grep_lower not in message.lower():
                            continue

                        all_entries.append(
                            LogEntry(
                                timestamp=timestamp_str,
                                message=message,
                                level=level_map.get(level.upper(), "6"),
                            )
                        )
                except (IndexError, ValueError):
                    continue
    except Exception as e:
        _LOGGER.warning("Error reading log file: %s", e)
        return [], False

    # Take last `limit` entries (newest)
    has_more = len(all_entries) > limit
    return all_entries[-limit:], has_more


def is_running_as_service() -> bool:
    """
    Check if the current process is running as a systemd service.

    Uses the INVOCATION_ID environment variable which systemd sets
    for processes it manages.
    
    Returns:
        True if running as a systemd service.
    """
    return bool(os.environ.get("INVOCATION_ID"))
