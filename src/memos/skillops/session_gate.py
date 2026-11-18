"""SessionGate — wrap a MOS instance with accountability and the no-delete rule.

Uses MOSCore's real signatures (MemOS commit e0ef84dd):
  add(messages=None, memory_content=None, doc_path=None, mem_cube_id=None, user_id=None, ...)
  search(query, user_id=None, install_cube_ids=None, top_k=None, mode="fast", ...)
  delete(mem_cube_id, memory_id, user_id=None)          ← hard delete; refused here

Every call emits a SIGNAL opcode and a clock-in/clock-out ledger record. Search results
are re-ranked by Sorter weight; statuses are never changed.
"""

from __future__ import annotations

import time
import uuid

from typing import Any

from .ranking import rank_search_result
from .signal_router import MOSSigCode, SignalRouter


class SessionGate:
    def __init__(
        self,
        mos: Any,
        agent_id: str = "AGT-MOS-0001",
        session_id: str | None = None,
        rerank: bool = True,
    ) -> None:
        self._mos = mos
        self.agent_id = agent_id
        self.session_id = session_id or str(uuid.uuid4())
        self.router = SignalRouter(agent_id, self.session_id)
        self.ledger: list[dict[str, Any]] = []
        self._rerank = rerank
        self._open: dict[str, Any] | None = None

    # ---------------------------------------------------------- session
    def __enter__(self) -> SessionGate:  # noqa: PYI034
        self._open = {
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "clock_in": time.time(),
            "tasks": [],
        }
        self.router.emit(MOSSigCode.MOS_SESSION_START, "session_open", {})
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._open is not None:
            self._open.update(clock_out=time.time(), outcome="error" if exc_type else "ok")
            self.ledger.append(self._open)
            self._open = None
        self.router.emit(
            MOSSigCode.MOS_SESSION_END,
            "session_close",
            {"success_rate": round(self.router.success_rate(), 4)},
        )

    def _task(self, name: str) -> None:
        if self._open is not None:
            self._open["tasks"].append(name)

    # ---------------------------------------------------------- operations
    def add(self, messages=None, memory_content=None, doc_path=None, mem_cube_id=None, **kwargs):
        self._task("mos.add")
        self.router.emit(
            MOSSigCode.MOS_ADD, "add", {"mem_cube_id": mem_cube_id, "messages": len(messages or [])}
        )
        return self._mos.add(
            messages=messages,
            memory_content=memory_content,
            doc_path=doc_path,
            mem_cube_id=mem_cube_id,
            **kwargs,
        )

    def search(self, query: str, **kwargs):
        self._task("mos.search")
        self.router.emit(MOSSigCode.MOS_SEARCH, "search", {"query_len": len(query)})
        result = self._mos.search(query, **kwargs)
        return rank_search_result(result) if self._rerank and isinstance(result, dict) else result

    def delete(self, mem_cube_id: str, memory_id: str, user_id: str | None = None):
        self.router.emit(MOSSigCode.DOCK_DENIED, "delete", {"memory_id": memory_id}, success=False)
        raise PermissionError(
            "DELETE NOTHING: MOS.delete is a hard delete. Archive instead "
            "(GovernedGraphDB turns delete_node into status='archived')."
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._mos, name)
