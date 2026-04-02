"""Configuration management for Mnemos.

Provides default configuration values and a loader that merges
JSON config files with environment variable overrides.
"""

from .defaults import DEFAULT_CONFIG
from .loader import load_config
