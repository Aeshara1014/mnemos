"""Links made without a model say only what was observed.

Without a model, a link comes from a word or meaning match alone:
correlation, not evidence. It was written SUPPORTS, which recall weights at
1.0 (CO_ACTIVATED 0.6). The night pass runs without a model every 4 hours, so
most of its links claimed a support nothing established. An encoding link
made without a model was also stamped "encoding", which the night treats as
already judged, so it could never be re-sorted. Riley's 638d3c2 and a0c424e,
built here our own way (Tara, Nov 7 2026).
"""

from __future__ import annotations

from mnemos.consolidation.connection_discovery import (
    _CLASSIFIED_FORMED_BY,
    _RECLASSIFIABLE_RELATIONS,
    run_connection_discovery,
)
from mnemos.core.engram import Engram
from mnemos.core.types import ConnectionRelation
from mnemos.encoding.encoder import Encoder

OLD = "The lighthouse keeper logged the storm in the green ledger at midnight."
NEW = "After the storm, the lighthouse keeper repainted the green ledger shelf."


def _memory(store, content: str) -> Engram:
    engram = Engram(content=content)
    store.save_engram(engram)
    return engram


def _links(store, source: Engram, target: Engram):
    return [c for c in store.get_connections(source.id) if c.target_id == target.id]


def test_night_pass_without_a_model_labels_a_match_co_activated(store):
    old = _memory(store, OLD)
    new = _memory(store, NEW)

    run_connection_discovery(store, embedding_index=None, config={}, llm_client=None)

    # One link between the pair, whichever memory the pass reached first.
    [link] = _links(store, new, old) + _links(store, old, new)
    assert link.relation == ConnectionRelation.CO_ACTIVATED
    assert link.formed_by == "consolidation_no_model"


def test_encoding_without_a_model_labels_a_match_co_activated(store):
    old = _memory(store, OLD)

    new = Encoder(store, llm_client=None).encode(content=NEW)

    [link] = _links(store, new, old)
    assert link.relation == ConnectionRelation.CO_ACTIVATED
    assert link.formed_by == "encoding_no_model"
    # Unjudged, so the night may re-sort it later.
    assert link.relation in _RECLASSIFIABLE_RELATIONS
    assert link.formed_by not in _CLASSIFIED_FORMED_BY
