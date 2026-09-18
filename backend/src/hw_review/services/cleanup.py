"""Guarded recursive cleanup for task-local workspaces only."""

from __future__ import annotations

import shutil
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID


class CleanupSafetyError(Exception):
    """Raised when a recursive-delete target cannot be proven task-local."""


class WorkspaceCleaner:
    """Remove only verified UUID direct children of a configured narrow root."""

    def __init__(self, work_root: Path, expiry: timedelta = timedelta(hours=24)) -> None:
        if expiry < timedelta(0):
            raise ValueError("expiry cannot be negative")
        root = Path(work_root)
        root.mkdir(parents=True, exist_ok=True)
        self._work_root = root.resolve()
        self._expiry = expiry

    def remove_verified(self, target: Path) -> bool:
        candidate = Path(target)
        if candidate.is_symlink():
            raise CleanupSafetyError("task cleanup target cannot be a symlink")
        if candidate.parent != self._work_root:
            raise CleanupSafetyError("task cleanup target must be a direct child of work root")

        resolved = candidate.resolve(strict=False)
        if resolved == self._work_root or resolved.parent != self._work_root:
            raise CleanupSafetyError("resolved cleanup target is outside work root")
        try:
            parsed_id = UUID(resolved.name)
        except ValueError as error:
            raise CleanupSafetyError("task cleanup target must have a UUID name") from error
        if str(parsed_id) != resolved.name:
            raise CleanupSafetyError("task cleanup target must use a canonical UUID name")

        if not candidate.exists():
            return False
        if not candidate.is_dir():
            raise CleanupSafetyError("task cleanup target must be a directory")

        shutil.rmtree(candidate)
        return True

    def clean_task(self, task_id: UUID) -> bool:
        return self.remove_verified(self._work_root / str(task_id))

    def clean_expired(self, now: datetime) -> list[UUID]:
        cutoff = now.timestamp() - self._expiry.total_seconds()
        eligible: list[tuple[UUID, Path]] = []
        for candidate in sorted(self._work_root.iterdir(), key=lambda path: path.name):
            if candidate.is_symlink() or not candidate.is_dir():
                continue
            try:
                task_id = UUID(candidate.name)
            except ValueError:
                continue
            if str(task_id) != candidate.name:
                continue
            if candidate.stat().st_mtime <= cutoff:
                eligible.append((task_id, candidate))

        removed: list[UUID] = []
        for task_id, candidate in eligible:
            if self.remove_verified(candidate):
                removed.append(task_id)
        return removed
