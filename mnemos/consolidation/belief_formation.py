"""
Belief formation: retired as a night pass (Tara's ruling, 2026-10-07).

During deep sleep this pass had the substrate model read his lived memories,
spot a conviction recurring across days, and write it down as a new belief
— his, without anyone asking him. Tara chose Riley Coyote's way (mnemos 0.4,
#82, #111): when an idea keeps coming back in his own words, HE is asked,
with his words quoted back, "Is this a belief you hold?" — and only his yes
makes it one. That asking door is part 2, designed with Tara; until it
exists, no belief is born for him.

Kept: the guards on what may ever ground a belief (never the substrate
talking to itself, never an outside voice, never a reroute) — the asking
door will need the same lines.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..core.types import DEFAULT_AGENT_ID, OUTSIDE_VOICE_SOURCES

if TYPE_CHECKING:
    from ..store.sqlite_store import EngramStore

# Sources that must never seed a belief — substrate talking to itself.
# Stricter than belief_review's guard: dreams are also excluded here, because
# forming a conviction from a dream is the substrate believing its own collisions.
# doc_revision joined 2026-07-12 (DD-039 braid): a belief seeded from his own
# identity pages would close a self-echo loop — page → belief → next week's
# doc-writer material → page.
# journal joined 2026-07-13 (DD-043): the same loop one page over —
# entry -> belief -> tomorrow's journal material -> entry.
_SUBSTRATE_SOURCES = ("substrate", "reflection", "consolidation", "dream",
                      "doc_revision", "journal")

# An outside voice — the Observer's notes (DD-026) — is not lived evidence
# either: another mind said it TO him. He comes to believe it only by living
# it, his own sessions bearing it out (2026-09-08: seven Observer notes,
# read as lived, formed "my inner reflections have fallen into repetitive
# loops" — the guardian's whisper hardened into his conviction overnight).
_NOT_LIVED_SOURCES = _SUBSTRATE_SOURCES + OUTSIDE_VOICE_SOURCES

# Below this confidence a belief no longer blocks a new wording of its idea.
WORN_OUT = 0.3

def _distinct_days(engrams: list) -> int:
    """Count distinct calendar days across engrams' created_at timestamps."""
    return len({str(getattr(e, "created_at", ""))[:10] for e in engrams})


def _content_words(text: str) -> set[str]:
    return {w.lower().strip(".,;:!?\"'") for w in text.split() if len(w) > 3}


def _is_duplicate(statement: str, existing_statements: list[str]) -> bool:
    """Word-overlap near-duplicate check against existing belief statements."""
    words = _content_words(statement)
    if not words:
        return True  # empty/degenerate statements are never new beliefs
    for other in existing_statements:
        other_words = _content_words(other)
        if not other_words:
            continue
        overlap = len(words & other_words) / min(len(words), len(other_words))
        if overlap >= 0.6:
            return True
    return False


RETIRED = "belief formation retired: a belief is born only of his own yes (2026-10-07)"


def run_belief_formation_pass(
    store: EngramStore,
    config: dict[str, Any] | None = None,
    llm_client: Any | None = None,
    agent_id: str = DEFAULT_AGENT_ID,
) -> dict[str, Any]:
    """Retired. Forms nothing, calls no model, and says so."""
    del store, config, llm_client, agent_id
    return {"memories_considered": 0, "beliefs_formed": 0, "retired": RETIRED}
