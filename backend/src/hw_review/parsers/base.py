"""Format-neutral parser helpers and stable parser errors."""

from __future__ import annotations

from hw_review.domain.hashing import normalize_display_text, normalized_text_hash


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


def a1_address(row: int, column: int) -> str:
    """Convert zero-based coordinates to an A1 cell address."""

    if row < 0 or column < 0:
        raise ValueError("row and column must be non-negative")
    letters = ""
    value = column + 1
    while value:
        value, remainder = divmod(value - 1, 26)
        letters = chr(65 + remainder) + letters
    return f"{letters}{row + 1}"
