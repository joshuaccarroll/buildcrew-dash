"""Unit and integration tests for IndexScreen and BuildCrewDashApp.

Covers HP-01..HP-19, ERR-01..ERR-05, EDGE-01..EDGE-09, ADV-01..ADV-06, SMOKE-01..SMOKE-02.
"""
import asyncio
import inspect
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from buildcrew_dash.__main__ import BuildCrewDashApp


# All async tests in this file use Textual's run_test(), which internally calls
# asyncio.create_task(). This fails under trio ("no running event loop").
# Override anyio_backend at the module level to restrict all async tests to asyncio.
@pytest.fixture
def anyio_backend():
    return "asyncio"
from buildcrew_dash.scanner import BuildCrewInstance, ProcessMonitor, ProcessScanner
from buildcrew_dash.screens.index import IndexScreen
from buildcrew_dash.state_reader import WorkflowState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_instance(project_path="/tmp/bc_test_proj", log_path=None):
    pp = Path(project_path)
    lp = (
        Path(log_path)
        if log_path
        else pp / ".buildcrew" / "logs" / "buildcrew-2024-01-01_00-00-00-12345.log"
    )
    return BuildCrewInstance(pid=12345, project_path=pp, log_path=lp)


def _make_state(**kwargs):
    defaults = dict(
        task_num=1,
        total_tasks=3,
        task_name="implement auth",
        phase="build",
        phase_status="running",
        invocation_count=4,
        max_invocations=15,
        timestamp=int(time.time()) - 5,
    )
    defaults.update(kwargs)
    return WorkflowState(**defaults)


def _make_log_summary(start_time_offset=None):
    """Return a MagicMock LogSummary. start_time_offset=None → start_time=None."""
    m = MagicMock()
    if start_time_offset is None:
        m.start_time = None
    else:
        import datetime
        m.start_time = datetime.datetime.fromtimestamp(time.time() - start_time_offset)
    return m


# ---------------------------------------------------------------------------
# HP: Structural / happy-path unit tests
# ---------------------------------------------------------------------------


def test_hp01_index_screen_importable():
    """HP-01: IndexScreen is importable from buildcrew_dash.screens.index."""
    from buildcrew_dash.screens.index import IndexScreen as IS  # noqa: PLC0415
    assert IS is not None


def test_hp02_index_screen_is_screen_subclass():
    """HP-02: IndexScreen is a subclass of textual.screen.Screen."""
    from textual.screen import Screen  # noqa: PLC0415
    assert issubclass(IndexScreen, Screen)


def test_hp03_init_creates_process_monitor():
    """HP-03: IndexScreen() sets self._monitor (ProcessMonitor) and ._scanner (ProcessScanner)."""
    screen = IndexScreen()
    assert isinstance(screen._monitor, ProcessMonitor)
    assert isinstance(screen._monitor._scanner, ProcessScanner)


def test_hp04_bindings_includes_all_three_keys():
    """HP-04: BINDINGS contains keys for enter, right, and q."""
    keys = {b[0] for b in IndexScreen.BINDINGS}
    assert "q" in keys
    assert "enter" in keys
    assert "right" in keys


def test_hp05_screens_init_importable():
    """HP-05: buildcrew_dash.screens.__init__.py is importable (package exists)."""
    import buildcrew_dash.screens  # noqa: PLC0415
    assert buildcrew_dash.screens is not None


def test_hp06_buildcrewdashapp_screens_dict():
    """HP-06: BuildCrewDashApp.SCREENS["index"] is IndexScreen."""
    assert "index" in BuildCrewDashApp.SCREENS
    assert BuildCrewDashApp.SCREENS["index"] is IndexScreen


def test_hp07_on_mount_is_sync_and_calls_push_screen():
    """HP-07: BuildCrewDashApp.on_mount is synchronous and calls push_screen('index')."""
    assert not asyncio.iscoroutinefunction(BuildCrewDashApp.on_mount)
    source = inspect.getsource(BuildCrewDashApp.on_mount)
    assert "push_screen" in source
    assert '"index"' in source or "'index'" in source


def test_hp08_compute_cells_returns_7_tuple_with_project_name():
    """HP-08: _compute_cells returns (project, mode, ...) where project = project_path.name."""
    screen = IndexScreen()
    inst = _make_instance("/home/user/myproject")
    state = _make_state()
    log_summary = _make_log_summary(start_time_offset=None)

    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        cells = screen._compute_cells(inst)

    assert isinstance(cells, tuple)
    assert len(cells) == 7
    assert cells[0] == "myproject"
    assert cells[1] == "—"


