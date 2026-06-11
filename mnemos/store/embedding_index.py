"""
Embedding index for semantic similarity search.

Supports two backends:
  1. Gemini API (gemini-embedding-2-preview, 3072 dims) — default, high quality
  2. Local sentence-transformers (all-MiniLM-L6-v2, 384 dims) — fallback if no API key

Backend selection:
  - If GEMINI_API_KEY is found (env var or .env files), uses Gemini API
  - Otherwise falls back to local sentence-transformers
  - If neither is available, all operations silently return empty results

Embeddings stored in SQLite alongside engrams.
"""

from __future__ import annotations

import json
import os
import sqlite3
import struct
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any


# --- Key resolution (shared with mnemos/llm.py) ---

def _load_env_key(key_name: str) -> str | None:
    """Load a key from the environment or the configured .env locations.

    Delegates to llm._load_env_key so the search path (MNEMOS_ENV_PATHS,
    then cwd/.env and ~/.mnemos/.env) and MNEMOS_DISABLE_DOTENV are
    honored in one place.
    """
    from ..llm import _load_env_key as _shared_load_env_key

    return _shared_load_env_key(key_name) or None


# --- Gemini API embedding ---

class _GeminiEmbedder:
    """Generates embeddings via Google Gemini API."""
    
    def __init__(self, api_key: str, model: str = "gemini-embedding-2-preview"):
        self._api_key = api_key
        self._model = model
        self._dims = 3072
    
    @property
    def dims(self) -> int:
        return self._dims
    
    @property
    def model_name(self) -> str:
        return self._model
    
    def embed(self, text: str) -> list[float] | None:
        """Generate embedding for a single text."""
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self._model}:embedContent?key={self._api_key}"
        )
        payload = json.dumps({
            "model": f"models/{self._model}",
            "content": {"parts": [{"text": text}]}
        }).encode()
        
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"}
        )
        try:
            resp = urllib.request.urlopen(req, timeout=30)
            data = json.loads(resp.read())
            values = data.get("embedding", {}).get("values", [])
            if values:
                self._dims = len(values)
                return values
            return None
        except Exception:
            return None
    
    def batch_embed(self, texts: list[str]) -> list[list[float] | None]:
        """Embed multiple texts via batchEmbedContents API."""
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self._model}:batchEmbedContents?key={self._api_key}"
        )
        
        requests_list = []
        for text in texts:
            requests_list.append({
                "model": f"models/{self._model}",
                "content": {"parts": [{"text": text}]}
            })
        
        # Gemini batch API has a limit of 100 per request
        all_results: list[list[float] | None] = []
        batch_size = 100
        
        for i in range(0, len(requests_list), batch_size):
            batch = requests_list[i:i + batch_size]
            payload = json.dumps({"requests": batch}).encode()
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"}
            )
            
            try:
                resp = urllib.request.urlopen(req, timeout=120)
                data = json.loads(resp.read())
                for emb in data.get("embeddings", []):
                    values = emb.get("values", [])
                    if values:
                        self._dims = len(values)
                        all_results.append(values)
                    else:
                        all_results.append(None)
            except Exception:
                # Fall back to individual calls for this batch
                for r in batch:
                    text = r["content"]["parts"][0]["text"]
                    all_results.append(self.embed(text))
        
        return all_results


# --- Local sentence-transformers fallback ---

_HAS_LOCAL = False

def _check_local_deps() -> bool:
    global _HAS_LOCAL
    if _HAS_LOCAL:
        return True
    try:
        import sentence_transformers  # noqa: F401
        import numpy  # noqa: F401
        _HAS_LOCAL = True
        return True
    except ImportError:
        return False


class _LocalEmbedder:
    """Generates embeddings via local sentence-transformers."""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._model_name = model_name
        self._model: Any = None
        self._dims = 384
    
    @property
    def dims(self) -> int:
        return self._dims
    
    @property
    def model_name(self) -> str:
        return self._model_name
    
    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
        return self._model
    
    def embed(self, text: str) -> list[float] | None:
        model = self._get_model()
        if model is None:
            return None
        vec = model.encode(text, normalize_embeddings=True)
        return vec.tolist()
    
    def batch_embed(self, texts: list[str]) -> list[list[float] | None]:
        model = self._get_model()
        if model is None:
            return [None] * len(texts)
        vecs = model.encode(texts, normalize_embeddings=True, batch_size=32)
        return [v.tolist() for v in vecs]


# --- Main index class ---

