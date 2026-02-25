"""Tests for activity_reader.py — AC-01 through AC-06 plus round-trip."""
from pathlib import Path
from unittest.mock import patch

import pytest

from buildcrew_dash.activity_reader import AgentActivity, read


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
    """AC-02: All six keys present → correct types and values."""
    f = tmp_path / "activity"
    f.write_text(
        "tool=Read\n"
        "tool_input=src/foo.py\n"
        "turn=5\n"
        "max_turns=50\n"
        "status=running\n"
        "timestamp=1700000000\n"
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
