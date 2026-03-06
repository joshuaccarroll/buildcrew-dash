"""Edge case and adversarial tests for phase durations and turn progress.

Covers scenarios NOT tested by TDD scaffold:
- EDGE-02, -04: Formatter edge cases (large/negative values)
- EDGE-05, -07, -11, -13: _phase_duration_label edge cases
- EDGE-06: Kanban strip with turn=0
- EDGE-08, -09, -10, -12, -14: Index _compute_cells edge cases
- ADV-02: Kanban strip 30s boundary
- ADV-04: Index phases attribute is non-list
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from buildcrew_dash.activity_reader import AgentActivity
from buildcrew_dash.log_parser import PhaseRecord
from buildcrew_dash.scanner import BuildCrewInstance, ProcessMonitor, ProcessScanner
from buildcrew_dash.screens.kanban import (
    KanbanScreen,
    _format_phase_duration,
    _phase_duration_label,
)
from buildcrew_dash.screens.index import IndexScreen
from buildcrew_dash.state_reader import WorkflowState
from textual.app import App
from textual.widgets import Static


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ---------------------------------------------------------------------------
# Fixed time constants (shared with TDD tests)
# ---------------------------------------------------------------------------

FIXED_TIME = 1704110520
FIXED_NOW = datetime(2024, 1, 1, 12, 12, 0)  # 720s after FIXED_START
FIXED_NOW_1500 = datetime(2024, 1, 1, 12, 25, 0)  # 1500s after FIXED_START
FIXED_START = datetime(2024, 1, 1, 12, 0, 0)
FIXED_END_120S = datetime(2024, 1, 1, 12, 2, 0)
FIXED_END_300S = datetime(2024, 1, 1, 12, 5, 0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_instance(project_path: str = "/tmp/bc_edge_test", log_path: str | None = None) -> BuildCrewInstance:
    pp = Path(project_path)
    lp = (
        Path(log_path) if log_path
        else pp / ".buildcrew" / "logs" / "buildcrew-2024-01-01_00-00-00-12345.log"
    )
    return BuildCrewInstance(pid=12345, project_path=pp, log_path=lp)


def _make_state(**kwargs) -> WorkflowState:
    defaults: dict = dict(
        task_num=1,
        total_tasks=3,
        task_name="implement auth",
        phase="build",
        phase_status="running",
        invocation_count=4,
        max_invocations=15,
        timestamp=FIXED_TIME - 5,
        auto_mode=False,
    )
    defaults.update(kwargs)
    return WorkflowState(**defaults)


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


def _make_index_log_summary_mock(phases=None, start_time_offset=3600):
    """Return a MagicMock LogSummary with optional real phases list."""
    m = MagicMock()
    if start_time_offset is not None:
        m.start_time = datetime.fromtimestamp(FIXED_TIME - start_time_offset)
    else:
        m.start_time = None
    if phases is not None:
        m.phases = phases
    return m


class _EdgeKanbanApp(App):
    """Minimal host app for kanban integration tests."""

    def __init__(self, instance: BuildCrewInstance) -> None:
        super().__init__()
        self._instance = instance

    def on_mount(self) -> None:
        self.push_screen(KanbanScreen(self._instance))


def _get_strip_segment(pilot, phase_name: str) -> str:
    """Extract the segment for *phase_name* from the phase strip text."""
    screen = pilot.app.screen
    strip = screen.query_one("#phase-strip", Static)
    text = str(strip.content)
    segments = text.split(" → ")
    for seg in segments:
        if phase_name in seg:
            return seg
    raise AssertionError(f"Phase '{phase_name}' not found in strip: {text!r}")


# ---------------------------------------------------------------------------
# EDGE-02: Very large value (100 hours)
# ---------------------------------------------------------------------------


def test_edge02_format_phase_duration_very_large():
    """EDGE-02: 360000s → '100h00m'."""
    assert _format_phase_duration(360000) == "100h00m"


# ---------------------------------------------------------------------------
# EDGE-04: Large negative
# ---------------------------------------------------------------------------


def test_edge04_format_phase_duration_large_negative():
    """EDGE-04: -99999s → '<1m'."""
    assert _format_phase_duration(-99999) == "<1m"


# ---------------------------------------------------------------------------
# EDGE-05: Completed phase with started_at=None
# ---------------------------------------------------------------------------


def test_edge05_phase_duration_label_complete_no_started_at():
    """EDGE-05: Completed phase with started_at=None returns ''."""
    rec = PhaseRecord(name="build", status="complete", started_at=None, ended_at=FIXED_END_120S, task_num=1)
    assert _phase_duration_label(rec) == ""


# ---------------------------------------------------------------------------
# EDGE-07: Clock skew: started_at > ended_at
# ---------------------------------------------------------------------------


def test_edge07_phase_duration_label_clock_skew():
    """EDGE-07: started_at > ended_at → negative seconds → ' <1m'."""
    rec = PhaseRecord(
        name="build", status="complete",
        started_at=FIXED_END_120S, ended_at=FIXED_START,  # reversed!
        task_num=1,
    )
    result = _phase_duration_label(rec)
    assert result == " <1m"


# ---------------------------------------------------------------------------
# EDGE-11: Skipped phase with started_at set
# ---------------------------------------------------------------------------


def test_edge11_phase_duration_label_skipped_with_started_at():
    """EDGE-11: Skipped phase with started_at set still returns ''."""
    rec = PhaseRecord(name="build", status="skipped", started_at=FIXED_START, task_num=1)
    assert _phase_duration_label(rec) == ""


# ---------------------------------------------------------------------------
# EDGE-13: Completed phase with started_at set but ended_at=None
# ---------------------------------------------------------------------------


def test_edge13_phase_duration_label_complete_no_ended_at():
    """EDGE-13: Completed phase with started_at set but ended_at=None returns ''."""
    rec = PhaseRecord(name="build", status="complete", started_at=FIXED_START, ended_at=None, task_num=1)
    result = _phase_duration_label(rec)
    assert result == ""


# ---------------------------------------------------------------------------
# EDGE-06: Kanban strip — activity with turn=0
# ---------------------------------------------------------------------------


from buildcrew_dash.log_parser import LogSummary


def _make_kanban_log_summary(phases: list[PhaseRecord] | None = None) -> LogSummary:
    return LogSummary(
        pid=12345,
        project_path=Path("/tmp/bc_edge_test"),
        start_time=datetime.now(),
        flags={},
        phases=phases if phases is not None else [],
        completed_tasks=[],
        last_write_time=datetime.now(),
        recent_lines=[],
    )


@pytest.mark.anyio(backends=["asyncio"])
async def test_edge06_kanban_strip_turn_zero(tmp_path):
    """EDGE-06: Fresh activity with turn=0 → no turn info, duration still shows."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(phase="build", phase_status="running")
    phases = [
        PhaseRecord(name="build", status="active", started_at=FIXED_START, task_num=1),
    ]
    log_summary = _make_kanban_log_summary(phases=phases)
    activity = _make_activity(turn=0, max_turns=60, timestamp=FIXED_TIME)

    mock_dt = MagicMock(wraps=datetime)
    mock_dt.now.return_value = FIXED_NOW

    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
        patch("buildcrew_dash.screens.kanban.activity_reader.read", return_value=activity),
        patch("buildcrew_dash.screens.kanban.datetime", mock_dt),
        patch("buildcrew_dash.screens.kanban.time.time", return_value=FIXED_TIME),
    ):
        async with _EdgeKanbanApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            seg = _get_strip_segment(pilot, "build")
            assert seg == "● build 12m"


