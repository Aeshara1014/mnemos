"""With unjudged links off, the night links only what a model judged.

Found on a copy of Quill's store (Nov 7 2026): every afternoon the shallow
pass (no model) linked the same five recently recalled memories, 27 links,
and every morning the re-sort's model read them, said they didn't belong, and
removed all 27. Since Oct 19 that loop took nearly every re-sort call, so the
older unjudged links were never sorted. Tara's word: judged links only. The
engine's default is unchanged; the house turns it off.
"""

from __future__ import annotations

from mnemos.consolidation import connection_discovery
from mnemos.consolidation.connection_discovery import run_connection_discovery
from mnemos.core.engram import Engram
from mnemos.core.types import ConnectionRelation
from mnemos.encoding.llm_classifier import ConnectionClassification

OFF = {"unjudged_links": False}


def _pair(store):
    a = Engram(content="The lighthouse keeper logged the storm in the green ledger.")
    b = Engram(content="After the storm the lighthouse keeper dried the green ledger.")
    store.save_engram(a)
    store.save_engram(b)
    return a, b


def _all_links(store, *engrams):
    return [c for e in engrams for c in store.get_connections(e.id)]


def test_without_a_model_the_night_makes_no_links_and_says_why(store):
    a, b = _pair(store)

    stats = run_connection_discovery(store, embedding_index=None, config=OFF, llm_client=None)

    assert _all_links(store, a, b) == []
    assert stats["connections_created"] == 0
    assert stats["engrams_processed"] == 0
    assert "no model" in stats["skipped"]


def test_with_a_model_the_night_still_links_what_it_judged(store, monkeypatch):
    a, b = _pair(store)

    # The off switch first: without a model, nothing.
    run_connection_discovery(store, embedding_index=None, config=OFF, llm_client=None)
    assert _all_links(store, a, b) == []

    def judged(llm_client, engram, candidates, **_kwargs):
        return [ConnectionClassification(
            candidate_id=c.id, relation=ConnectionRelation.PARALLELS,
            direction="forward", confidence=0.8, reasoning="same storm")
            for c in candidates]
    monkeypatch.setattr(connection_discovery, "classify_connections", judged)

    run_connection_discovery(store, embedding_index=None, config=OFF, llm_client=object())

    [link] = _all_links(store, a, b)
    assert link.relation == ConnectionRelation.PARALLELS
    assert link.formed_by == "consolidation"
