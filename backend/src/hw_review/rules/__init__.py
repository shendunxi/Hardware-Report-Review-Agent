"""Frozen A11 checklist definitions and deterministic local evaluation."""

from .a11_engine import A11Engine, NormalizedDocumentQuery, rollup
from .a11_registry import A11Registry

__all__ = ["A11Engine", "A11Registry", "NormalizedDocumentQuery", "rollup"]