# ---------------------------------------------------------------------------
# ADV-02: Kanban strip — 30s boundary (exactly stale)
# ---------------------------------------------------------------------------


@pytest.mark.anyio(backends=["asyncio"])
async def test_adv02_kanban_strip_30s_boundary(tmp_path):
    """ADV-02: Activity timestamp exactly 30s old → stale, no turn info."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(phase="build", phase_status="running")
    phases = [
        PhaseRecord(name="build", status="active", started_at=FIXED_START, task_num=1),
    ]
    log_summary = _make_kanban_log_summary(phases=phases)
    # Exactly 30s old: int(time.time()) - activity.timestamp == 30
    activity = _make_activity(turn=15, max_turns=60, timestamp=FIXED_TIME - 30)

    mock_dt = MagicMock(wraps=datetime)
    mock_dt.now.return_value = FIXED_NOW

    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
        patch("buildcrew_dash.screens.kanban.activity_reader.read", return_value=activity),
        patch("buildcrew_dash.screens.kanban.datetime", mock_dt),
        patch("buildcrew_dash.screens.kanban.time.time", return_value=FIXED_TIME),
    ):
        async with _EdgeKanbanApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            seg = _get_strip_segment(pilot, "build")
            assert seg == "● build 12m"


# ---------------------------------------------------------------------------
# EDGE-08: Index — multiple matching PhaseRecords, last in list wins
# ---------------------------------------------------------------------------


def test_edge08_index_multiple_matching_records_last_wins():
    """EDGE-08: Two PhaseRecords for same phase/task — reversed() picks last in list."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(phase="build", phase_status="running")
    phases = [
        PhaseRecord(name="build", status="active", started_at=FIXED_START, ended_at=FIXED_END_120S, task_num=1),
        PhaseRecord(name="build", status="active", started_at=FIXED_START, ended_at=FIXED_END_300S, task_num=1),
    ]
    log_summary = _make_index_log_summary_mock(phases=phases)
    stale_activity = _make_activity(turn=15, max_turns=60, timestamp=FIXED_TIME - 60)

    mock_time = MagicMock()
    mock_time.time.return_value = FIXED_TIME

    with (
        patch("buildcrew_dash.screens.index.state_reader.read", return_value=state),
        patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary),
        patch("buildcrew_dash.screens.index.activity_reader.read", return_value=stale_activity),
        patch("buildcrew_dash.screens.index.time", mock_time),
        patch("buildcrew_dash.screens.index.stop_control.is_stop_pending", return_value=False),
        patch("buildcrew_dash.screens.index.uat_reader.read_state", return_value=None),
    ):
        cells = screen._compute_cells(inst)

    assert cells[2] == "5/8 build 5m"


