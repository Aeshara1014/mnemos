"""
Configuration loader for Mnemos.

Loads configuration from three sources with increasing priority:
1. Default values (from defaults.py)
2. JSON config file (if it exists)
3. Environment variables (MNEMOS_ prefix)

Environment variable mapping:
    MNEMOS_STORE_DB_PATH -> config["store"]["db_path"]
    MNEMOS_CONSOLIDATION_DECAY_RATE -> config["consolidation"]["decay_rate"]
    etc.

The loader performs deep merging: JSON config values override defaults,
and environment variables override JSON config values.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

from .defaults import DEFAULT_CONFIG


def load_config(
    config_path: str | Path | None = None,
    env_prefix: str = "MNEMOS_",
) -> dict[str, Any]:
    """Load Mnemos configuration from defaults, JSON file, and env vars.

    Priority (highest wins):
    1. Environment variables (MNEMOS_ prefix)
    2. JSON config file
    3. Default values

    Args:
        config_path: Path to a JSON configuration file. If None, looks for
            ~/.mnemos/config.json. If that doesn't exist, uses defaults only.
        env_prefix: Prefix for environment variable overrides.

    Returns:
        Merged configuration dictionary.

    Raises:
        json.JSONDecodeError: If the config file contains invalid JSON.
    """
    raise NotImplementedError("Step 15: Config loader implementation")


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge override into base, returning a new dict.

    Args:
        base: The base dictionary (not modified).
        override: Values to overlay on top of base.

    Returns:
        New dictionary with merged values.
    """
    result = deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _apply_env_overrides(config: dict, prefix: str) -> dict:
    """Apply environment variable overrides to config.

    Maps MNEMOS_SECTION_KEY=value to config["section"]["key"] = value.
    Attempts type coercion: bool, int, float, then string.

    Args:
        config: The configuration dict to apply overrides to (modified in place).
        prefix: The environment variable prefix to scan for.

    Returns:
        The modified config dict.
    """
    raise NotImplementedError("Step 15: Env override implementation")
