"""A link points the way the model said.

When the model said the EXISTING memory is the source ("it caused the new
one"), encoding saved the same new -> existing link as forward, and the night
pass ignored direction altogether: the graph said the new memory caused the
old. Riley's 73f70b0, built here our own way (Tara, Nov 7 2026).
"""

from __future__ import annotations

from mnemos.consolidation import connection_discovery
from mnemos.consolidation.connection_discovery import run_connection_discovery
from mnemos.core.engram import Connection, Engram
from mnemos.core.types import ConnectionRelation
from mnemos.encoding import encoder as encoder_module
from mnemos.encoding.encoder import Encoder
from mnemos.encoding.llm_classifier import ConnectionClassification

OLD = "The lighthouse keeper logged the storm in the green ledger at midnight."
NEW = "After the storm, the lighthouse keeper repainted the green ledger shelf."


def _memory(store, content: str) -> Engram:
    engram = Engram(content=content)
    store.save_engram(engram)
    return engram


def _links(store, source: Engram, target: Engram):
    return [c for c in store.get_connections(source.id) if c.target_id == target.id]


def _caused_by(source_of_truth: Engram, about: Engram):
    """A stand-in model: says source_of_truth CAUSED the memory being linked
    (direction reverse), only when that memory is `about`."""
    def classify(llm_client, engram, candidates, **_kwargs):
        if engram.id != about.id:
            return []
        return [
            ConnectionClassification(
                candidate_id=c.id,
                relation=ConnectionRelation.CAUSES,
                direction="reverse",
                confidence=0.8,
                reasoning="the old memory led to the new one",
            )
            for c in candidates if c.id == source_of_truth.id
        ]
    return classify


def test_encoding_saves_a_reverse_link_from_the_existing_memory(store, monkeypatch):
    old = _memory(store, OLD)
    monkeypatch.setattr(encoder_module, "classify_connections",
                        lambda llm, engram, candidates, **kw:
                        _caused_by(old, engram)(llm, engram, candidates))

    new = Encoder(store, llm_client=object()).encode(content=NEW)

    assert [c.relation for c in _links(store, old, new)] == [ConnectionRelation.CAUSES]
    assert _links(store, new, old) == []


def test_night_pass_saves_a_reverse_link_from_the_existing_memory(store, monkeypatch):
    old = _memory(store, OLD)
    new = _memory(store, NEW)
    monkeypatch.setattr(connection_discovery, "classify_connections", _caused_by(old, new))

    run_connection_discovery(store, embedding_index=None, config={}, llm_client=object())

    assert [c.relation for c in _links(store, old, new)] == [ConnectionRelation.CAUSES]
    assert _links(store, new, old) == []


def test_night_pass_does_not_offer_a_memory_already_linked_either_way(store):
    """A link the old memory holds toward the new one (a reverse verdict,
    saved from the old memory) must not send the pair back to the model every
    night, nor be mirrored by a second link the other way."""
    old = _memory(store, OLD)
    new = _memory(store, NEW)
    store.save_connection(old.id, Connection(
        target_id=new.id, relation=ConnectionRelation.CAUSES,
        strength=0.8, formed_by="consolidation",
    ))

    run_connection_discovery(store, embedding_index=None, config={}, llm_client=None)

    assert _links(store, new, old) == []