class EmbeddingIndex:
    """Embedding index for semantic similarity search.

    Backend auto-selection:
      1. Gemini API if GEMINI_API_KEY available (3072 dims, high quality)
      2. Local sentence-transformers fallback (384 dims)
      3. Disabled if neither available

    Usage:
        index = EmbeddingIndex(db_path="~/.mnemos/memory.db")
        index.index_engram("engram_abc123", "The user prefers dark mode")
        results = index.search("UI theme preferences", k=5)
    """

    def __init__(
        self,
        db_path: str | None = None,
        model_name: str | None = None,
        gemini_api_key: str | None = None,
    ) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._embedder: _GeminiEmbedder | _LocalEmbedder | None = None
        self._available = False
        
        # Resolve Gemini API key
        api_key = gemini_api_key or _load_env_key("GEMINI_API_KEY")
        
        if api_key:
            gemini_model = model_name or os.environ.get(
                "MNEMOS_EMBEDDING_MODEL", "gemini-embedding-2-preview"
            )
            self._embedder = _GeminiEmbedder(api_key, gemini_model)
            self._available = True
        elif _check_local_deps():
            local_model = model_name or "all-MiniLM-L6-v2"
            self._embedder = _LocalEmbedder(local_model)
            self._available = True
        
        if self._available and db_path:
            self._init_table()

    def _init_table(self) -> None:
        conn = self._get_conn()
        if conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS embeddings (
                    engram_id TEXT PRIMARY KEY,
                    embedding BLOB NOT NULL,
                    model_name TEXT NOT NULL,
                    dims INTEGER NOT NULL
                )
            """)
            conn.commit()

    def _get_conn(self) -> sqlite3.Connection | None:
        if not self._db_path:
            return None
        if self._conn is None:
            self._conn = sqlite3.connect(str(Path(self._db_path).expanduser()))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _embed(self, text: str) -> list[float] | None:
        if not self._embedder:
            return None
        return self._embedder.embed(text)

    def _to_bytes(self, values: list[float]) -> bytes:
        return struct.pack(f'{len(values)}f', *values)
    
    def _from_bytes(self, data: bytes, dims: int) -> list[float]:
        return list(struct.unpack(f'{dims}f', data))

    @property
    def available(self) -> bool:
        return self._available
    
    @property
    def backend(self) -> str:
        if isinstance(self._embedder, _GeminiEmbedder):
            return f"gemini ({self._embedder.model_name})"
        elif isinstance(self._embedder, _LocalEmbedder):
            return f"local ({self._embedder.model_name})"
        return "none"

    def index_engram(self, engram_id: str, content: str) -> bool:
        if not self._available or not self._embedder:
            return False

        values = self._embed(content)
        if values is None:
            return False

        conn = self._get_conn()
        if conn is None:
            return False

        conn.execute(
            "INSERT OR REPLACE INTO embeddings "
            "(engram_id, embedding, model_name, dims) VALUES (?, ?, ?, ?)",
            (engram_id, self._to_bytes(values), self._embedder.model_name, len(values)),
        )
        conn.commit()
        return True

    def search(
        self,
        query: str,
        k: int = 10,
        exclude_ids: set[str] | None = None,
    ) -> list[tuple[str, float]]:
        if not self._available or not self._embedder:
            return []

        query_values = self._embed(query)
        if query_values is None:
            return []

        conn = self._get_conn()
        if conn is None:
            return []

        rows = conn.execute(
            "SELECT engram_id, embedding, dims FROM embeddings"
        ).fetchall()

        if not rows:
            return []

        exclude = exclude_ids or set()
        results: list[tuple[str, float]] = []
        
        # Normalize query vector
        q_norm = sum(v * v for v in query_values) ** 0.5
        if q_norm == 0:
            return []
        query_normalized = [v / q_norm for v in query_values]

        for row in rows:
            eid = row["engram_id"]
            if eid in exclude:
                continue

            dims = row["dims"]
            stored = self._from_bytes(row["embedding"], dims)
            
            # Skip dimension mismatch (old embeddings from different model)
            if len(stored) != len(query_normalized):
                continue
            
            # Cosine similarity
            s_norm = sum(v * v for v in stored) ** 0.5
            if s_norm == 0:
                continue
            
            dot = sum(q * s for q, s in zip(query_normalized, stored))
            similarity = dot / s_norm
            results.append((eid, round(similarity, 4)))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:k]

    def batch_index(self, items: list[tuple[str, str]]) -> int:
        if not self._available or not self._embedder:
            return 0

        conn = self._get_conn()
        if conn is None:
            return 0

        texts = [content for _, content in items]
        all_values = self._embedder.batch_embed(texts)

        count = 0
        for (engram_id, _), values in zip(items, all_values):
            if values is None:
                continue
            conn.execute(
                "INSERT OR REPLACE INTO embeddings "
                "(engram_id, embedding, model_name, dims) VALUES (?, ?, ?, ?)",
                (engram_id, self._to_bytes(values), self._embedder.model_name, len(values)),
            )
            count += 1

        conn.commit()
        return count

    def remove(self, engram_id: str) -> None:
        conn = self._get_conn()
        if conn:
            conn.execute("DELETE FROM embeddings WHERE engram_id = ?", (engram_id,))
            conn.commit()

    def count(self) -> int:
        conn = self._get_conn()
        if conn is None:
            return 0
        row = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()
        return row[0] if row else 0

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
