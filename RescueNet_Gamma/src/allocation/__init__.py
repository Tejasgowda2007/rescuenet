"""
RescueNet Allocation & Conflict Management Package.

Enforces zero lost updates via conflict ledgers and guarantees
mathematically impossible double-allocation of scarce disaster resources.
"""

from .escrow import EscrowManager, InsufficientQuotaError
from .tokens import TokenManager, UnauthorizedAllocationError
from .conflict_resolver import ConflictResolver

__all__ = [
    "EscrowManager",
    "InsufficientQuotaError",
    "TokenManager",
    "UnauthorizedAllocationError",
    "ConflictResolver",
]