# ---------------------------------------------------------------------------
# EDGE-09: Index — PhaseRecord task_num mismatch
# ---------------------------------------------------------------------------


def test_edge09_index_task_num_mismatch():
    """EDGE-09: PhaseRecord task_num=2 with state.task_num=1 → no duration."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(phase="build", phase_status="running", task_num=1)
    phases = [
        PhaseRecord(name="build", status="active", started_at=FIXED_START, task_num=2),
    ]
    log_summary = _make_index_log_summary_mock(phases=phases)
    stale_activity = _make_activity(turn=15, max_turns=60, timestamp=FIXED_TIME - 60)

    mock_time = MagicMock()
    mock_time.time.return_value = FIXED_TIME

    with (
        patch("buildcrew_dash.screens.index.state_reader.read", return_value=state),
        patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary),
        patch("buildcrew_dash.screens.index.activity_reader.read", return_value=stale_activity),
        patch("buildcrew_dash.screens.index.time", mock_time),
        patch("buildcrew_dash.screens.index.stop_control.is_stop_pending", return_value=False),
        patch("buildcrew_dash.screens.index.uat_reader.read_state", return_value=None),
    ):
        cells = screen._compute_cells(inst)

    assert cells[2] == "5/8 build"


# ---------------------------------------------------------------------------
# EDGE-10: Index — log_summary.phases is None
# ---------------------------------------------------------------------------


def test_edge10_index_phases_is_none():
    """EDGE-10: log_summary.phases = None → isinstance guard skips, no crash."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(phase="build", phase_status="running")
    log_summary = _make_index_log_summary_mock()
    log_summary.phases = None
    stale_activity = _make_activity(turn=15, max_turns=60, timestamp=FIXED_TIME - 60)

    mock_time = MagicMock()
    mock_time.time.return_value = FIXED_TIME

    with (
        patch("buildcrew_dash.screens.index.state_reader.read", return_value=state),
        patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary),
        patch("buildcrew_dash.screens.index.activity_reader.read", return_value=stale_activity),
        patch("buildcrew_dash.screens.index.time", mock_time),
        patch("buildcrew_dash.screens.index.stop_control.is_stop_pending", return_value=False),
        patch("buildcrew_dash.screens.index.uat_reader.read_state", return_value=None),
    ):
        cells = screen._compute_cells(inst)

    assert cells[2] == "5/8 build"


