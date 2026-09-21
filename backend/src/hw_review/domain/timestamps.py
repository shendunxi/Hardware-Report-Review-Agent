"""The single implementation of the UTC-normalization rule.

Every persisted timestamp must carry a UTC offset. The domain refuses a naive
datetime rather than guessing a zone, and the persistence layer stores ISO text,
so both layers need exactly the same rule. Duplicating it invited the two copies
to drift; keeping it here means a stored value and a validated model can never
disagree about what "the same instant" means.
"""

from __future__ import annotations

from datetime import datetime, timezone

_NO_OFFSET = "timestamp must include a UTC offset"
_NO_STORED_OFFSET = "stored timestamp has no UTC offset"


def as_utc(value: datetime) -> datetime:
    """Normalize an aware datetime to UTC; reject a naive one."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(_NO_OFFSET)
    return value.astimezone(timezone.utc)


def as_utc_optional(value: datetime | None) -> datetime | None:
    """``as_utc`` for an optional field, where ``None`` means "not set yet"."""

    return None if value is None else as_utc(value)


def as_stored_text(value: datetime) -> str:
    """Render a timestamp for storage. ISO text, always offset-qualified."""

    return as_utc(value).isoformat()


def from_stored_text(value: str) -> datetime:
    """Parse a stored timestamp. A value without an offset is corrupt."""

    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(_NO_STORED_OFFSET)
    return parsed.astimezone(timezone.utc)
