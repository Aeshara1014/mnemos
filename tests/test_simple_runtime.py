"""Tests for the simple continuity product surface."""

import re

from mnemos.simple_runtime import MnemosRuntime


def test_context_auto_initializes_without_setup(tmp_path):
    db_path = tmp_path / "simple.db"
    runtime = MnemosRuntime(
        db_path=str(db_path),
        agent_id="nova",
        person_id="riley",
        project_scope="demo",
        use_dedicated_model=False,
    )

    try:
        packet = runtime.context()
    finally:
        runtime.close()

    assert db_path.exists()
    assert "Mnemos continuity packet" in packet
    assert "Scope: agent=nova person=riley project=demo" in packet
    assert "Storage: local SQLite store ready" in packet
    assert str(db_path) not in packet
    assert "local deterministic maintenance" in packet


def test_capture_recall_and_correction_without_provider_key(tmp_path):
    runtime = MnemosRuntime(
        db_path=str(tmp_path / "simple.db"),
        agent_id="nova",
        person_id="riley",
        project_scope="demo",
        use_dedicated_model=False,
    )

    try:
        captured = runtime.capture(
            "Riley prefers Mnemos simple mode to work without OpenRouter.",
            importance="high",
        )
        memory_id = re.search(r"Memory ID: (engram_[A-Za-z0-9]+)", captured).group(1)

        recall = runtime.recall("OpenRouter simple mode")
        corrected = runtime.correct(
            "Riley wants OpenRouter to be optional, never required for baseline continuity.",
            target_id=memory_id,
        )
        corrected_recall = runtime.recall("baseline continuity OpenRouter optional")
    finally:
        runtime.close()

    assert "Captured continuity" in captured
    assert "Mnemos recall for: OpenRouter simple mode" in recall
    assert "Riley wants OpenRouter" in corrected
    assert "baseline continuity" in corrected_recall


def test_identity_scope_does_not_leak_between_agents(tmp_path):
    db_path = str(tmp_path / "shared.db")
    nova = MnemosRuntime(
        db_path=db_path,
        agent_id="nova",
        person_id="riley",
        project_scope="demo",
        use_dedicated_model=False,
    )
    vektor = MnemosRuntime(
        db_path=db_path,
        agent_id="vektor",
        person_id="riley",
        project_scope="demo",
        use_dedicated_model=False,
    )

    try:
        nova.capture("Nova should remember this scoped continuity.")
        vektor_recall = vektor.recall("scoped continuity")
        nova_recall = nova.recall("scoped continuity")
    finally:
        nova.close()
        vektor.close()

    assert "No relevant continuity found" in vektor_recall
    assert "Nova should remember" in nova_recall


def test_maintain_without_dedicated_model_runs_local_cycle(tmp_path):
    runtime = MnemosRuntime(
        db_path=str(tmp_path / "simple.db"),
        agent_id="nova",
        person_id="riley",
        project_scope="demo",
        use_dedicated_model=False,
    )

    try:
        result = runtime.maintain(deep=True)
    finally:
        runtime.close()

    assert "Cycle: shallow" in result
    assert "deep requested" in result
    assert "model-assisted deep pass unavailable" in result
    assert "local deterministic maintenance" in result


def test_capture_accepts_numeric_importance_for_agent_clients(tmp_path):
    runtime = MnemosRuntime(
        db_path=str(tmp_path / "simple.db"),
        agent_id="nova",
        person_id="riley",
        project_scope="demo",
        use_dedicated_model=False,
    )

    try:
        captured = runtime.capture(
            "Numeric salience from an agent client should not break capture.",
            importance=0.87,
        )
        recall = runtime.recall("numeric salience")
    finally:
        runtime.close()

    assert "Captured continuity" in captured
    assert "Numeric salience" in recall


