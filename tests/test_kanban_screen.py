"""Unit and integration tests for KanbanScreen.

Covers HP-01..HP-20, ERR-01..ERR-04, EDGE-01..EDGE-08, ADV-01..ADV-03, SMOKE-01..SMOKE-02,
AC-04..AC-11 (DataTable spec), and activity/stop-control tests.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from buildcrew_dash.log_parser import LogSummary, PhaseRecord
from buildcrew_dash.scanner import BuildCrewInstance, ProcessMonitor, ProcessScanner
from buildcrew_dash.screens.kanban import COLUMNS, PHASE_COL_IDS, KanbanScreen
from buildcrew_dash.state_reader import WorkflowState
from textual.app import App
from textual.widgets import DataTable, Static


# All async tests use Textual's run_test(), which requires asyncio.
# Override anyio_backend at module level to exclude trio.
@pytest.fixture
def anyio_backend():
    return "asyncio"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_instance(project_path: str = "/tmp/bc_kanban_test", log_path: str | None = None) -> BuildCrewInstance:
    pp = Path(project_path)
    lp = (
        Path(log_path)
        if log_path
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
        timestamp=int(time.time()) - 5,
        auto_mode=False,
    )
    defaults.update(kwargs)
    return WorkflowState(**defaults)


def _make_log_summary(
    completed_tasks: list[str] | None = None,
    phases: list[PhaseRecord] | None = None,
    recent_lines: list[str] | None = None,
) -> LogSummary:
    return LogSummary(
        pid=12345,
        project_path=Path("/tmp/bc_kanban_test"),
        start_time=datetime.now(),
        flags={},
        phases=phases if phases is not None else [],
        completed_tasks=completed_tasks if completed_tasks is not None else [],
        last_write_time=datetime.now(),
        recent_lines=recent_lines if recent_lines is not None else [],
    )


def _get_table(pilot) -> DataTable:
    return pilot.app.query_one("#task-table", DataTable)


def _get_cell(table: DataTable, row_key: str, col_key: str) -> str:
    return str(table.get_cell(row_key, col_key))


class _KanbanTestApp(App):
    """Minimal host app that pushes KanbanScreen for testing."""

    def __init__(self, instance: BuildCrewInstance) -> None:
        super().__init__()
        self._instance = instance

    def on_mount(self) -> None:
        self.push_screen(KanbanScreen(self._instance))


# ---------------------------------------------------------------------------
# HP-01..HP-09: Structural / unit tests (no Textual runtime needed)
# ---------------------------------------------------------------------------


def test_hp01_kanban_screen_importable():
    """HP-01: KanbanScreen is importable from buildcrew_dash.screens.kanban."""
    from buildcrew_dash.screens.kanban import KanbanScreen as KS  # noqa: PLC0415
    assert KS is not None


def test_hp02_kanban_screen_is_screen_subclass():
    """HP-02: KanbanScreen is a subclass of textual.screen.Screen."""
    from textual.screen import Screen  # noqa: PLC0415
    assert issubclass(KanbanScreen, Screen)


def test_hp03_bindings_has_all_three_keys():
    """HP-03: BINDINGS contains action keys 'escape', 'left', and 'l'."""
    keys = {b[0] for b in KanbanScreen.BINDINGS}
    assert "escape" in keys
    assert "left" in keys
    assert "l" in keys


def test_hp04_columns_has_ten_entries_in_order():
    """HP-04: COLUMNS has exactly 10 (col_id, label) tuples in spec order."""
    expected = [
        ("col-todo", "todo"),
        ("col-spec", "spec"),
        ("col-research", "research"),
        ("col-review", "review"),
        ("col-build", "build"),
        ("col-codereview", "codereview"),
        ("col-test", "test"),
        ("col-outcome", "outcome"),
        ("col-verify", "verify"),
        ("col-complete", "complete"),
    ]
    assert COLUMNS == expected


def test_hp05_phase_col_ids_correct():
    """HP-05: PHASE_COL_IDS contains the 8 non-terminal phase names."""
    assert PHASE_COL_IDS == frozenset(
        {"spec", "research", "review", "build", "codereview", "test", "outcome", "verify"}
    )


def test_hp06_init_sets_fields():
    """HP-06: __init__ sets instance, _exited=False, and _monitor (ProcessMonitor)."""
    inst = _make_instance()
    screen = KanbanScreen(inst)
    assert screen.instance is inst
    assert screen._exited is False
    assert isinstance(screen._monitor, ProcessMonitor)
    assert isinstance(screen._monitor._scanner, ProcessScanner)


def test_hp07_on_mount_is_async():
    """HP-07: KanbanScreen.on_mount is an async (coroutine) function."""
    assert asyncio.iscoroutinefunction(KanbanScreen.on_mount)


def test_hp08_refresh_data_is_async():
    """HP-08: KanbanScreen.refresh_data is an async (coroutine) function."""
    assert asyncio.iscoroutinefunction(KanbanScreen.refresh_data)


def test_hp09_action_toggle_log_is_sync():
    """HP-09: action_toggle_log is a synchronous (non-async) function."""
    assert not asyncio.iscoroutinefunction(KanbanScreen.action_toggle_log)


# ---------------------------------------------------------------------------
# HP-10..HP-20: Integration tests (Textual runtime)
# ---------------------------------------------------------------------------


@pytest.mark.anyio(backends=["asyncio"])
async def test_hp10_compose_yields_all_required_widgets(tmp_path):
    """HP-10: compose() yields Header, ScrollableContainer#kanban-area, DataTable, Collapsible, Log, Footer."""
    from textual.widgets import Collapsible, Footer, Header, Log  # noqa: PLC0415
    from textual.containers import ScrollableContainer  # noqa: PLC0415

    inst = _make_instance(str(tmp_path))
    log_summary = _make_log_summary()
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=None),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            assert screen.query_one("#kanban-area", ScrollableContainer) is not None
            assert screen.query_one("#log-panel", Collapsible) is not None
            assert screen.query_one("#log-widget", Log) is not None
            assert screen.query_one(Header) is not None
            assert screen.query_one(Footer) is not None
            assert screen.query_one("#task-header", Static) is not None
            assert screen.query_one("#phase-strip", Static) is not None
            assert screen.query_one("#task-table", DataTable) is not None
            # No Vertical containers in the DOM
            assert len(screen.query("Vertical")) == 0


