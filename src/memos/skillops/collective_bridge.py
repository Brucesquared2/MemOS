"""Map Collective contributions onto MemOS TextualMemoryItems — without upgrading status.

Collective lifecycle (WG-00, CANDIDATE)   ->  MemOS memory_type / status
  PROMOTED   (RATIFIED)                    ->  LongTermMemory / activated
  CANDIDATE, HELD, CONFLICT (froth)        ->  WorkingMemory  / resolving
  SUPERSEDED (kept, never erased)          ->  LongTermMemory / archived

Every item carries ``metadata.info["collective"]`` with lifecycle, authority, provenance,
contributor and evidence digests, so a claim never travels without its status. An item
that has no collective block is treated as UNRATIFIED / DERIVED.
"""

from __future__ import annotations

import uuid

from typing import Any

from memos.memories.textual.item import (
    SourceMessage,
    TextualMemoryItem,
    TreeNodeTextualMemoryMetadata,
)


_NAMESPACE = uuid.UUID("6f2b1d3e-9c41-4a8e-8f0e-c011ec7e0001")

_STATUS: dict[str, tuple[str, str]] = {
    "PROMOTED": ("LongTermMemory", "activated"),
    "SUPERSEDED": ("LongTermMemory", "archived"),
    "CANDIDATE": ("WorkingMemory", "resolving"),
    "HELD": ("WorkingMemory", "resolving"),
    "CONFLICT": ("WorkingMemory", "resolving"),
}

UNRATIFIED_DEFAULT = {"lifecycle": "CANDIDATE", "authority": "UNRATIFIED", "provenance": "DERIVED"}


def memos_status_for(lifecycle: str, authority: str) -> tuple[str, str]:
    memory_type, status = _STATUS.get(lifecycle, ("WorkingMemory", "resolving"))
    if status == "activated" and authority != "RATIFIED":
        return "WorkingMemory", "resolving"  # never upgrade an unratified claim
    return memory_type, status


def item_id_for(contribution_id: str) -> str:
    """MemOS ids must be UUIDs; derive a stable one from the contribution id."""
    return str(uuid.uuid5(_NAMESPACE, contribution_id))


def contribution_to_item(
    view: dict[str, Any],
    evidence: list[dict[str, Any]] | None = None,
    sorter_scores: dict[str, float] | None = None,
) -> TextualMemoryItem:
    """`view` is Contribution.view() / a Librarian context entry from the Collective.

    `sorter_scores` (the anchor's 8 Sorter dimensions) only affect ranking order.
    """
    memory_type, status = memos_status_for(view["lifecycle"], view["authority"])
    evidence = evidence if evidence is not None else view.get("evidence", [])
    sources = [
        SourceMessage(type="doc", doc_path=e.get("source_ref"), content=e.get("digest"))
        for e in evidence
    ] or None
    collective = {
        k: view.get(k)
        for k in (
            "contribution_id",
            "anchor_id",
            "claim_key",
            "lifecycle",
            "authority",
            "provenance",
            "contributor",
            "evidence_refs",
            "verifications",
            "promoted_by",
            "superseded_by",
            "conflicts_with",
            "valid_until",
        )
    }
    if sorter_scores:
        collective["sorter_scores"] = dict(sorter_scores)
    metadata = TreeNodeTextualMemoryMetadata(
        memory_type=memory_type,
        status=status,
        key=view.get("claim_key"),
        tags=[view["anchor_id"]] if view.get("anchor_id") else None,
        source="system",
        sources=sources,
        info={"collective": collective},
    )
    return TextualMemoryItem(
        id=item_id_for(view["contribution_id"]), memory=view["claim"], metadata=metadata
    )


def item_collective_view(item: TextualMemoryItem) -> dict[str, Any]:
    info = getattr(item.metadata, "info", None) or {}
    block = info.get("collective")
    if not block:
        return {**UNRATIFIED_DEFAULT, "contribution_id": None, "origin": "memos-native"}
    return dict(block)
