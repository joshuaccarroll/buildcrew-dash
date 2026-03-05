"""TDD tests for index screen phase duration display (AC-09..AC-13, AC-16).

Tests call _compute_cells directly with mocked state/log/activity readers.
Phase column is cells[2].

Mock targets:
- buildcrew_dash.screens.index.state_reader.read
- buildcrew_dash.screens.index.log_parser.parse
- buildcrew_dash.screens.index.activity_reader.read
- buildcrew_dash.screens.index.datetime  (for datetime.now in duration calc)
- buildcrew_dash.screens.index.time      (for time.time in turn staleness & health)
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from buildcrew_dash.activity_reader import AgentActivity
from buildcrew_dash.log_parser import PhaseRecord
from buildcrew_dash.scanner import BuildCrewInstance
from buildcrew_dash.screens.index import IndexScreen
from buildcrew_dash.state_reader import WorkflowState


# ---------------------------------------------------------------------------
# Fixed time constants
# ---------------------------------------------------------------------------

FIXED_TIME = 1704110520  # arbitrary epoch seconds
FIXED_NOW = datetime(2024, 1, 1, 12, 25, 0)  # 1500s after FIXED_START
FIXED_START = datetime(2024, 1, 1, 12, 0, 0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_instance(project_path: str = "/tmp/bc_tdd_index") -> BuildCrewInstance:
    pp = Path(project_path)
    lp = pp / ".buildcrew" / "logs" / "buildcrew-2024-01-01_00-00-00-12345.log"
    return BuildCrewInstance(pid=12345, project_path=pp, log_path=lp)


def _make_state(**kwargs) -> WorkflowState:
    defaults = dict(
        task_num=1,
        total_tasks=3,
        task_name="implement auth",
        phase="build",
        phase_status="running",
        invocation_count=4,
        max_invocations=15,
        timestamp=FIXED_TIME - 5,
    )
    defaults.update(kwargs)
    return WorkflowState(**defaults)


def _make_log_summary_mock(phases=None, start_time_offset=3600):
    """Return a MagicMock LogSummary with optional real phases list."""
    m = MagicMock()
    if start_time_offset is not None:
        m.start_time = datetime.fromtimestamp(FIXED_TIME - start_time_offset)
    else:
        m.start_time = None
    if phases is not None:
        m.phases = phases
    return m


def _make_activity(**kwargs) -> AgentActivity:
    defaults = dict(
        tool="Read",
        tool_input="src/foo.py",
        turn=15,
        max_turns=60,
        status="tool_use",
        timestamp=FIXED_TIME,
    )
    defaults.update(kwargs)
    return AgentActivity(**defaults)


# ---------------------------------------------------------------------------
# AC-09/AC-16a: Active PhaseRecord with started_at + fresh activity → duration + turn
# ---------------------------------------------------------------------------


def test_AC09_active_phase_record_fresh_activity_shows_duration_and_turn():
    """AC-09/AC-16a: Active PhaseRecord 1500s ago + fresh activity → 'build 25m T15/60'."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(phase="build", phase_status="running")
    phases = [
        PhaseRecord(name="build", status="active", started_at=FIXED_START, task_num=1),
    ]
    log_summary = _make_log_summary_mock(phases=phases)
    activity = _make_activity(turn=15, max_turns=60, timestamp=FIXED_TIME)

    mock_dt = MagicMock(wraps=datetime)
    mock_dt.now.return_value = FIXED_NOW

    mock_time = MagicMock()
    mock_time.time.return_value = FIXED_TIME

    with (
        patch("buildcrew_dash.screens.index.state_reader.read", return_value=state),
        patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary),
        patch("buildcrew_dash.screens.index.activity_reader.read", return_value=activity),
        patch("buildcrew_dash.screens.index.time", mock_time),
        patch("buildcrew_dash.screens.index.datetime", mock_dt),
        patch("buildcrew_dash.screens.index.stop_control.is_stop_pending", return_value=False),
    ):
        cells = screen._compute_cells(inst)

    assert cells[2] == "build 25m T15/60"


# ---------------------------------------------------------------------------
# AC-09/AC-16b: Active PhaseRecord with started_at + stale activity → duration only
# ---------------------------------------------------------------------------


