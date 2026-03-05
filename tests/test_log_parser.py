from datetime import datetime
from pathlib import Path

import pytest

from buildcrew_dash.log_parser import LogSummary, PhaseRecord, parse

_FIXTURES = Path(__file__).parent / "fixtures/logs"


def test_complete_run():
    result = parse(_FIXTURES / "buildcrew-2024-01-15_10-00-00-12345.log")
    assert result.pid == 12345
    assert result.start_time == datetime(2024, 1, 15, 10, 0, 0)
    assert len(result.phases) == 8
    assert [p.name for p in result.phases] == [
        "spec", "research", "review", "tdd-scaffold", "build", "simplify", "codereview", "verify"
    ]
    for phase in result.phases:
        assert phase.status == "complete"
    assert result.flags["skip_spec"] == "false"
    assert result.flags["branch"] == "main"
    assert len(result.flags) == 8
    assert result.completed_tasks == ["implement the thing"]
    # All phases are for task 1 (single completed task)
    for phase in result.phases:
        assert phase.task_num == 1


def test_in_progress():
    result = parse(_FIXTURES / "buildcrew-2024-01-15_11-00-00-99999.log")
    assert result.pid == 99999
    assert len(result.phases) == 3
    assert result.phases[0].name == "spec"
    assert result.phases[0].status == "complete"
    assert result.phases[1].name == "research"
    assert result.phases[1].status == "complete"
    assert result.phases[2].name == "review"
    assert result.phases[2].status == "active"
    assert result.phases[2].started_at == datetime(2024, 1, 15, 11, 0, 6)
    assert result.phases[2].ended_at is None
    assert result.completed_tasks == []
    # No [OK] Completed: → all phases are task 1
    assert result.phases[0].task_num == 1
    assert result.phases[1].task_num == 1
    assert result.phases[2].task_num == 1


def test_retry():
    result = parse(_FIXTURES / "buildcrew-2024-01-15_12-00-00-55555.log")
    assert result.pid == 55555
    assert len(result.phases) == 1
    assert result.phases[0].name == "research"
    assert result.phases[0].status == "complete"
    assert result.phases[0].verdict == "complete"
    assert result.phases[0].started_at == datetime(2024, 1, 15, 12, 0, 1)
    assert result.phases[0].ended_at == datetime(2024, 1, 15, 12, 0, 3)
    assert result.completed_tasks == []
    assert result.phases[0].task_num == 1


def test_missing_file():
    with pytest.raises(FileNotFoundError):
        parse(Path("/nonexistent/path/to/file.log"))


def test_types_and_recent_lines(tmp_path):
    log_file = tmp_path / "buildcrew-2024-01-15_10-00-00-77777.log"
    log_file.write_text(
        "[2024-01-15T10:00:00] [OK] Completed: do the thing\n"
        "[2024-01-15T10:00:01] [OK] Completed: do the thing\n"
    )
    result = parse(log_file)
    assert isinstance(result.start_time, datetime) is False
    assert isinstance(result.flags, dict) is True
    assert isinstance(result.recent_lines, list) is True
    assert len(result.recent_lines) == 2
    assert all(line.strip() != "" for line in result.recent_lines) is True
    assert result.completed_tasks == ["do the thing"]


# ---------------------------------------------------------------------------
# PermissionError / UnicodeDecodeError fallback (ERR-03, ERR-04, EDGE-01, EDGE-02)
# ---------------------------------------------------------------------------


def test_permission_error_returns_fallback(tmp_path):
    """ERR-03: PermissionError on read_text returns fallback LogSummary with pid=0."""
    from pathlib import Path as _Path
    from unittest.mock import patch as _patch
    log_dir = tmp_path / ".buildcrew" / "logs"
    log_dir.mkdir(parents=True)
    log_file = log_dir / "buildcrew-2024-01-15_10-00-00-12345.log"
    log_file.touch()

    with _patch.object(_Path, "read_text", side_effect=PermissionError("permission denied")):
        result = parse(log_file)

    assert result.pid == 0
    assert result.recent_lines == ["(log unreadable)"]
    assert result.flags == {}
    assert result.phases == []
    assert result.completed_tasks == []