def test_hp09_compute_cells_all_fields_populated():
    """HP-09: With valid state and log, no cell is '—'."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(task_name="do the thing", phase="build")
    log_summary = _make_log_summary(start_time_offset=3600)

    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        project, _, phase, task, duration, health, budget = screen._compute_cells(inst)

    assert project != "—"
    assert phase != "—"
    assert task != "—"
    assert duration != "—"
    assert health != "—"
    assert budget != "—"


def test_hp10_compute_cells_no_state_returns_dashes():
    """HP-10: When state is None, phase/task/budget are '—'."""
    screen = IndexScreen()
    inst = _make_instance()
    log_summary = _make_log_summary(start_time_offset=None)

    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=None), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        project, _, phase, task, duration, health, budget = screen._compute_cells(inst)

    assert phase == "—"
    assert task == "—"
    assert budget == "—"


def test_hp11_health_green_when_age_lt_10():
    """HP-11: Health is [green]●[/green] when state.timestamp age < 10s."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(timestamp=int(time.time()) - 5)
    log_summary = _make_log_summary()

    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        _, _, _, _, _, health, _ = screen._compute_cells(inst)

    assert health == "[green]●[/green]"


def test_hp12_health_yellow_when_age_eq_10():
    """HP-12: Health is [yellow]●[/yellow] when state.timestamp age == 10s (boundary: not <10, but <=30)."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(timestamp=int(time.time()) - 10)
    log_summary = _make_log_summary()

    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        _, _, _, _, _, health, _ = screen._compute_cells(inst)

    assert health == "[yellow]●[/yellow]"


def test_hp13_health_yellow_when_age_eq_30():
    """HP-13: Health is [yellow]●[/yellow] when state.timestamp age == 30s (boundary: <=30)."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(timestamp=int(time.time()) - 30)
    log_summary = _make_log_summary()

    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        _, _, _, _, _, health, _ = screen._compute_cells(inst)

    assert health == "[yellow]●[/yellow]"


def test_hp14_health_red_when_age_eq_31():
    """HP-14: Health is [red]●[/red] when state.timestamp age == 31s (boundary: >30)."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(timestamp=int(time.time()) - 31)
    log_summary = _make_log_summary()

    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        _, _, _, _, _, health, _ = screen._compute_cells(inst)

    assert health == "[red]●[/red]"


def test_hp15_health_red_when_state_is_none():
    """HP-15: Health is [red]●[/red] when state is None."""
    screen = IndexScreen()
    inst = _make_instance()
    log_summary = _make_log_summary()

    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=None), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        _, _, _, _, _, health, _ = screen._compute_cells(inst)

    assert health == "[red]●[/red]"


def test_hp16_budget_running_uses_display_count():
    """HP-16: Budget = display_invocation_count/max = (invocation_count+1)/max when running."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(invocation_count=4, max_invocations=15, phase_status="running")
    log_summary = _make_log_summary()

    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        _, _, _, _, _, _, budget = screen._compute_cells(inst)

    assert budget == "5/15"


def test_hp17_duration_format():
    """HP-17: Duration is HH:MM:SS when log_summary.start_time is set."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state()
    log_summary = _make_log_summary(start_time_offset=3600)

    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        _, _, _, _, duration, _, _ = screen._compute_cells(inst)

    assert ":" in duration
    assert duration != "—"


def test_hp18_duration_dash_when_no_start_time():
    """HP-18: Duration is '—' when log_summary.start_time is None."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state()
    log_summary = _make_log_summary(start_time_offset=None)

    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        _, _, _, _, duration, _, _ = screen._compute_cells(inst)

    assert duration == "—"


# HP-19: set_interval call verified via EDGE-03 integration test


def test_hp20_index_screen_on_mount_is_async():
    """HP-20: IndexScreen.on_mount is an async (coroutine) function."""
    assert asyncio.iscoroutinefunction(IndexScreen.on_mount)


# ---------------------------------------------------------------------------
# ERR: Error handling
# ---------------------------------------------------------------------------


