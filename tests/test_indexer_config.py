"""Indexer project resolution: durable config.json fallback for known/active projects.

Precedence: explicit arg > config dict > env (MNEMOS_*) > config.json indexer.* > [].
Config sits BELOW env so a live env value is never overridden by a stale file,
and known/active read separate keys so active is never coerced to known.
"""
import json

from pathlib import Path

from mnemos.indexer.session_indexer import SessionIndexer


def _seed_home(tmp_path, cfg):
    mn = tmp_path / ".mnemos"
    mn.mkdir(parents=True, exist_ok=True)
    (mn / "config.json").write_text(json.dumps(cfg))
    return tmp_path


def test_known_projects_fall_back_to_config(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(_seed_home(tmp_path, {"indexer": {"known_projects": ["claude-field", "mnemos"]}})))
    monkeypatch.delenv("MNEMOS_KNOWN_PROJECTS", raising=False)
    monkeypatch.delenv("MNEMOS_ACTIVE_PROJECTS", raising=False)
    idx = SessionIndexer(agent_id="t", db_path=str(tmp_path / "t.db"))
    assert idx.known_projects == ["claude-field", "mnemos"]
    # active is independent — config only set known, so active stays empty (not coerced)
    assert idx.active_projects == []


def test_active_projects_independent_from_config(monkeypatch, tmp_path):
    cfg = {"indexer": {"known_projects": ["a", "b"], "active_projects": ["b"]}}
    monkeypatch.setenv("HOME", str(_seed_home(tmp_path, cfg)))
    monkeypatch.delenv("MNEMOS_KNOWN_PROJECTS", raising=False)
    monkeypatch.delenv("MNEMOS_ACTIVE_PROJECTS", raising=False)
    idx = SessionIndexer(agent_id="t", db_path=str(tmp_path / "t.db"))
    assert idx.known_projects == ["a", "b"]
    assert idx.active_projects == ["b"]


def test_env_takes_precedence_over_config(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(_seed_home(tmp_path, {"indexer": {"known_projects": ["fromconfig"]}})))
    monkeypatch.setenv("MNEMOS_KNOWN_PROJECTS", "fromenv")
    idx = SessionIndexer(agent_id="t", db_path=str(tmp_path / "t.db"))
    assert idx.known_projects == ["fromenv"]


def test_malformed_config_does_not_crash_construction(monkeypatch, tmp_path):
    mn = tmp_path / ".mnemos"
    mn.mkdir(parents=True, exist_ok=True)
    (mn / "config.json").write_text("{ this is not valid json")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("MNEMOS_KNOWN_PROJECTS", raising=False)
    monkeypatch.delenv("MNEMOS_ACTIVE_PROJECTS", raising=False)
    # Must construct without raising; falls through to []
    idx = SessionIndexer(agent_id="t", db_path=str(tmp_path / "t.db"))
    assert idx.known_projects == []
    assert idx.active_projects == []


def test_explicit_arg_beats_everything(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(_seed_home(tmp_path, {"indexer": {"known_projects": ["fromconfig"]}})))
    monkeypatch.setenv("MNEMOS_KNOWN_PROJECTS", "fromenv")
    idx = SessionIndexer(agent_id="t", db_path=str(tmp_path / "t.db"), known_projects=["explicit"])
    assert idx.known_projects == ["explicit"]
