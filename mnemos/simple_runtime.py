"""Simple-mode continuity runtime for Mnemos.

This module is intentionally MCP-agnostic so the product path can be tested
without a running client. It exposes the real Mnemos stack through five simple
operations: context, capture, recall, correct, and maintain.
"""

from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config.loader import load_config
from .consolidation.daemon import ConsolidationDaemon
from .core.types import SourceType
from .encoding.encoder import Encoder
from .retrieval.reactive import ReactiveRetriever
from .store.embedding_index import EmbeddingIndex
from .store.sqlite_store import EngramStore


SIMPLE_TOOL_NAMES = (
    "mnemos_context",
    "mnemos_capture",
    "mnemos_recall",
    "mnemos_correct",
    "mnemos_maintain",
)


def _slugify(value: str, fallback: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    return clean or fallback


def _default_project_scope() -> str:
    cwd = Path.cwd()
    if cwd.name:
        return _slugify(cwd.name, "global")
    return "global"


@dataclass(frozen=True)
class MnemosScope:
    """Resolved identity and storage scope for simple mode."""

    agent_id: str
    person_id: str
    project_scope: str
    db_path: str


def resolve_scope(
    *,
    db_path: str | None = None,
    agent_id: str | None = None,
    person_id: str | None = None,
    project_scope: str | None = None,
) -> MnemosScope:
    """Resolve Mnemos identity from explicit args, env, config, then defaults."""

    try:
        config = load_config()
    except Exception:
        config = {}

    resolved_agent = _slugify(
        agent_id
        or os.environ.get("MNEMOS_AGENT_ID", "")
        or str(config.get("agent_id", ""))
        or "mnemos-agent",
        "mnemos-agent",
    )
    resolved_person = _slugify(
        person_id
        or os.environ.get("MNEMOS_PERSON_ID", "")
        or str(config.get("person_id", ""))
        or str(config.get("user_name", ""))
        or "user",
        "user",
    )
    resolved_project = _slugify(
        project_scope
        or os.environ.get("MNEMOS_PROJECT_SCOPE", "")
        or str(config.get("project_scope", ""))
        or _default_project_scope(),
        "global",
    )

    explicit_db = db_path or os.environ.get("MNEMOS_DB_PATH")
    if explicit_db:
        resolved_db = explicit_db
    else:
        store_config = config.get("store", {}) if isinstance(config.get("store"), dict) else {}
        configured = store_config.get("db_path")
        if configured and configured != "~/.mnemos/memory.db":
            resolved_db = str(configured)
        else:
            resolved_db = f"~/.mnemos/{resolved_agent}.db"

    return MnemosScope(
        agent_id=resolved_agent,
        person_id=resolved_person,
        project_scope=resolved_project,
        db_path=resolved_db,
    )


def _dedicated_model_requested() -> bool:
    """Return true only when simple mode has explicit model configuration."""

    explicit_env = (
        "MNEMOS_LLM_PROVIDER",
        "MNEMOS_MODEL",
        "OPENROUTER_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
    )
    if any(os.environ.get(key) for key in explicit_env):
        return True
    try:
        config = load_config()
    except Exception:
        return False
    llm_config = config.get("llm", {}) if isinstance(config.get("llm"), dict) else {}
    return bool(llm_config.get("provider") or llm_config.get("model"))


def _classify_kind(content: str) -> str:
    text = content.lower()
    if any(marker in text for marker in ("how to", "process", "workflow", "steps", "procedure")):
        return "procedural"
    if any(marker in text for marker in ("todo", "remember to", "next time", "follow up", "should do")):
        return "prospective"
    if any(marker in text for marker in ("decided", "built", "debugged", "met", "changed", "fixed")):
        return "episodic"
    return "semantic"


def _classify_domain(content: str) -> str:
    text = content.lower()
    if any(marker in text for marker in ("identity", "who i am", "who you are", "selfhood")):
        return "identity"
    if any(marker in text for marker in ("always", "preference", "prefers", "principle", "boundary")):
        return "foundational"
    if any(marker in text for marker in ("again", "recurring", "pattern", "usually", "often")):
        return "recurring"
    if any(marker in text for marker in ("roadmap", "long term", "long-term", "arc", "future")):
        return "long-arc"
    if any(marker in text for marker in ("current", "today", "now", "temporary", "session")):
        return "situational"
    return "topical"


def _simple_tags(content: str, context: str = "") -> list[str]:
    text = f"{content} {context}".lower()
    tags = ["continuity"]
    for label, markers in {
        "preference": ("prefer", "preference", "likes", "wants"),
        "decision": ("decided", "decision", "chosen", "agreed"),
        "project": ("project", "repo", "workspace", "build"),
        "identity": ("identity", "agent", "user", "self"),
        "correction": ("correction", "wrong", "update", "forget"),
    }.items():
        if any(marker in text for marker in markers):
            tags.append(label)
    return sorted(set(tags))


_STOPWORDS = {
    "about",
    "after",
    "agent",
    "before",
    "continuity",
    "context",
    "durable",
    "memory",
    "mnemos",
    "note",
    "notes",
    "should",
    "that",
    "this",
    "when",
    "with",
}


def _query_terms(query: str) -> set[str]:
    return {
        term
        for term in re.findall(r"[a-zA-Z0-9]+", query.lower())
        if len(term) >= 3 and term not in _STOPWORDS
    }


def _has_query_overlap(query: str, text: str) -> bool:
    terms = _query_terms(query)
    if not terms:
        return True
    text_terms = _query_terms(text)
    return bool(terms & text_terms)


def _filter_continuity(query: str, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not query.strip():
        return entries
    return [
        entry for entry in entries
        if _has_query_overlap(query, entry.get("content", ""))
        or float(entry.get("score", 0.0)) >= 0.55
    ]


def _filter_memories(query: str, results: list[Any]) -> list[Any]:
    if not query.strip():
        return results
    filtered = []
    for result in results:
        engram = result.engram
        searchable = " ".join([
            engram.content or "",
            engram.impact or "",
            " ".join(engram.tags or []),
        ])
        if _has_query_overlap(query, searchable) or float(result.score) >= 1.35:
            filtered.append(result)
    return filtered


class MnemosRuntime:
    """High-level continuity interface used by simple MCP mode and tests."""

    def __init__(
        self,
        *,
        db_path: str | None = None,
        agent_id: str | None = None,
        person_id: str | None = None,
        project_scope: str | None = None,
        use_dedicated_model: bool = True,
    ) -> None:
        self.scope = resolve_scope(
            db_path=db_path,
            agent_id=agent_id,
            person_id=person_id,
            project_scope=project_scope,
        )
        self._store: EngramStore | None = None
        self._encoder: Encoder | None = None
        self._retriever: ReactiveRetriever | None = None
        self._embedding_index: EmbeddingIndex | None = None
        self._llm_client: Any | None = None
        self._use_dedicated_model = use_dedicated_model

    @property
    def db_path(self) -> Path:
        return Path(self.scope.db_path).expanduser()

    @property
    def has_dedicated_model(self) -> bool:
        self._ensure_init()
        return self._llm_client is not None

    def close(self) -> None:
        if self._store is not None:
            self._store.close()
        self._store = None
        self._encoder = None
        self._retriever = None
        self._embedding_index = None
        self._llm_client = None

    def _ensure_init(self) -> None:
        if self._store is not None:
            return

        self._store = EngramStore(self.scope.db_path)
        self._embedding_index = EmbeddingIndex(db_path=self.scope.db_path)
        try:
            from .llm import create_client

            self._llm_client = (
                create_client()
                if self._use_dedicated_model and _dedicated_model_requested()
                else None
            )
        except Exception:
            self._llm_client = None

        self._encoder = Encoder(
            self._store,
            embedding_index=self._embedding_index,
            llm_client=self._llm_client,
        )
        self._retriever = ReactiveRetriever(
            self._store,
            embedding_index=self._embedding_index,
        )

    def _stats(self) -> dict[str, Any]:
        self._ensure_init()
        assert self._store is not None
        return self._store.get_stats(self.scope.agent_id)

    def context(self, query: str = "", max_results: int = 5) -> str:
        """Return the startup continuity packet for an agent."""

        self._ensure_init()
        assert self._store is not None

        maintenance = self.maintain(auto=True)
        stats = self._stats()
        continuity = self._store.search_hypomnema(
            query,
            agent_id=self.scope.agent_id,
            person_id=self.scope.person_id,
            project_scope=self.scope.project_scope,
            limit=max_results,
        )
        continuity = _filter_continuity(query, continuity)
        memories = self._retrieve(query, max_results=max_results) if query else []

        lines = [
            "Mnemos continuity packet",
            f"Scope: agent={self.scope.agent_id} person={self.scope.person_id} project={self.scope.project_scope}",
            "Storage: local SQLite store ready",
            (
                "Status: "
                f"{stats.get('engrams_active', 0)} memories, "
                f"{stats.get('hypomnema_active', 0)} continuity notes, "
                f"{stats.get('connections', 0)} connections"
            ),
            "",
            "Use this at the start of a session. Capture important preferences, decisions, project state, corrections, and durable context as the conversation unfolds.",
            "",
            "Maintenance:",
            _indent(maintenance),
        ]

        if continuity:
            lines.extend(["", "Continuity notes:"])
            lines.extend(_format_continuity(entry) for entry in continuity)
        else:
            lines.extend(["", "Continuity notes: none yet. Capture durable context when the user gives it."])

        if memories:
            lines.extend(["", "Relevant memories:"])
            lines.extend(_format_memory(result) for result in memories)

        return "\n".join(lines)

    def identity_graph(self, max_nodes: int = 18) -> dict[str, Any]:
        """Build a portable identity graph snapshot for visual-capable clients."""

        self._ensure_init()
        assert self._store is not None

        max_nodes = min(max(int(max_nodes or 18), 4), 48)
        stats = self._stats()
        continuity = self._store.search_hypomnema(
            "",
            agent_id=self.scope.agent_id,
            person_id=self.scope.person_id,
            project_scope=self.scope.project_scope,
            limit=max_nodes,
        )
        engrams = self._store.get_active_engrams(
            agent_id=self.scope.agent_id,
            limit=max_nodes,
            load_connections=False,
        )

        domain_counts: dict[str, int] = {}
        for entry in continuity:
            domain = entry.get("domain") or "topical"
            domain_counts[domain] = domain_counts.get(domain, 0) + 1

        nodes: list[dict[str, Any]] = [
            {
                "id": f"agent:{self.scope.agent_id}",
                "label": self.scope.agent_id,
                "kind": "agent",
                "weight": 1.0,
            }
        ]
        edges: list[dict[str, Any]] = []
        for domain, count in sorted(domain_counts.items(), key=lambda item: (-item[1], item[0])):
            domain_id = f"domain:{domain}"
            nodes.append({
                "id": domain_id,
                "label": domain,
                "kind": "domain",
                "weight": count,
            })
            edges.append({
                "source": f"agent:{self.scope.agent_id}",
                "target": domain_id,
                "relation": "contains",
                "strength": min(1.0, 0.35 + count * 0.12),
            })

        for entry in continuity[:max_nodes]:
            domain = entry.get("domain") or "topical"
            node_id = f"continuity:{entry['id']}"
            nodes.append({
                "id": node_id,
                "label": _short_label(entry.get("content", ""), 44),
                "kind": "continuity",
                "domain": domain,
                "confidence": round(float(entry.get("confidence", 0.0)), 3),
                "salience": round(float(entry.get("salience", 0.0)), 3),
                "created_at": entry.get("created_at"),
            })
            edges.append({
                "source": f"domain:{domain}",
                "target": node_id,
                "relation": "anchors",
                "strength": round(float(entry.get("salience", 0.5)), 3),
            })

        for engram in engrams[: max(3, max_nodes // 2)]:
            node_id = f"memory:{engram.id}"
            nodes.append({
                "id": node_id,
                "label": _short_label(engram.impact or engram.content, 38),
                "kind": "memory",
                "confidence": round(float(engram.source.confidence), 3),
                "strength": round(float(engram.strength), 3),
                "stability": round(float(engram.stability), 3),
                "accessibility": round(float(engram.accessibility), 3),
                "source_type": engram.source.type,
                "created_at": engram.created_at,
            })
            edges.append({
                "source": f"agent:{self.scope.agent_id}",
                "target": node_id,
                "relation": "encodes",
                "strength": round(float(engram.accessibility), 3),
            })

        timeline = _build_timeline(continuity, engrams)
        summary = (
            f"{stats.get('engrams_active', 0)} active memories, "
            f"{stats.get('hypomnema_active', 0)} continuity notes, "
            f"{stats.get('connections', 0)} connections"
        )
        snapshot = {
            "version": 1,
            "scope": {
                "agent_id": self.scope.agent_id,
                "person_id": self.scope.person_id,
                "project_scope": self.scope.project_scope,
            },
            "summary": summary,
            "stats": {
                "active_memories": stats.get("engrams_active", 0),
                "continuity_notes": stats.get("hypomnema_active", 0),
                "connections": stats.get("connections", 0),
                "archived": stats.get("archived", 0),
            },
            "nodes": nodes,
            "edges": edges,
            "timeline": timeline,
        }
        snapshot["svg"] = _render_identity_svg(snapshot)
        return snapshot

    def capture(
        self,
        content: str,
        context: str = "",
        importance: str | float = "auto",
    ) -> str:
        """Capture durable continuity without exposing Mnemos internals."""

        if not content.strip():
            return "Nothing captured: content was empty."

        self._ensure_init()
        assert self._store is not None
        assert self._encoder is not None

        full_content = content.strip()
        if context.strip():
            full_content = f"{full_content}\n\nContext: {context.strip()}"

        domain = _classify_domain(full_content)
        kind = _classify_kind(full_content)
        tags = _simple_tags(content, context)
        confidence, salience = _importance_scores(importance, domain)
        impact = _impact_for(content, domain)

        engram = self._encoder.encode(
            content=full_content,
            impact=impact,
            kind=kind,
            tags=tags,
            source=SourceType.SESSION,
            agent_id=self.scope.agent_id,
            override_confidence=confidence,
            skip_surprise_detection=True,
        )
        note_id = self._store.write_hypomnema_entry(
            content.strip(),
            agent_id=self.scope.agent_id,
            person_id=self.scope.person_id,
            project_scope=self.scope.project_scope,
            source="observed",
            domain=domain,
            tags=tags,
            confidence=confidence,
            salience=salience,
            foundational=domain in {"foundational", "identity"},
            related_engram_id=engram.id,
        )
        self._store.mark_hypomnema_promoted(note_id, engram.id)
        maintenance = self.maintain(auto=True)

        return (
            "Captured continuity.\n"
            f"Memory ID: {engram.id}\n"
            f"Continuity note ID: {note_id}\n"
            f"Scope: {self.scope.agent_id}/{self.scope.person_id}/{self.scope.project_scope}\n"
            "Maintenance:\n"
            f"{_indent(maintenance)}"
        )

    def recall(self, query: str, max_results: int = 5) -> str:
        """Recall relevant continuity and durable memories."""

        if not query.strip():
            return "Recall needs a query."

        self._ensure_init()
        assert self._store is not None

        continuity = self._store.search_hypomnema(
            query,
            agent_id=self.scope.agent_id,
            person_id=self.scope.person_id,
            project_scope=self.scope.project_scope,
            limit=max_results,
        )
        continuity = _filter_continuity(query, continuity)
        memories = self._retrieve(query, max_results=max_results)

        if not continuity and not memories:
            return "No relevant continuity found."

        lines = [f"Mnemos recall for: {query.strip()}"]
        if continuity:
            lines.extend(["", "Continuity notes:"])
            lines.extend(_format_continuity(entry) for entry in continuity)
        if memories:
            lines.extend(["", "Durable memories:"])
            lines.extend(_format_memory(result) for result in memories)
        return "\n".join(lines)

    def correct(
        self,
        correction: str,
        target_id: str = "",
        query: str = "",
        action: str = "update",
    ) -> str:
        """Correct, supersede, or archive stale memory."""

        if not correction.strip() and action not in {"forget", "archive", "remove", "delete"}:
            return "Correction needs replacement text or a forget/archive action."

        self._ensure_init()
        assert self._store is not None
        assert self._encoder is not None

        action = action.strip().lower() or "update"
        target = target_id.strip()

        if target:
            hypo = self._store.get_hypomnema_entry(
                target,
                agent_id=self.scope.agent_id,
                person_id=self.scope.person_id,
                project_scope=self.scope.project_scope,
            )
            if hypo is not None:
                if action in {"forget", "archive", "remove", "delete"}:
                    self._store.archive_hypomnema_entry(
                        target,
                        reason=f"simple correction action={action}",
                        agent_id=self.scope.agent_id,
                        person_id=self.scope.person_id,
                        project_scope=self.scope.project_scope,
                    )
                    related_engram_id = hypo.get("related_engram_id") or hypo.get("graduated_to_engram_id")
                    if related_engram_id:
                        related = self._store.get_engram(related_engram_id)
                        if related is not None:
                            self._store.archive_engram(related, reason=f"simple_correction_{action}")
                    return f"Archived continuity note {target}."

                self._store.revise_hypomnema_entry(
                    target,
                    correction,
                    reason="simple correction",
                    agent_id=self.scope.agent_id,
                    person_id=self.scope.person_id,
                    project_scope=self.scope.project_scope,
                    confidence=0.92,
                    salience=0.75,
                )
                return f"Updated continuity note {target}."

            engram = self._store.get_engram(target)
            if engram is not None:
                self._store.archive_engram(engram, reason=f"simple_correction_{action}")
                if action in {"forget", "archive", "remove", "delete"} and not correction.strip():
                    return f"Archived memory {target}."
                replacement = self._encoder.encode(
                    content=correction.strip(),
                    impact="Correction to earlier continuity.",
                    kind=_classify_kind(correction),
                    tags=["continuity", "correction"],
                    source=SourceType.SESSION,
                    agent_id=self.scope.agent_id,
                    override_confidence=0.92,
                    skip_surprise_detection=True,
                )
                return (
                    f"Archived memory {target} and captured correction {replacement.id}.\n"
                    f"Correction: {correction.strip()}"
                )

        search_text = query.strip() or correction.strip()
        query_text = query.strip()
        if query_text:
            matches = self._store.search_hypomnema(
                query_text,
                agent_id=self.scope.agent_id,
                person_id=self.scope.person_id,
                project_scope=self.scope.project_scope,
                limit=1,
            )
            if matches:
                match = matches[0]
                if action in {"forget", "archive", "remove", "delete"}:
                    self._store.archive_hypomnema_entry(
                        match["id"],
                        reason=f"simple correction action={action}; query={query_text}",
                        agent_id=self.scope.agent_id,
                        person_id=self.scope.person_id,
                        project_scope=self.scope.project_scope,
                    )
                    related_engram_id = match.get("related_engram_id") or match.get("graduated_to_engram_id")
                    if related_engram_id:
                        related = self._store.get_engram(related_engram_id)
                        if related is not None:
                            self._store.archive_engram(related, reason=f"simple_correction_{action}")
                    maintenance = self.maintain(auto=True)
                    return (
                        f"Archived closest continuity note {match['id']}.\n"
                        "Maintenance:\n"
                        f"{_indent(maintenance)}"
                    )

                note_id = match["id"]
                if action in {"supersede", "replace"}:
                    note_id = self._store.supersede_hypomnema_entry(
                        match["id"],
                        correction,
                        reason=f"simple correction action={action}; query={query_text}",
                        agent_id=self.scope.agent_id,
                        person_id=self.scope.person_id,
                        project_scope=self.scope.project_scope,
                    )
                else:
                    self._store.revise_hypomnema_entry(
                        match["id"],
                        correction,
                        reason=f"simple correction query={query_text}",
                        agent_id=self.scope.agent_id,
                        person_id=self.scope.person_id,
                        project_scope=self.scope.project_scope,
                        confidence=0.92,
                        salience=0.75,
                    )

                related_engram_id = match.get("related_engram_id") or match.get("graduated_to_engram_id")
                if related_engram_id:
                    related = self._store.get_engram(related_engram_id)
                    if related is not None:
                        self._store.archive_engram(related, reason=f"simple_correction_{action}")

                replacement = self._encoder.encode(
                    content=correction.strip(),
                    impact="Corrected continuity for future interactions.",
                    kind=_classify_kind(correction),
                    tags=sorted(set(["continuity", "correction", *_simple_tags(correction)])),
                    source=SourceType.SESSION,
                    agent_id=self.scope.agent_id,
                    override_confidence=0.92,
                    skip_surprise_detection=True,
                )
                self._store.mark_hypomnema_promoted(note_id, replacement.id)
                maintenance = self.maintain(auto=True)
                return (
                    f"Updated closest continuity note {note_id}.\n"
                    f"Memory ID: {replacement.id}\n"
                    "Maintenance:\n"
                    f"{_indent(maintenance)}"
                )

        if action in {"forget", "archive", "remove", "delete"} and search_text:
            matches = self._retrieve(search_text, max_results=1)
            if matches:
                engram = matches[0].engram
                self._store.archive_engram(engram, reason=f"simple_correction_{action}")
                return f"Archived closest matching memory {engram.id}."

        return self.capture(
            correction.strip(),
            context=f"Correction supplied through mnemos_correct. Prior query: {query.strip()}",
            importance="high",
        )

    def maintain(self, deep: bool = False, auto: bool = False) -> str:
        """Run the best available maintenance without requiring setup."""

        self._ensure_init()
        assert self._store is not None

        requested_deep = bool(deep)
        can_run_deep = requested_deep and self._llm_client is not None
        daemon = ConsolidationDaemon(
            store=self._store,
            config={},
            llm_client=self._llm_client if can_run_deep else None,
            embedding_index=self._embedding_index,
        )
        stats = daemon.run_cycle(deep=can_run_deep, agent_id=self.scope.agent_id)
        promoted = self._promote_candidates(limit=3)
        if can_run_deep:
            completed = "model-assisted deep maintenance completed"
        elif requested_deep:
            completed = "local deterministic maintenance completed; model-assisted deep pass unavailable"
        else:
            completed = "local deterministic maintenance completed"

        model_note = "dedicated model available" if self._llm_client else "no dedicated model configured"
        if requested_deep and not can_run_deep:
            model_note += "; deep requested, ran local deterministic maintenance"
        elif not requested_deep:
            model_note += "; ran local deterministic maintenance"
        if auto:
            model_note += " during normal use"

        lines = [
            f"Requested: {'deep' if requested_deep else 'standard'}",
            f"Cycle: {stats.get('cycle_type', 'shallow')}",
            f"Completed: {completed}",
            f"Passes: {', '.join(stats.get('passes_run', [])) or 'none'}",
            f"Promoted continuity notes: {promoted}",
            f"Model path: {model_note}",
        ]
        errors = [key for key in stats if key.endswith("_error")]
        for key in errors:
            lines.append(f"{key}: {stats[key]}")
        return "\n".join(lines)

    def _retrieve(self, query: str, max_results: int = 5) -> list[Any]:
        assert self._store is not None
        assert self._retriever is not None
        emotional_state = self._store.get_latest_emotional_state(self.scope.agent_id)
        return _filter_memories(query, self._retriever.retrieve(
            cue=query,
            agent_id=self.scope.agent_id,
            max_results=max(1, max_results),
            emotional_state=emotional_state,
        ))

    def _promote_candidates(self, limit: int = 3) -> int:
        assert self._store is not None
        assert self._encoder is not None
        candidates = self._store.get_hypomnema_promotion_candidates(
            agent_id=self.scope.agent_id,
            person_id=self.scope.person_id,
            project_scope=self.scope.project_scope,
            limit=limit,
        )
        promoted = 0
        for entry in candidates:
            if entry.get("related_engram_id"):
                self._store.mark_hypomnema_promoted(entry["id"], entry["related_engram_id"])
                promoted += 1
                continue
            engram = self._encoder.encode(
                content=entry["content"],
                impact="Stable continuity promoted during simple maintenance.",
                kind="semantic",
                tags=["continuity", "promoted", *entry.get("tags", [])],
                source=SourceType.BACKGROUND,
                agent_id=self.scope.agent_id,
                override_confidence=float(entry["confidence"]),
                skip_surprise_detection=True,
            )
            self._store.mark_hypomnema_promoted(entry["id"], engram.id)
            promoted += 1
        return promoted


def _importance_scores(importance: str | float, domain: str) -> tuple[float, float]:
    if isinstance(importance, (float, int)):
        normalized_score = min(max(float(importance), 0.0), 1.0)
        confidence = min(max(0.55 + (normalized_score * 0.4), 0.55), 0.95)
        salience = min(max(0.35 + (normalized_score * 0.55), 0.35), 0.9)
        return confidence, salience

    normalized = str(importance).strip().lower()
    if normalized in {"low", "minor"}:
        return 0.72, 0.45
    if normalized in {"high", "important", "critical"}:
        return 0.92, 0.82
    if domain in {"foundational", "identity"}:
        return 0.9, 0.8
    if domain in {"recurring", "long-arc"}:
        return 0.86, 0.72
    return 0.82, 0.66


def _impact_for(content: str, domain: str) -> str:
    if domain in {"foundational", "identity"}:
        return "Foundational continuity for future interactions."
    if domain == "recurring":
        return "Recurring pattern worth carrying across sessions."
    if domain == "long-arc":
        return "Long-arc context that should shape future work."
    if domain == "situational":
        return "Current working context for continuity."
    if "prefer" in content.lower() or "wants" in content.lower():
        return "Preference to respect in future decisions."
    return "Durable continuity captured from the session."


def _format_continuity(entry: dict[str, Any]) -> str:
    score = entry.get("score", 0.0)
    content = entry["content"].replace("\n", " ")
    if len(content) > 180:
        content = content[:177] + "..."
    return (
        f"- [{score:.2f}] {content}\n"
        f"  id={entry['id']} domain={entry['domain']} confidence={entry['confidence']:.2f}"
    )


def _format_memory(result: Any) -> str:
    engram = result.engram
    display = engram.impact or engram.content
    display = display.replace("\n", " ")
    if len(display) > 180:
        display = display[:177] + "..."
    return (
        f"- [{result.score:.2f}] {display}\n"
        f"  id={engram.id} kind={engram.kind} confidence={engram.source.confidence:.2f}"
    )


def _indent(text: str) -> str:
    return "\n".join(f"  {line}" if line else "" for line in text.splitlines())


def _short_label(value: str, limit: int) -> str:
    clean = " ".join(value.split())
    if len(clean) <= limit:
        return clean
    return clean[: max(1, limit - 1)].rstrip() + "..."


def _build_timeline(entries: list[dict[str, Any]], engrams: list[Any]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, int]] = {}
    for entry in entries:
        day = str(entry.get("created_at") or "")[:10] or "unknown"
        bucket = buckets.setdefault(day, {"continuity": 0, "memories": 0})
        bucket["continuity"] += 1
    for engram in engrams:
        day = str(getattr(engram, "created_at", "") or "")[:10] or "unknown"
        bucket = buckets.setdefault(day, {"continuity": 0, "memories": 0})
        bucket["memories"] += 1
    return [
        {"date": day, **counts}
        for day, counts in sorted(buckets.items())
        if day != "unknown"
    ]


def _render_identity_svg(snapshot: dict[str, Any]) -> str:
    width = 1280
    height = 800
    palette = {
        "bg": "#0e0e11",
        "surface": "#151518",
        "raised": "#1a1a1e",
        "rule": "rgba(220,219,216,0.10)",
        "rule_strong": "rgba(220,219,216,0.20)",
        "line": "rgba(220,219,216,0.34)",
        "text": "#F4F3F0",
        "body": "rgba(210,208,204,0.70)",
        "muted": "rgba(161,159,155,0.48)",
        "ghost": "rgba(132,130,126,0.16)",
        "node": "rgba(244,243,240,0.88)",
        "node_soft": "rgba(244,243,240,0.12)",
        "node_mid": "rgba(244,243,240,0.28)",
    }
    graph_x = 318
    graph_y = 150
    graph_w = 892
    graph_h = 482
    center_x = graph_x + graph_w * 0.44
    center_y = graph_y + graph_h * 0.44
    nodes = snapshot["nodes"]
    domain_nodes = [node for node in nodes if node["kind"] == "domain"]
    continuity_nodes = [node for node in nodes if node["kind"] == "continuity"]
    memory_nodes = [node for node in nodes if node["kind"] == "memory"]

    positions: dict[str, tuple[float, float]] = {
        f"agent:{snapshot['scope']['agent_id']}": (center_x, center_y)
    }

    if domain_nodes:
        for index, node in enumerate(domain_nodes):
            step = graph_h * 0.54 / max(1, len(domain_nodes) - 1)
            positions[node["id"]] = (graph_x + 144, graph_y + 116 + index * step)

    if continuity_nodes:
        for index, node in enumerate(continuity_nodes):
            row = index % 8
            col = index // 8
            positions[node["id"]] = (
                graph_x + graph_w - 250 + col * 96,
                graph_y + 78 + row * 44,
            )

    timeline = snapshot.get("timeline", [])
    if memory_nodes:
        start_x = graph_x + 72
        step = (graph_w - 144) / max(1, len(memory_nodes) - 1)
        for index, node in enumerate(memory_nodes):
            positions[node["id"]] = (start_x + index * step, graph_y + graph_h - 62)

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        "<title id=\"title\">Mnemos Identity Graph</title>",
        "<desc id=\"desc\">A scoped monochrome snapshot of an agent identity graph, continuity anchors, memory traces, and formation over time.</desc>",
        "<defs>",
        "<pattern id=\"grid\" width=\"32\" height=\"32\" patternUnits=\"userSpaceOnUse\"><path d=\"M 32 0 L 0 0 0 32\" fill=\"none\" stroke=\"rgba(220,219,216,0.035)\" stroke-width=\"1\"/></pattern>",
        "<filter id=\"shadow\"><feDropShadow dx=\"0\" dy=\"10\" stdDeviation=\"18\" flood-color=\"#000\" flood-opacity=\"0.32\"/></filter>",
        "<filter id=\"fine-glow\"><feDropShadow dx=\"0\" dy=\"0\" stdDeviation=\"5\" flood-color=\"#F4F3F0\" flood-opacity=\"0.13\"/></filter>",
        "</defs>",
        f'<rect width="{width}" height="{height}" fill="{palette["bg"]}"/>',
        '<rect width="1280" height="800" fill="url(#grid)" opacity="0.9"/>',
        f'<rect x="38" y="34" width="{width - 76}" height="{height - 68}" rx="6" fill="none" stroke="{palette["rule"]}"/>',
        f'<text x="58" y="70" fill="{palette["muted"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="11" letter-spacing="0">MNEMOS.IDENTITY_GRAPH / SCOPED TOPOLOGY</text>',
        f'<text x="58" y="104" fill="{palette["text"]}" font-family="Inter, Arial, sans-serif" font-size="29" font-weight="620">Mnemos Identity Graph</text>',
        f'<text x="58" y="132" fill="{palette["body"]}" font-family="Inter, Arial, sans-serif" font-size="13">{_escape(snapshot["summary"])}</text>',
        f'<text x="1032" y="70" fill="{palette["muted"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="10" text-anchor="end">schema=v{_escape(snapshot.get("version", 1))}</text>',
        f'<text x="1178" y="70" fill="{palette["muted"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="10" text-anchor="end">nodes={len(nodes):02d} / edges={len(snapshot["edges"]):02d}</text>',
        f'<rect x="58" y="150" width="220" height="220" rx="6" fill="{palette["surface"]}" stroke="{palette["rule"]}" filter="url(#shadow)"/>',
        f'<text x="78" y="184" fill="{palette["muted"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="10">SCOPE</text>',
        f'<text x="78" y="218" fill="{palette["text"]}" font-family="Inter, Arial, sans-serif" font-size="20" font-weight="540">{_escape(snapshot["scope"]["agent_id"])}</text>',
        f'<text x="78" y="250" fill="{palette["body"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="11">person  {_escape(snapshot["scope"]["person_id"])}</text>',
        f'<text x="78" y="276" fill="{palette["body"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="11">project {_escape(snapshot["scope"]["project_scope"])}</text>',
        f'<line x1="78" y1="306" x2="258" y2="306" stroke="{palette["rule"]}"/>',
        f'<text x="78" y="336" fill="{palette["muted"]}" font-family="Inter, Arial, sans-serif" font-size="12">portable SVG plus structured graph data</text>',
        f'<rect x="58" y="394" width="220" height="238" rx="6" fill="{palette["surface"]}" stroke="{palette["rule"]}" filter="url(#shadow)"/>',
        f'<text x="78" y="426" fill="{palette["muted"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="10">MEASURES</text>',
        f'<rect x="{graph_x}" y="{graph_y}" width="{graph_w}" height="{graph_h}" rx="6" fill="{palette["surface"]}" stroke="{palette["rule_strong"]}" filter="url(#shadow)"/>',
        f'<rect x="{graph_x + 1}" y="{graph_y + 1}" width="{graph_w - 2}" height="{graph_h - 2}" rx="5" fill="url(#grid)" opacity="0.55"/>',
        f'<text x="{graph_x + 22}" y="{graph_y + 34}" fill="{palette["muted"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="10">TOPOLOGY FIELD</text>',
        f'<text x="{graph_x + graph_w - 22}" y="{graph_y + 34}" fill="{palette["muted"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="10" text-anchor="end">formation live / monochrome</text>',
    ]

    stats = snapshot.get("stats", {})
    stat_rows = [
        ("active memories", stats.get("active_memories", 0)),
        ("continuity notes", stats.get("continuity_notes", 0)),
        ("connections", stats.get("connections", 0)),
        ("archived", stats.get("archived", 0)),
    ]
    for index, (label, value) in enumerate(stat_rows):
        y = 464 + index * 38
        lines.append(f'<text x="78" y="{y}" fill="{palette["text"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="22" font-weight="540">{_escape(value)}</text>')
        lines.append(f'<text x="132" y="{y}" fill="{palette["muted"]}" font-family="Inter, Arial, sans-serif" font-size="12">{_escape(label)}</text>')

    if domain_nodes:
        lines.append(f'<text x="78" y="650" fill="{palette["muted"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="10">DOMAIN INDEX</text>')
        for index, node in enumerate(domain_nodes[:5]):
            y = 678 + index * 20
            weight = int(node.get("weight", 0))
            lines.append(f'<text x="78" y="{y}" fill="{palette["body"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="10">{_escape(_short_label(node["label"], 15))}</text>')
            lines.append(f'<text x="250" y="{y}" fill="{palette["muted"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="10" text-anchor="end">{weight:02d}</text>')

    for edge in snapshot["edges"]:
        source = positions.get(edge["source"])
        target = positions.get(edge["target"])
        if not source or not target:
            continue
        opacity = min(max(float(edge.get("strength", 0.45)), 0.18), 0.85)
        dash = {
            "contains": "",
            "anchors": "5 8",
            "encodes": "2 7",
        }.get(str(edge.get("relation")), "")
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        lines.append(
            f'<line x1="{source[0]:.1f}" y1="{source[1]:.1f}" x2="{target[0]:.1f}" y2="{target[1]:.1f}" '
            f'stroke="{palette["line"]}" stroke-width="{0.8 + opacity * 1.8:.2f}" opacity="{opacity:.2f}"{dash_attr}/>'
        )

    def draw_node(node: dict[str, Any]) -> None:
        x, y = positions[node["id"]]
        kind = node["kind"]
        if kind == "agent":
            radius = 58
        elif kind == "domain":
            radius = 24 + min(float(node.get("weight", 1)), 6) * 2
        elif kind == "continuity":
            radius = 10 + min(float(node.get("salience", 0.45)), 1.0) * 9
        else:
            radius = 8 + min(float(node.get("accessibility", 0.45)), 1.0) * 8
        label = _escape(node["label"])
        if kind == "agent":
            lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="76" fill="{palette["node_soft"]}" stroke="{palette["ghost"]}"/>')
            lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{palette["raised"]}" stroke="{palette["node"]}" stroke-width="1.4" filter="url(#fine-glow)"/>')
            lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{palette["node"]}"/>')
            lines.append(
                f'<text x="{x:.1f}" y="{y - 10:.1f}" fill="{palette["text"]}" font-family="Inter, Arial, sans-serif" '
                f'font-size="15" font-weight="540" text-anchor="middle">{label}</text>'
            )
            lines.append(
                f'<text x="{x:.1f}" y="{y + 18:.1f}" fill="{palette["muted"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" '
                'font-size="10" text-anchor="middle">agent core</text>'
            )
        elif kind == "domain":
            lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{palette["node_soft"]}" stroke="{palette["node_mid"]}" stroke-width="1.2"/>')
            lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4" fill="{palette["node"]}"/>')
            lines.append(
                f'<text x="{x - radius - 12:.1f}" y="{y + 4:.1f}" fill="{palette["body"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" '
                f'font-size="10" text-anchor="end">{label}</text>'
            )
        elif kind == "continuity":
            lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{palette["node_soft"]}" stroke="{palette["node_mid"]}" stroke-width="1"/>')
            lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.8" fill="{palette["node"]}"/>')
            lines.append(
                f'<text x="{x + radius + 12:.1f}" y="{y - 2:.1f}" fill="{palette["body"]}" font-family="Inter, Arial, sans-serif" '
                f'font-size="10">{_escape(_short_label(node["label"], 34))}</text>'
            )
            lines.append(
                f'<text x="{x + radius + 12:.1f}" y="{y + 13:.1f}" fill="{palette["muted"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" '
                f'font-size="8">salience {float(node.get("salience", 0.0)):.2f}</text>'
            )
        else:
            lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{palette["node_soft"]}" stroke="{palette["node_mid"]}" stroke-width="1"/>')
            lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.6" fill="{palette["node"]}"/>')
            lines.append(
                f'<text x="{x:.1f}" y="{y + 31:.1f}" fill="{palette["muted"]}" font-family="Inter, Arial, sans-serif" '
                f'font-size="9" text-anchor="middle">{_escape(_short_label(node["label"], 18))}</text>'
            )

    for node in domain_nodes:
        draw_node(node)
    for node in continuity_nodes:
        draw_node(node)
    for node in memory_nodes:
        draw_node(node)
    draw_node(nodes[0])

    if timeline:
        lines.append(f'<rect x="{graph_x}" y="662" width="{graph_w}" height="70" rx="6" fill="{palette["surface"]}" stroke="{palette["rule"]}"/>')
        lines.append(f'<text x="{graph_x + 22}" y="688" fill="{palette["muted"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="10">FORMATION OVER TIME</text>')
        max_total = max(1, max(item["continuity"] + item["memories"] for item in timeline))
        start_x = graph_x + 180
        bar_w = min(34, 520 / max(1, len(timeline)))
        for index, item in enumerate(timeline[-16:]):
            total = item["continuity"] + item["memories"]
            h = 8 + (total / max_total) * 35
            x = start_x + index * (bar_w + 8)
            y = 717 - h
            lines.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" rx="2" fill="{palette["node"]}" opacity="0.66"/>')
            lines.append(f'<text x="{x + bar_w / 2:.1f}" y="724" fill="{palette["muted"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="8" text-anchor="middle">{_escape(item["date"][-5:])}</text>')
    else:
        lines.append(f'<rect x="{graph_x}" y="662" width="{graph_w}" height="70" rx="6" fill="{palette["surface"]}" stroke="{palette["rule"]}"/>')
        lines.append(f'<text x="{graph_x + 22}" y="702" fill="{palette["muted"]}" font-family="JetBrains Mono, SF Mono, Menlo, monospace" font-size="10">FORMATION OVER TIME / no dated events yet</text>')

    lines.append("</svg>")
    return "\n".join(lines)


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)