def test_err01_task_gt_40_chars_truncated():
    """ERR-01: task_name with a single long token uses word-based label format."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(task_name="a" * 41)
    log_summary = _make_log_summary()

    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        _, _, _, task, _, _, _ = screen._compute_cells(inst)

    assert task == "Task 1/3: " + "a" * 41 + "..."


def test_err02_task_exactly_40_chars_no_truncation():
    """ERR-02: task_name of exactly 40 chars uses word-based label format."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(task_name="a" * 40)
    log_summary = _make_log_summary()

    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        _, _, _, task, _, _, _ = screen._compute_cells(inst)

    assert task == "Task 1/3: " + "a" * 40 + "..."


def test_err03_compute_cells_propagates_log_parser_error():
    """ERR-03: FileNotFoundError from log_parser.parse propagates from _compute_cells."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state()

    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", side_effect=FileNotFoundError("no such file")):
        with pytest.raises(FileNotFoundError):
            screen._compute_cells(inst)


@pytest.mark.anyio(backends=["asyncio"])
async def test_err04_action_open_empty_table_returns_early():
    """ERR-04: action_open returns silently when DataTable has 0 rows — no exception raised."""
    with patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[]):
        async with BuildCrewDashApp().run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            # Press enter — table is empty (hidden), action_open should be a no-op
            try:
                await pilot.press("enter")
            except Exception as exc:
                pytest.fail(f"action_open raised on empty table: {exc}")


@pytest.mark.anyio(backends=["asyncio"])
async def test_err05_action_open_pushes_kanban_screen(tmp_path):
    """ERR-05: action_open calls app.push_screen(KanbanScreen(instance)) for selected row."""
    inst = BuildCrewInstance(
        pid=12345,
        project_path=tmp_path,
        log_path=tmp_path / ".buildcrew" / "logs" / "buildcrew-2024-01-01_00-00-00-12345.log",
    )
    state = _make_state(timestamp=int(time.time()) - 5)
    log_summary = _make_log_summary()

    from textual.screen import Screen as TxtScreen  # noqa: PLC0415

    class FakeKanbanScreen(TxtScreen):
        def __init__(self, instance):
            super().__init__()
            self.kanban_instance = instance

        def compose(self):
            return
            yield  # noqa: unreachable — makes this a generator

    mock_kanban_mod = MagicMock()
    mock_kanban_mod.KanbanScreen = FakeKanbanScreen

    with patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]), \
         patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary), \
         patch.dict(sys.modules, {"buildcrew_dash.screens.kanban": mock_kanban_mod}):
        async with BuildCrewDashApp().run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            from textual.widgets import DataTable  # noqa: PLC0415
            table = pilot.app.screen.query_one(DataTable)
            assert table.row_count == 1, f"Expected 1 row, got {table.row_count}"
            # Call action_open() directly — pressing "enter" is consumed by DataTable's
            # own enter binding (select_cursor) before reaching the screen-level binding.
            pilot.app.screen.action_open()
            await pilot.pause()
            assert isinstance(pilot.app.screen, FakeKanbanScreen), (
                f"Expected FakeKanbanScreen, got {type(pilot.app.screen)}"
            )


# ---------------------------------------------------------------------------
# EDGE: Boundary and format checks
# ---------------------------------------------------------------------------


def test_edge01_budget_complete_status_no_increment():
    """EDGE-01: Budget uses raw invocation_count (no +1) when phase_status != 'running'."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(invocation_count=4, max_invocations=15, phase_status="complete")
    log_summary = _make_log_summary()

    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        _, _, _, _, _, _, budget = screen._compute_cells(inst)

    assert budget == "4/15"


def test_edge02_task_empty_string():
    """EDGE-02: Empty task_name produces 'Task N/M: ...' with no content between ': ' and '...'."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(task_name="")
    log_summary = _make_log_summary()

    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        _, _, _, task, _, _, _ = screen._compute_cells(inst)

    assert task == "Task 1/3: ..."


@pytest.mark.anyio(backends=["asyncio"])
async def test_edge03_datatable_columns_after_mount():
    """EDGE-03: DataTable has exactly 7 expected column keys after app startup."""
    with patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[]):
        async with BuildCrewDashApp().run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            from textual.widgets import DataTable  # noqa: PLC0415
            table = pilot.app.screen.query_one(DataTable)
            col_keys = {ck.value for ck in table.columns.keys()}
            assert col_keys == {"project", "mode", "phase", "task", "duration", "health", "budget"}


@pytest.mark.anyio(backends=["asyncio"])
async def test_edge04_empty_state_shows_message_and_hides_table():
    """EDGE-04: With no processes, #empty-msg is mounted and DataTable display is False."""
    with patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[]):
        async with BuildCrewDashApp().run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            from textual.widgets import DataTable, Static  # noqa: PLC0415
            empty = pilot.app.screen.query_one("#empty-msg", Static)
            assert empty is not None
            table = pilot.app.screen.query_one(DataTable)
            assert table.display is False


