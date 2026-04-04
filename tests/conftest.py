"""Shared test fixtures for Mnemos."""
import os
import tempfile
import pytest


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