@pytest.mark.anyio(backends=["asyncio"])
async def test_hp11_all_ten_columns_rendered(tmp_path):
    """HP-11: DataTable has exactly 10 columns matching COLUMNS spec order."""
    inst = _make_instance(str(tmp_path))
    log_summary = _make_log_summary()
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=None),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            table = screen.query_one("#task-table", DataTable)
            assert len(table.columns) == 10
            col_ids = [k.value for k in table.columns.keys()]
            assert col_ids == [col_id for col_id, _ in COLUMNS]


@pytest.mark.anyio(backends=["asyncio"])
async def test_hp12_log_panel_collapsed_by_default(tmp_path):
    """HP-12: Collapsible#log-panel starts collapsed=True."""
    from textual.widgets import Collapsible  # noqa: PLC0415

    inst = _make_instance(str(tmp_path))
    log_summary = _make_log_summary()
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=None),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            panel = pilot.app.screen.query_one("#log-panel", Collapsible)
            assert panel.collapsed is True


@pytest.mark.anyio(backends=["asyncio"])
async def test_hp13_active_task_in_correct_phase_column(tmp_path):
    """HP-13: Running task with phase='build' → task-2 cell in col-build shows 'Task 1'."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(task_name="implement auth", phase="build", phase_status="running", task_num=1, total_tasks=1)
    log_summary = _make_log_summary()
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            table = pilot.app.screen.query_one("#task-table", DataTable)
            assert _get_cell(table, "task-1", "col-build") == "Task 1"


@pytest.mark.anyio(backends=["asyncio"])
async def test_hp14_completed_tasks_in_col_complete(tmp_path):
    """HP-14: Completed tasks (task_row_num < task_num) appear in col-complete."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(task_name="current task", task_num=2, total_tasks=2)
    log_summary = _make_log_summary(completed_tasks=["task A", "task B"])
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            table = pilot.app.screen.query_one("#task-table", DataTable)
            # task-1 is completed (row 1 < task_num 2)
            assert _get_cell(table, "task-1", "col-complete") == "Task 1"
            # task-2 is active, not in col-complete
            assert _get_cell(table, "task-2", "col-complete") == ""


@pytest.mark.anyio(backends=["asyncio"])
async def test_hp15_current_task_excluded_from_col_complete(tmp_path):
    """HP-15: Active task (task_row_num == task_num) shows in active phase col, not col-complete."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(task_name="implement auth", task_num=2, total_tasks=2)
    log_summary = _make_log_summary(completed_tasks=["implement auth", "previous task"])
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            table = pilot.app.screen.query_one("#task-table", DataTable)
            assert _get_cell(table, "task-1", "col-complete") == "Task 1"
            assert _get_cell(table, "task-2", "col-complete") == ""
            assert _get_cell(table, "task-2", "col-build") == "Task 2"


@pytest.mark.anyio(backends=["asyncio"])
async def test_hp16_future_placeholder_cards_in_col_todo(tmp_path):
    """HP-16: Tasks task_num+1..total_tasks appear as 'Task N' in col-todo; active task's col-todo is ''."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(task_name="task one", task_num=1, total_tasks=3, phase="build")
    log_summary = _make_log_summary()
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            table = pilot.app.screen.query_one("#task-table", DataTable)
            assert _get_cell(table, "task-2", "col-todo") == "Task 2"
            assert _get_cell(table, "task-3", "col-todo") == "Task 3"
            # Active task (task-1) col-todo is empty
            assert _get_cell(table, "task-1", "col-todo") == ""


@pytest.mark.anyio(backends=["asyncio"])
async def test_hp17_no_state_shows_unknown_in_col_todo(tmp_path):
    """HP-17: When state is None, a single 'row-unknown' row with '(unknown)' in col-todo."""
    inst = _make_instance(str(tmp_path))
    log_summary = _make_log_summary()
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=None),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            table = pilot.app.screen.query_one("#task-table", DataTable)
            assert table.row_count == 1
            assert _get_cell(table, "row-unknown", "col-todo") == "(unknown)"


