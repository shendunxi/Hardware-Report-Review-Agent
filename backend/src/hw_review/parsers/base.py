"""Format-neutral parser helpers and stable parser errors."""

from __future__ import annotations

from hw_review.domain.addressing import a1_address
from hw_review.domain.hashing import normalize_display_text, normalized_text_hash

__all__ = [
    "DocumentLookupError",
    "ParserError",
    "a1_address",
    "normalize_display_text",
    "normalized_text_hash",
]


class ParserError(Exception):
    """Stable parsing failure suitable for orchestration diagnostics."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class DocumentLookupError(LookupError):
    """Stable failure for normalized document lookups."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)



