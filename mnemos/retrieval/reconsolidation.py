"""
Post-retrieval memory reconsolidation.

Every time a memory is retrieved, it is reconsolidated — its strength,
stability, and connections are updated based on the current context.
This models the neuroscience finding that memories become labile (modifiable)
upon retrieval and are then re-stored in an updated form.

This is what makes Mnemos memories "living" — they change every time
they are touched, rather than being static records.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..core.engram import Engram
from ..core.types import ConnectionRelation

if TYPE_CHECKING:
    from ..store.sqlite_store import EngramStore


def reconsolidate(
    engram: Engram,
    current_context: str,
    co_retrieved_ids: list[str],
    store: EngramStore,
    strength_delta: float = 0.05,
    stability_delta: float = 0.01,
    accessibility_floor: float = 0.8,
) -> Engram:
    """Update a memory after retrieval (reconsolidation).

    Models the reconsolidation window: when a memory is retrieved, it
    becomes temporarily labile and is re-stored with updates based on
    the current retrieval context.

    Effects:
    1. Access metadata updated (count, timestamp)
    2. Strength increased (retrieval strengthens storage)
    3. Stability increased slowly (spaced repetition effect)
    4. Accessibility boosted (just accessed = highly retrievable)
    5. Connections to co-retrieved engrams created/strengthened
    6. Version snapshot saved for audit trail
    7. Persisted to store

    Args:
        engram: The engram being reconsolidated.
        current_context: The retrieval cue / context (for audit trail).
        co_retrieved_ids: IDs of other engrams retrieved alongside this one.
        store: The storage backend for persisting updates.
        strength_delta: How much to increase strength per retrieval.
        stability_delta: How much to increase stability per retrieval.
        accessibility_floor: Minimum accessibility after retrieval.

    Returns:
        The updated engram after reconsolidation.
    """
    # 1. Access metadata
    engram.record_access()
    engram.reconsolidation_count += 1

    # 2. Strength increases — retrieval is rehearsal
    engram.strength = min(1.0, engram.strength + strength_delta)

    # 3. Stability increases slowly — spaced repetition effect
    engram.stability = min(1.0, engram.stability + stability_delta)

    # 4. Accessibility boost — just accessed, very retrievable now
    engram.accessibility = min(1.0, max(engram.accessibility, accessibility_floor))

    # 5. Co-retrieval connections — memories retrieved together become linked
    for co_id in co_retrieved_ids:
        if co_id != engram.id:
            engram.add_connection(
                target_id=co_id,
                relation=ConnectionRelation.SUPPORTS,
                strength=0.3,
                formed_by="retrieval",
            )

    # 6. Version snapshot for audit trail
    engram.add_version(reason="reconsolidation")

    # 7. Persist
    store.save_engram(engram)

    return engram