def test_AC09_active_phase_record_stale_activity_shows_duration_only():
    """AC-09/AC-16b: Active PhaseRecord 1500s ago + stale activity → 'build 25m'."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(phase="build", phase_status="running")
    phases = [
        PhaseRecord(name="build", status="active", started_at=FIXED_START, task_num=1),
    ]
    log_summary = _make_log_summary_mock(phases=phases)
    stale_activity = _make_activity(turn=15, max_turns=60, timestamp=FIXED_TIME - 60)

    mock_dt = MagicMock(wraps=datetime)
    mock_dt.now.return_value = FIXED_NOW

    mock_time = MagicMock()
    mock_time.time.return_value = FIXED_TIME

    with (
        patch("buildcrew_dash.screens.index.state_reader.read", return_value=state),
        patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary),
        patch("buildcrew_dash.screens.index.activity_reader.read", return_value=stale_activity),
        patch("buildcrew_dash.screens.index.time", mock_time),
        patch("buildcrew_dash.screens.index.datetime", mock_dt),
        patch("buildcrew_dash.screens.index.stop_control.is_stop_pending", return_value=False),
    ):
        cells = screen._compute_cells(inst)

    assert cells[2] == "build 25m"


# ---------------------------------------------------------------------------
# AC-10/AC-16c: No matching PhaseRecord + fresh activity → phase name + turn only
# ---------------------------------------------------------------------------


def test_AC10_no_matching_record_fresh_activity_shows_turn_only():
    """AC-10/AC-16c: No matching PhaseRecord, fresh activity → 'build T15/60'."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(phase="build", phase_status="running")
    log_summary = _make_log_summary_mock(phases=[])
    activity = _make_activity(turn=15, max_turns=60, timestamp=FIXED_TIME)

    mock_time = MagicMock()
    mock_time.time.return_value = FIXED_TIME

    with (
        patch("buildcrew_dash.screens.index.state_reader.read", return_value=state),
        patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary),
        patch("buildcrew_dash.screens.index.activity_reader.read", return_value=activity),
        patch("buildcrew_dash.screens.index.time", mock_time),
        patch("buildcrew_dash.screens.index.stop_control.is_stop_pending", return_value=False),
    ):
        cells = screen._compute_cells(inst)

    assert cells[2] == "build T15/60"


# ---------------------------------------------------------------------------
# AC-10/AC-16d: No matching PhaseRecord + stale activity → phase name only
# ---------------------------------------------------------------------------


def test_AC10_no_matching_record_stale_activity_shows_phase_only():
    """AC-10/AC-16d: No matching PhaseRecord, stale activity → 'build'."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(phase="build", phase_status="running")
    log_summary = _make_log_summary_mock(phases=[])
    stale_activity = _make_activity(turn=15, max_turns=60, timestamp=FIXED_TIME - 60)

    mock_time = MagicMock()
    mock_time.time.return_value = FIXED_TIME

    with (
        patch("buildcrew_dash.screens.index.state_reader.read", return_value=state),
        patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary),
        patch("buildcrew_dash.screens.index.activity_reader.read", return_value=stale_activity),
        patch("buildcrew_dash.screens.index.time", mock_time),
        patch("buildcrew_dash.screens.index.stop_control.is_stop_pending", return_value=False),
    ):
        cells = screen._compute_cells(inst)

    assert cells[2] == "build"


# ---------------------------------------------------------------------------
# AC-11/AC-16e: MagicMock lacking phases attr → guard prevents crash
# ---------------------------------------------------------------------------


def test_AC11_guard_prevents_crash_on_mock_without_phases():
    """AC-11/AC-16e: log_summary lacking real 'phases' attr (MagicMock spec=[]) → guard prevents crash."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(phase="build", phase_status="running")
    # MagicMock with spec=[] has no 'phases' attribute
    log_summary = MagicMock(spec=[])
    log_summary.start_time = datetime.fromtimestamp(FIXED_TIME - 3600)
    activity = _make_activity(turn=15, max_turns=60, timestamp=FIXED_TIME)

    mock_time = MagicMock()
    mock_time.time.return_value = FIXED_TIME

    with (
        patch("buildcrew_dash.screens.index.state_reader.read", return_value=state),
        patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary),
        patch("buildcrew_dash.screens.index.activity_reader.read", return_value=activity),
        patch("buildcrew_dash.screens.index.time", mock_time),
        patch("buildcrew_dash.screens.index.stop_control.is_stop_pending", return_value=False),
    ):
        cells = screen._compute_cells(inst)

    # Guard skips duration lookup; fresh activity still adds turn info
    assert cells[2] == "build T15/60"