@pytest.mark.anyio(backends=["asyncio"])
async def test_hp18_replanning_uses_last_non_skipped_phase(tmp_path):
    """HP-18: phase='replanning' → replan cell in col of last non-skipped phase (col-codereview)."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(
        task_name="refactor login",
        phase="replanning",
        phase_status="running",
        task_num=1,
        total_tasks=1,
    )
    phases = [
        PhaseRecord(name="build", status="complete", task_num=1),
        PhaseRecord(name="codereview", status="complete", task_num=1),
        PhaseRecord(name="replanning", status="active", task_num=1),
    ]
    log_summary = _make_log_summary(phases=phases)
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            table = pilot.app.screen.query_one("#task-table", DataTable)
            assert _get_cell(table, "task-1", "col-codereview") == "[yellow]Task 1 replan[/yellow]"


@pytest.mark.anyio(backends=["asyncio"])
async def test_hp19_log_widget_updated_with_recent_lines(tmp_path):
    """HP-19: Log widget is populated with recent_lines; no exception raised."""
    from textual.widgets import Log  # noqa: PLC0415

    inst = _make_instance(str(tmp_path))
    state = _make_state(task_num=1, total_tasks=1)
    log_summary = _make_log_summary(recent_lines=["line one", "line two", "line three"])
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            log_widget = pilot.app.screen.query_one("#log-widget", Log)
            assert log_widget is not None
            assert log_widget.line_count >= 3


@pytest.mark.anyio(backends=["asyncio"])
async def test_hp20_action_toggle_log_toggles_panel(tmp_path):
    """HP-20: action_toggle_log() flips collapsed: True→False→True."""
    from textual.widgets import Collapsible  # noqa: PLC0415

    inst = _make_instance(str(tmp_path))
    log_summary = _make_log_summary()
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=None),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            panel = screen.query_one("#log-panel", Collapsible)
            assert panel.collapsed is True

            screen.action_toggle_log()
            await pilot.pause()
            assert panel.collapsed is False

            screen.action_toggle_log()
            await pilot.pause()
            assert panel.collapsed is True


# ---------------------------------------------------------------------------
# ERR: Error handling
# ---------------------------------------------------------------------------


@pytest.mark.anyio(backends=["asyncio"])
async def test_err01_key_error_from_state_reader_caught(tmp_path):
    """ERR-01: KeyError from state_reader.read is caught; state treated as None → row-unknown."""
    inst = _make_instance(str(tmp_path))
    log_summary = _make_log_summary()
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", side_effect=KeyError("task_num")),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            table = pilot.app.screen.query_one("#task-table", DataTable)
            assert table.row_count == 1
            assert _get_cell(table, "row-unknown", "col-todo") == "(unknown)"


@pytest.mark.anyio(backends=["asyncio"])
async def test_err02_value_error_from_state_reader_caught(tmp_path):
    """ERR-02: ValueError from state_reader.read is caught; state treated as None → row-unknown."""
    inst = _make_instance(str(tmp_path))
    log_summary = _make_log_summary()
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", side_effect=ValueError("bad int value")),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            table = pilot.app.screen.query_one("#task-table", DataTable)
            assert table.row_count == 1
            assert _get_cell(table, "row-unknown", "col-todo") == "(unknown)"


@pytest.mark.anyio(backends=["asyncio"])
async def test_err03_process_exit_mounts_exit_banner(tmp_path):
    """ERR-03: When monitored instance exits (log_path in removed), exit banner is mounted in #kanban-area."""
    inst = _make_instance(str(tmp_path))
    log_summary = _make_log_summary()
    state = _make_state(task_num=1, total_tasks=1)
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            # After first refresh, instance is in _known; now simulate exit (scan returns [])
            with patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[]):
                await screen.refresh_data()
                await pilot.pause()

            assert screen._exited is True
            banner = screen.query_one("#exit-banner", Static)
            assert banner is not None


@pytest.mark.anyio(backends=["asyncio"])
async def test_err04_file_not_found_from_log_parser_notifies(tmp_path):
    """ERR-04: FileNotFoundError from log_parser.parse is caught by refresh_data and calls notify."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(task_num=1, total_tasks=1)
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=_make_log_summary()),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            notified = []
            screen.notify = lambda msg, **_: notified.append(msg)
            # Now trigger a refresh where log_parser raises FileNotFoundError
            with (
                patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
                patch("buildcrew_dash.state_reader.read", return_value=state),
                patch("buildcrew_dash.log_parser.parse", side_effect=FileNotFoundError("log gone")),
            ):
                await screen.refresh_data()
            assert any("log gone" in m for m in notified), (
                f"Expected notify with 'log gone'; got: {notified}"
            )


# ---------------------------------------------------------------------------
# EDGE: Boundary conditions
# ---------------------------------------------------------------------------


@pytest.mark.anyio(backends=["asyncio"])
async def test_edge01_phase_not_in_phase_col_ids_silently_ignored(tmp_path):
    """EDGE-01: Phase not in PHASE_COL_IDS → all PHASE_COL_IDS cells are empty; no crash."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(
        task_name="some task",
        phase="unknown_phase",
        phase_status="running",
        task_num=1,
        total_tasks=1,
    )
    log_summary = _make_log_summary()
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            table = pilot.app.screen.query_one("#task-table", DataTable)
            for phase in PHASE_COL_IDS:
                assert _get_cell(table, "task-1", f"col-{phase}") == "", (
                    f"Unexpected content in col-{phase}"
                )


@pytest.mark.anyio(backends=["asyncio"])
async def test_edge02_exited_true_causes_immediate_return(tmp_path):
    """EDGE-02: _exited=True → refresh_data returns immediately; DataTable rows unchanged."""
    inst = _make_instance(str(tmp_path))
    log_summary = _make_log_summary(completed_tasks=["task A"])
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=None),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            table = screen.query_one("#task-table", DataTable)
            initial_row_count = table.row_count
            screen._exited = True

            await screen.refresh_data()
            await pilot.pause()

            assert table.row_count == initial_row_count


@pytest.mark.anyio(backends=["asyncio"])
async def test_edge03_replanning_all_phases_skipped_falls_back_to_col_build(tmp_path):
    """EDGE-03: Replanning with no non-skipped non-replanning phases → replan cell in col-build (fallback)."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(
        task_name="stuck task",
        phase="replanning",
        phase_status="running",
        task_num=1,
        total_tasks=1,
    )
    phases = [
        PhaseRecord(name="build", status="skipped"),
        PhaseRecord(name="codereview", status="skipped"),
    ]
    log_summary = _make_log_summary(phases=phases)
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            table = pilot.app.screen.query_one("#task-table", DataTable)
            assert _get_cell(table, "task-1", "col-build") == "[yellow]Task 1 replan[/yellow]"


@pytest.mark.anyio(backends=["asyncio"])
async def test_edge04_task_num_equals_total_tasks_no_placeholders(tmp_path):
    """EDGE-04: task_num == total_tasks → no pending tasks; all col-todo cells are empty."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(task_name="last task", task_num=3, total_tasks=3, phase="build")
    log_summary = _make_log_summary()
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            table = pilot.app.screen.query_one("#task-table", DataTable)
            assert _get_cell(table, "task-1", "col-todo") == ""
            assert _get_cell(table, "task-2", "col-todo") == ""
            assert _get_cell(table, "task-3", "col-todo") == ""


