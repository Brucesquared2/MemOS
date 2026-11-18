# Collective memory bridge (`memos.skillops`)

Status: **CANDIDATE**, opt-in. Part of CWCP-MEMORY-INTEGRATION-001. The full package is
in the SuperAGI repository at `docs/collective_memory/`, on the same branch.

In this design MemOS is a **derived, rebuildable store and retrieval engine**. Authority
lives in the Collective's append-only evidence ledger (SuperAGI
`superagi/mem0/collective/`). MemOS holds projections of it.

| Module | Purpose |
|---|---|
| `collective_bridge` | Converts a Collective contribution view to a `TextualMemoryItem`. Only PROMOTED + RATIFIED becomes `LongTermMemory/activated`. Everything else is `WorkingMemory/resolving` or `archived`. Lifecycle, authority, provenance and evidence travel in `metadata.info["collective"]`. |
| `governed_graph.GovernedGraphDB` | Wraps any `BaseGraphDB`. `delete_node` → `status=archived`; `delete_edge` refused; `clear` raises; activated writes to protected memory types are held as `resolving` unless ratified. |
| `ranking` | Re-ranks search results by the 8-dimension Sorter composite. Orders only; never changes status. |
| `session_gate.SessionGate` | Wraps `MOS` with the real `add/search/delete` signatures, emits signal opcodes, records clock-in/clock-out, and refuses hard `delete`. |
| `signal_router` | Deterministic 12-bit opcodes (CANDIDATE table). |

## MemOS behaviours this addresses (observed at `e0ef84d`)

1. `tree_text_memory/organize/handler.py:146`: `_hard_update` hard-deletes the older of two
   conflicting memories. Behind `GovernedGraphDB` that memory is archived instead. Tested
   against the real `NodeHandler`, with a control test showing the deletion happens
   without the wrapper.
2. `handler.py` `_resolve_in_graph`: LLM-merges conflicts. Deletion is prevented, but the
   automatic merge remains. Disable it for institutional cubes.
3. `dream/pipeline/persistence.py`: writes consolidations straight into `LongTermMemory` as
   `activated`. Behind the wrapper these writes are held as `resolving` until the
   Collective ratifies them.

```python
from memos.skillops import GovernedGraphDB, SessionGate
graph_store = GovernedGraphDB(existing_graph_db)   # pass wherever MemOS takes a graph_store
with SessionGate(mos) as gate:
    gate.add(memory_content="…", mem_cube_id="cube-1")
    results = gate.search("nvme")
```

Tests: `python -m pytest tests/skillops -q` (7 passed).
