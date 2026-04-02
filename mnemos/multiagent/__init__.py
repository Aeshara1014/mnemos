"""Multi-agent memory capabilities for Mnemos.

Enables multiple agents to share memories, maintain relationships,
federate across instances, and attest to memory provenance.

Modules:
- shared_pool: Shared memory pool with visibility controls
- relationships: Inter-agent relationship tracking
- federation: Cross-instance memory synchronization
- attestation: Cryptographic memory provenance attestation
"""

from .shared_pool import SharedPool
from .relationships import RelationshipTracker
from .federation import FederationClient
from .attestation import AttestationService
