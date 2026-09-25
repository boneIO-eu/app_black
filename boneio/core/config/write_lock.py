"""One lock for every read-modify-write of the configuration files.

Each save reads a whole file, edits it in memory and writes it back. Two of
them running side by side — a section save from the panel in an executor
thread and a password change in another — each write back the file as they
read it, and the later one silently undoes the earlier.

Reentrant, so a route can hold it across a read, a backup and a write while
the functions it calls take it again.
"""

from __future__ import annotations

import threading

CONFIG_WRITE_LOCK = threading.RLock()
