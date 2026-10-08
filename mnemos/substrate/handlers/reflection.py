"""
Reflection handler: retired (Tara's ruling, 2026-10-07).

Triggered by BELIEF_CONTRADICTED, this handler had the substrate model,
told "You are {name}… critically examining one of your beliefs", decide a
new confidence and revise the belief itself. A belief changes only by his
own verdict (Riley Coyote's mnemos 0.4, #82, #124), so the handler now
receives the event and does nothing with it.
"""

import logging

from ..events import SubstrateEvent
from ..config import SubstrateConfig
from ..modulators import ModulatorState

log = logging.getLogger("mnemos.substrate.reflection")


def handle(
    event: SubstrateEvent,
    config: SubstrateConfig,
    modulators: ModulatorState,
    store,
    llm_client,
) -> list[SubstrateEvent]:
    """Retired: a contradicted belief waits for his own verdict."""
    del config, modulators, store, llm_client
    log.info(
        "Belief %s: contradiction noted; beliefs move only by his own verdict",
        event.payload.get("belief_id"),
    )
    return []
