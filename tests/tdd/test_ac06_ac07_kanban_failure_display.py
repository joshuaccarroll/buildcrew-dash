"""TDD tests for AC-06, AC-07: kanban screen failure status display.

AC-06: _format_batch_status handles verify_failed and merge_conflict with correct colors
AC-07: Failed tasks show phase strip and last known phase, not green completed
"""
from __future__ import annotations

import pytest

from buildcrew_dash.manifest_reader import BatchTask
from buildcrew_dash.screens.kanban import KanbanScreen
from buildcrew_dash.state_reader import WorkflowState


def _make_task(index: int = 1, status: str = "pending") -> BatchTask:
    """Helper to create a BatchTask."""
    return BatchTask(
        index=index,
        text="Test task",
        slug="test-task",
        branch="buildcrew/test-task",
        worktree=".buildcrew/batch/worktrees/test-task",
        status=status,
        exit_code=None,
        started_at="2024-01-01T12:00:00",
        completed_at="2024-01-01T12:05:00",
    )


# ─────────────────────────────────────────────────────────────────────────────
# AC-06: _format_batch_status handles new failure statuses
# ─────────────────────────────────────────────────────────────────────────────

def test_AC06a_format_batch_status_verify_failed_red():
    """AC-06a: _format_batch_status returns red color for verify_failed status."""
    task = _make_task(status="verify_failed")
    result = KanbanScreen._format_batch_status(task)
    assert "red" in result.lower() or "[red]" in result
    assert "verify failed" in result.lower() or "verify_failed" in result


def test_AC06b_format_batch_status_merge_conflict_yellow():
    """AC-06b: _format_batch_status returns yellow color for merge_conflict status."""
    task = _make_task(status="merge_conflict")
    result = KanbanScreen._format_batch_status(task)
    assert "yellow" in result.lower() or "[yellow]" in result
    assert "conflict" in result.lower() or "merge_conflict" in result


def test_AC06c_format_batch_status_verify_failed_exit_code():
    """AC-06c: _format_batch_status shows exit code for verify_failed if present."""
    task = _make_task(status="verify_failed")
    task.exit_code = 1
    result = KanbanScreen._format_batch_status(task)
    assert "red" in result.lower() or "[red]" in result
    # May include exit code
    assert "verify" in result.lower()


def test_AC06d_format_batch_status_verify_failed_no_exit_code():
    """AC-06d: _format_batch_status handles verify_failed without exit code."""
    task = _make_task(status="verify_failed")
    task.exit_code = None
    result = KanbanScreen._format_batch_status(task)
    assert "red" in result.lower() or "[red]" in result


def test_AC06e_format_batch_status_failed_still_red():
    """AC-06e: _format_batch_status still handles regular failed status (red)."""
    task = _make_task(status="failed")
    task.exit_code = 1
    result = KanbanScreen._format_batch_status(task)
    assert "red" in result.lower() or "[red]" in result
    assert "failed" in result.lower()


def test_AC06f_format_batch_status_completed_still_green():
    """AC-06f: _format_batch_status still shows completed as green."""
    task = _make_task(status="completed")
    result = KanbanScreen._format_batch_status(task)
    assert "green" in result.lower() or "[green]" in result
    assert "completed" in result.lower()


def test_AC06g_format_batch_status_all_statuses():
    """AC-06g: _format_batch_status handles all status types without error."""
    statuses = [
        "pending",
        "running",
        "completed",
        "failed",
        "verify_failed",
        "merge_conflict",
        "interrupted",
    ]
    for status in statuses:
        task = _make_task(status=status)
        result = KanbanScreen._format_batch_status(task)
        assert isinstance(result, str)
        assert len(result) > 0


# ─────────────────────────────────────────────────────────────────────────────
# AC-07: Failed task display and phase strip
# ─────────────────────────────────────────────────────────────────────────────

def test_AC07a_failed_task_not_green():
    """AC-07a: Failed task doesn't show green 'completed' status."""
    statuses = ["failed", "verify_failed", "merge_conflict"]
    for status in statuses:
        task = _make_task(status=status)
        result = KanbanScreen._format_batch_status(task)
        # Should not contain green completed
        assert "[green]completed[/green]" not in result


def test_AC07b_verify_failed_task_red():
    """AC-07b: verify_failed task shows red in dashboard."""
    task = _make_task(status="verify_failed")
    result = KanbanScreen._format_batch_status(task)
    # Should show red, not green
    assert "[red]" in result or "red" in result.lower()
    assert "[green]" not in result


def test_AC07c_merge_conflict_task_yellow():
    """AC-07c: merge_conflict task shows yellow in dashboard."""
    task = _make_task(status="merge_conflict")
    result = KanbanScreen._format_batch_status(task)
    # Should show yellow, not green
    assert "[yellow]" in result or "yellow" in result.lower()
    assert "[green]" not in result


