"""Deterministic 12-bit opcodes for MemOS operations (no LLM in the routing path).

Codes mirror SuperAGI ``superagi/mem0/signal_lang.py`` (CANDIDATE table; the
authoritative SIGNAL-LANG wire format lives in the SIGNAL-LANG project). Verified
SIGNAL event names from harvest_payload_layout_v1 are carried as ``event_type``.
"""

from __future__ import annotations

from enum import IntEnum
from typing import TYPE_CHECKING, Any, NamedTuple

from memos.log import get_logger


if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger(__name__)


class MOSSigCode(IntEnum):
    MOS_ADD = 0x100
    MOS_SEARCH = 0x101
    MOS_ARCHIVE = 0x103
    MOS_SESSION_START = 0x400
    MOS_SESSION_END = 0x401
    CONTRIBUTION_SUBMITTED = 0x603  # event_type "warehouse.contribute"
    CONTRIBUTION_PROMOTED = 0x605  # event_type "warehouse.promote" (Steward only)
    MEMORY_RETRIEVED = 0x607
    DOCK_DENIED = 0x608
    MOS_FAULT = 0x900


class RouteRecord(NamedTuple):
    signal_code: int
    operation: str
    agent_id: str
    session_id: str
    success: bool
    payload: dict[str, Any]


class SignalRouter:
    def __init__(
        self,
        agent_id: str = "AGT-MOS-0001",
        session_id: str = "mos-session",
        sink: Callable[[RouteRecord], None] | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.session_id = session_id
        self._sink = sink
        self._audit: list[RouteRecord] = []

    def emit(
        self, code: MOSSigCode, operation: str, payload: dict[str, Any], success: bool = True
    ) -> RouteRecord:
        record = RouteRecord(int(code), operation, self.agent_id, self.session_id, success, payload)
        self._audit.append(record)
        if self._sink is not None:
            try:
                self._sink(record)
            except Exception:
                logger.exception("signal sink failed for %s", operation)
        return record

    def audit(self, limit: int = 50) -> list[dict[str, Any]]:
        return [{**r._asdict(), "signal_code": hex(r.signal_code)} for r in self._audit[-limit:]]

    def success_rate(self) -> float:
        return sum(r.success for r in self._audit) / len(self._audit) if self._audit else 1.0