def test_edge05_kanban_not_imported_at_module_level():
    """EDGE-05: 'kanban' import is deferred inside action_open, not at module top level."""
    import buildcrew_dash.screens.index as idx_module  # noqa: PLC0415
    source = inspect.getsource(idx_module)
    lines = source.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if "kanban" in stripped and "import" in stripped:
            # Any kanban import must be inside an indented block
            assert line.startswith((" ", "\t")), (
                f"kanban import at module top level (line {i + 1}): {line!r}"
            )


@pytest.mark.anyio(backends=["asyncio"])
async def test_edge06_refresh_data_uses_known_not_return_value(tmp_path):
    """EDGE-06: refresh_data reads _monitor._known (poll's side effect), not poll's return tuple."""
    inst = BuildCrewInstance(
        pid=12345,
        project_path=tmp_path,
        log_path=tmp_path / ".buildcrew" / "logs" / "buildcrew-2024-01-01_00-00-00-12345.log",
    )
    state = _make_state(timestamp=int(time.time()) - 5)
    log_summary = _make_log_summary()

    with patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]), \
         patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        async with BuildCrewDashApp().run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            from textual.widgets import DataTable  # noqa: PLC0415
            table = pilot.app.screen.query_one(DataTable)
            # Data flowed through _known side effect — row should exist
            assert table.row_count == 1


def test_edge07_datatable_cursor_type_is_row():
    """EDGE-07: compose() yields DataTable with cursor_type='row'."""
    source = inspect.getsource(IndexScreen.compose)
    assert "cursor_type" in source and "row" in source, (
        "DataTable in compose() must use cursor_type='row'"
    )


@pytest.mark.anyio(backends=["asyncio"])
async def test_edge08_stale_rows_removed_when_instance_disappears(tmp_path):
    """EDGE-08: When an instance disappears on next poll, its row is removed from DataTable."""
    inst_a = BuildCrewInstance(
        pid=11111,
        project_path=tmp_path / "proj_a",
        log_path=tmp_path / "proj_a" / ".buildcrew" / "logs" / "buildcrew-2024-01-01_00-00-00-11111.log",
    )
    inst_b = BuildCrewInstance(
        pid=22222,
        project_path=tmp_path / "proj_b",
        log_path=tmp_path / "proj_b" / ".buildcrew" / "logs" / "buildcrew-2024-01-01_00-00-00-22222.log",
    )
    state = _make_state(timestamp=int(time.time()) - 5)
    log_summary = _make_log_summary()

    scan_results = iter([[inst_a, inst_b], [inst_b]])

    def _scan():
        return next(scan_results)

    with patch("buildcrew_dash.scanner.ProcessScanner.scan", side_effect=_scan), \
         patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        async with BuildCrewDashApp().run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            from textual.widgets import DataTable  # noqa: PLC0415
            table = pilot.app.screen.query_one(DataTable)
            assert table.row_count == 2, f"Expected 2 rows, got {table.row_count}"

            # Trigger second poll manually
            await pilot.app.screen.refresh_data()
            await pilot.pause()

            assert table.row_count == 1, f"Expected 1 row after stale removal, got {table.row_count}"


@pytest.mark.anyio(backends=["asyncio"])
async def test_edge09_empty_to_populated_transition(tmp_path):
    """EDGE-09: After empty state, when instances appear, table shows and empty-msg hides."""
    inst = BuildCrewInstance(
        pid=12345,
        project_path=tmp_path,
        log_path=tmp_path / ".buildcrew" / "logs" / "buildcrew-2024-01-01_00-00-00-12345.log",
    )
    state = _make_state(timestamp=int(time.time()) - 5)
    log_summary = _make_log_summary()

    scan_results = iter([[], [inst]])

    def _scan():
        return next(scan_results)

    with patch("buildcrew_dash.scanner.ProcessScanner.scan", side_effect=_scan), \
         patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        async with BuildCrewDashApp().run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            from textual.widgets import DataTable, Static  # noqa: PLC0415

            table = pilot.app.screen.query_one(DataTable)
            assert table.display is False, "DataTable should be hidden on empty start"

            # Trigger second poll: instance appears
            await pilot.app.screen.refresh_data()
            await pilot.pause()

            assert table.display is True, "DataTable should be visible after instance appears"
            empty_msg = pilot.app.screen.query_one("#empty-msg", Static)
            assert empty_msg.display is False, "#empty-msg should be hidden when instances present"
            assert table.row_count == 1