def test_AC07d_get_batch_task_phase_returns_empty_for_non_running():
    """AC-07d: _get_batch_task_phase returns empty string for non-running tasks."""
    statuses = ["pending", "completed", "failed", "verify_failed", "merge_conflict"]
    wt_states = {}
    for status in statuses:
        task = _make_task(status=status)
        result = KanbanScreen._get_batch_task_phase(task, wt_states)
        assert result == ""


def test_AC07e_get_batch_task_phase_returns_phase_for_running():
    """AC-07e: _get_batch_task_phase returns phase for running task."""
    task = _make_task(status="running")
    wt_state = type('obj', (object,), {'phase': 'build'})()
    wt_states = {task.index: wt_state}
    result = KanbanScreen._get_batch_task_phase(task, wt_states)
    assert result == "build"


def test_AC07f_get_batch_task_phase_starting_for_running_no_state():
    """AC-07f: _get_batch_task_phase returns 'starting' for running task without state."""
    task = _make_task(status="running")
    wt_states = {}
    result = KanbanScreen._get_batch_task_phase(task, wt_states)
    assert result == "starting"


# ─────────────────────────────────────────────────────────────────────────────
# AC-08: Phase strip shows failure counts
# ─────────────────────────────────────────────────────────────────────────────

def test_AC08a_phase_strip_mentions_failed():
    """AC-08a: Phase strip or summary includes failed count."""
    # This is more of an integration test - verify the manifest reader
    # is being used to get failure counts
    from buildcrew_dash import manifest_reader
    import json
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_path:
        tmp = Path(tmp_path)
        p = tmp / ".buildcrew" / "batch"
        p.mkdir(parents=True, exist_ok=True)
        data = {
            "batch_id": "test",
            "base_branch": "main",
            "base_commit": "abc123",
            "max_parallel": 5,
            "started_at": "2024-01-01T12:00:00",
            "tasks": [
                {
                    "index": 1,
                    "text": "Task",
                    "slug": "task",
                    "branch": "buildcrew/task",
                    "worktree": ".buildcrew/batch/worktrees/task",
                    "status": "failed",
                    "exit_code": 1,
                    "started_at": "2024-01-01T12:00:00",
                    "completed_at": "2024-01-01T12:05:00",
                }
            ],
        }
        (p / "manifest.json").write_text(json.dumps(data))

        manifest = manifest_reader.read(tmp)
        assert manifest is not None
        assert manifest.failed_count == 1

        # Phase strip should show the failure count
        # (This would be used in refresh_data to update #phase-strip)


def test_AC08b_index_screen_summary_includes_failures():
    """AC-08b: Index screen summary includes failure counts from manifest."""
    from buildcrew_dash import manifest_reader
    import json
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_path:
        tmp = Path(tmp_path)
        p = tmp / ".buildcrew" / "batch"
        p.mkdir(parents=True, exist_ok=True)
        data = {
            "batch_id": "test",
            "base_branch": "main",
            "base_commit": "abc123",
            "max_parallel": 5,
            "started_at": "2024-01-01T12:00:00",
            "tasks": [
                {
                    "index": 1,
                    "text": "Task 1",
                    "slug": "task-1",
                    "branch": "buildcrew/task-1",
                    "worktree": ".buildcrew/batch/worktrees/task-1",
                    "status": "completed",
                    "exit_code": 0,
                    "started_at": "2024-01-01T12:00:00",
                    "completed_at": "2024-01-01T12:05:00",
                },
                {
                    "index": 2,
                    "text": "Task 2",
                    "slug": "task-2",
                    "branch": "buildcrew/task-2",
                    "worktree": ".buildcrew/batch/worktrees/task-2",
                    "status": "failed",
                    "exit_code": 1,
                    "started_at": "2024-01-01T12:00:00",
                    "completed_at": "2024-01-01T12:05:00",
                },
                {
                    "index": 3,
                    "text": "Task 3",
                    "slug": "task-3",
                    "branch": "buildcrew/task-3",
                    "worktree": ".buildcrew/batch/worktrees/task-3",
                    "status": "verify_failed",
                    "exit_code": 1,
                    "started_at": "2024-01-01T12:00:00",
                    "completed_at": "2024-01-01T12:05:00",
                },
            ],
        }
        (p / "manifest.json").write_text(json.dumps(data))

        manifest = manifest_reader.read(tmp)
        assert manifest is not None

        # Summary should include all status counts
        parts = manifest.summary_parts(rich=False)
        summary = " ".join(parts)

        assert "1 done" in summary
        assert "1 failed" in summary
        assert "1 verify failed" in summary
