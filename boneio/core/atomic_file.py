"""Replace a file's content without ever leaving half of it on disk.

The controller has no UPS and runs from an SD card or eMMC. A plain
``open(path, "w")`` truncates the file first, so power lost during the write
leaves ``config.yaml`` cut short — and a controller that no longer boots.
Writing next to the target and renaming over it means a reader, or the next
boot, sees either the old file or the new one, never a mix.

Kept free of heavy imports: the recovery app uses it too.
"""

from __future__ import annotations

import glob
import os
import tempfile
import time
from pathlib import Path


#: A temp file this old was left by a writer that died: a save takes well
#: under a second, and one still running must not lose its file.
_STALE_TEMP_SECONDS = 60
#: What tempfile.mkstemp appends to the prefix.
_TEMP_SUFFIX_LEN = 8


def _remove_stale_temps(target: Path) -> None:
    """Delete temp files left by writes that never reached the rename.

    Nothing can clean up after a power cut or SIGKILL mid-write, so without
    this they pile up in the config directory, one per interrupted save.
    """
    prefix = f".{target.name}."
    cutoff = time.time() - _STALE_TEMP_SECONDS
    try:
        candidates = list(target.parent.glob(f"{glob.escape(prefix)}*"))
    except OSError:
        return
    for candidate in candidates:
        if len(candidate.name) != len(prefix) + _TEMP_SUFFIX_LEN:
            continue
        try:
            if candidate.lstat().st_mtime < cutoff:
                candidate.unlink()
        except OSError:
            continue


def _new_file_mode() -> int:
    """What ``open(path, "w")`` would have given a new file under our umask.

    Read from /proc rather than with os.umask(), which can only be read by
    setting it, and would briefly change it for every other thread.
    """
    try:
        with open("/proc/self/status", encoding="ascii") as f:
            for line in f:
                if line.startswith("Umask:"):
                    return 0o666 & ~int(line.split()[1], 8)
    except (OSError, ValueError, IndexError):
        pass
    return 0o644


def write_atomically(
    path: str | os.PathLike[str], content: str | bytes, mode: int | None = None
) -> None:
    """Write ``content`` to ``path`` atomically.

    Keeps the original's permission bits: an included file that holds a broker
    password is often 0600, and a rewrite must not widen that. A symlink is
    followed, so the file it points to is replaced rather than the link.

    Args:
        path: File to write. Its directory must exist.
        content: New content; ``str`` is written as UTF-8.
        mode: Permission bits to set. Defaults to the existing file's, or what
            the process umask gives a new one.
    """
    target = Path(os.path.realpath(path))
    if mode is None:
        try:
            mode = target.stat().st_mode & 0o777
        except FileNotFoundError:
            mode = _new_file_mode()

    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content.encode("utf-8") if isinstance(content, str) else content)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise

    _remove_stale_temps(target)

    # The rename lives in the directory entry; without this a power cut right
    # after it can still bring back the old file.
    try:
        dir_fd = os.open(target.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        os.close(dir_fd)
