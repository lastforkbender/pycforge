"""Bounded Phase 11 container facts and analysis."""

from .analysis import BoundedContainerAnalyzer
from .model import (
    MAX_CONTAINER_ELEMENTS,
    ContainerAccessFact,
    ContainerBindingFact,
    ContainerIterationFact,
    ContainerShapeFact,
)

__all__ = [
    "MAX_CONTAINER_ELEMENTS",
    "BoundedContainerAnalyzer",
    "ContainerAccessFact",
    "ContainerBindingFact",
    "ContainerIterationFact",
    "ContainerShapeFact",
]
