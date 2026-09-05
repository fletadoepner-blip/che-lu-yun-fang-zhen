"""Public API for exposing the frozen UGAT model to external algorithms."""

from .config import UGATConfig
from .algorithm import UGATAlgorithm
from .contract import Algorithm, AlgorithmContext
from .registry import AlgorithmRegistry, registry

registry.register("ugat", UGATAlgorithm)

__all__ = [
    "Algorithm",
    "AlgorithmContext",
    "AlgorithmRegistry",
    "UGATAlgorithm",
    "UGATConfig",
    "registry",
]