@pytest.mark.anyio(backends=["asyncio"])
async def test_edge05_empty_completed_tasks_no_cards_in_col_complete(tmp_path):
    """EDGE-05: Active task has no completed predecessors → col-complete cell is empty."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(task_num=1, total_tasks=1)
    log_summary = _make_log_summary(completed_tasks=[])
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            table = pilot.app.screen.query_one("#task-table", DataTable)
            assert _get_cell(table, "task-1", "col-complete") == ""


@pytest.mark.anyio(backends=["asyncio"])
async def test_edge06_second_refresh_removes_old_cards_first(tmp_path):
    """EDGE-06: Second refresh_data clears DataTable and rebuilds; phase transition moves cell content."""
    inst = _make_instance(str(tmp_path))
    state_build = _make_state(task_name="task one", phase="build", task_num=1, total_tasks=1)
    state_test = _make_state(task_name="task one", phase="test", task_num=1, total_tasks=1)
    log_summary = _make_log_summary()

    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state_build),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            table = screen.query_one("#task-table", DataTable)
            # First refresh: task-1 active in col-build
            assert _get_cell(table, "task-1", "col-build") == "Task 1"
            assert _get_cell(table, "task-1", "col-test") == ""

            # Second refresh with state_test
            with (
                patch("buildcrew_dash.state_reader.read", return_value=state_test),
                patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
            ):
                await screen.refresh_data()
                await pilot.pause()

            assert _get_cell(table, "task-1", "col-build") == ""
            assert _get_cell(table, "task-1", "col-test") == "Task 1"


@pytest.mark.anyio(backends=["asyncio"])
async def test_edge07_phase_status_not_running_no_active_card(tmp_path):
    """EDGE-07: phase_status='complete' → no active-phase cell; all PHASE_COL_IDS cells are empty."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(
        task_name="some task",
        phase="build",
        phase_status="complete",
        task_num=1,
        total_tasks=1,
    )
    log_summary = _make_log_summary()
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            table = pilot.app.screen.query_one("#task-table", DataTable)
            for phase in PHASE_COL_IDS:
                assert _get_cell(table, "task-1", f"col-{phase}") == "", (
                    f"Unexpected content in col-{phase} when phase_status='complete'"
                )


@pytest.mark.anyio(backends=["asyncio"])
async def test_edge08_task_num_zero_total_zero_no_placeholders(tmp_path):
    """EDGE-08: task_num=0, total_tasks=0 → range(1,1) is empty; table has 0 rows."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(task_name="edge task", task_num=0, total_tasks=0, phase="build")
    log_summary = _make_log_summary()
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            table = pilot.app.screen.query_one("#task-table", DataTable)
            assert table.row_count == 0


# ---------------------------------------------------------------------------
# ADV: Adversarial tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio(backends=["asyncio"])
async def test_adv01_empty_log_no_state_no_crash(tmp_path):
    """ADV-01: Empty log (no phases, no completed_tasks, no recent_lines) + state=None → no crash."""
    inst = _make_instance(str(tmp_path))
    log_summary = _make_log_summary(completed_tasks=[], phases=[], recent_lines=[])
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=None),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            table = pilot.app.screen.query_one("#task-table", DataTable)
            assert table.row_count == 1
            assert _get_cell(table, "row-unknown", "col-todo") == "(unknown)"


@pytest.mark.anyio(backends=["asyncio"])
async def test_adv02_large_total_tasks_all_placeholders_in_col_todo(tmp_path):
    """ADV-02: total_tasks=20 → 20 rows; pending tasks 2–20 show 'Task N' in col-todo."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(task_name="task one", task_num=1, total_tasks=20, phase="build")
    log_summary = _make_log_summary()
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            table = pilot.app.screen.query_one("#task-table", DataTable)
            assert table.row_count == 20
            for n in range(2, 21):
                assert _get_cell(table, f"task-{n}", "col-todo") == f"Task {n}", (
                    f"Missing 'Task {n}' in col-todo"
                )
            assert _get_cell(table, "task-1", "col-build") == "Task 1"


@pytest.mark.anyio(backends=["asyncio"])
async def test_adv03_refresh_after_exited_no_double_banner(tmp_path):
    """ADV-03: Calling refresh_data again after _exited=True doesn't mount a second exit banner."""
    inst = _make_instance(str(tmp_path))
    log_summary = _make_log_summary()
    state = _make_state(task_num=1, total_tasks=1)
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            # First: trigger exit
            with patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[]):
                await screen.refresh_data()
                await pilot.pause()
            assert screen._exited is True

            # Second: call again — must return early, no second banner
            await screen.refresh_data()
            await pilot.pause()

            banners = list(screen.query("#exit-banner"))
            assert len(banners) == 1, f"Expected 1 exit banner, found {len(banners)}"


# ---------------------------------------------------------------------------
# SMOKE
# ---------------------------------------------------------------------------


def test_smoke01_kanban_screen_instantiation():
    """SMOKE-01: KanbanScreen can be instantiated with a BuildCrewInstance without error."""
    inst = _make_instance()
    screen = KanbanScreen(inst)
    assert screen is not None
    assert screen.instance is inst
    assert screen._exited is False


@pytest.mark.anyio(backends=["asyncio"])
async def test_smoke02_kanban_screen_mounts_cleanly(tmp_path):
    """SMOKE-02: KanbanScreen mounts with all required widgets; DataTable has 10 columns; no Verticals."""
    from textual.widgets import Collapsible, Footer, Header, Log  # noqa: PLC0415
    from textual.containers import ScrollableContainer  # noqa: PLC0415

    inst = _make_instance(str(tmp_path))
    log_summary = _make_log_summary()
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=None),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            assert isinstance(pilot.app.screen, KanbanScreen)
            screen = pilot.app.screen
            assert screen.query_one(Header) is not None
            assert screen.query_one(Footer) is not None
            assert screen.query_one("#kanban-area", ScrollableContainer) is not None
            assert screen.query_one("#log-panel", Collapsible) is not None
            assert screen.query_one("#log-widget", Log) is not None
            # DataTable is present with 10 columns
            table = screen.query_one("#task-table", DataTable)
            assert table is not None
            assert len(table.columns) == 10
            # No Vertical containers in the DOM
            assert len(screen.query("Vertical")) == 0


