"""Config changes an agent proposed, waiting for an administrator.

A key in the ``propose`` scope cannot save; it files the section it would
have saved, already validated, and a person approves or rejects it in the
panel. They are kept in ``proposals.json`` beside the config, so a restart
does not lose them, and a proposal nobody looks at expires.
"""

from __future__ import annotations

import json
import logging
import secrets
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from boneio.core.atomic_file import write_atomically

_LOGGER = logging.getLogger(__name__)

PROPOSALS_FILENAME = "proposals.json"
#: A queue an agent fills faster than anyone reads is refused, not grown.
MAX_PENDING = 20
LIFETIME = timedelta(days=14)
MAX_RATIONALE = 2000


class ProposalError(Exception):
    """A proposal could not be filed, found or stored."""


@dataclass(slots=True)
class Proposal:
    id: str
    section: str
    data: Any
    rationale: str
    author: str
    created_at: str
    #: Digest of the section when the proposal was made: approving one made
    #: against an older section would undo what changed since.
    base: str


def _now() -> datetime:
    return datetime.now(UTC)


class ProposalStore:
    """Loads, prunes and persists pending proposals."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._items: dict[str, Proposal] = {}
        self._stamp: tuple[int, int] | None = None
        self._loaded = False
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        return self._path

    def _file_stamp(self) -> tuple[int, int] | None:
        try:
            info = self._path.stat()
        except OSError:
            return None
        return (info.st_mtime_ns, info.st_size)

    def _ensure_loaded(self) -> None:
        stamp = self._file_stamp()
        if not (self._loaded and stamp == self._stamp):
            items: dict[str, Proposal] = {}
            if stamp is not None:
                try:
                    raw = json.loads(self._path.read_text(encoding="utf-8"))
                    for entry in raw.get("proposals", []):
                        items[entry["id"]] = Proposal(**entry)
                except (OSError, ValueError, TypeError, KeyError) as err:
                    _LOGGER.error("Cannot read %s, pending proposals are dropped: %s", self._path, err)
            self._items, self._stamp, self._loaded = items, stamp, True
        cutoff = _now() - LIFETIME
        expired = [p.id for p in self._items.values() if datetime.fromisoformat(p.created_at) < cutoff]
        if expired:
            for proposal_id in expired:
                del self._items[proposal_id]
            self._save()

    def _save(self) -> None:
        payload = {"version": 1, "proposals": [asdict(p) for p in self._items.values()]}
        try:
            write_atomically(self._path, json.dumps(payload, indent=2), mode=0o600)
        except OSError as err:
            raise ProposalError(f"Cannot write {self._path}: {err}") from err
        self._stamp = self._file_stamp()

    def list(self) -> list[Proposal]:
        with self._lock:
            self._ensure_loaded()
            return sorted(self._items.values(), key=lambda p: p.created_at)

    def get(self, proposal_id: str) -> Proposal:
        with self._lock:
            self._ensure_loaded()
            try:
                return self._items[proposal_id]
            except KeyError:
                raise ProposalError("There is no such proposal.") from None

    def add(self, section: str, data: Any, rationale: str, author: str, base: str) -> Proposal:
        """File a proposal.

        Raises:
            ProposalError: When the queue is full or the file cannot be written.
        """
        proposal = Proposal(
            id=secrets.token_hex(4),
            section=section,
            data=data,
            rationale=(rationale or "").strip()[:MAX_RATIONALE],
            author=author,
            created_at=_now().isoformat(timespec="seconds"),
            base=base,
        )
        with self._lock:
            self._ensure_loaded()
            if len(self._items) >= MAX_PENDING:
                raise ProposalError(
                    f"{MAX_PENDING} proposals are already waiting; the controller's "
                    "administrator has to review them first."
                )
            self._items[proposal.id] = proposal
            self._save()
        _LOGGER.info("Proposal %s for '%s' filed by %s", proposal.id, section, author)
        return proposal

    def remove(self, proposal_id: str) -> Proposal:
        """Take a proposal out of the queue, approved or rejected.

        Raises:
            ProposalError: If there is no such proposal.
        """
        with self._lock:
            self._ensure_loaded()
            proposal = self._items.pop(proposal_id, None)
            if proposal is None:
                raise ProposalError("There is no such proposal.")
            self._save()
        return proposal
