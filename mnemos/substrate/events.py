"""
Substrate event system.

Events are the internal language of the substrate. Consolidation produces them,
handlers consume them. Each event carries enough context for a handler to act
without needing to query the database again.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(str, Enum):
    """Events that the substrate can produce and handlers can consume."""

    # Belief events (from tier crossing detection)
    BELIEF_CONTRADICTED = "belief_contradicted"
    BELIEF_CONFIRMED = "belief_confirmed"

    # Memory events (from consolidation passes)
    MEMORY_SOFTENED = "memory_softened"       # Decay reduced a memory's vividness
    CONNECTION_DISCOVERED = "connection_discovered"  # New connection found between engrams
    SURPRISE_DETECTED = "surprise_detected"   # Something unexpected in encoding

    # Temporal events
    SILENCE_EXTENDED = "silence_extended"      # Long gap since last memory formation

    # Living events (produced by living-tick handlers to signal a real write)
    WANDERING_RECORDED = "wandering_recorded"  # A silence wander was actually encoded
    INSIGHT_RECORDED = "insight_recorded"      # A connection insight was actually encoded
    SURPRISE_RECORDED = "surprise_recorded"    # A surprise reflection was actually encoded

    # Accumulation events
    SALIENCE_ACCUMULATED = "salience_accumulated"  # Built-up unprocessed salience


@dataclass
class SubstrateEvent:
    """A single event produced during a substrate tick."""

    event_type: EventType
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = ""  # Which phase produced this event

    def __repr__(self) -> str:
        return f"Event({self.event_type.value}, source={self.source})"
