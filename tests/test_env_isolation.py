"""Ambient configuration hygiene for llm._load_env_key.

Library code must not silently read a developer's personal workspace
files. MNEMOS_ENV_PATHS makes the .env search path explicit configuration;
MNEMOS_DISABLE_DOTENV (set by conftest for every test) turns ambient
file reads off entirely.
"""

from mnemos.llm import _load_env_key


def test_disable_dotenv_blocks_file_reads(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("SOME_TEST_KEY=from-file\n")
    monkeypatch.setenv("MNEMOS_ENV_PATHS", str(env_file))
    monkeypatch.setenv("MNEMOS_DISABLE_DOTENV", "1")
    assert _load_env_key("SOME_TEST_KEY") == ""


def test_env_paths_override_is_respected(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text('SOME_TEST_KEY="from-file"\n')
    monkeypatch.setenv("MNEMOS_ENV_PATHS", str(env_file))
    monkeypatch.delenv("MNEMOS_DISABLE_DOTENV", raising=False)
    assert _load_env_key("SOME_TEST_KEY") == "from-file"


def test_process_env_wins_over_files(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("SOME_TEST_KEY=from-file\n")
    monkeypatch.setenv("MNEMOS_ENV_PATHS", str(env_file))
    monkeypatch.delenv("MNEMOS_DISABLE_DOTENV", raising=False)
    monkeypatch.setenv("SOME_TEST_KEY", "from-env")
    assert _load_env_key("SOME_TEST_KEY") == "from-env"


def test_multiple_env_paths_first_hit_wins(tmp_path, monkeypatch):
    first = tmp_path / "a.env"
    second = tmp_path / "b.env"
    first.write_text("SOME_TEST_KEY=first\n")
    second.write_text("SOME_TEST_KEY=second\n")
    monkeypatch.setenv("MNEMOS_ENV_PATHS", f"{first}:{second}")
    monkeypatch.delenv("MNEMOS_DISABLE_DOTENV", raising=False)
    assert _load_env_key("SOME_TEST_KEY") == "first"
