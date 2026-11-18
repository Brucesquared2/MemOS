"""GovernedGraphDB — wrap any MemOS BaseGraphDB with the Collective's preservation rules.

Why: three MemOS code paths conflict with the Collective doctrine (observed at MemOS
commit e0ef84dd, see docs/collective_memory/COMPATIBILITY.md):
  1. tree_text_memory/organize/handler.py:146  ``_hard_update`` hard-deletes the older
     of two conflicting memories ("Never fix by deleting" — WG-04).
  2. handler.py ``_resolve_in_graph``          LLM-merges a conflict and archives both
     sides without any Steward decision.
  3. dream/pipeline/persistence.py             writes LLM consolidations straight to
     LongTermMemory with status "activated" (no self-authorization — WG-00/LAW).

The wrapper changes outcomes at the storage boundary, so none of those modules need
editing:
  * delete_node  → node is kept and marked status="archived" (tombstone recorded)
  * delete_edge  → refused (no-op) and recorded; relationships are never erased
  * clear        → raises PermissionError
  * add_node / update_node that would make an *activated LongTermMemory* node without
    passing ``promotion_gate`` → stored as status="resolving" (froth) instead

Everything else is delegated unchanged.
"""

from __future__ import annotations

import time

from collections.abc import Callable
from typing import Any


PROTECTED_TYPES = frozenset({"LongTermMemory", "UserMemory", "SkillMemory", "InsightMemory"})

PromotionGate = Callable[[str, dict[str, Any]], bool]


def ratified_only(node_id: str, metadata: dict[str, Any]) -> bool:
    """Default gate: only nodes promoted (RATIFIED) by the Collective may be activated."""
    info = metadata.get("info") or {}
    return (info.get("collective") or {}).get("authority") == "RATIFIED"


class GovernedGraphDB:
    def __init__(
        self,
        inner: Any,
        promotion_gate: PromotionGate = ratified_only,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._inner = inner
        self._gate = promotion_gate
        self._clock = clock
        self.audit: list[dict[str, Any]] = []

    # ---------------------------------------------------------- preservation
    def delete_node(self, id: str, *args: Any, **kwargs: Any) -> None:
        user_name = kwargs.get("user_name")
        fields = {
            "status": "archived",
            "archived_reason": "delete_node intercepted",
            "archived_at": self._clock(),
        }
        if user_name is not None:
            self._inner.update_node(id, fields, user_name=user_name)
        else:
            self._inner.update_node(id, fields)
        self._record("delete_node→archived", id=id)

    def delete_edge(
        self, source_id: str, target_id: str, type: str, *args: Any, **kwargs: Any
    ) -> None:
        self._record("delete_edge refused", source_id=source_id, target_id=target_id, type=type)

    def clear(self, *args: Any, **kwargs: Any) -> None:
        self._record("clear refused")
        raise PermissionError("GovernedGraphDB: clear() would erase evidence; refused")

    # ---------------------------------------------------------- promotion gate
    def add_node(
        self, id: str, memory: str, metadata: dict[str, Any], *args: Any, **kwargs: Any
    ) -> None:
        metadata = self._gate_metadata(id, dict(metadata))
        self._inner.add_node(id, memory, metadata, *args, **kwargs)

    def add_nodes_batch(self, nodes: list[dict[str, Any]], *args: Any, **kwargs: Any) -> None:
        gated = [
            {**n, "metadata": self._gate_metadata(n["id"], dict(n.get("metadata") or {}))}
            for n in nodes
        ]
        self._inner.add_nodes_batch(gated, *args, **kwargs)

    def update_node(self, id: str, fields: dict[str, Any], *args: Any, **kwargs: Any) -> None:
        fields = dict(fields)
        if fields.get("status") == "activated":
            current = (
                self._inner.get_node(
                    id, **({"user_name": kwargs["user_name"]} if "user_name" in kwargs else {})
                )
                or {}
            )
            merged = {**(current.get("metadata") or {}), **fields}
            if merged.get("memory_type") in PROTECTED_TYPES and not self._gate(id, merged):
                fields["status"] = "resolving"
                self._record("activation held for ratification", id=id)
        self._inner.update_node(id, fields, *args, **kwargs)

    def _gate_metadata(self, id: str, metadata: dict[str, Any]) -> dict[str, Any]:
        if (
            metadata.get("memory_type") in PROTECTED_TYPES
            and metadata.get("status", "activated") == "activated"
            and not self._gate(id, metadata)
        ):
            metadata["status"] = "resolving"
            info = dict(metadata.get("info") or {})
            info.setdefault(
                "collective",
                {"lifecycle": "CANDIDATE", "authority": "UNRATIFIED", "provenance": "DERIVED"},
            )
            metadata["info"] = info
            self._record("activation held for ratification", id=id, source=metadata.get("source"))
        return metadata

    def _record(self, action: str, **detail: Any) -> None:
        self.audit.append({"action": action, "at": self._clock(), **detail})

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)
