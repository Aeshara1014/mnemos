"""
Session lifecycle management for Mnemos.

MnemosSession tracks encoding context during an active conversation.
It maintains a record of what happened during the session so that
encoding has full context (what was in working memory, what tools
were called, what the emotional state was, etc.).

Lifecycle:
    session.start(session_id, agent_id)
    # During conversation:
    session.on_message(content, role="user")
    session.on_message(content, role="assistant")
    session.on_tool_result(tool_name, result)
    # At end:
    session.end()  # triggers final encoding pass
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..store.sqlite_store import EngramStore
    from ..encoding.encoder import Encoder


class MnemosSession:
    """Manages memory encoding during an active conversation session.

    The session object is the primary integration point for agent platforms.
    It tracks messages, tool results, and context throughout a conversation,
    then triggers encoding when the session ends.

    Usage:
        session = MnemosSession(store=store, encoder=encoder)
        session.start("session_123", "anima")

        # As messages come in:
        session.on_message("What's the weather?", role="user")
        session.on_message("It's sunny in Portland.", role="assistant")
        session.on_tool_result("weather_api", {"temp": 72, "condition": "sunny"})

        # When conversation ends:
        session.end()
    """

    def __init__(
        self,
        store: EngramStore,
        encoder: Encoder,
    ) -> None:
        self._store = store
        self._encoder = encoder
        self._session_id: str | None = None
        self._agent_id: str = "default"
        self._messages: list[dict[str, Any]] = []
        self._tool_results: list[dict[str, Any]] = []
        self._active: bool = False

    def start(self, session_id: str, agent_id: str = "default") -> None:
        """Begin tracking a new conversation session.

        Initializes session state, loads the agent's current emotional
        state and working memory context for encoding.

        Args:
            session_id: Unique identifier for this conversation session.
            agent_id: The agent whose memories will be encoded.
        """
        raise NotImplementedError("Step 10: Session start implementation")

    def on_message(self, content: str, role: str = "user") -> None:
        """Record a message exchanged during the session.

        Messages are accumulated and used for encoding decisions when
        the session ends. The role determines confidence scoring
        (user messages get higher confidence than assistant messages).

        Args:
            content: The message text content.
            role: Who sent the message ("user", "assistant", "system").
        """
        raise NotImplementedError("Step 10: Message recording implementation")

    def on_tool_result(self, tool_name: str, result: Any) -> None:
        """Record a tool invocation result during the session.

        Tool results may be encoded as procedural memories if they
        represent significant outcomes.

        Args:
            tool_name: The name of the tool that was invoked.
            result: The result returned by the tool.
        """
        raise NotImplementedError("Step 10: Tool result recording implementation")

    def end(self) -> None:
        """End the session and trigger final encoding.

        Processes accumulated messages and tool results through the
        encoding pipeline, creating engrams for significant content.
        Updates the agent's emotional state based on session events.
        Marks the session as inactive.
        """
        raise NotImplementedError("Step 10: Session end implementation")
