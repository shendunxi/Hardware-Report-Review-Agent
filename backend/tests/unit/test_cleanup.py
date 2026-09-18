"""Behavioral tests for task-workspace cleanup guardrails."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from hw_review.services.cleanup import CleanupSafetyError, WorkspaceCleaner


TASK_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_TASK_ID = UUID("22222222-2222-4222-8222-222222222222")
NOW = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)


def _cleaner(tmp_path: Path) -> tuple[WorkspaceCleaner, Path]:
    root = tmp_path / "work"
    root.mkdir()
    return WorkspaceCleaner(root), root.resolve()


@pytest.mark.parametrize("unsafe_kind", ["root", "sibling", "ancestor", "nested", "non_uuid"])
def test_remove_verified_refuses_unsafe_target_categories(
    tmp_path: Path,
    unsafe_kind: str,
) -> None:
    # Catches widening recursive deletion beyond one canonical UUID child of work_root.
    cleaner, root = _cleaner(tmp_path)
    sibling = tmp_path / str(TASK_ID)
    ancestor = root.parent
    task = root / str(TASK_ID)
    nested = task / "input"
    non_uuid = root / "cache"
    sibling.mkdir()
    task.mkdir()
    nested.mkdir()
    non_uuid.mkdir()
    unsafe = {
        "root": root,
        "sibling": sibling,
        "ancestor": ancestor,
        "nested": nested,
        "non_uuid": non_uuid,
    }[unsafe_kind]

    with pytest.raises(CleanupSafetyError):
        cleaner.remove_verified(unsafe)

    assert root.exists()
    assert unsafe.exists()


def test_remove_verified_refuses_symlink_task_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Catches a task-looking symlink redirecting recursive deletion outside work_root.
    cleaner, root = _cleaner(tmp_path)
    external = tmp_path / "external"
    external.mkdir()
    link = root / str(TASK_ID)
    try:
        link.symlink_to(external, target_is_directory=True)
    except OSError:
        original_is_symlink = Path.is_symlink
        monkeypatch.setattr(
            Path,
            "is_symlink",
            lambda path: path == link or original_is_symlink(path),
        )

    with pytest.raises(CleanupSafetyError):
        cleaner.remove_verified(link)

    assert external.exists()


def test_clean_task_removes_only_requested_uuid_directory(tmp_path: Path) -> None:
    # Catches clean_task deleting the root, a neighboring task, or refusing a valid target.
    cleaner, root = _cleaner(tmp_path)
    requested = root / str(TASK_ID)
    neighbor = root / str(OTHER_TASK_ID)
    (requested / "input").mkdir(parents=True)
    (requested / "input" / "payload.pdf").write_bytes(b"data")
    neighbor.mkdir()

    removed = cleaner.clean_task(TASK_ID)

    assert removed is True
    assert not requested.exists()
    assert neighbor.exists()
    assert root.exists()


def test_clean_task_returns_false_when_safe_target_does_not_exist(tmp_path: Path) -> None:
    # Catches absence being mistaken for an unsafe path or reported as a deletion.
    cleaner, root = _cleaner(tmp_path)

    assert cleaner.clean_task(TASK_ID) is False
    assert root.exists()


def test_expired_cleanup_removes_only_eligible_task_directories_deterministically(
    tmp_path: Path,
) -> None:
    # Catches early deletion, deletion of unrelated entries, and nondeterministic reporting.
    cleaner, root = _cleaner(tmp_path)
    expired_ids = [OTHER_TASK_ID, TASK_ID]
    active_id = UUID("33333333-3333-4333-8333-333333333333")
    for task_id in (*expired_ids, active_id):
        (root / str(task_id)).mkdir()
    unrelated_dir = root / "cache"
    unrelated_dir.mkdir()
    unrelated_file = root / "notes.txt"
    unrelated_file.write_text("keep", encoding="utf-8")

    expired_time = (NOW - timedelta(hours=24)).timestamp()
    active_time = (NOW - timedelta(hours=23, minutes=59)).timestamp()
    for task_id in expired_ids:
        os.utime(root / str(task_id), (expired_time, expired_time))
    os.utime(root / str(active_id), (active_time, active_time))
    os.utime(unrelated_dir, (expired_time, expired_time))

    removed = cleaner.clean_expired(NOW)

    assert removed == sorted(expired_ids, key=str)
    assert all(not (root / str(task_id)).exists() for task_id in expired_ids)
    assert (root / str(active_id)).exists()
    assert unrelated_dir.exists()
    assert unrelated_file.exists()


def test_expired_cleanup_uses_configured_expiry_threshold(tmp_path: Path) -> None:
    # Catches hard-coding 24 hours when a caller configures a different safe expiry.
    root = tmp_path / "work"
    root.mkdir()
    cleaner = WorkspaceCleaner(root, expiry=timedelta(hours=2))
    task_dir = root / str(TASK_ID)
    task_dir.mkdir()
    old_time = (NOW - timedelta(hours=2)).timestamp()
    os.utime(task_dir, (old_time, old_time))

    assert cleaner.clean_expired(NOW) == [TASK_ID]
    assert not task_dir.exists()
