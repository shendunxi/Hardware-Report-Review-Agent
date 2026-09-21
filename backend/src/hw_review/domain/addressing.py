"""A1 cell addressing, shared by the parsers and the domain models.

Parsers build an address from a zero-based coordinate and the ``TableCell`` model
re-derives it to prove the two agree. That check is only meaningful while both
sides share one implementation, so it lives here rather than in either module.
"""

from __future__ import annotations

_COLUMN_BASE = 26
_FIRST_LETTER = 65  # "A"


def a1_address(row: int, column: int) -> str:
    """Convert zero-based coordinates to an A1 cell address."""

    if row < 0 or column < 0:
        raise ValueError("row and column must be non-negative")
    letters = ""
    value = column + 1
    while value:
        value, remainder = divmod(value - 1, _COLUMN_BASE)
        letters = chr(_FIRST_LETTER + remainder) + letters
    return f"{letters}{row + 1}"
