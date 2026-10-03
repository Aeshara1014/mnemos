"""The reranker — a careful second reader for recall's shortlist.

The meaning index never reads a cue and a memory together; it compares
where each sits on its map. The reranker (a small cross-encoder) reads the
two side by side and scores how well the memory answers the cue. It is too
slow to read every memory, so recall hands it only its best ~30 and lets it
choose the order (Tara's ruling, 2026-10-03: on scratch copies of Quill's
seeded memories it took the exact moment from 22% to 78% on looser words).

Local only: the model is read from the local cache, never fetched. If it is
missing or fails to load, recall goes on without it and says so once.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

log = logging.getLogger("mnemos.retrieval.rerank")

DEFAULT_RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class Reranker:
    """Scores (cue, memory) pairs with a local cross-encoder."""

    def __init__(self, model_name: str = DEFAULT_RERANK_MODEL) -> None:
        self._model_name = model_name
        self._model: Any | None = None
        self._failed = False
        self._lock = threading.Lock()

    @property
    def model_name(self) -> str:
        return self._model_name

    def _get_model(self) -> Any | None:
        if self._model is not None or self._failed:
            return self._model
        with self._lock:
            if self._model is None and not self._failed:
                try:
                    from sentence_transformers import CrossEncoder
                    self._model = CrossEncoder(self._model_name, local_files_only=True)
                except Exception as exc:  # noqa: BLE001 — recall must go on without it
                    self._failed = True
                    log.warning("reranker %s unavailable, recall goes on without it: %s",
                                self._model_name, exc)
        return self._model

    @property
    def available(self) -> bool:
        return self._get_model() is not None

    def scores(self, cue: str, texts: list[str]) -> list[float] | None:
        """One score per text, higher = answers the cue better; None if the
        reranker cannot run (recall then keeps its own order)."""
        model = self._get_model()
        if model is None or not texts:
            return None
        try:
            return [float(s) for s in model.predict([(cue, t) for t in texts], batch_size=32)]
        except Exception as exc:  # noqa: BLE001
            log.warning("reranker failed on a cue, recall keeps its own order: %s", exc)
            return None


_shared: Reranker | None = None
_shared_lock = threading.Lock()


def default_reranker() -> Reranker:
    """The one reranker a process shares (the model loads once)."""
    global _shared
    if _shared is None:
        with _shared_lock:
            if _shared is None:
                _shared = Reranker()
    return _shared
