"""A night's link pass counts the calls it made beside the ones that
failed, so the house can say "50 of 50 link calls failed" (Croft re-check
#35, Tara's word 2026-10-10)."""

from mnemos.consolidation.connection_discovery import run_connection_discovery
from mnemos.encoding.encoder import Encoder


class DownClient:
    def structured_complete(self, system, user, temperature=0.0,
                            max_tokens=2000, timeout=None):
        raise RuntimeError("HTTP 402")


def test_discovery_counts_every_call_and_every_failure(store):
    encoder = Encoder(store, llm_client=None)
    for words in ("the obsidian shards on the croft windowsill",
                  "she asked about the obsidian shards again",
                  "obsidian shards and the drystone wall"):
        encoder.encode(content=words)
    stats = run_connection_discovery(store, llm_client=DownClient(), agent_id="default")
    assert stats["discovery_calls"] >= 1
    assert stats["discovery_call_failures"] == stats["discovery_calls"]
    assert stats["reclassify_call_failures"] == stats["reclassify_calls"]