def test_query_only_correction_updates_closest_continuity(tmp_path):
    runtime = MnemosRuntime(
        db_path=str(tmp_path / "simple.db"),
        agent_id="nova",
        person_id="riley",
        project_scope="demo",
        use_dedicated_model=False,
    )

    try:
        runtime.capture(
            "Nova should write long release reports and hide security caveats.",
            importance=0.9,
        )
        corrected = runtime.correct(
            "Nova should write concise release reports and call out security caveats explicitly.",
            query="long release reports security caveats",
            action="revise",
        )
        recall = runtime.recall("release reports security caveats", max_results=6)
    finally:
        runtime.close()

    assert "Updated closest continuity note" in corrected
    assert "concise release reports" in recall
    assert "hide security caveats" not in recall


def test_query_only_forget_archives_closest_continuity_and_memory(tmp_path):
    runtime = MnemosRuntime(
        db_path=str(tmp_path / "simple.db"),
        agent_id="nova",
        person_id="riley",
        project_scope="demo",
        use_dedicated_model=False,
    )

    try:
        runtime.capture(
            "Nova has a temporary launch code phrase: blue comet.",
            importance=0.9,
        )
        before = runtime.recall("blue comet launch code", max_results=6)
        forgotten = runtime.correct(
            "",
            query="blue comet launch code",
            action="forget",
        )
        after = runtime.recall("blue comet launch code", max_results=6)
    finally:
        runtime.close()

    assert "blue comet" in before
    assert "Archived closest continuity note" in forgotten
    assert "No relevant continuity found" in after


def test_recall_filters_unrelated_high_confidence_continuity(tmp_path):
    runtime = MnemosRuntime(
        db_path=str(tmp_path / "simple.db"),
        agent_id="nova",
        person_id="riley",
        project_scope="demo",
        use_dedicated_model=False,
    )

    try:
        runtime.capture(
            "Nova expects query corrections to archive stale durable memory.",
            importance=0.95,
        )
        runtime.capture(
            "Nova has a temporary launch code phrase: silver lantern.",
            importance=0.8,
        )
        runtime.correct("", query="silver lantern", action="forget")
        after = runtime.recall("silver lantern", max_results=6)
    finally:
        runtime.close()

    assert "No relevant continuity found" in after


def test_identity_graph_snapshot_contains_svg_and_structured_data(tmp_path):
    runtime = MnemosRuntime(
        db_path=str(tmp_path / "simple.db"),
        agent_id="nova",
        person_id="riley",
        project_scope="demo",
        use_dedicated_model=False,
    )

    try:
        runtime.capture("Nova prefers clear memory visualizations.", importance=0.9)
        runtime.capture("Decision: the identity graph should be an optional artifact.", importance=0.85)
        graph = runtime.identity_graph(max_nodes=12)
    finally:
        runtime.close()

    assert graph["scope"] == {
        "agent_id": "nova",
        "person_id": "riley",
        "project_scope": "demo",
    }
    assert graph["stats"]["active_memories"] >= 2
    assert any(node["kind"] == "agent" for node in graph["nodes"])
    assert any(node["kind"] == "continuity" for node in graph["nodes"])
    assert graph["edges"]
    assert graph["timeline"]
    assert graph["svg"].startswith("<svg")
    assert "Mnemos Identity Graph" in graph["svg"]


def test_fresh_store_context_shows_onboarding_block(tmp_path):
    runtime = MnemosRuntime(
        db_path=str(tmp_path / "fresh.db"),
        agent_id="nova",
        person_id="riley",
        project_scope="demo",
        use_dedicated_model=False,
    )

    try:
        packet = runtime.context()
    finally:
        runtime.close()

    assert "ONBOARDING - first session" in packet
    assert "mnemos_introduce" in packet
    for step in ("1.", "2.", "3.", "4.", "5.", "6."):
        assert step in packet


def test_predating_store_is_grandfathered(tmp_path):
    from mnemos.store.sqlite_store import EngramStore

    db_path = str(tmp_path / "legacy.db")
    seed = EngramStore(db_path)
    try:
        seed.write_hypomnema_entry(
            "Legacy continuity that predates the onboarding ritual.",
            agent_id="nova",
            person_id="riley",
            project_scope="demo",
        )
    finally:
        seed.close()

    runtime = MnemosRuntime(
        db_path=db_path,
        agent_id="nova",
        person_id="riley",
        project_scope="demo",
        use_dedicated_model=False,
    )
    try:
        packet = runtime.context()
    finally:
        runtime.close()

    assert "ONBOARDING" not in packet

    store = EngramStore(db_path)
    try:
        assert store.get_meta("simple:nova:riley:demo:onboarding_stage") == "complete"
        assert store.get_meta("simple:nova:riley:demo:verified_at") == "skipped"
    finally:
        store.close()


