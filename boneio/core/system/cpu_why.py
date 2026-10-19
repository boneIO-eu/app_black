"""Why boneIO itself uses the CPU: which thread, and what code it is in.

The answer is a sampling profiler made of the standard library. Per-thread CPU
from ``/proc`` says which thread burns; sampling ``sys._current_frames()`` for
that thread a few dozen times says where. The most frequent stack is the hot
spot.

Stacks of asyncio *tasks* are deliberately not the answer: a task's stack shows
where it is waiting, and a waiting task uses no CPU. The tasks are only
counted, which is enough to catch a reconnect loop or a task that leaks.

Everything except :func:`task_counts` blocks and belongs in a worker thread.
"""

from __future__ import annotations

import asyncio
import sys
import threading
import time
import traceback
from collections import Counter
from dataclasses import asdict, dataclass

import psutil


@dataclass(frozen=True)
class ThreadUsage:
    """One thread of this process and its share of one core."""

    native_id: int
    name: str
    percent: float


def _thread_times() -> dict[int, float]:
    return {t.id: t.user_time + t.system_time for t in psutil.Process().threads()}


def thread_usage(interval: float = 1.0) -> list[ThreadUsage]:
    """Each thread's CPU over *interval* seconds, busiest first. Blocks."""
    before = _thread_times()
    started = time.perf_counter()
    time.sleep(interval)
    after = _thread_times()
    wall = max(time.perf_counter() - started, 1e-6)
    names = {t.native_id: t.name for t in threading.enumerate()}
    usage = [
        ThreadUsage(
            tid,
            names.get(tid, f"tid {tid}"),
            round(100 * (spent - before.get(tid, 0.0)) / wall, 1),
        )
        for tid, spent in after.items()
    ]
    return sorted(usage, key=lambda t: t.percent, reverse=True)


def _short(path: str) -> str:
    for marker in ("/site-packages/", "/boneio/"):
        if marker in path:
            tail = path.rpartition(marker)[2]
            return f"boneio/{tail}" if marker == "/boneio/" else tail
    return path


def hot_stacks(
    native_id: int, samples: int = 20, interval: float = 0.05, depth: int = 6
) -> list[tuple[str, int]]:
    """The stacks a thread was seen in, most frequent first. Blocks.

    Args:
        native_id: The thread's OS id, as :func:`thread_usage` reports it.
        samples: How many times to look.
        interval: Seconds between looks.
        depth: Innermost frames kept per stack.

    Returns:
        ``(stack, count)`` pairs; a stack is one ``file:line function`` per
        line, innermost last. Empty for a thread Python does not know.
    """
    ident = next((t.ident for t in threading.enumerate() if t.native_id == native_id), None)
    if ident is None:
        return []
    seen: Counter[str] = Counter()
    for _ in range(samples):
        frame = sys._current_frames().get(ident)
        if frame is None:
            break
        frames = traceback.extract_stack(frame)[-depth:]
        seen["\n".join(f"{_short(f.filename)}:{f.lineno} {f.name}" for f in frames)] += 1
        time.sleep(interval)
    return seen.most_common()


def task_counts() -> dict[str, int]:
    """Running asyncio tasks per coroutine, the 15 most numerous.

    Must be called on the event loop.
    """
    names = Counter(
        getattr(task.get_coro(), "__qualname__", repr(task.get_coro()))
        for task in asyncio.all_tasks()
    )
    return dict(names.most_common(15))


def explain(interval: float = 1.0) -> dict:
    """Per-thread CPU and, for the busiest thread, where it spends it. Blocks."""
    threads = thread_usage(interval)
    hot = next((t for t in threads if t.percent > 0), None)
    stacks = hot_stacks(hot.native_id) if hot else []
    return {
        "threads": [asdict(t) for t in threads],
        "hot_thread": hot.name if hot else None,
        "stacks": [{"stack": stack, "count": count} for stack, count in stacks],
    }
