"""Tests for activity_reader.py — AC-01 through AC-06 plus round-trip, verify status."""
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from buildcrew_dash.activity_reader import AgentActivity, VerifyStatus, read, read_verify_status


# ---------------------------------------------------------------------------
# AC-01: Absent file returns None
# ---------------------------------------------------------------------------


def test_ac01_absent_file_returns_none():
    """AC-01: read() with a path that does not exist returns None."""
    path = Path(__file__).parent.parent / "tests/fixtures/states/absent.state"
    assert read(path) is None


# ---------------------------------------------------------------------------
# AC-02: Valid file parses all fields correctly
# ---------------------------------------------------------------------------


def test_ac02_valid_file_parses_all_fields(tmp_path):
    """AC-02: Uppercase keys (as written by stream_processor) → parsed correctly via lowercasing."""
    f = tmp_path / "activity"
    f.write_text(
        "TOOL=Read\n"
        "TOOL_INPUT=src/foo.py\n"
        "TURN=5\n"
        "MAX_TURNS=50\n"
        "STATUS=running\n"
        "TIMESTAMP=1700000000\n"
    )
    result = read(f)
    assert result is not None
    assert result.tool == "Read"
    assert result.tool_input == "src/foo.py"
    assert result.turn == 5
    assert isinstance(result.turn, int)
    assert result.max_turns == 50
    assert isinstance(result.max_turns, int)
    assert result.status == "running"
    assert result.timestamp == 1700000000
    assert isinstance(result.timestamp, int)


# ---------------------------------------------------------------------------
# AC-03: Missing fields return defaults (no KeyError)
# ---------------------------------------------------------------------------


def test_ac03_missing_fields_returns_defaults(tmp_path):
    """AC-03: Only turn and max_turns present → other fields at defaults, no KeyError."""
    f = tmp_path / "activity"
    f.write_text("turn=5\nmax_turns=50\n")
    result = read(f)
    assert result is not None
    assert result.tool == ""
    assert result.tool_input == ""
    assert result.status == ""
    assert result.timestamp == 0
    assert result.turn == 5
    assert result.max_turns == 50


# ---------------------------------------------------------------------------
# AC-04: Malformed file (no = signs) returns defaults
# ---------------------------------------------------------------------------


def test_ac04_malformed_no_equals_returns_defaults(tmp_path):
    """AC-04: File with no key=value lines returns AgentActivity with all defaults."""
    f = tmp_path / "activity"
    f.write_text("malformed garbage\nno equals here\n")
    result = read(f)
    assert result is not None
    assert result.tool == ""
    assert result.tool_input == ""
    assert result.turn == 0
    assert result.max_turns == 0
    assert result.status == ""
    assert result.timestamp == 0


# ---------------------------------------------------------------------------
# AC-05: PermissionError returns None
# ---------------------------------------------------------------------------


def test_ac05_permission_error_returns_none(tmp_path):
    """AC-05: PermissionError when opening file → read() returns None."""
    f = tmp_path / "activity"
    f.write_text("tool=Read\n")
    with patch("pathlib.Path.read_text", side_effect=PermissionError("access denied")):
        result = read(f)
    assert result is None


# ---------------------------------------------------------------------------
# AC-06: Comment lines are skipped
# ---------------------------------------------------------------------------


def test_ac06_comment_lines_skipped(tmp_path):
    """AC-06: Lines starting with # are ignored; other keys parse normally."""
    f = tmp_path / "activity"
    f.write_text("# a comment\nturn=7\nmax_turns=10\n")
    result = read(f)
    assert result is not None
    assert result.turn == 7
    assert result.max_turns == 10
    assert result.tool == ""
    assert result.tool_input == ""
    assert result.status == ""
    assert result.timestamp == 0


# ---------------------------------------------------------------------------
# Round-trip: write all six keys and read back
# ---------------------------------------------------------------------------


def test_round_trip(tmp_path):
    """Round-trip: write all six keys and verify all six fields match."""
    f = tmp_path / "activity"
    f.write_text(
        "tool=Write\n"
        "tool_input=output/result.txt\n"
        "turn=12\n"
        "max_turns=100\n"
        "status=tool_use\n"
        "timestamp=1700001234\n"
    )
    result = read(f)
    assert result is not None
    assert result.tool == "Write"
    assert result.tool_input == "output/result.txt"
    assert result.turn == 12
    assert result.max_turns == 100
    assert result.status == "tool_use"
    assert result.timestamp == 1700001234


# ---------------------------------------------------------------------------
# Key casing: uppercase keys (as written by stream_processor) are lowercased
# ---------------------------------------------------------------------------


def test_uppercase_keys_parsed_as_lowercase(tmp_path):
    """Uppercase keys written by stream_processor are lowercased during parsing."""
    f = tmp_path / "activity"
    f.write_text("TOOL=Bash\nTURN=3\nMAX_TURNS=30\nSTATUS=running\nTIMESTAMP=1700000000\n")
    result = read(f)
    assert result is not None
    assert result.tool == "Bash"
    assert result.turn == 3
    assert result.max_turns == 30
    assert result.status == "running"
    assert result.timestamp == 1700000000


# ---------------------------------------------------------------------------
# VerifyStatus: read_verify_status()
# ---------------------------------------------------------------------------


def test_verify_status_no_files(tmp_path):
    """No verify output files → all False."""
    vs = read_verify_status(tmp_path)
    assert vs == VerifyStatus(security=False, tests=False, outcome=False)


def test_verify_status_all_files_present(tmp_path):
    """All three verify output files present → all True."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "security-audit.md").write_text("audit")
    (claude_dir / "verify-evidence.md").write_text("evidence")
    (claude_dir / "outcome-report.md").write_text("outcome")
    vs = read_verify_status(tmp_path)
    assert vs == VerifyStatus(security=True, tests=True, outcome=True)


def test_verify_status_partial_files(tmp_path):
    """Only security file present → security=True, others=False."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "security-audit.md").write_text("audit")
    vs = read_verify_status(tmp_path)
    assert vs.security is True
    assert vs.tests is False
    assert vs.outcome is False


def test_verify_status_stale_files_filtered(tmp_path):
    """Files older than phase_start are treated as not current."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    f = claude_dir / "security-audit.md"
    f.write_text("old audit")
    # phase_start is in the future relative to the file's mtime
    phase_start = datetime(2099, 1, 1)
    vs = read_verify_status(tmp_path, phase_start=phase_start)
    assert vs.security is False


def test_verify_status_current_files_pass(tmp_path):
    """Files newer than phase_start are treated as current."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "security-audit.md").write_text("new audit")
    # phase_start is in the past
    phase_start = datetime(2000, 1, 1)
    vs = read_verify_status(tmp_path, phase_start=phase_start)
    assert vs.security is True
