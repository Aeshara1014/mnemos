"""
Mnemos Substrate — the cognitive consolidation daemon.

Runs periodic consolidation cycles: decay, connection discovery,
belief review, event cascade through handlers.

Usage:
    from mnemos.substrate import Substrate, SubstrateConfig

    config = SubstrateConfig(agent_id="my_agent", agent_name="MyAgent")
    substrate = Substrate(config)
    summary = substrate.tick()
"""

from .config import SubstrateConfig
from .tick import Substrate

__all__ = ["Substrate", "SubstrateConfig"]
