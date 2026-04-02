"""Retrieval pipeline: cue-driven memory access with reconsolidation.

Reactive retrieval combines FTS5, embedding similarity, and connection graph
traversal to find relevant memories. Every retrieval event triggers
reconsolidation, updating the accessed memory's strength and connections.
"""

from .reactive import ReactiveRetriever
from .reconsolidation import reconsolidate