@pytest.mark.anyio(backends=["asyncio"])
async def test_discovery_mode_kanban(tmp_path):
    """Discovery mode: kanban area hidden, log panel expanded, no old-style task cards."""
    from textual.widgets import Collapsible  # noqa: PLC0415

    inst = _make_instance(str(tmp_path))
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=_make_state(phase="discovery", task_num=0, total_tasks=0)),
        patch("buildcrew_dash.log_parser.parse", return_value=_make_log_summary()),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            assert screen.query_one("#kanban-area").display is False
            assert screen.query_one("#log-panel", Collapsible).collapsed is False
            # No task-card widgets (DataTable doesn't use them)
            assert len(list(screen.query(".task-card"))) == 0


# ---------------------------------------------------------------------------
# AC-04..AC-11: DataTable acceptance criteria
# ---------------------------------------------------------------------------


@pytest.mark.anyio(backends=["asyncio"])
async def test_ac04_no_vertical_datatable_in_kanban_area(tmp_path):
    """AC-04: No Vertical widgets in DOM; DataTable#task-table is direct child of #kanban-area."""
    inst = _make_instance(str(tmp_path))
    log_summary = _make_log_summary()
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=None),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            assert len(screen.query("Vertical")) == 0
            assert len(screen.query("#task-table")) == 1
            table = screen.query_one("#task-table", DataTable)
            assert table.parent.id == "kanban-area"


@pytest.mark.anyio(backends=["asyncio"])
async def test_ac05_table_columns_spec_order(tmp_path):
    """AC-05: DataTable has 10 columns in spec order with correct labels."""
    inst = _make_instance(str(tmp_path))
    log_summary = _make_log_summary()
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=None),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            table = pilot.app.screen.query_one("#task-table", DataTable)
            assert len(table.columns) == 10
            keys = [k.value for k in table.columns.keys()]
            assert keys == [col_id for col_id, _ in COLUMNS]
            col_keys = list(table.columns.keys())
            assert table.columns[col_keys[4]].label.plain == "build"
            assert table.columns[col_keys[0]].label.plain == "todo"
            assert table.columns[col_keys[9]].label.plain == "complete"


@pytest.mark.anyio(backends=["asyncio"])
async def test_ac06_three_row_scenario(tmp_path):
    """AC-06: task_num=2, total_tasks=3 → 3 rows with correct keys and cell values."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(task_num=2, total_tasks=3, phase="build", phase_status="running")
    log_summary = _make_log_summary(phases=[], completed_tasks=[])
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.screens.kanban.activity_reader.read", return_value=None),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            table = pilot.app.screen.query_one("#task-table", DataTable)
            assert table.row_count == 3
            row_keys = [k.value for k in table.rows.keys()]
            assert "task-1" in row_keys
            assert "task-2" in row_keys
            assert "task-3" in row_keys
            # task-1 is completed
            assert _get_cell(table, "task-1", "col-complete") == "Task 1"
            assert _get_cell(table, "task-1", "col-todo") == ""
            assert _get_cell(table, "task-1", "col-build") == ""
            # task-2 is active
            assert _get_cell(table, "task-2", "col-build") == "Task 2"
            assert _get_cell(table, "task-2", "col-todo") == ""
            assert _get_cell(table, "task-2", "col-complete") == ""
            # task-3 is pending
            assert _get_cell(table, "task-3", "col-todo") == "Task 3"
            assert _get_cell(table, "task-3", "col-build") == ""
            assert _get_cell(table, "task-3", "col-complete") == ""


@pytest.mark.anyio(backends=["asyncio"])
async def test_ac07_phase_status_cell_values(tmp_path):
    """AC-07: phase_status running/awaiting_input/max_turns/permission_denied → correct cell markup."""
    inst = _make_instance(str(tmp_path))
    log_summary = _make_log_summary(phases=[], completed_tasks=[])
    base = dict(task_num=2, total_tasks=2, phase="build")

    for phase_status, expected in [
        ("running", "Task 2"),
        ("awaiting_input", "[yellow]Task 2 ⏸[/yellow]"),
        ("max_turns", "[red]Task 2 ⚠[/red]"),
        ("permission_denied", "[red]Task 2 ⚠[/red]"),
    ]:
        state = _make_state(**base, phase_status=phase_status)
        with (
            patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
            patch("buildcrew_dash.state_reader.read", return_value=state),
            patch("buildcrew_dash.screens.kanban.activity_reader.read", return_value=None),
            patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
        ):
            async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
                await pilot.pause()
                table = pilot.app.screen.query_one("#task-table", DataTable)
                actual = _get_cell(table, "task-2", "col-build")
                assert actual == expected, (
                    f"phase_status={phase_status!r}: expected {expected!r}, got {actual!r}"
                )


@pytest.mark.anyio(backends=["asyncio"])
async def test_ac08_completed_skipped_active_phase_cells(tmp_path):
    """AC-08: Complete/skipped/active phases render correct markup in DataTable cells."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(task_num=1, total_tasks=1, phase="test", phase_status="running")
    log_summary = _make_log_summary(phases=[
        PhaseRecord(name="build", status="complete", verdict="looks good", task_num=1),
        PhaseRecord(name="spec", status="skipped", task_num=1),
    ], completed_tasks=[])
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.screens.kanban.activity_reader.read", return_value=None),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            table = pilot.app.screen.query_one("#task-table", DataTable)
            assert _get_cell(table, "task-1", "col-build") == "[green]✓ looks good[/green]"
            assert _get_cell(table, "task-1", "col-spec") == "[dim]- skipped[/dim]"
            assert _get_cell(table, "task-1", "col-test") == "Task 1"
            assert _get_cell(table, "task-1", "col-todo") == ""
            assert _get_cell(table, "task-1", "col-complete") == ""


