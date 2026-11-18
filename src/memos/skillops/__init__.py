"""SkillOps / Collective-memory bridge for MemOS — CWCP-MEMORY-INTEGRATION-001.

MemOS is used as a *derived* graph store and retrieval engine underneath the
Collective's governed memory (SuperAGI ``superagi/mem0/collective``). Authority stays in
the Collective's append-only ledger; MemOS holds rebuildable projections.

Modules:
  collective_bridge  contribution view  <->  TextualMemoryItem (status never upgraded)
  governed_graph     GovernedGraphDB: wraps any BaseGraphDB so nothing is hard-deleted
                     and nothing becomes activated LongTermMemory without ratification
  ranking            Sorter-weighted re-ranking (orders results; never changes status)
  signal_router      deterministic 12-bit opcodes for MOS operations
  session_gate       wraps a MOS instance with the real add/search/delete signatures

STATUS: CANDIDATE. Opt-in; importing this package changes no MemOS behaviour.
"""

from .collective_bridge import contribution_to_item, item_collective_view, memos_status_for
from .governed_graph import GovernedGraphDB, ratified_only
from .ranking import rank_items, sorter_composite
from .session_gate import SessionGate
from .signal_router import MOSSigCode, SignalRouter


__all__ = [
    "GovernedGraphDB",
    "MOSSigCode",
    "SessionGate",
    "SignalRouter",
    "contribution_to_item",
    "item_collective_view",
    "memos_status_for",
    "rank_items",
    "ratified_only",
    "sorter_composite",
]
