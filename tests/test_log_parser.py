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
        "spec", "research", "review", "build", "codereview", "test", "verify", "outcome"
    ]
    for phase in result.phases[:7]:
        assert phase.status == "complete"
    assert result.phases[7].status == "skipped"
    assert result.phases[7].verdict is None
    assert result.phases[7].started_at is None
    assert result.flags["skip_spec"] == "false"
    assert result.flags["branch"] == "main"
    assert len(result.flags) == 8
    assert result.completed_tasks == ["implement the thing"]


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