@pytest.mark.anyio(backends=["asyncio"])
async def test_ac10_unknown_row_when_state_none(tmp_path):
    """AC-10: state=None → single 'row-unknown' row; col-todo='(unknown)', all others ''."""
    inst = _make_instance(str(tmp_path))
    log_summary = _make_log_summary(phases=[], completed_tasks=[])
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=None),
        patch("buildcrew_dash.screens.kanban.activity_reader.read", return_value=None),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            table = pilot.app.screen.query_one("#task-table", DataTable)
            assert table.row_count == 1
            row_keys = [k.value for k in table.rows.keys()]
            assert row_keys[0] == "row-unknown"
            assert _get_cell(table, "row-unknown", "col-todo") == "(unknown)"
            for col_id, _ in COLUMNS:
                if col_id != "col-todo":
                    assert _get_cell(table, "row-unknown", col_id) == "", (
                        f"Expected '' in {col_id} for row-unknown, got {_get_cell(table, 'row-unknown', col_id)!r}"
                    )


def test_ac11_css_has_task_table_no_task_card():
    """AC-11: CSS has #task-table + height: 1fr; does NOT contain .task-card/.phase-card/.status-."""
    css = KanbanScreen.CSS
    assert ".task-card" not in css
    assert ".phase-card" not in css
    assert ".status-" not in css
    assert "#task-table" in css
    assert "height: 1fr" in css


# ---------------------------------------------------------------------------
# Phase strip tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio(backends=["asyncio"])
async def test_awaiting_input_card(tmp_path):
    """Awaiting input phase_status → yellow markup cell in col-build."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(phase="build", phase_status="awaiting_input", task_num=1, total_tasks=1)
    log_summary = _make_log_summary()
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            table = pilot.app.screen.query_one("#task-table", DataTable)
            assert _get_cell(table, "task-1", "col-build") == "[yellow]Task 1 ⏸[/yellow]"


@pytest.mark.anyio(backends=["asyncio"])
async def test_permission_denied_card(tmp_path):
    """Permission denied phase_status → red markup cell in col-build."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(phase="build", phase_status="permission_denied", task_num=1, total_tasks=1)
    log_summary = _make_log_summary()
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            table = pilot.app.screen.query_one("#task-table", DataTable)
            assert _get_cell(table, "task-1", "col-build") == "[red]Task 1 ⚠[/red]"


@pytest.mark.anyio(backends=["asyncio"])
async def test_max_turns_card(tmp_path):
    """Max turns phase_status → red markup cell in col-build."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(phase="build", phase_status="max_turns", task_num=1, total_tasks=1)
    log_summary = _make_log_summary()
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            table = pilot.app.screen.query_one("#task-table", DataTable)
            assert _get_cell(table, "task-1", "col-build") == "[red]Task 1 ⚠[/red]"


@pytest.mark.anyio(backends=["asyncio"])
async def test_phase_strip_content(tmp_path):
    """Phase strip shows ✓ for complete, ● for active, ○ for pending; 7 separators."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(phase="build", phase_status="running")
    log_summary = _make_log_summary(phases=[
        PhaseRecord(name="spec", status="complete", task_num=1),
        PhaseRecord(name="build", status="active", task_num=1),
    ])
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            strip = screen.query_one("#phase-strip", Static)
            text = str(strip.content)
            assert text.index("✓ spec") < text.index("● build")
            assert text.index("● build") < text.index("○ test")
            assert text.count(" → ") == 7


@pytest.mark.anyio(backends=["asyncio"])
async def test_phase_strip_awaiting_input_symbol(tmp_path):
    """Phase strip shows ⏸ for awaiting_input phase, not ●."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(phase="build", phase_status="awaiting_input")
    log_summary = _make_log_summary(phases=[
        PhaseRecord(name="spec", status="complete", task_num=1),
        PhaseRecord(name="build", status="active", task_num=1),
    ])
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            strip = screen.query_one("#phase-strip", Static)
            text = str(strip.content)
            assert "⏸" in text
            assert "● build" not in text


@pytest.mark.anyio(backends=["asyncio"])
async def test_phase_strip_failed_symbol(tmp_path):
    """Phase strip shows ✗ for a failed phase."""
    inst = _make_instance(str(tmp_path))
    log_summary = _make_log_summary(phases=[
        PhaseRecord(name="spec", status="failed"),
    ])
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=None),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            strip = screen.query_one("#phase-strip", Static)
            text = str(strip.content)
            assert "✗ spec" in text


@pytest.mark.anyio(backends=["asyncio"])
async def test_verdict_card_deduplication(tmp_path):
    """Calling refresh_data twice with same complete phase: cell shows correct verdict both times."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(phase="build", phase_status="complete", task_num=1, total_tasks=1)
    log_summary = _make_log_summary(phases=[
        PhaseRecord(name="build", status="complete", verdict="approved", task_num=1),
    ])
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            table = screen.query_one("#task-table", DataTable)
            assert _get_cell(table, "task-1", "col-build") == "[green]✓ approved[/green]"
            # Second refresh must not duplicate or corrupt
            await screen.refresh_data()
            await pilot.pause()
            assert _get_cell(table, "task-1", "col-build") == "[green]✓ approved[/green]"


@pytest.mark.anyio(backends=["asyncio"])
async def test_auto_badge_shows_when_auto_mode_true(tmp_path):
    """#auto-badge shows cyan AUTO when auto_mode=True."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(auto_mode=True)
    log_summary = _make_log_summary()
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            await screen.refresh_data()
            badge = screen.query_one("#auto-badge", Static)
            assert str(badge.content) == "[bold cyan]AUTO[/bold cyan]"


@pytest.mark.anyio(backends=["asyncio"])
async def test_auto_badge_hidden_when_auto_mode_false(tmp_path):
    """#auto-badge is empty when auto_mode=False."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(auto_mode=False)
    log_summary = _make_log_summary()
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            await screen.refresh_data()
            badge = screen.query_one("#auto-badge", Static)
            assert str(badge.content) == ""


# ---------------------------------------------------------------------------
# AC-09, AC-10, AC-11: Subagent activity display
# ---------------------------------------------------------------------------


