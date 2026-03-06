"""TDD tests for kanban phase strip durations and turn info (AC-02..AC-08, AC-15).

Phase strip integration tests: run KanbanScreen via Textual run_test(), extract
the #phase-strip Static text, split on " → ", find the segment for the phase
under test, and assert the exact segment value.

Mock targets:
- buildcrew_dash.screens.kanban.datetime  (for datetime.now in live elapsed)
- buildcrew_dash.screens.kanban.time      (for time.time in turn-info staleness)
- buildcrew_dash.screens.kanban.activity_reader.read (for AgentActivity)
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from buildcrew_dash.activity_reader import AgentActivity
from buildcrew_dash.log_parser import LogSummary, PhaseRecord
from buildcrew_dash.scanner import BuildCrewInstance, ProcessMonitor, ProcessScanner
from buildcrew_dash.screens.kanban import KanbanScreen
from buildcrew_dash.state_reader import WorkflowState
from textual.app import App
from textual.widgets import Static


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ---------------------------------------------------------------------------
# Fixed time constants
# ---------------------------------------------------------------------------

FIXED_TIME = 1704110520  # arbitrary epoch seconds
FIXED_NOW = datetime(2024, 1, 1, 12, 12, 0)  # 720s after FIXED_START
FIXED_START = datetime(2024, 1, 1, 12, 0, 0)
FIXED_END_120S = datetime(2024, 1, 1, 12, 2, 0)  # 120s after FIXED_START
FIXED_END_90S = datetime(2024, 1, 1, 12, 1, 30)  # 90s after FIXED_START


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_instance(project_path: str = "/tmp/bc_tdd_kanban", log_path: str | None = None) -> BuildCrewInstance:
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


def _make_log_summary(phases: list[PhaseRecord] | None = None) -> LogSummary:
    return LogSummary(
        pid=12345,
        project_path=Path("/tmp/bc_tdd_kanban"),
        start_time=datetime.now(),
        flags={},
        phases=phases if phases is not None else [],
        completed_tasks=[],
        last_write_time=datetime.now(),
        recent_lines=[],
    )


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


class _TddKanbanApp(App):
    """Minimal host app that pushes KanbanScreen for testing."""

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
# AC-02: Completed phase with both timestamps → shows duration
# ---------------------------------------------------------------------------


@pytest.mark.anyio(backends=["asyncio"])
async def test_AC02_completed_phase_with_timestamps_shows_duration(tmp_path):
    """AC-02/AC-15a: Completed phase with started_at/ended_at 120s apart → '✓ build 2m'."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(phase="simplify", phase_status="running")
    phases = [
        PhaseRecord(name="build", status="complete", started_at=FIXED_START, ended_at=FIXED_END_120S, task_num=1),
        PhaseRecord(name="simplify", status="active", task_num=1),
    ]
    log_summary = _make_log_summary(phases=phases)

    mock_dt = MagicMock(wraps=datetime)
    mock_dt.now.return_value = FIXED_NOW

    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
        patch("buildcrew_dash.screens.kanban.activity_reader.read", return_value=None),
        patch("buildcrew_dash.screens.kanban.datetime", mock_dt),
        patch("buildcrew_dash.screens.kanban.time.time", return_value=FIXED_TIME),
    ):
        async with _TddKanbanApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            seg = _get_strip_segment(pilot, "build")
            assert seg == "✓ 5/8 build 2m"


# ---------------------------------------------------------------------------
# AC-02: Failed phase with both timestamps → shows duration
# ---------------------------------------------------------------------------


@pytest.mark.anyio(backends=["asyncio"])
async def test_AC02_failed_phase_with_timestamps_shows_duration(tmp_path):
    """AC-02/AC-15b: Failed phase with timestamps 90s apart → '✗ build 1m'."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(phase="simplify", phase_status="running")
    phases = [
        PhaseRecord(name="build", status="failed", started_at=FIXED_START, ended_at=FIXED_END_90S, task_num=1),
        PhaseRecord(name="simplify", status="active", task_num=1),
    ]
    log_summary = _make_log_summary(phases=phases)

    mock_dt = MagicMock(wraps=datetime)
    mock_dt.now.return_value = FIXED_NOW

    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
        patch("buildcrew_dash.screens.kanban.activity_reader.read", return_value=None),
        patch("buildcrew_dash.screens.kanban.datetime", mock_dt),
        patch("buildcrew_dash.screens.kanban.time.time", return_value=FIXED_TIME),
    ):
        async with _TddKanbanApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            seg = _get_strip_segment(pilot, "build")
            assert seg == "✗ 5/8 build 1m"


# ---------------------------------------------------------------------------
# AC-03: Active phase with PhaseRecord and started_at → shows live duration
# ---------------------------------------------------------------------------


@pytest.mark.anyio(backends=["asyncio"])
async def test_AC03_active_phase_with_record_shows_live_duration(tmp_path):
    """AC-03/AC-15c: Active phase with started_at 720s ago, no activity → '● build 12m'."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(phase="build", phase_status="running")
    phases = [
        PhaseRecord(name="build", status="active", started_at=FIXED_START, task_num=1),
    ]
    log_summary = _make_log_summary(phases=phases)

    mock_dt = MagicMock(wraps=datetime)
    mock_dt.now.return_value = FIXED_NOW

    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
        patch("buildcrew_dash.screens.kanban.activity_reader.read", return_value=None),
        patch("buildcrew_dash.screens.kanban.datetime", mock_dt),
        patch("buildcrew_dash.screens.kanban.time.time", return_value=FIXED_TIME),
    ):
        async with _TddKanbanApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            seg = _get_strip_segment(pilot, "build")
            assert seg == "● 5/8 build 12m"


