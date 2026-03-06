"""Unit tests for uat_reader module."""
from __future__ import annotations

import json
import time
from pathlib import Path

from buildcrew_dash import uat_reader
from buildcrew_dash.uat_reader import UATState, UATVerdict

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# read_state tests
# ---------------------------------------------------------------------------


def test_read_state_valid_fixture(tmp_path):
    """read_state with valid fixture returns UATState with correct fields."""
    bc = tmp_path / ".buildcrew"
    bc.mkdir()
    ts = str(int(time.time()))
    (bc / ".uat-state").write_text(
        f"UAT_PHASE=execute\n"
        f"UAT_ITERATION=2\n"
        f"UAT_STATUS=running\n"
        f"UAT_TIMESTAMP={ts}\n"
        f"UAT_PROJECT_NAME=buildcrew\n"
    )
    result = uat_reader.read_state(tmp_path)
    assert result is not None
    assert isinstance(result, UATState)
    assert result.phase == "execute"
    assert result.iteration == 2
    assert result.status == "running"
    assert result.timestamp == int(ts)
    assert result.project_name == "buildcrew"


def test_read_state_missing_file(tmp_path):
    """read_state with missing file returns None."""
    result = uat_reader.read_state(tmp_path)
    assert result is None


def test_read_state_malformed_partial(tmp_path):
    """read_state with malformed/partial key=value returns None."""
    bc = tmp_path / ".buildcrew"
    bc.mkdir()
    (bc / ".uat-state").write_text("UAT_PHASE=execute\nUAT_ITERATION=2\n")
    result = uat_reader.read_state(tmp_path)
    assert result is None


def test_read_state_stale_timestamp(tmp_path):
    """read_state with stale timestamp (>7200s ago) returns None."""
    bc = tmp_path / ".buildcrew"
    bc.mkdir()
    old_ts = str(int(time.time()) - 8000)
    (bc / ".uat-state").write_text(
        f"UAT_PHASE=execute\n"
        f"UAT_ITERATION=1\n"
        f"UAT_STATUS=running\n"
        f"UAT_TIMESTAMP={old_ts}\n"
        f"UAT_PROJECT_NAME=test\n"
    )
    result = uat_reader.read_state(tmp_path)
    assert result is None


def test_read_state_non_numeric_iteration(tmp_path):
    """read_state with non-numeric iteration returns None."""
    bc = tmp_path / ".buildcrew"
    bc.mkdir()
    ts = str(int(time.time()))
    (bc / ".uat-state").write_text(
        f"UAT_PHASE=execute\n"
        f"UAT_ITERATION=abc\n"
        f"UAT_STATUS=running\n"
        f"UAT_TIMESTAMP={ts}\n"
        f"UAT_PROJECT_NAME=test\n"
    )
    result = uat_reader.read_state(tmp_path)
    assert result is None


def test_read_state_accepts_str_path(tmp_path):
    """read_state accepts a plain str path."""
    bc = tmp_path / ".buildcrew"
    bc.mkdir()
    ts = str(int(time.time()))
    (bc / ".uat-state").write_text(
        f"UAT_PHASE=stories\n"
        f"UAT_ITERATION=1\n"
        f"UAT_STATUS=running\n"
        f"UAT_TIMESTAMP={ts}\n"
        f"UAT_PROJECT_NAME=test\n"
    )
    result = uat_reader.read_state(str(tmp_path))
    assert result is not None
    assert result.phase == "stories"


def test_read_state_ignores_comments_and_blanks(tmp_path):
    """read_state ignores comment and blank lines."""
    bc = tmp_path / ".buildcrew"
    bc.mkdir()
    ts = str(int(time.time()))
    (bc / ".uat-state").write_text(
        f"# comment\n"
        f"\n"
        f"UAT_PHASE=harness\n"
        f"UAT_ITERATION=1\n"
        f"UAT_STATUS=running\n"
        f"UAT_TIMESTAMP={ts}\n"
        f"UAT_PROJECT_NAME=test\n"
    )
    result = uat_reader.read_state(tmp_path)
    assert result is not None
    assert result.phase == "harness"


# ---------------------------------------------------------------------------
# read_verdict tests
# ---------------------------------------------------------------------------


def test_read_verdict_valid_fixture(tmp_path, monkeypatch):
    """read_verdict with valid fixture JSON returns UATVerdict with scenario list."""
    signal_dir = tmp_path / ".buildcrew" / "uat-signals" / "test-project"
    signal_dir.mkdir(parents=True)
    data = json.loads((FIXTURES / "verdict.json").read_text())
    (signal_dir / "verdict.json").write_text(json.dumps(data))

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    result = uat_reader.read_verdict("test-project")
    assert result is not None
    assert isinstance(result, UATVerdict)
    assert result.status == "fail"
    assert result.build_iteration == 2
    assert result.total == 4
    assert result.passed == 2
    assert result.failed == 1
    assert result.errored == 1
    assert result.disputed == 0
    assert len(result.scenarios) == 4
    assert result.scenarios[0]["scenario"] == "User creates a new project"
    assert result.scenarios[0]["status"] == "pass"
    assert result.scenarios[2]["status"] == "fail"


def test_read_verdict_missing_file(tmp_path, monkeypatch):
    """read_verdict with missing file returns None."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    result = uat_reader.read_verdict("nonexistent-project")
    assert result is None


def test_read_verdict_no_signal_dir(tmp_path, monkeypatch):
    """read_verdict with project_name that has no signal dir returns None."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    result = uat_reader.read_verdict("no-such-project")
    assert result is None


def test_read_verdict_invalid_json(tmp_path, monkeypatch):
    """read_verdict with invalid JSON returns None."""
    signal_dir = tmp_path / ".buildcrew" / "uat-signals" / "bad-json"
    signal_dir.mkdir(parents=True)
    (signal_dir / "verdict.json").write_text("not valid json {{{")

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    result = uat_reader.read_verdict("bad-json")
    assert result is None


def test_read_verdict_missing_required_key(tmp_path, monkeypatch):
    """read_verdict with missing required key returns None."""
    signal_dir = tmp_path / ".buildcrew" / "uat-signals" / "missing-key"
    signal_dir.mkdir(parents=True)
    (signal_dir / "verdict.json").write_text('{"status": "pass"}')

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    result = uat_reader.read_verdict("missing-key")
    assert result is None