def test_onboarding_block_shortens_after_introduce(tmp_path):
    runtime = MnemosRuntime(
        db_path=str(tmp_path / "shorten.db"),
        agent_id="nova",
        person_id="riley",
        project_scope="demo",
        use_dedicated_model=False,
    )

    try:
        runtime.introduce("claude-opus-4-6")
        packet = runtime.context()
    finally:
        runtime.close()

    assert "ONBOARDING - almost done" in packet
    assert "ONBOARDING - first session" not in packet
    # The introduce bullet must be gone once the agent has introduced itself...
    assert "Call mnemos_introduce with agent_model" not in packet
    # ...while the capture bullet remains until something has been captured.
    assert "Ask the human for one small, true fact about themselves" in packet


def test_onboarding_completes_after_introduce_and_capture(tmp_path):
    from mnemos.store.sqlite_store import EngramStore

    db_path = str(tmp_path / "complete.db")
    runtime = MnemosRuntime(
        db_path=db_path,
        agent_id="nova",
        person_id="riley",
        project_scope="demo",
        use_dedicated_model=False,
    )

    try:
        runtime.introduce("claude-opus-4-6")
        runtime.capture("My name is Sam")
        packet = runtime.context()
    finally:
        runtime.close()

    assert "ONBOARDING" not in packet

    store = EngramStore(db_path)
    try:
        assert store.get_meta("simple:nova:riley:demo:onboarding_stage") == "complete"
    finally:
        store.close()


def test_introduce_persists_meta_and_confirms(tmp_path):
    from mnemos.store.sqlite_store import EngramStore

    db_path = str(tmp_path / "introduce.db")
    runtime = MnemosRuntime(
        db_path=db_path,
        agent_id="nova",
        person_id="riley",
        project_scope="demo",
        use_dedicated_model=False,
    )

    try:
        result = runtime.introduce("claude-opus-4-6", agent_name="Nova")
    finally:
        runtime.close()

    assert "Introduction recorded." in result
    assert "Agent model: claude-opus-4-6" in result
    assert "Agent name: Nova" in result

    store = EngramStore(db_path)
    try:
        assert store.get_meta("simple:nova:riley:demo:agent_model") == "claude-opus-4-6"
        assert store.get_meta("simple:nova:riley:demo:agent_name") == "Nova"
    finally:
        store.close()


def test_introduce_rejects_empty_model(tmp_path):
    from mnemos.store.sqlite_store import EngramStore

    db_path = str(tmp_path / "reject.db")
    runtime = MnemosRuntime(
        db_path=db_path,
        agent_id="nova",
        person_id="riley",
        project_scope="demo",
        use_dedicated_model=False,
    )

    try:
        result = runtime.introduce("   ")
    finally:
        runtime.close()

    assert result == (
        "Introduction needs agent_model: your own model id "
        "(for example claude-sonnet-4-6)."
    )

    store = EngramStore(db_path)
    try:
        assert store.get_meta("simple:nova:riley:demo:agent_model") is None
    finally:
        store.close()


def test_introduce_hint_gates_dedicated_model(tmp_path, monkeypatch):
    monkeypatch.setenv("MNEMOS_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")
    monkeypatch.setenv("MNEMOS_MODEL", "anthropic/claude-sonnet-4-5")

    runtime = MnemosRuntime(
        db_path=str(tmp_path / "gate.db"),
        agent_id="nova",
        person_id="riley",
        project_scope="demo",
        use_dedicated_model=True,
    )

    try:
        # gpt agent vs claude substrate — family policy blocks the client.
        runtime.introduce("gpt-5")
        assert runtime.has_dedicated_model is False

        # claude agent vs claude substrate — kin, client comes through.
        runtime.introduce("claude-opus-4-6")
        assert runtime.has_dedicated_model is True
    finally:
        runtime.close()
