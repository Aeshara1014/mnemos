"""ClaudeCLIClient permissions flag: opt-in, default off.

Background maintenance is pure text work; it must not carry a tool-capable
permissions bypass unless the operator explicitly opts in.
"""
from mnemos.llm import ClaudeCLIClient, _create_client_unchecked


class TestClaudeCLIPermissionsFlag:
    def test_default_command_has_no_skip_permissions(self):
        client = ClaudeCLIClient(model="claude-haiku-4-5-20251001")
        cmd = client._build_cmd("soften this memory")
        assert "--dangerously-skip-permissions" not in cmd
        assert cmd[-2:] == ["-p", "soften this memory"]

    def test_opt_in_adds_the_flag(self):
        client = ClaudeCLIClient(skip_permissions=True)
        assert "--dangerously-skip-permissions" in client._build_cmd("x")

    def test_create_client_defaults_off(self, monkeypatch):
        monkeypatch.setenv("MNEMOS_LLM_PROVIDER", "claude-cli")
        client = _create_client_unchecked()
        assert isinstance(client, ClaudeCLIClient)
        assert client._skip_permissions is False

    def test_create_client_env_opt_in(self, monkeypatch):
        monkeypatch.setenv("MNEMOS_LLM_PROVIDER", "claude-cli")
        monkeypatch.setenv("MNEMOS_CLAUDE_CLI_SKIP_PERMISSIONS", "1")
        client = _create_client_unchecked()
        assert client._skip_permissions is True