# ---------------------------------------------------------------------------
# AC-04: Active phase without PhaseRecord → no duration
# ---------------------------------------------------------------------------


@pytest.mark.anyio(backends=["asyncio"])
async def test_AC04_active_phase_without_record_no_duration(tmp_path):
    """AC-04/AC-15d: Active phase without PhaseRecord (rec=None), no activity → '● build'."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(phase="build", phase_status="running")
    # No PhaseRecord for build — it'll be rec=None in the loop
    log_summary = _make_log_summary(phases=[])

    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
        patch("buildcrew_dash.screens.kanban.activity_reader.read", return_value=None),
        patch("buildcrew_dash.screens.kanban.time.time", return_value=FIXED_TIME),
    ):
        async with _TddKanbanApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            seg = _get_strip_segment(pilot, "build")
            assert seg == "● 5/8 build"


# ---------------------------------------------------------------------------
# AC-05: Active phase with fresh activity → shows turn info
# ---------------------------------------------------------------------------


@pytest.mark.anyio(backends=["asyncio"])
async def test_AC05_active_phase_with_fresh_activity_shows_turn(tmp_path):
    """AC-05/AC-15e: Active phase with fresh activity and started_at 720s ago → '● build 12m T15/60'."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(phase="build", phase_status="running")
    phases = [
        PhaseRecord(name="build", status="active", started_at=FIXED_START, task_num=1),
    ]
    log_summary = _make_log_summary(phases=phases)
    activity = _make_activity(turn=15, max_turns=60, timestamp=FIXED_TIME)

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
        async with _TddKanbanApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            seg = _get_strip_segment(pilot, "build")
            assert seg == "● 5/8 build 12m T15/60"


# ---------------------------------------------------------------------------
# AC-06: Active phase with stale activity → no turn info
# ---------------------------------------------------------------------------


@pytest.mark.anyio(backends=["asyncio"])
async def test_AC06_active_phase_with_stale_activity_no_turn(tmp_path):
    """AC-06/AC-15f: Active phase with stale activity (>30s) and started_at 720s ago → '● build 12m'."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(phase="build", phase_status="running")
    phases = [
        PhaseRecord(name="build", status="active", started_at=FIXED_START, task_num=1),
    ]
    log_summary = _make_log_summary(phases=phases)
    stale_activity = _make_activity(turn=15, max_turns=60, timestamp=FIXED_TIME - 60)

    mock_dt = MagicMock(wraps=datetime)
    mock_dt.now.return_value = FIXED_NOW

    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
        patch("buildcrew_dash.screens.kanban.activity_reader.read", return_value=stale_activity),
        patch("buildcrew_dash.screens.kanban.datetime", mock_dt),
        patch("buildcrew_dash.screens.kanban.time.time", return_value=FIXED_TIME),
    ):
        async with _TddKanbanApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            seg = _get_strip_segment(pilot, "build")
            assert seg == "● 5/8 build 12m"


# ---------------------------------------------------------------------------
# AC-07: Skipped phase → no duration, no turn info
# ---------------------------------------------------------------------------


@pytest.mark.anyio(backends=["asyncio"])
async def test_AC07_skipped_phase_no_duration(tmp_path):
    """AC-07/AC-15g: Skipped phase → '- build'."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(phase="simplify", phase_status="running")
    phases = [
        PhaseRecord(name="build", status="skipped", task_num=1),
        PhaseRecord(name="simplify", status="active", task_num=1),
    ]
    log_summary = _make_log_summary(phases=phases)

    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
        patch("buildcrew_dash.screens.kanban.activity_reader.read", return_value=None),
        patch("buildcrew_dash.screens.kanban.time.time", return_value=FIXED_TIME),
    ):
        async with _TddKanbanApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            seg = _get_strip_segment(pilot, "build")
            assert seg == "- 5/8 build"


# ---------------------------------------------------------------------------
# AC-07: Future phase (no record, not state.phase) → no duration
# ---------------------------------------------------------------------------


@pytest.mark.anyio(backends=["asyncio"])
async def test_AC07_future_phase_no_duration(tmp_path):
    """AC-07/AC-15h: Future/unknown phase with no record and not matching state.phase → '○ codereview'."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(phase="build", phase_status="running")
    phases = [
        PhaseRecord(name="build", status="active", started_at=FIXED_START, task_num=1),
    ]
    log_summary = _make_log_summary(phases=phases)

    mock_dt = MagicMock(wraps=datetime)
    mock_dt.now.return_value = FIXED_NOW

    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
        patch("buildcrew_dash.screens.kanban.activity_reader.read", return_value=None),
        patch("buildcrew_dash.screens.kanban.datetime", mock_dt),
        patch("buildcrew_dash.screens.kanban.time.time", return_value=FIXED_TIME),
    ):
        async with _TddKanbanApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            seg = _get_strip_segment(pilot, "codereview")
            assert seg == "○ 7/8 codereview"
