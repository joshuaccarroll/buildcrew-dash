"""Unit tests for manifest_reader module."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from buildcrew_dash import manifest_reader
from buildcrew_dash.manifest_reader import BatchManifest, BatchTask

FIXTURES = Path(__file__).parent / "fixtures" / "manifests"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_manifest(tmp_path: Path, data: dict) -> None:
    p = tmp_path / ".buildcrew" / "batch"
    p.mkdir(parents=True, exist_ok=True)
    (p / "manifest.json").write_text(json.dumps(data))


def _basic_manifest_data() -> dict:
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
                "status": "pending",
                "exit_code": None,
                "started_at": None,
                "completed_at": None,
            }
        ],
    }


# ---------------------------------------------------------------------------
# Missing / invalid file tests
# ---------------------------------------------------------------------------


def test_missing_file_returns_none(tmp_path):
    result = manifest_reader.read(tmp_path)
    assert result is None


def test_empty_file_returns_none(tmp_path):
    p = tmp_path / ".buildcrew" / "batch"
    p.mkdir(parents=True)
    (p / "manifest.json").write_text("")
    assert manifest_reader.read(tmp_path) is None


def test_invalid_json_returns_none(tmp_path):
    p = tmp_path / ".buildcrew" / "batch"
    p.mkdir(parents=True)
    (p / "manifest.json").write_text("{not valid json")
    assert manifest_reader.read(tmp_path) is None


def test_missing_required_key_returns_none(tmp_path):
    data = _basic_manifest_data()
    del data["batch_id"]
    _write_manifest(tmp_path, data)
    assert manifest_reader.read(tmp_path) is None


def test_missing_tasks_key_returns_none(tmp_path):
    data = _basic_manifest_data()
    del data["tasks"]
    _write_manifest(tmp_path, data)
    assert manifest_reader.read(tmp_path) is None


def test_missing_task_required_key_returns_none(tmp_path):
    data = _basic_manifest_data()
    del data["tasks"][0]["index"]
    _write_manifest(tmp_path, data)
    assert manifest_reader.read(tmp_path) is None


# ---------------------------------------------------------------------------
# Successful parse tests
# ---------------------------------------------------------------------------


def test_basic_manifest_parses_all_fields(tmp_path):
    data = _basic_manifest_data()
    _write_manifest(tmp_path, data)
    result = manifest_reader.read(tmp_path)
    assert result is not None
    assert result.batch_id == "20240101-120000"
    assert result.base_branch == "main"
    assert result.base_commit == "abc123"
    assert result.max_parallel == 5
    assert result.started_at == "2024-01-01T12:00:00"
    assert len(result.tasks) == 1
    t = result.tasks[0]
    assert t.index == 1
    assert t.text == "Task one"
    assert t.slug == "task-one"
    assert t.branch == "buildcrew/task-one"
    assert t.worktree == ".buildcrew/batch/worktrees/task-one"
    assert t.status == "pending"
    assert t.exit_code is None
    assert t.started_at is None
    assert t.completed_at is None


def test_task_with_all_fields_populated(tmp_path):
    data = _basic_manifest_data()
    data["tasks"][0].update({
        "status": "completed",
        "exit_code": 0,
        "started_at": "2024-01-01T12:00:01",
        "completed_at": "2024-01-01T12:05:30",
    })
    _write_manifest(tmp_path, data)
    result = manifest_reader.read(tmp_path)
    assert result is not None
    t = result.tasks[0]
    assert t.status == "completed"
    assert t.exit_code == 0
    assert t.started_at == "2024-01-01T12:00:01"
    assert t.completed_at == "2024-01-01T12:05:30"


def test_empty_tasks_list_returns_manifest_with_total_zero(tmp_path):
    data = _basic_manifest_data()
    data["tasks"] = []
    _write_manifest(tmp_path, data)
    result = manifest_reader.read(tmp_path)
    assert result is not None
    assert result.total == 0


def test_max_parallel_parsed_as_int(tmp_path):
    data = _basic_manifest_data()
    _write_manifest(tmp_path, data)
    result = manifest_reader.read(tmp_path)
    assert isinstance(result.max_parallel, int)
    assert result.max_parallel == 5


# ---------------------------------------------------------------------------
# Count property tests
# ---------------------------------------------------------------------------


def test_count_properties_mixed_statuses(tmp_path):
    """Load the mixed_status fixture and verify all count properties."""
    data = json.loads((FIXTURES / "mixed_status.json").read_text())
    _write_manifest(tmp_path, data)
    result = manifest_reader.read(tmp_path)
    assert result is not None
    assert result.total == 5
    assert result.pending_count == 1
    assert result.running_count == 1
    assert result.completed_count == 1
    assert result.failed_count == 1
    assert result.interrupted_count == 1


def test_count_properties_all_pending(tmp_path):
    data = _basic_manifest_data()
    data["tasks"] = [
        {**data["tasks"][0], "index": i, "slug": f"task-{i}"}
        for i in range(1, 4)
    ]
    _write_manifest(tmp_path, data)
    result = manifest_reader.read(tmp_path)
    assert result.total == 3
    assert result.pending_count == 3
    assert result.running_count == 0
    assert result.completed_count == 0
    assert result.failed_count == 0
    assert result.interrupted_count == 0


# ---------------------------------------------------------------------------
# Fixture file tests
# ---------------------------------------------------------------------------


def test_basic_fixture_parses(tmp_path):
    """Verify the basic.json fixture is valid and parseable."""
    data = json.loads((FIXTURES / "basic.json").read_text())
    _write_manifest(tmp_path, data)
    result = manifest_reader.read(tmp_path)
    assert result is not None
    assert result.total == 3
    assert result.completed_count == 1
    assert result.running_count == 1
    assert result.pending_count == 1


def test_mixed_status_fixture_parses(tmp_path):
    """Verify the mixed_status.json fixture is valid and parseable."""
    data = json.loads((FIXTURES / "mixed_status.json").read_text())
    _write_manifest(tmp_path, data)
    result = manifest_reader.read(tmp_path)
    assert result is not None
    assert result.total == 5