def _make_activity(**kwargs):
    from buildcrew_dash.activity_reader import AgentActivity  # noqa: PLC0415
    defaults = dict(
        tool="Read",
        tool_input="src/foo.py",
        turn=5,
        max_turns=50,
        status="tool_use",
        timestamp=int(time.time()),
    )
    defaults.update(kwargs)
    return AgentActivity(**defaults)


@pytest.mark.anyio(backends=["asyncio"])
async def test_ac09_running_label_with_fresh_activity(tmp_path):
    """AC-09: Fresh activity → turn info in #task-header, NOT in DataTable cell."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(task_num=1, total_tasks=1, phase="build", phase_status="running")
    log_summary = _make_log_summary()
    activity = _make_activity(tool="Read", tool_input="src/foo.py", turn=5, max_turns=50)
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.screens.kanban.activity_reader.read", return_value=activity),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            await screen.refresh_data()
            header = screen.query_one("#task-header", Static)
            header_text = str(header.content)
            assert "Turn 5/50" in header_text, f"Expected 'Turn 5/50' in header: {header_text!r}"
            assert "Read: src/foo.py" in header_text, f"Expected 'Read: src/foo.py' in header: {header_text!r}"
            # Cell must NOT contain turn info
            table = screen.query_one("#task-table", DataTable)
            assert _get_cell(table, "task-1", "col-build") == "Task 1"


@pytest.mark.anyio(backends=["asyncio"])
async def test_ac10_running_label_with_no_activity(tmp_path):
    """AC-10: activity=None → no turn info in header; active cell is plain 'Task N'."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(task_num=1, total_tasks=1, phase="build", phase_status="running")
    log_summary = _make_log_summary()
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.screens.kanban.activity_reader.read", return_value=None),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            await screen.refresh_data()
            header = screen.query_one("#task-header", Static)
            assert "Turn" not in str(header.content)
            table = screen.query_one("#task-table", DataTable)
            assert _get_cell(table, "task-1", "col-build") == "Task 1"


