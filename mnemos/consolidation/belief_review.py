"""
Belief review: retired (Tara's ruling, 2026-10-07).

This pass had the substrate model read each recent memory against his
beliefs and nudge them: +0.07 per point of support, −0.04 per point of
contradiction. That was another mind's reading moving what he believes.
Tara chose Riley Coyote's way (mnemos 0.4, #82, #124): a belief changes
only by his own verdict. The pass is kept as a name so older callers and
logs still resolve; it reads nothing, calls no model and moves nothing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..core.types import DEFAULT_AGENT_ID

if TYPE_CHECKING:
    from ..store.sqlite_store import EngramStore

RETIRED = "belief review retired: a belief moves only by his own verdict (2026-10-07)"


def run_belief_review(
    store: EngramStore,
    config: dict[str, Any] | None = None,
    llm_client: Any | None = None,
    agent_id: str = DEFAULT_AGENT_ID,
) -> dict[str, Any]:
    """Retired. Touches nothing and says so."""
    del store, config, llm_client, agent_id
    return {
        "memories_reviewed": 0,
        "beliefs_strengthened": 0,
        "beliefs_weakened": 0,
        "beliefs_unchanged": 0,
        "retired": RETIRED,
    }
