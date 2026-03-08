"""TDD tests for AC-04, AC-05: manifest_reader failure status handling.

AC-04: manifest_reader.BatchManifest tracks verify_failed_count and merge_conflict_count
AC-05: summary_parts() includes failure statuses in dashboard summary
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from buildcrew_dash import manifest_reader
from buildcrew_dash.manifest_reader import BatchManifest, BatchTask


def _write_manifest(tmp_path: Path, data: dict) -> None:
    """Helper to write manifest.json to temp directory."""
    p = tmp_path / ".buildcrew" / "batch"
    p.mkdir(parents=True, exist_ok=True)
    (p / "manifest.json").write_text(json.dumps(data))


def _basic_manifest_data(status: str = "pending") -> dict:
    """Helper to create minimal manifest data."""
    return {
        "batch_id": "20240101-120000",
        "base_branch": "main",
        "base_commit": "abc123",
        "max_parallel": 5,
        "started_at": "2024-01-01T12:00:00",
        "tasks": [
            {
                "index": 1,
                "text": "Task one",
                "slug": "task-one",
                "branch": "buildcrew/task-one",
                "worktree": ".buildcrew/batch/worktrees/task-one",
                "status": status,
                "exit_code": None,
                "started_at": None,
                "completed_at": None,
            }
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# AC-04: verify_failed_count and merge_conflict_count properties
# ─────────────────────────────────────────────────────────────────────────────

def test_AC04a_verify_failed_count_zero_when_no_verify_failed_tasks(tmp_path: Path):
    """AC-04a: verify_failed_count returns 0 when no tasks have verify_failed status."""
    data = _basic_manifest_data()
    _write_manifest(tmp_path, data)

    manifest = manifest_reader.read(tmp_path)
    assert manifest is not None
    assert manifest.verify_failed_count == 0


def test_AC04b_verify_failed_count_counts_verify_failed_tasks(tmp_path: Path):
    """AC-04b: verify_failed_count returns count of tasks with verify_failed status."""
    data = _basic_manifest_data()
    data["tasks"] = [
        {
            "index": 1,
            "text": "Failed verification",
            "slug": "task-one",
            "branch": "buildcrew/task-one",
            "worktree": ".buildcrew/batch/worktrees/task-one",
            "status": "verify_failed",
            "exit_code": 1,
            "started_at": "2024-01-01T12:00:00",
            "completed_at": "2024-01-01T12:05:00",
        },
        {
            "index": 2,
            "text": "Also failed verification",
            "slug": "task-two",
            "branch": "buildcrew/task-two",
            "worktree": ".buildcrew/batch/worktrees/task-two",
            "status": "verify_failed",
            "exit_code": 1,
            "started_at": "2024-01-01T12:00:00",
            "completed_at": "2024-01-01T12:05:00",
        },
        {
            "index": 3,
            "text": "Normal task",
            "slug": "task-three",
            "branch": "buildcrew/task-three",
            "worktree": ".buildcrew/batch/worktrees/task-three",
            "status": "completed",
            "exit_code": 0,
            "started_at": "2024-01-01T12:00:00",
            "completed_at": "2024-01-01T12:05:00",
        },
    ]
    _write_manifest(tmp_path, data)

    manifest = manifest_reader.read(tmp_path)
    assert manifest is not None
    assert manifest.verify_failed_count == 2


def test_AC04c_merge_conflict_count_zero_when_no_conflicts(tmp_path: Path):
    """AC-04c: merge_conflict_count returns 0 when no tasks have merge_conflict status."""
    data = _basic_manifest_data()
    _write_manifest(tmp_path, data)

    manifest = manifest_reader.read(tmp_path)
    assert manifest is not None
    assert manifest.merge_conflict_count == 0


def test_AC04d_merge_conflict_count_counts_conflict_tasks(tmp_path: Path):
    """AC-04d: merge_conflict_count returns count of tasks with merge_conflict status."""
    data = _basic_manifest_data()
    data["tasks"] = [
        {
            "index": 1,
            "text": "Merge conflict",
            "slug": "task-one",
            "branch": "buildcrew/task-one",
            "worktree": ".buildcrew/batch/worktrees/task-one",
            "status": "merge_conflict",
            "exit_code": None,
            "started_at": "2024-01-01T12:00:00",
            "completed_at": "2024-01-01T12:05:00",
        },
        {
            "index": 2,
            "text": "Another conflict",
            "slug": "task-two",
            "branch": "buildcrew/task-two",
            "worktree": ".buildcrew/batch/worktrees/task-two",
            "status": "merge_conflict",
            "exit_code": None,
            "started_at": "2024-01-01T12:00:00",
            "completed_at": "2024-01-01T12:05:00",
        },
    ]
    _write_manifest(tmp_path, data)

    manifest = manifest_reader.read(tmp_path)
    assert manifest is not None
    assert manifest.merge_conflict_count == 2


def test_AC04e_failure_counts_independent(tmp_path: Path):
    """AC-04e: verify_failed_count and merge_conflict_count are independent."""
    data = _basic_manifest_data()
    data["tasks"] = [
        {
            "index": 1,
            "text": "Verify failed",
            "slug": "task-one",
            "branch": "buildcrew/task-one",
            "worktree": ".buildcrew/batch/worktrees/task-one",
            "status": "verify_failed",
            "exit_code": 1,
            "started_at": "2024-01-01T12:00:00",
            "completed_at": "2024-01-01T12:05:00",
        },
        {
            "index": 2,
            "text": "Merge conflict",
            "slug": "task-two",
            "branch": "buildcrew/task-two",
            "worktree": ".buildcrew/batch/worktrees/task-two",
            "status": "merge_conflict",
            "exit_code": None,
            "started_at": "2024-01-01T12:00:00",
            "completed_at": "2024-01-01T12:05:00",
        },
    ]
    _write_manifest(tmp_path, data)

    manifest = manifest_reader.read(tmp_path)
    assert manifest is not None
    assert manifest.verify_failed_count == 1
    assert manifest.merge_conflict_count == 1


# ─────────────────────────────────────────────────────────────────────────────
# AC-05: summary_parts includes failure statuses
# ─────────────────────────────────────────────────────────────────────────────

def test_AC05a_summary_parts_includes_verify_failed(tmp_path: Path):
    """AC-05a: summary_parts() includes verify_failed status when tasks fail verification."""
    data = _basic_manifest_data()
    data["tasks"] = [
        {
            "index": 1,
            "text": "Verify failed",
            "slug": "task-one",
            "branch": "buildcrew/task-one",
            "worktree": ".buildcrew/batch/worktrees/task-one",
            "status": "verify_failed",
            "exit_code": 1,
            "started_at": "2024-01-01T12:00:00",
            "completed_at": "2024-01-01T12:05:00",
        },
    ]
    _write_manifest(tmp_path, data)

    manifest = manifest_reader.read(tmp_path)
    assert manifest is not None

    parts = manifest.summary_parts(rich=False)
    assert any("verify failed" in part for part in parts)
    assert "1 verify failed" in " ".join(parts)


def test_AC05b_summary_parts_includes_merge_conflict(tmp_path: Path):
    """AC-05b: summary_parts() includes merge_conflict status when tasks have conflicts."""
    data = _basic_manifest_data()
    data["tasks"] = [
        {
            "index": 1,
            "text": "Merge conflict",
            "slug": "task-one",
            "branch": "buildcrew/task-one",
            "worktree": ".buildcrew/batch/worktrees/task-one",
            "status": "merge_conflict",
            "exit_code": None,
            "started_at": "2024-01-01T12:00:00",
            "completed_at": "2024-01-01T12:05:00",
        },
    ]
    _write_manifest(tmp_path, data)

    manifest = manifest_reader.read(tmp_path)
    assert manifest is not None

    parts = manifest.summary_parts(rich=False)
    assert any("conflict" in part for part in parts)
    assert "1 conflict" in " ".join(parts)


def test_AC05c_summary_parts_rich_colors_verify_failed(tmp_path: Path):
    """AC-05c: summary_parts(rich=True) colors verify_failed red."""
    data = _basic_manifest_data()
    data["tasks"] = [
        {
            "index": 1,
            "text": "Verify failed",
            "slug": "task-one",
            "branch": "buildcrew/task-one",
            "worktree": ".buildcrew/batch/worktrees/task-one",
            "status": "verify_failed",
            "exit_code": 1,
            "started_at": "2024-01-01T12:00:00",
            "completed_at": "2024-01-01T12:05:00",
        },
    ]
    _write_manifest(tmp_path, data)

    manifest = manifest_reader.read(tmp_path)
    assert manifest is not None

    parts = manifest.summary_parts(rich=True)
    verify_failed_parts = [p for p in parts if "verify failed" in p]
    assert len(verify_failed_parts) > 0
    # Rich format should include color codes
    assert "[red]" in verify_failed_parts[0]
    assert "[/red]" in verify_failed_parts[0]


def test_AC05d_summary_parts_rich_colors_merge_conflict(tmp_path: Path):
    """AC-05d: summary_parts(rich=True) colors merge_conflict yellow."""
    data = _basic_manifest_data()
    data["tasks"] = [
        {
            "index": 1,
            "text": "Merge conflict",
            "slug": "task-one",
            "branch": "buildcrew/task-one",
            "worktree": ".buildcrew/batch/worktrees/task-one",
            "status": "merge_conflict",
            "exit_code": None,
            "started_at": "2024-01-01T12:00:00",
            "completed_at": "2024-01-01T12:05:00",
        },
    ]
    _write_manifest(tmp_path, data)

    manifest = manifest_reader.read(tmp_path)
    assert manifest is not None

    parts = manifest.summary_parts(rich=True)
    conflict_parts = [p for p in parts if "conflict" in p]
    assert len(conflict_parts) > 0
    # Rich format should include color codes
    assert "[yellow]" in conflict_parts[0]
    assert "[/yellow]" in conflict_parts[0]


def test_AC05e_summary_parts_with_mixed_statuses(tmp_path: Path):
    """AC-05e: summary_parts() shows all failure types together."""
    data = _basic_manifest_data()
    data["tasks"] = [
        {
            "index": 1,
            "text": "Task 1",
            "slug": "task-one",
            "branch": "buildcrew/task-one",
            "worktree": ".buildcrew/batch/worktrees/task-one",
            "status": "completed",
            "exit_code": 0,
            "started_at": "2024-01-01T12:00:00",
            "completed_at": "2024-01-01T12:05:00",
        },
        {
            "index": 2,
            "text": "Task 2",
            "slug": "task-two",
            "branch": "buildcrew/task-two",
            "worktree": ".buildcrew/batch/worktrees/task-two",
            "status": "failed",
            "exit_code": 1,
            "started_at": "2024-01-01T12:00:00",
            "completed_at": "2024-01-01T12:05:00",
        },
        {
            "index": 3,
            "text": "Task 3",
            "slug": "task-three",
            "branch": "buildcrew/task-three",
            "worktree": ".buildcrew/batch/worktrees/task-three",
            "status": "verify_failed",
            "exit_code": 1,
            "started_at": "2024-01-01T12:00:00",
            "completed_at": "2024-01-01T12:05:00",
        },
        {
            "index": 4,
            "text": "Task 4",
            "slug": "task-four",
            "branch": "buildcrew/task-four",
            "worktree": ".buildcrew/batch/worktrees/task-four",
            "status": "merge_conflict",
            "exit_code": None,
            "started_at": "2024-01-01T12:00:00",
            "completed_at": "2024-01-01T12:05:00",
        },
    ]
    _write_manifest(tmp_path, data)

    manifest = manifest_reader.read(tmp_path)
    assert manifest is not None

    parts = manifest.summary_parts(rich=False)
    summary = " ".join(parts)

    # All status types should be present
    assert "1 done" in summary
    assert "1 failed" in summary
    assert "1 verify failed" in summary
    assert "1 conflict" in summary