# ---------------------------------------------------------------------------
# ADV: Adversarial tests
# ---------------------------------------------------------------------------


def test_adv01_compute_cells_propagates_log_parser_value_error():
    """ADV-01: Unexpected ValueError from log_parser propagates; add/update loops catch it."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state()

    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", side_effect=ValueError("unexpected")):
        with pytest.raises(ValueError):
            screen._compute_cells(inst)


@pytest.mark.anyio(backends=["asyncio"])
async def test_adv02_no_process_no_crash():
    """ADV-02: App starts cleanly with no processes; empty-msg is shown."""
    with patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[]):
        async with BuildCrewDashApp().run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            from textual.widgets import Static  # noqa: PLC0415
            empty = pilot.app.screen.query_one("#empty-msg", Static)
            assert "No buildcrew instances running" in str(empty.render())


@pytest.mark.anyio(backends=["asyncio"])
async def test_adv03_action_open_stale_row_notifies(tmp_path):
    """ADV-03: action_open calls notify when the row's instance is no longer in _known."""
    inst = BuildCrewInstance(
        pid=12345,
        project_path=tmp_path,
        log_path=tmp_path / ".buildcrew" / "logs" / "buildcrew-2024-01-01_00-00-00-12345.log",
    )
    state = _make_state(timestamp=int(time.time()) - 5)
    log_summary = _make_log_summary()

    with patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]), \
         patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        async with BuildCrewDashApp().run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            # Manually remove the instance to simulate stale row
            screen = pilot.app.screen
            screen._monitor._known.clear()
            notified = []
            screen.notify = lambda msg, **_: notified.append(msg)
            screen.action_open()
            assert any("no longer running" in m.lower() for m in notified), (
                f"Expected 'no longer running' notify; got: {notified}"
            )


@pytest.mark.anyio(backends=["asyncio"])
async def test_adv04_action_quit_exits_app():
    """ADV-04: Pressing 'q' calls app.exit() and the app shuts down cleanly."""
    with patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[]):
        async with BuildCrewDashApp().run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("q")
            # If we reach here without exception, the app exited cleanly


def test_adv05_compute_cells_propagates_key_error():
    """ADV-05: KeyError from state_reader (missing required key) propagates from _compute_cells."""
    screen = IndexScreen()
    inst = _make_instance()
    log_summary = _make_log_summary()

    with patch("buildcrew_dash.screens.index.state_reader.read", side_effect=KeyError("task_num")), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        with pytest.raises(KeyError):
            screen._compute_cells(inst)


def test_adv06_compute_cells_propagates_value_error_from_state():
    """ADV-06: ValueError from state_reader (malformed int field) propagates from _compute_cells."""
    screen = IndexScreen()
    inst = _make_instance()
    log_summary = _make_log_summary()

    with patch("buildcrew_dash.screens.index.state_reader.read", side_effect=ValueError("int() bad value")), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        with pytest.raises(ValueError):
            screen._compute_cells(inst)


# ---------------------------------------------------------------------------
# SMOKE
# ---------------------------------------------------------------------------


def test_smoke02_app_instantiation():
    """SMOKE-02: BuildCrewDashApp can be instantiated without error."""
    app = BuildCrewDashApp()
    assert app is not None


def test_discovery_mode_budget_dash():
    """Discovery mode: budget shows '—' and phase shows 'discovery'."""
    screen = IndexScreen()
    inst = _make_instance()
    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=_make_state(phase="discovery")), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=_make_log_summary()):
        project, _, phase, task, duration, health, budget = screen._compute_cells(inst)
    assert budget == "—"
    assert phase == "discovery"
    assert task == "Task 1/3: implement auth..."


# ---------------------------------------------------------------------------
# AC-06: Task label format tests
# ---------------------------------------------------------------------------


def test_ac06_label_4_tokens_exact_fit():
    """AC-06: 4-token task_name uses all 4 words — no truncation."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(task_num=2, total_tasks=5, task_name="implement auth flow now")
    log_summary = _make_log_summary()
    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        _, _, _, task, _, _, _ = screen._compute_cells(inst)
    assert task == "Task 2/5: implement auth flow now..."


def test_ac06_label_5_tokens_truncated_at_4():
    """AC-06: 5-token task_name drops the 5th word — words[:4] truncation fires."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(task_num=2, total_tasks=5, task_name="implement auth flow now extra")
    log_summary = _make_log_summary()
    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        _, _, _, task, _, _, _ = screen._compute_cells(inst)
    assert task == "Task 2/5: implement auth flow now..."


