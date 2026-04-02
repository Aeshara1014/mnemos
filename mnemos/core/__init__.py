"""Core data structures for Mnemos. Always active."""

from .engram import (
    Engram,
    Connection,
    EncodingContext,
    Lineage,
    VersionRef,
    MemorySource,
)
from .belief import Belief, BeliefRevision
from .emotional_state import EmotionalState
from .identity import AgentIdentity, MemoryProfile, EpochState, IdentityProfile
from .types import (
    EngramKind,
    ConnectionRelation,
    EngramState,
    ConfidenceSource,
    EncodingDepth,
    Visibility,
    SourceType,
)