def test_unicode_decode_error_returns_fallback(tmp_path):
    """ERR-04: UnicodeDecodeError on read_text returns fallback LogSummary."""
    from pathlib import Path as _Path
    from unittest.mock import patch as _patch
    log_dir = tmp_path / ".buildcrew" / "logs"
    log_dir.mkdir(parents=True)
    log_file = log_dir / "buildcrew-2024-01-15_10-00-00-12345.log"
    log_file.touch()

    err = UnicodeDecodeError("utf-8", b"\xff\xfe", 0, 1, "invalid start byte")
    with _patch.object(_Path, "read_text", side_effect=err):
        result = parse(log_file)

    assert result.pid == 0
    assert result.recent_lines == ["(log unreadable)"]
    assert result.flags == {}
    assert result.phases == []
    assert result.completed_tasks == []


def test_fallback_project_path(tmp_path):
    """EDGE-01/EDGE-02: Fallback LogSummary project_path is log_path.resolve().parent.parent.parent."""
    from pathlib import Path as _Path
    from unittest.mock import patch as _patch
    log_dir = tmp_path / ".buildcrew" / "logs"
    log_dir.mkdir(parents=True)
    log_file = log_dir / "buildcrew-2024-01-15_10-00-00-12345.log"
    log_file.touch()

    with _patch.object(_Path, "read_text", side_effect=PermissionError("denied")):
        result = parse(log_file)

    # log_file.parent = .buildcrew/logs, .parent.parent = .buildcrew, .parent.parent.parent = tmp_path
    assert result.project_path == log_file.resolve().parent.parent.parent
    assert result.project_path == tmp_path.resolve()


def test_multi_task_phases_have_correct_task_nums(tmp_path):
    """AC-03: Two-task log: first task's phases get task_num=1, second task's phases get task_num=2."""
    log_file = tmp_path / "buildcrew-2024-01-01_00-00-00-1.log"
    log_file.write_text(
        "[2024-01-01T00:00:01] === PHASE: spec started (max_turns=5) ===\n"
        "[2024-01-01T00:00:02] === PHASE: spec ended (verdict: ok) ===\n"
        "[2024-01-01T00:00:03] === PHASE: build started (max_turns=5) ===\n"
        "[2024-01-01T00:00:04] === PHASE: build ended (verdict: ok) ===\n"
        "[2024-01-01T00:00:05] [OK] Completed: task1\n"
        "[2024-01-01T00:00:06] === PHASE: spec started (max_turns=5) ===\n"
        "[2024-01-01T00:00:07] === PHASE: spec ended (verdict: ok) ===\n"
        "[2024-01-01T00:00:08] === PHASE: build started (max_turns=5) ===\n"
        "[2024-01-01T00:00:09] === PHASE: build ended (verdict: ok) ===\n"
        "[2024-01-01T00:00:10] [OK] Completed: task2\n"
    )
    result = parse(log_file)
    assert len(result.phases) == 4
    assert result.phases[0].task_num == 1  # first spec
    assert result.phases[1].task_num == 1  # first build
    assert result.phases[2].task_num == 2  # second spec
    assert result.phases[3].task_num == 2  # second build
    assert len(result.completed_tasks) == 2


def test_phases_before_any_completed_have_task_num_1(tmp_path):
    """AC-02 variant: Phases before any [OK] Completed: line all get task_num=1."""
    log_file = tmp_path / "buildcrew-2024-01-01_00-00-00-1.log"
    log_file.write_text(
        "[2024-01-01T00:00:01] === PHASE: spec started (max_turns=5) ===\n"
        "[2024-01-01T00:00:02] === PHASE: spec ended (verdict: ok) ===\n"
        "[2024-01-01T00:00:03] [INFO] Skipping phase: research\n"
        "[2024-01-01T00:00:04] === PHASE: build started (max_turns=5) ===\n"
        "[2024-01-01T00:00:05] [OK] Completed: mytask\n"
    )
    result = parse(log_file)
    assert len(result.phases) == 3
    assert result.phases[0].task_num == 1  # spec (complete)
    assert result.phases[1].task_num == 1  # research (skipped)
    assert result.phases[2].task_num == 1  # build (active — no ended line)
    assert len(result.completed_tasks) == 1


def test_skipped_phases_get_task_num(tmp_path):
    """Skipped phases get the current task_num at the time they appear."""
    log_file = tmp_path / "buildcrew-2024-01-01_00-00-00-1.log"
    log_file.write_text(
        "[2024-01-01T00:00:01] [INFO] Skipping phase: research\n"
    )
    result = parse(log_file)
    assert len(result.phases) == 1
    assert result.phases[0].name == "research"
    assert result.phases[0].status == "skipped"
    assert result.phases[0].task_num == 1
