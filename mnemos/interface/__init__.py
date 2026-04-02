"""Interface layer: session lifecycle, prompt building, observability, and export.

The interface module provides the API surface that agent platforms (OpenClaw,
custom frameworks) use to integrate Mnemos into their conversation loops.

Key components:
- MnemosSession: manages encoding during active conversations
- PromptBuilder: constructs memory-enhanced prompt sections within token budgets
- MemoryInspector: observability and debugging tools
- export/import: portable memory format for backup and migration
"""

from .session import MnemosSession
from .prompt_builder import PromptBuilder
from .memory_inspector import MemoryInspector
from .export import export_memory, import_memory
