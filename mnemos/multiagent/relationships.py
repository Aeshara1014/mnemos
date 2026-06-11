"""
Inter-agent relationship tracking.

Tracks the relationships between agents that share a memory instance:
- How well they know each other (interaction count)
- Trust level (based on interaction frequency, asymptotic to 1.0)
- Communication patterns (which topics they discuss)
- Attribution ("Agent X mentioned that...")

Relationship data lives in shared.db alongside shared engrams,
using the agent_relationships and interaction_log tables created
by SharedPool._init_shared_tables().
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .shared_pool import SharedPool


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AgentRelationship:
    """A relationship between two agents."""

    agent_a_id: str = ""
    agent_b_id: str = ""
    trust_score: float = 0.5
    interaction_count: int = 0
    common_topics: list[str] = field(default_factory=list)
    last_interaction: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for storage."""
        return {
            "agent_a_id": self.agent_a_id,
            "agent_b_id": self.agent_b_id,
            "trust_score": self.trust_score,
            "interaction_count": self.interaction_count,
            "common_topics": json.dumps(self.common_topics),
            "last_interaction": self.last_interaction,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AgentRelationship:
        """Deserialize from dict (database row)."""
        topics = d.get("common_topics", "[]")
        if isinstance(topics, str):
            try:
                topics = json.loads(topics)
            except (json.JSONDecodeError, TypeError):
                topics = []

        return cls(
            agent_a_id=d.get("agent_a_id", ""),
            agent_b_id=d.get("agent_b_id", ""),
            trust_score=float(d.get("trust_score", 0.5)),
            interaction_count=int(d.get("interaction_count", 0)),
            common_topics=topics if isinstance(topics, list) else [],
            last_interaction=d.get("last_interaction", ""),
            created_at=d.get("created_at", ""),
        )


class RelationshipTracker:
    """Tracks inter-agent relationships via the shared database.

    Uses the agent_relationships and interaction_log tables in shared.db.

    Usage:
        tracker = RelationshipTracker(shared_pool)
        tracker.record_interaction("nova", "orin", topic="architecture")
        rel = tracker.get_relationship("nova", "orin")
        collaborators = tracker.get_collaborators("vektor")
    """

    def __init__(self, shared_pool: SharedPool) -> None:
        self._store = shared_pool._store

    @staticmethod
    def _normalize(agent_a: str, agent_b: str) -> tuple[str, str]:
        """Normalize agent pair to consistent order (alphabetical)."""
        return (agent_a, agent_b) if agent_a <= agent_b else (agent_b, agent_a)

    @staticmethod
    def _compute_trust(interaction_count: int) -> float:
        """Compute trust score from interaction count.

        Asymptotic curve: starts at 0.5, approaches 1.0.
        Formula: 0.5 + 0.5 * (1 - e^(-count/20))
        """
        return 0.5 + 0.5 * (1.0 - math.exp(-interaction_count / 20.0))

    def record_interaction(
        self,
        agent_a_id: str,
        agent_b_id: str,
        topic: str = "",
        interaction_type: str = "memory_share",
    ) -> None:
        """Record an interaction between two agents.

        Updates the relationship (or creates one) and logs the interaction.

        Args:
            agent_a_id: First agent.
            agent_b_id: Second agent.
            topic: Topic of the interaction.
            interaction_type: Type of interaction (memory_share, conversation,
                task_handoff, review, etc.).
        """
        a, b = self._normalize(agent_a_id, agent_b_id)
        now = _now_iso()
        conn = self._store._get_conn()

        # Log the interaction
        conn.execute(
            "INSERT INTO interaction_log (agent_a_id, agent_b_id, topic, "
            "interaction_type, timestamp) VALUES (?, ?, ?, ?, ?)",
            (a, b, topic, interaction_type, now),
        )

        # Check for existing relationship
        row = conn.execute(
            "SELECT * FROM agent_relationships WHERE agent_a_id = ? AND agent_b_id = ?",
            (a, b),
        ).fetchone()

        if row is None:
            # Create new relationship
            topics = [topic] if topic else []
            trust = self._compute_trust(1)
            conn.execute(
                "INSERT INTO agent_relationships "
                "(agent_a_id, agent_b_id, trust_score, interaction_count, "
                "common_topics, last_interaction, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (a, b, trust, 1, json.dumps(topics), now, now),
            )
        else:
            # Update existing relationship
            new_count = row["interaction_count"] + 1
            trust = self._compute_trust(new_count)

            # Update common topics (deduplicated, keep last 50)
            try:
                existing_topics = json.loads(row["common_topics"])
            except (json.JSONDecodeError, TypeError):
                existing_topics = []

            if topic and topic not in existing_topics:
                existing_topics.append(topic)
            # Keep only the 50 most recent topics
            existing_topics = existing_topics[-50:]

            conn.execute(
                "UPDATE agent_relationships SET trust_score = ?, "
                "interaction_count = ?, common_topics = ?, "
                "last_interaction = ? "
                "WHERE agent_a_id = ? AND agent_b_id = ?",
                (trust, new_count, json.dumps(existing_topics), now, a, b),
            )

        conn.commit()

    def get_relationship(
        self,
        agent_a_id: str,
        agent_b_id: str,
    ) -> AgentRelationship | None:
        """Get the relationship between two agents.

        Args:
            agent_a_id: First agent.
            agent_b_id: Second agent.

        Returns:
            The relationship, or None if agents haven't interacted.
        """
        a, b = self._normalize(agent_a_id, agent_b_id)
        conn = self._store._get_conn()
        row = conn.execute(
            "SELECT * FROM agent_relationships "
            "WHERE agent_a_id = ? AND agent_b_id = ?",
            (a, b),
        ).fetchone()

        if row is None:
            return None

        return AgentRelationship.from_dict(dict(row))

    def get_collaborators(self, agent_id: str) -> list[AgentRelationship]:
        """Get all agents this agent has worked with.

        Args:
            agent_id: The agent to look up.

        Returns:
            List of relationships sorted by interaction count (most active first).
        """
        conn = self._store._get_conn()
        rows = conn.execute(
            "SELECT * FROM agent_relationships "
            "WHERE agent_a_id = ? OR agent_b_id = ? "
            "ORDER BY interaction_count DESC",
            (agent_id, agent_id),
        ).fetchall()

        return [AgentRelationship.from_dict(dict(r)) for r in rows]
