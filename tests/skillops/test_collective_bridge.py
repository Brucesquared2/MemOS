"""Collective-memory bridge: MemOS stays a derived store; nothing is erased or self-promoted."""

from datetime import datetime, timedelta

import pytest

from memos.memories.textual.item import TextualMemoryItem, TreeNodeTextualMemoryMetadata
from memos.memories.textual.tree_text_memory.organize.handler import NodeHandler
from memos.skillops import (
    GovernedGraphDB,
    SessionGate,
    contribution_to_item,
    item_collective_view,
    rank_items,
)


class FakeGraph:
    """Minimal in-memory stand-in for a BaseGraphDB backend."""

    def __init__(self):
        self.nodes, self.edges, self.deleted = {}, set(), []

    def add_node(self, id, memory, metadata, user_name=None):
        self.nodes[id] = {"id": id, "memory": memory, "metadata": dict(metadata)}

    def add_nodes_batch(self, nodes, user_name=None):
        for n in nodes:
            self.add_node(n["id"], n["memory"], n["metadata"])

    def update_node(self, id, fields, user_name=None):
        self.nodes[id]["metadata"].update(fields)

    def get_node(self, id, include_embedding=False, **kw):
        return self.nodes.get(id)

    def delete_node(self, id, user_name=None):
        self.deleted.append(id)
        self.nodes.pop(id)

    def add_edge(self, s, t, type, user_name=None):
        self.edges.add((s, t, type))

    def delete_edge(self, s, t, type, user_name=None):
        self.edges.discard((s, t, type))

    def clear(self):
        self.nodes.clear()


VIEW = {
    "contribution_id": "CONTRIB-001",
    "anchor_id": "ANCHOR-NVME",
    "claim_key": "hot_tier_capacity",
    "claim": "SYN-01 hot tier is 3x2TB NVMe",
    "lifecycle": "CANDIDATE",
    "authority": "UNRATIFIED",
    "provenance": "DERIVED",
    "contributor": "AGT-HARV-SYN",
    "evidence_refs": ["a" * 64],
    "verifications": [],
    "promoted_by": None,
    "superseded_by": None,
    "conflicts_with": [],
    "valid_until": None,
    "evidence": [{"digest": "a" * 64, "source_ref": "synthetic://syn-01.txt"}],
}


def _item(text, minutes_ago):
    ts = (datetime.now() - timedelta(minutes=minutes_ago)).isoformat()
    return TextualMemoryItem(
        memory=text,
        metadata=TreeNodeTextualMemoryMetadata(memory_type="LongTermMemory", updated_at=ts),
    )


def test_contribution_maps_without_status_upgrade():
    item = contribution_to_item(VIEW)
    assert (item.metadata.memory_type, item.metadata.status) == ("WorkingMemory", "resolving")
    assert item.metadata.sources[0].doc_path == "synthetic://syn-01.txt"
    assert item_collective_view(item)["authority"] == "UNRATIFIED"
    # lifecycle says PROMOTED but authority is not RATIFIED → still not activated
    forged = contribution_to_item({**VIEW, "lifecycle": "PROMOTED"})
    assert forged.metadata.status == "resolving"
    real = contribution_to_item({**VIEW, "lifecycle": "PROMOTED", "authority": "RATIFIED"})
    assert (real.metadata.memory_type, real.metadata.status) == ("LongTermMemory", "activated")
    assert contribution_to_item(VIEW).id == item.id  # stable identity across projections


def test_native_memos_items_default_to_unratified():
    assert item_collective_view(_item("x", 0))["authority"] == "UNRATIFIED"


