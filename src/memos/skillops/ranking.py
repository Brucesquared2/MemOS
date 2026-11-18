"""Sorter-weighted re-ranking of MemOS search results.

Source basis: THE_COLLECTIVE_MASTER_CANON_v1 8-dimension Sorter (authority, relevance,
recency, uniqueness, confidence, relationship, retention, reconstructability);
D12 draft: composite = unweighted mean; "Weighted memory decides what evidence is shown
first." Ranking only reorders; it never changes lifecycle, authority or status.
"""

from __future__ import annotations

from typing import Any

from memos.memories.textual.item import TextualMemoryItem


SORTER_DIMENSIONS = (
    "authority",
    "relevance",
    "recency",
    "uniqueness",
    "confidence",
    "relationship",
    "retention",
    "reconstructability",
)


def sorter_composite(scores: dict[str, float] | None) -> float | None:
    if not scores or any(d not in scores for d in SORTER_DIMENSIONS):
        return None
    return sum(float(scores[d]) for d in SORTER_DIMENSIONS) / len(SORTER_DIMENSIONS)


def _key(item: TextualMemoryItem, sorter_share: float) -> float:
    info = getattr(item.metadata, "info", None) or {}
    comp = sorter_composite((info.get("collective") or {}).get("sorter_scores"))
    sem = getattr(item.metadata, "relativity", None)
    sem = 0.5 if sem is None else float(sem)
    if comp is None:
        return sem
    return sorter_share * comp + (1.0 - sorter_share) * sem


def rank_items(
    items: list[TextualMemoryItem], sorter_share: float = 0.5
) -> list[TextualMemoryItem]:
    """Stable sort, highest first. Items without Sorter scores rank by similarity alone."""
    if not 0.0 <= sorter_share <= 1.0:
        raise ValueError("sorter_share must be in [0, 1]")
    return sorted(items, key=lambda i: _key(i, sorter_share), reverse=True)


def rank_search_result(result: dict[str, Any], sorter_share: float = 0.5) -> dict[str, Any]:
    """Re-rank each bucket of a MOSSearchResult["text_mem"] in place and return it."""
    for bucket in result.get("text_mem", []) or []:
        memories = bucket.get("memories")
        if isinstance(memories, list) and all(isinstance(m, TextualMemoryItem) for m in memories):
            bucket["memories"] = rank_items(memories, sorter_share)
    return result