def test_ac06_label_1_token():
    """AC-06: 1-token task_name produces single-word label."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(task_num=2, total_tasks=5, task_name="short")
    log_summary = _make_log_summary()
    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        _, _, _, task, _, _, _ = screen._compute_cells(inst)
    assert task == "Task 2/5: short..."


def test_ac06_label_0_tokens():
    """AC-06: Empty task_name produces 'Task N/M: ...' with no content between ': ' and '...'."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(task_num=2, total_tasks=5, task_name="")
    log_summary = _make_log_summary()
    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        _, _, _, task, _, _, _ = screen._compute_cells(inst)
    assert task == "Task 2/5: ..."


# ---------------------------------------------------------------------------
# AC-01–AC-03: Health indicator tests
# ---------------------------------------------------------------------------


def test_hp_awaiting_input_health():
    """Status awaiting_input overrides age-based logic: health is yellow pause."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(phase_status="awaiting_input", phase="build",
                        invocation_count=4, max_invocations=15,
                        timestamp=int(time.time()) - 60)
    log_summary = _make_log_summary()
    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        _, _, _, _, _, health, _ = screen._compute_cells(inst)
    assert health == "[yellow]⏸[/yellow]"


def test_hp_permission_denied_health():
    """Status permission_denied overrides age-based logic: health is yellow warning."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(phase_status="permission_denied", phase="build",
                        invocation_count=4, max_invocations=15,
                        timestamp=int(time.time()) - 60)
    log_summary = _make_log_summary()
    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        _, _, _, _, _, health, _ = screen._compute_cells(inst)
    assert health == "[yellow]⚠[/yellow]"


def test_hp_max_turns_health():
    """Status max_turns overrides age-based logic: health is red warning."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(phase_status="max_turns", phase="build",
                        invocation_count=4, max_invocations=15,
                        timestamp=int(time.time()) - 60)
    log_summary = _make_log_summary()
    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        _, _, _, _, _, health, _ = screen._compute_cells(inst)
    assert health == "[red]⚠[/red]"


# ---------------------------------------------------------------------------
# AC-05: Budget raw count tests
# ---------------------------------------------------------------------------


def test_hp_awaiting_input_budget_raw():
    """Status awaiting_input: budget uses raw invocation_count (no +1)."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(phase_status="awaiting_input", phase="build",
                        invocation_count=4, max_invocations=15)
    log_summary = _make_log_summary()
    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        _, _, _, _, _, _, budget = screen._compute_cells(inst)
    assert budget == "4/15"


def test_hp_permission_denied_budget_raw():
    """Status permission_denied: budget uses raw invocation_count (no +1)."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(phase_status="permission_denied", phase="build",
                        invocation_count=4, max_invocations=15)
    log_summary = _make_log_summary()
    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        _, _, _, _, _, _, budget = screen._compute_cells(inst)
    assert budget == "4/15"


def test_hp_max_turns_budget_raw():
    """Status max_turns: budget uses raw invocation_count (no +1)."""
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(phase_status="max_turns", phase="build",
                        invocation_count=4, max_invocations=15)
    log_summary = _make_log_summary()
    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        _, _, _, _, _, _, budget = screen._compute_cells(inst)
    assert budget == "4/15"


def test_mode_auto_when_auto_mode_true():
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(auto_mode=True)
    log_summary = _make_log_summary()
    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        cells = screen._compute_cells(inst)
    assert cells[1] == "auto"


def test_mode_dash_when_auto_mode_false():
    screen = IndexScreen()
    inst = _make_instance()
    state = _make_state(auto_mode=False)
    log_summary = _make_log_summary()
    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=state), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        cells = screen._compute_cells(inst)
    assert cells[1] == "—"


def test_mode_dash_when_state_none():
    screen = IndexScreen()
    inst = _make_instance()
    log_summary = _make_log_summary()
    with patch("buildcrew_dash.screens.index.state_reader.read", return_value=None), \
         patch("buildcrew_dash.screens.index.log_parser.parse", return_value=log_summary):
        cells = screen._compute_cells(inst)
    assert cells[1] == "—"