def test_memos_hard_update_no_longer_deletes():
    """Real MemOS NodeHandler._hard_update (handler.py:146) through the governed wrapper."""
    raw = FakeGraph()
    old, new = _item("hot tier is 3x2TB", 10), _item("hot tier is 2x4TB", 1)
    for it in (old, new):
        raw.add_node(it.id, it.memory, it.metadata.model_dump())
    NodeHandler(GovernedGraphDB(raw), llm=None, embedder=None)._hard_update(old, new)
    assert raw.deleted == []
    assert raw.nodes[old.id]["metadata"]["status"] == "archived"
    assert raw.nodes[new.id]["memory"] == "hot tier is 2x4TB"

    unguarded = FakeGraph()  # control: without the wrapper MemOS erases the older memory
    for it in (old, new):
        unguarded.add_node(it.id, it.memory, it.metadata.model_dump())
    NodeHandler(unguarded, llm=None, embedder=None)._hard_update(old, new)
    assert unguarded.deleted == [old.id]


def test_dream_style_write_is_held_for_ratification():
    raw = FakeGraph()
    g = GovernedGraphDB(raw)
    # exactly the metadata shape dream/pipeline/persistence.py writes
    g.add_node(
        "dream_mem_1",
        "consolidated insight",
        {"memory_type": "LongTermMemory", "status": "activated", "source": "dream"},
    )
    assert raw.nodes["dream_mem_1"]["metadata"]["status"] == "resolving"
    assert raw.nodes["dream_mem_1"]["metadata"]["info"]["collective"]["authority"] == "UNRATIFIED"
    g.update_node("dream_mem_1", {"status": "activated"})
    assert raw.nodes["dream_mem_1"]["metadata"]["status"] == "resolving"
    ratified = contribution_to_item({**VIEW, "lifecycle": "PROMOTED", "authority": "RATIFIED"})
    g.add_node(ratified.id, ratified.memory, ratified.metadata.model_dump())
    assert raw.nodes[ratified.id]["metadata"]["status"] == "activated"
    assert [a["action"] for a in g.audit].count("activation held for ratification") == 2


def test_edges_and_store_cannot_be_erased():
    raw = FakeGraph()
    g = GovernedGraphDB(raw)
    raw.add_edge("a", "b", "SUPPORTS")
    g.delete_edge("a", "b", "SUPPORTS")
    assert ("a", "b", "SUPPORTS") in raw.edges
    with pytest.raises(PermissionError):
        g.clear()
    assert g.add_edge is not None  # other methods delegate


def test_ranking_orders_but_never_changes_status():
    low = contribution_to_item(
        {**VIEW, "contribution_id": "C-LOW"},
        sorter_scores=dict.fromkeys(
            (
                "authority",
                "relevance",
                "recency",
                "uniqueness",
                "confidence",
                "relationship",
                "retention",
                "reconstructability",
            ),
            0.1,
        ),
    )
    high = contribution_to_item(
        {**VIEW, "contribution_id": "C-HIGH"},
        sorter_scores=dict.fromkeys(
            (
                "authority",
                "relevance",
                "recency",
                "uniqueness",
                "confidence",
                "relationship",
                "retention",
                "reconstructability",
            ),
            1.0,
        ),
    )
    ranked = rank_items([low, high])
    assert [item_collective_view(i)["contribution_id"] for i in ranked] == ["C-HIGH", "C-LOW"]
    assert all(i.metadata.status == "resolving" for i in ranked)


def test_session_gate_uses_real_signatures_and_refuses_delete():
    calls = []

    class FakeMOS:
        def add(self, messages=None, memory_content=None, doc_path=None, mem_cube_id=None, **kw):
            calls.append(("add", mem_cube_id, memory_content))

        def search(self, query, **kw):
            return {"text_mem": [{"cube_id": "c", "memories": []}], "act_mem": [], "para_mem": []}

        def delete(self, mem_cube_id, memory_id, user_id=None):
            calls.append(("delete", memory_id))

    with SessionGate(FakeMOS()) as gate:
        gate.add(memory_content="note", mem_cube_id="cube-1")
        assert gate.search("nvme")["text_mem"][0]["memories"] == []
        with pytest.raises(PermissionError):
            gate.delete("cube-1", "mem-1")
    assert calls == [("add", "cube-1", "note")]
    assert gate.ledger[0]["tasks"] == ["mos.add", "mos.search"]