@pytest.mark.anyio(backends=["asyncio"])
async def test_ac11_stale_activity_ignored(tmp_path):
    """AC-11: Stale activity (timestamp 60s ago) → no turn info in header; cell is plain 'Task N'."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(task_num=1, total_tasks=1, phase="build", phase_status="running")
    log_summary = _make_log_summary()
    stale_activity = _make_activity(timestamp=int(time.time()) - 60)
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.screens.kanban.activity_reader.read", return_value=stale_activity),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            await screen.refresh_data()
            header = screen.query_one("#task-header", Static)
            assert "Turn" not in str(header.content), (
                f"Unexpected 'Turn' in header with stale activity: {str(header.content)!r}"
            )
            table = screen.query_one("#task-table", DataTable)
            assert _get_cell(table, "task-1", "col-build") == "Task 1"


# ---------------------------------------------------------------------------
# Stop/Cancel tests
# ---------------------------------------------------------------------------


def test_stop01_s_binding_in_bindings():
    """AC-01: s key is in BINDINGS with label Stop/Cancel."""
    binding = next((b for b in KanbanScreen.BINDINGS if b[0] == "s"), None)
    assert binding is not None
    assert binding[1] == "toggle_stop"
    assert binding[2] == "Stop/Cancel"


def test_stop02_action_toggle_stop_is_sync():
    """AC-04: action_toggle_stop is synchronous."""
    assert not asyncio.iscoroutinefunction(KanbanScreen.action_toggle_stop)


@pytest.mark.anyio(backends=["asyncio"])
async def test_stop03_header_shows_stopping_when_pending(tmp_path):
    """AC-03: header is prefixed with Stopping... when stop is pending."""
    inst = _make_instance(str(tmp_path))
    state = _make_state()
    log_summary = _make_log_summary()
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
        patch("buildcrew_dash.activity_reader.read", return_value=None),
        patch("buildcrew_dash.stop_control.is_stop_pending", return_value=True),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            header = pilot.app.screen.query_one("#task-header", Static)
            assert "[yellow]Stopping...[/yellow]" in str(header.content)


@pytest.mark.anyio(backends=["asyncio"])
async def test_stop04_action_toggle_stop_requests_stop(tmp_path):
    """AC-06: action_toggle_stop calls request_stop when no stop is pending."""
    inst = _make_instance(str(tmp_path))
    log_summary = _make_log_summary()
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=None),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
        patch("buildcrew_dash.activity_reader.read", return_value=None),
        patch("buildcrew_dash.stop_control.is_stop_pending", return_value=False),
        patch("buildcrew_dash.stop_control.request_stop") as mock_req,
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            screen.action_toggle_stop()
            mock_req.assert_called_once_with(inst.project_path)


def test_stop05_action_toggle_stop_noop_when_exited(tmp_path):
    """AC-05: action_toggle_stop is a no-op when _exited is True."""
    inst = _make_instance(str(tmp_path))
    screen = KanbanScreen(inst)
    screen._exited = True
    with (
        patch("buildcrew_dash.stop_control.is_stop_pending") as mock_pending,
        patch("buildcrew_dash.stop_control.request_stop") as mock_req,
    ):
        screen.action_toggle_stop()
        mock_pending.assert_not_called()
        mock_req.assert_not_called()


def test_stop06_action_toggle_stop_cancels_stop(tmp_path):
    """AC-07: action_toggle_stop calls cancel_stop and notifies when stop is pending."""
    inst = _make_instance(str(tmp_path))
    screen = KanbanScreen(inst)
    screen._exited = False
    with (
        patch("buildcrew_dash.stop_control.is_stop_pending", return_value=True),
        patch("buildcrew_dash.stop_control.cancel_stop") as mock_cancel,
        patch.object(screen, "notify") as mock_notify,
    ):
        screen.action_toggle_stop()
        mock_cancel.assert_called_once_with(inst.project_path)
        mock_notify.assert_called_once_with("Stop cancelled")


def test_stop07_action_toggle_stop_notifies_on_oserror(tmp_path):
    """AC-08: action_toggle_stop notifies on OSError and does not re-raise."""
    inst = _make_instance(str(tmp_path))
    screen = KanbanScreen(inst)
    screen._exited = False
    with (
        patch("buildcrew_dash.stop_control.is_stop_pending", return_value=False),
        patch("buildcrew_dash.stop_control.request_stop", side_effect=OSError("disk full")),
        patch.object(screen, "notify") as mock_notify,
    ):
        screen.action_toggle_stop()  # must not raise
        mock_notify.assert_called_once_with("Stop failed: disk full")


# ---------------------------------------------------------------------------
# Batch mode tests
# ---------------------------------------------------------------------------


def _make_batch_manifest(**kwargs):
    """Create a mock BatchManifest for testing."""
    from buildcrew_dash.manifest_reader import BatchManifest, BatchTask  # noqa: PLC0415
    defaults = dict(
        batch_id="20240101-120000",
        base_branch="main",
        base_commit="abc123",
        max_parallel=5,
        started_at="2024-01-01T12:00:00",
        tasks=[
            BatchTask(index=1, text="Task one", slug="task-one",
                      branch="buildcrew/task-one", worktree=".buildcrew/batch/worktrees/task-one",
                      status="running", started_at="2024-01-01T12:00:01"),
            BatchTask(index=2, text="Task two", slug="task-two",
                      branch="buildcrew/task-two", worktree=".buildcrew/batch/worktrees/task-two",
                      status="completed", exit_code=0,
                      started_at="2024-01-01T12:00:02", completed_at="2024-01-01T12:05:30"),
            BatchTask(index=3, text="Task three", slug="task-three",
                      branch="buildcrew/task-three", worktree=".buildcrew/batch/worktrees/task-three",
                      status="pending"),
        ],
    )
    defaults.update(kwargs)
    return BatchManifest(**defaults)


_SENTINEL = object()


def _batch_patches(inst, manifest=_SENTINEL, wt_phase="build"):
    """Context manager with all patches needed for batch mode tests."""
    if manifest is _SENTINEL:
        manifest = _make_batch_manifest()

    def mock_state_read(path):
        path_str = str(path)
        if "worktrees" in path_str:
            return _make_state(phase=wt_phase, task_num=1, total_tasks=1)
        return _make_state(phase="batch", task_num=0, total_tasks=5)

    from contextlib import ExitStack  # noqa: PLC0415
    stack = ExitStack()
    stack.enter_context(patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]))
    stack.enter_context(patch("buildcrew_dash.state_reader.read", side_effect=mock_state_read))
    stack.enter_context(patch("buildcrew_dash.log_parser.parse", return_value=_make_log_summary()))
    stack.enter_context(patch("buildcrew_dash.activity_reader.read", return_value=None))
    stack.enter_context(patch("buildcrew_dash.stop_control.is_stop_pending", return_value=False))
    stack.enter_context(patch("buildcrew_dash.manifest_reader.read", return_value=manifest))
    return stack


@pytest.mark.anyio(backends=["asyncio"])
async def test_batch_mode_kanban_area_hidden(tmp_path):
    """Batch mode: kanban area is hidden, batch area is visible."""
    inst = _make_instance(str(tmp_path))
    with _batch_patches(inst):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            assert screen.query_one("#kanban-area").display is False
            assert screen.query_one("#batch-area").display is True


@pytest.mark.anyio(backends=["asyncio"])
async def test_batch_mode_log_panel_collapsed(tmp_path):
    """Batch mode: log panel stays collapsed (batch table is primary view)."""
    from textual.widgets import Collapsible  # noqa: PLC0415

    inst = _make_instance(str(tmp_path))
    with _batch_patches(inst):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            assert screen.query_one("#log-panel", Collapsible).collapsed is True


@pytest.mark.anyio(backends=["asyncio"])
async def test_batch_mode_header_text(tmp_path):
    """Batch mode: task header shows manifest-aware counts."""
    inst = _make_instance(str(tmp_path))
    with _batch_patches(inst):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            header = screen.query_one("#task-header", Static)
            header_str = str(header.content)
            assert "Batch (3)" in header_str
            assert "1 running" in header_str
            assert "1 done" in header_str
            assert "1 pending" in header_str


@pytest.mark.anyio(backends=["asyncio"])
async def test_batch_mode_batch_table_shows_tasks(tmp_path):
    """Batch mode: batch table has one row per manifest task."""
    inst = _make_instance(str(tmp_path))
    with _batch_patches(inst):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            batch_table = screen.query_one("#batch-table", DataTable)
            assert batch_table.row_count == 3


@pytest.mark.anyio(backends=["asyncio"])
async def test_batch_mode_running_task_shows_phase(tmp_path):
    """Batch mode: running task shows its current phase from worktree state."""
    inst = _make_instance(str(tmp_path))
    with _batch_patches(inst, wt_phase="test"):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            batch_table = screen.query_one("#batch-table", DataTable)
            phase_cell = str(batch_table.get_cell("batch-1", "batch-phase"))
            assert phase_cell == "test"


@pytest.mark.anyio(backends=["asyncio"])
async def test_batch_mode_batch_area_hidden_in_normal_mode(tmp_path):
    """Normal mode: batch area is hidden."""
    inst = _make_instance(str(tmp_path))
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=_make_state(phase="build", task_num=1, total_tasks=1)),
        patch("buildcrew_dash.log_parser.parse", return_value=_make_log_summary()),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            assert screen.query_one("#batch-area").display is False
            assert screen.query_one("#kanban-area").display is True


@pytest.mark.anyio(backends=["asyncio"])
async def test_batch_mode_no_manifest_fallback(tmp_path):
    """Batch mode without manifest: falls back to simple header."""
    inst = _make_instance(str(tmp_path))
    with _batch_patches(inst, manifest=None):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            header = screen.query_one("#task-header", Static)
            assert "Batch: 5 tasks (parallel)" in str(header.content)
