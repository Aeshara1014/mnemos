"""Shared test fixtures for Mnemos."""
import os
import tempfile
import pytest


@pytest.fixture(autouse=True)
def _isolate_mnemos_env(monkeypatch):
    """No developer's real environment bleeds into tests.

    MNEMOS_DISABLE_DOTENV stops llm._load_env_key (and the OpenClaw key
    lookup) from reading workspace .env files; the MNEMOS_*/provider
    variables are cleared so every test starts from a clean slate and
    sets exactly what it needs via monkeypatch.setenv.
    """
    for var in (
        "MNEMOS_LLM_PROVIDER", "MNEMOS_MODEL", "MNEMOS_AGENT_MODEL",
        "MNEMOS_SUBSTRATE_AFFINITY", "MNEMOS_AGENT_ID", "MNEMOS_PERSON_ID",
        "MNEMOS_PROJECT_SCOPE", "MNEMOS_DB_PATH", "MNEMOS_ENV_PATHS",
        "MNEMOS_WORKSPACE", "MNEMOS_MODE",
        "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("MNEMOS_DISABLE_DOTENV", "1")


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database path."""
    return str(tmp_path / "test_memory.db")


@pytest.fixture
def store(tmp_db):
    """Create a temporary EngramStore."""
    from mnemos.store.sqlite_store import EngramStore
    s = EngramStore(tmp_db)
    yield s
    s.close()


@pytest.fixture
def encoder(store):
    """Create an Encoder with no LLM (rule-based fallback)."""
    from mnemos.encoding.encoder import Encoder
    return Encoder(store, llm_client=None)


@pytest.fixture
def retriever(store):
    """Create a ReactiveRetriever."""
    from mnemos.retrieval.reactive import ReactiveRetriever
    return ReactiveRetriever(store)


@pytest.fixture
def stub_llm():
    """Minimal LLM stand-in: prose for complete(), empty array for structured."""
    class _StubLLM:
        def complete(self, prompt):
            return "A considered response."

        def structured_complete(self, system, user, temperature=0.0,
                                max_tokens=2000):
            return "[]"

    return _StubLLM()


@pytest.fixture
def capture_urlopen(monkeypatch):
    """Capture urllib POSTs; the test chooses the canned response body.

    Returns (calls, respond_with): calls collects {url, body, headers,
    timeout} per request; respond_with(dict) sets the JSON the fake
    server returns.
    """
    import io
    import json as _json

    calls = []
    canned: dict = {}

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(req, timeout=None):
        calls.append({
            "url": req.full_url,
            "body": _json.loads(req.data.decode()),
            "headers": dict(req.header_items()),
            "timeout": timeout,
        })
        return _Resp(_json.dumps(canned).encode())

    def respond_with(d):
        nonlocal canned
        canned = d

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    return calls, respond_with
