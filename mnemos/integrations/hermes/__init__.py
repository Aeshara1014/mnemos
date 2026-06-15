"""Hermes memory-provider integration for Mnemos."""

from .installer import (
    HermesInstallResult,
    build_diagnostics,
    install_hermes_plugin,
    provider_plugin_dirs,
    render_plugin_shim,
)
from .provider import MnemosMemoryProviderCore, build_memory_provider_class
from .scope import HermesMnemosConfig, HermesScope, derive_hermes_scope

__all__ = [
    "HermesInstallResult",
    "HermesMnemosConfig",
    "HermesScope",
    "MnemosMemoryProviderCore",
    "build_diagnostics",
    "build_memory_provider_class",
    "derive_hermes_scope",
    "install_hermes_plugin",
    "provider_plugin_dirs",
    "render_plugin_shim",
]