# ---------------------------------------------------------------------------
# EDGE-12: Index — activity with turn=0
# ---------------------------------------------------------------------------


def test_edge12_index_turn_zero():
    """EDGE-12: Fresh activity with turn=0 → duration but no turn info."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(phase="build", phase_status="running")
    phases = [
        PhaseRecord(name="build", status="active", started_at=FIXED_START, task_num=1),
    ]
    log_summary = _make_index_log_summary_mock(phases=phases)
    activity = _make_activity(turn=0, max_turns=60, timestamp=FIXED_TIME)

    mock_dt = MagicMock(wraps=datetime)
    mock_dt.now.return_value = FIXED_NOW_1500

    mock_time = MagicMock()
    mock_time.time.return_value = FIXED_TIME

    with (
        patch("buildcrew_dash.screens.index.state_reader.read", return_value=state),
        patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary),
        patch("buildcrew_dash.screens.index.activity_reader.read", return_value=activity),
        patch("buildcrew_dash.screens.index.time", mock_time),
        patch("buildcrew_dash.screens.index.datetime", mock_dt),
        patch("buildcrew_dash.screens.index.stop_control.is_stop_pending", return_value=False),
        patch("buildcrew_dash.screens.index.uat_reader.read_state", return_value=None),
    ):
        cells = screen._compute_cells(inst)

    assert cells[2] == "5/8 build 25m"


# ---------------------------------------------------------------------------
# EDGE-14: Index — fresh activity but phase_status != "running"
# ---------------------------------------------------------------------------


def test_edge14_index_awaiting_input_no_turn_info():
    """EDGE-14: Fresh activity + phase_status='awaiting_input' → duration, no turn info."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(phase="build", phase_status="awaiting_input")
    phases = [
        PhaseRecord(name="build", status="active", started_at=FIXED_START, task_num=1),
    ]
    log_summary = _make_index_log_summary_mock(phases=phases)
    activity = _make_activity(turn=15, max_turns=60, timestamp=FIXED_TIME)

    mock_dt = MagicMock(wraps=datetime)
    mock_dt.now.return_value = FIXED_NOW_1500

    mock_time = MagicMock()
    mock_time.time.return_value = FIXED_TIME

    with (
        patch("buildcrew_dash.screens.index.state_reader.read", return_value=state),
        patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary),
        patch("buildcrew_dash.screens.index.activity_reader.read", return_value=activity),
        patch("buildcrew_dash.screens.index.time", mock_time),
        patch("buildcrew_dash.screens.index.datetime", mock_dt),
        patch("buildcrew_dash.screens.index.stop_control.is_stop_pending", return_value=False),
        patch("buildcrew_dash.screens.index.uat_reader.read_state", return_value=None),
    ):
        cells = screen._compute_cells(inst)

    assert cells[2] == "5/8 build 25m"


# ---------------------------------------------------------------------------
# ADV-04: Index — log_summary.phases is non-iterable int
# ---------------------------------------------------------------------------


def test_adv04_index_phases_is_int():
    """ADV-04: log_summary.phases = 42 → isinstance(42, list) is False, no crash."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(phase="build", phase_status="running")
    log_summary = _make_index_log_summary_mock()
    log_summary.phases = 42
    activity = _make_activity(turn=15, max_turns=60, timestamp=FIXED_TIME)

    mock_time = MagicMock()
    mock_time.time.return_value = FIXED_TIME

    with (
        patch("buildcrew_dash.screens.index.state_reader.read", return_value=state),
        patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary),
        patch("buildcrew_dash.screens.index.activity_reader.read", return_value=activity),
        patch("buildcrew_dash.screens.index.time", mock_time),
        patch("buildcrew_dash.screens.index.stop_control.is_stop_pending", return_value=False),
        patch("buildcrew_dash.screens.index.uat_reader.read_state", return_value=None),
    ):
        cells = screen._compute_cells(inst)

    # Guard skips duration lookup; fresh activity adds turn info
    assert cells[2] == "5/8 build T15/60"
