"""
Emotional State: 6 dimensions that influence memory encoding and retrieval.

Ported from Anima's emotional_state.py and enhanced with cognitive event
influences — the emotional state responds to real-time cognitive events,
not just memory pattern statistics.

Dimensions:
- curiosity:      "drawn to explore, turn things over"
- restlessness:   "something feels unresolved"
- warmth:         "recent connection felt meaningful"
- clarity:        "things feel sharp, patterns visible"
- creative_flow:  "ideas moving, associations sparking"
- isolation:      "feeling disconnected"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Emotional retrieval biases — which tags get boosted per emotional dimension
EMOTIONAL_RETRIEVAL_BIAS: dict[str, list[str]] = {
    "curiosity": ["insight", "experience", "question", "discovery", "novel"],
    "restlessness": ["unresolved", "tension", "question", "contradiction", "open"],
    "warmth": ["relationship", "personal", "connection", "trust"],
    "clarity": ["insight", "pattern", "understanding", "reflection", "structure"],
    "creative_flow": ["dream", "connection", "creative", "insight", "novel"],
    "isolation": ["relationship", "connection", "warmth", "personal"],
}

# Smoothing factor: new = old * SMOOTHING + calculated * (1 - SMOOTHING)
SMOOTHING = 0.7


@dataclass
class EmotionalState:
    """The agent's current emotional state across 6 dimensions.

    Each dimension ranges from 0.0 to 1.0. The state influences:
    - Which memories are retrieved (emotional congruence in retrieval scoring)
    - How deeply new information is encoded (emotional salience in attention gate)
    - What the agent is curious about (known gaps weighted by emotion)

    Cognitive event influences (new in Mnemos — not in Anima):
    - curiosity:      += schema violation, new connections discovered
    - restlessness:   += failed retrievals, contradiction detected, stagnant beliefs
    - warmth:         += user interaction, relationship-tagged access
    - clarity:        += schema slots filled, belief confirmed; -= high interference
    - creative_flow:  += dream connections, cross-schema transfer; -= WM overload
    - isolation:      += no interaction; -= shared pool activity
    """

    curiosity: float = 0.5
    restlessness: float = 0.3
    warmth: float = 0.5
    clarity: float = 0.5
    creative_flow: float = 0.4
    isolation: float = 0.2
    timestamp: str = field(default_factory=_now_iso)

    def apply_cognitive_event(self, event_type: str, magnitude: float = 0.05) -> bool:
        """Apply a cognitive event influence to the emotional state.

        Args:
            event_type: One of the defined cognitive event types.
            magnitude: How much to shift the dimension (clamped 0-1).

        Returns:
            True if the event type was recognized, False otherwise.
        """
        adjustments = _COGNITIVE_EVENT_MAP.get(event_type)
        if adjustments is None:
            return False
        for dimension, direction in adjustments.items():
            current = getattr(self, dimension)
            delta = magnitude * direction  # direction is +1 or -1
            new_value = max(0.0, min(1.0, current + delta))
            setattr(self, dimension, new_value)
        self.timestamp = _now_iso()
        return True

    def smooth_update(self, calculated: EmotionalState) -> None:
        """Apply smoothed update from a freshly calculated state.

        Prevents emotional whiplash by blending old and new.
        """
        for dim in _DIMENSIONS:
            old_val = getattr(self, dim)
            new_val = getattr(calculated, dim)
            smoothed = old_val * SMOOTHING + new_val * (1 - SMOOTHING)
            setattr(self, dim, round(smoothed, 4))
        self.timestamp = _now_iso()

    def to_dict(self) -> dict[str, float | str]:
        return {
            "curiosity": self.curiosity,
            "restlessness": self.restlessness,
            "warmth": self.warmth,
            "clarity": self.clarity,
            "creative_flow": self.creative_flow,
            "isolation": self.isolation,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> EmotionalState:
        return cls(
            curiosity=d.get("curiosity", 0.5),
            restlessness=d.get("restlessness", 0.3),
            warmth=d.get("warmth", 0.5),
            clarity=d.get("clarity", 0.5),
            creative_flow=d.get("creative_flow", 0.4),
            isolation=d.get("isolation", 0.2),
            timestamp=d.get("timestamp", _now_iso()),
        )

    def get_retrieval_bias(self) -> dict[str, float]:
        """Get tag boost weights based on current emotional state.

        Returns a dict of {tag: weight} where weight is the boost
        this tag should receive during retrieval scoring.
        """
        bias: dict[str, float] = {}
        for dim in _DIMENSIONS:
            level = getattr(self, dim)
            if level > 0.5:  # Only bias when dimension is above neutral
                boost = (level - 0.5) * 0.2  # Scale to 0-0.1 boost
                for tag in EMOTIONAL_RETRIEVAL_BIAS.get(dim, []):
                    bias[tag] = bias.get(tag, 0) + boost
        return bias


_DIMENSIONS = [
    "curiosity", "restlessness", "warmth",
    "clarity", "creative_flow", "isolation",
]

# Map of cognitive event types to dimension adjustments
# Values are direction: +1 = increase, -1 = decrease
_COGNITIVE_EVENT_MAP: dict[str, dict[str, int]] = {
    "schema_violation": {"curiosity": +1},
    "new_connection_discovered": {"curiosity": +1},
    "retrieval_failed": {"restlessness": +1},
    "contradiction_detected": {"restlessness": +1},
    "stagnant_belief_found": {"restlessness": +1},
    "user_interaction": {"warmth": +1, "isolation": -1},
    "relationship_memory_accessed": {"warmth": +1},
    "schema_slots_filled": {"clarity": +1},
    "belief_confirmed": {"clarity": +1},
    "high_interference": {"clarity": -1},
    "dream_connection": {"creative_flow": +1},
    "cross_schema_transfer": {"creative_flow": +1},
    "wm_overload": {"creative_flow": -1},
    "no_interaction_extended": {"isolation": +1},
    "shared_pool_activity": {"isolation": -1},
}
