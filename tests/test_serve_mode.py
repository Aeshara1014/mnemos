"""Tests for `mnemos serve` tool-surface mode resolution (simple vs advanced).

Covers the persistence fix: advanced mode can be set durably via
``server.mode`` in ~/.mnemos/config.json instead of only a volatile env var.
"""
import json

from mnemos import cli
from mnemos.config.defaults import DEFAULT_CONFIG
from mnemos.config.loader import load_config


def test_default_config_exposes_server_mode_simple():
    assert DEFAULT_CONFIG["server"]["mode"] == "simple"


def test_config_file_overrides_server_mode(tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"server": {"mode": "advanced"}}))
    loaded = load_config(config_path=cfg)
    assert loaded["server"]["mode"] == "advanced"


def test_resolve_default_mode_env_takes_precedence(monkeypatch):
    monkeypatch.setenv("MNEMOS_MODE", "advanced")
    assert cli._resolve_default_mode() == "advanced"


def test_resolve_default_mode_reads_config(monkeypatch):
    # No explicit MNEMOS_MODE; server.mode is supplied through the loader's
    # MNEMOS_SERVER_MODE -> config["server"]["mode"] env mapping (no file needed).
    monkeypatch.delenv("MNEMOS_MODE", raising=False)
    monkeypatch.setenv("MNEMOS_SERVER_MODE", "advanced")
    assert cli._resolve_default_mode() == "advanced"


def test_resolve_default_mode_defaults_to_simple(monkeypatch):
    monkeypatch.delenv("MNEMOS_MODE", raising=False)
    monkeypatch.delenv("MNEMOS_SERVER_MODE", raising=False)
    # Pin the config layer to built-in defaults, independent of any real
    # ~/.mnemos/config.json on the test machine.
    monkeypatch.setattr(cli, "load_config", lambda *a, **k: {"server": {"mode": "simple"}})
    assert cli._resolve_default_mode() == "simple"
