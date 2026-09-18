"""Canonical deterministic hashing shared by domain validation and parsers."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable


def normalize_display_text(value: str) -> str:
    """Normalize line endings and surrounding whitespace, and nothing else."""

    return value.replace("\r\n", "\n").replace("\r", "\n").strip()


def normalized_text_hash(value: str) -> str:
    """Hash canonical display text as UTF-8 SHA-256."""

    return hashlib.sha256(normalize_display_text(value).encode("utf-8")).hexdigest()


def ordered_identity_hash(parts: Iterable[str]) -> str:
    """Hash ordered structural identities with an unambiguous separator."""

    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()

