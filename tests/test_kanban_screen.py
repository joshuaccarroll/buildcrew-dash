"""Unit and integration tests for KanbanScreen.

Covers HP-01..HP-20, ERR-01..ERR-04, EDGE-01..EDGE-08, ADV-01..ADV-03, SMOKE-01..SMOKE-02.
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
from textual.widgets import Static


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
    """HP-10: compose() yields Header, ScrollableContainer#kanban-area, Collapsible#log-panel, Log#log-widget, Footer."""
    from textual.widgets import Collapsible, Footer, Header, Log, Static  # noqa: PLC0415
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


@pytest.mark.anyio(backends=["asyncio"])
async def test_hp11_all_ten_columns_rendered(tmp_path):
    """HP-11: compose() renders exactly 10 Vertical containers with spec-required IDs."""
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
            for col_id, _ in COLUMNS:
                col = screen.query_one(f"#{col_id}")
                assert col is not None, f"Missing column #{col_id}"


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
    """HP-13: Running task with phase='build' → task-card with task_name in col-build."""
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
            screen = pilot.app.screen
            col = screen.query_one("#col-build")
            cards = list(col.query(".task-card"))
            assert len(cards) == 1
            assert str(cards[0].content) == "Task 1"


@pytest.mark.anyio(backends=["asyncio"])
async def test_hp14_completed_tasks_in_col_complete(tmp_path):
    """HP-14: Completed tasks (not matching state.task_name) appear in col-complete."""
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
            screen = pilot.app.screen
            col = screen.query_one("#col-complete")
            cards = list(col.query(".task-card"))
            texts = [str(c.content) for c in cards]
            assert "Task 1" in texts
            assert "Task 2" in texts


@pytest.mark.anyio(backends=["asyncio"])
async def test_hp15_current_task_excluded_from_col_complete(tmp_path):
    """HP-15: Task matching state.task_name is excluded from col-complete (Rule A filter)."""
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
            screen = pilot.app.screen
            col = screen.query_one("#col-complete")
            cards = list(col.query(".task-card"))
            texts = [str(c.content) for c in cards]
            assert "implement auth" not in texts
            assert "Task 1" in texts
            assert len(texts) == 1


@pytest.mark.anyio(backends=["asyncio"])
async def test_hp16_future_placeholder_cards_in_col_todo(tmp_path):
    """HP-16: Tasks task_num+1..total_tasks appear as 'Task N' placeholders in col-todo."""
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
            screen = pilot.app.screen
            col = screen.query_one("#col-todo")
            cards = list(col.query(".task-card"))
            texts = [str(c.content) for c in cards]
            assert "Task 2" in texts
            assert "Task 3" in texts
            # Task 1 (current) should not appear as a placeholder
            assert "Task 1" not in texts


@pytest.mark.anyio(backends=["asyncio"])
async def test_hp17_no_state_shows_unknown_in_col_todo(tmp_path):
    """HP-17: When state is None, '(unknown)' card is mounted in col-todo."""
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
            col = screen.query_one("#col-todo")
            cards = list(col.query(".task-card"))
            texts = [str(c.content) for c in cards]
            assert "(unknown)" in texts


@pytest.mark.anyio(backends=["asyncio"])
async def test_hp18_replanning_uses_last_non_skipped_phase(tmp_path):
    """HP-18: phase='replanning' → card with task_name and 'Replanning...' in col-codereview (last complete phase)."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(
        task_name="refactor login",
        phase="replanning",
        phase_status="running",
        task_num=1,
        total_tasks=1,
    )
    phases = [
        PhaseRecord(name="build", status="complete"),
        PhaseRecord(name="codereview", status="complete"),
        PhaseRecord(name="replanning", status="active"),
    ]
    log_summary = _make_log_summary(phases=phases)
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            col = screen.query_one("#col-codereview")
            cards = list(col.query(".task-card"))
            assert len(cards) == 1
            card_text = str(cards[0].content)
            assert "Task 1" in card_text
            assert "Replanning..." in card_text


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
            # Verify the widget is present and has content (line_count > 0)
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
    """ERR-01: KeyError from state_reader.read is caught; state treated as None."""
    inst = _make_instance(str(tmp_path))
    log_summary = _make_log_summary()
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", side_effect=KeyError("task_num")),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            # state=None fallback: (unknown) card should appear in col-todo
            col = screen.query_one("#col-todo")
            cards = list(col.query(".task-card"))
            assert any("unknown" in str(c.content) for c in cards)


@pytest.mark.anyio(backends=["asyncio"])
async def test_err02_value_error_from_state_reader_caught(tmp_path):
    """ERR-02: ValueError from state_reader.read is caught; state treated as None."""
    inst = _make_instance(str(tmp_path))
    log_summary = _make_log_summary()
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", side_effect=ValueError("bad int value")),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            col = screen.query_one("#col-todo")
            cards = list(col.query(".task-card"))
            assert any("unknown" in str(c.content) for c in cards)


@pytest.mark.anyio(backends=["asyncio"])
async def test_err03_process_exit_mounts_exit_banner(tmp_path):
    """ERR-03: When monitored instance exits (log_path in removed), exit banner is mounted in #kanban-area."""
    from textual.widgets import Static  # noqa: PLC0415

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
    """EDGE-01: Phase not in PHASE_COL_IDS → no card placed; no NoMatches exception."""
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
            screen = pilot.app.screen
            # No task-card in any phase column — phase was silently dropped
            for phase in PHASE_COL_IDS:
                cards = list(screen.query_one(f"#col-{phase}").query(".task-card"))
                assert cards == [], f"Unexpected card in col-{phase}: {[str(c.content) for c in cards]}"


@pytest.mark.anyio(backends=["asyncio"])
async def test_edge02_exited_true_causes_immediate_return(tmp_path):
    """EDGE-02: _exited=True → refresh_data returns immediately; cards unchanged; poll not called."""
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
            initial_card_count = len(list(screen.query(".task-card")))
            screen._exited = True

            # poll would fail if called (no scan mock), verifying early return
            await screen.refresh_data()
            await pilot.pause()

            final_card_count = len(list(screen.query(".task-card")))
            assert final_card_count == initial_card_count


@pytest.mark.anyio(backends=["asyncio"])
async def test_edge03_replanning_all_phases_skipped_falls_back_to_col_build(tmp_path):
    """EDGE-03: Replanning with no non-skipped non-replanning phases → card in col-build (fallback)."""
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
            screen = pilot.app.screen
            col = screen.query_one("#col-build")
            cards = list(col.query(".task-card"))
            assert len(cards) == 1
            assert "Replanning..." in str(cards[0].content)


@pytest.mark.anyio(backends=["asyncio"])
async def test_edge04_task_num_equals_total_tasks_no_placeholders(tmp_path):
    """EDGE-04: task_num == total_tasks → no 'Task N' placeholder cards in col-todo."""
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
            screen = pilot.app.screen
            col = screen.query_one("#col-todo")
            cards = list(col.query(".task-card"))
            for c in cards:
                assert not str(c.content).startswith("Task "), (
                    f"Unexpected placeholder card: {c.content!r}"
                )


@pytest.mark.anyio(backends=["asyncio"])
async def test_edge05_empty_completed_tasks_no_cards_in_col_complete(tmp_path):
    """EDGE-05: Empty completed_tasks → zero task-cards in col-complete."""
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
            screen = pilot.app.screen
            col = screen.query_one("#col-complete")
            cards = list(col.query(".task-card"))
            assert cards == []


@pytest.mark.anyio(backends=["asyncio"])
async def test_edge06_second_refresh_removes_old_cards_first(tmp_path):
    """EDGE-06: Second refresh_data removes old cards before placing new (build→test)."""
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
            # First refresh: card in col-build
            assert len(list(screen.query_one("#col-build").query(".task-card"))) == 1
            assert len(list(screen.query_one("#col-test").query(".task-card"))) == 0

            # Second refresh with state_test: card moves to col-test
            with (
                patch("buildcrew_dash.state_reader.read", return_value=state_test),
                patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
            ):
                await screen.refresh_data()
                await pilot.pause()

            assert len(list(screen.query_one("#col-build").query(".task-card"))) == 0
            assert len(list(screen.query_one("#col-test").query(".task-card"))) == 1


@pytest.mark.anyio(backends=["asyncio"])
async def test_edge07_phase_status_not_running_no_active_card(tmp_path):
    """EDGE-07: phase_status='complete' → no task-card placed in any phase column."""
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
            screen = pilot.app.screen
            for phase in PHASE_COL_IDS:
                cards = list(screen.query_one(f"#col-{phase}").query(".task-card"))
                assert cards == [], f"Unexpected card in col-{phase} when phase_status='complete'"


@pytest.mark.anyio(backends=["asyncio"])
async def test_edge08_task_num_zero_total_zero_no_placeholders(tmp_path):
    """EDGE-08: task_num=0, total_tasks=0 → range(1,1) is empty; no placeholder cards."""
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
            screen = pilot.app.screen
            col = screen.query_one("#col-todo")
            cards = list(col.query(".task-card"))
            for c in cards:
                assert not str(c.content).startswith("Task "), (
                    f"Unexpected placeholder: {c.content!r}"
                )


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
            screen = pilot.app.screen
            col = screen.query_one("#col-todo")
            cards = list(col.query(".task-card"))
            assert any("unknown" in str(c.content) for c in cards)


@pytest.mark.anyio(backends=["asyncio"])
async def test_adv02_large_total_tasks_all_placeholders_in_col_todo(tmp_path):
    """ADV-02: total_tasks=20 → 19 'Task N' placeholder cards (Tasks 2–20) in col-todo."""
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
            screen = pilot.app.screen
            col = screen.query_one("#col-todo")
            cards = list(col.query(".task-card"))
            texts = [str(c.content) for c in cards]
            for n in range(2, 21):
                assert f"Task {n}" in texts, f"Missing placeholder 'Task {n}'"


@pytest.mark.anyio(backends=["asyncio"])
async def test_adv03_refresh_after_exited_no_double_banner(tmp_path):
    """ADV-03: Calling refresh_data again after _exited=True doesn't mount a second exit banner."""
    from textual.widgets import Static  # noqa: PLC0415

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
    """SMOKE-02: KanbanScreen mounts in a Textual app with all required widgets present."""
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
            # All spec-required widgets present
            assert screen.query_one(Header) is not None
            assert screen.query_one(Footer) is not None
            assert screen.query_one("#kanban-area", ScrollableContainer) is not None
            assert screen.query_one("#log-panel", Collapsible) is not None
            assert screen.query_one("#log-widget", Log) is not None
            for col_id, _ in COLUMNS:
                assert screen.query_one(f"#{col_id}") is not None


@pytest.mark.anyio(backends=["asyncio"])
async def test_discovery_mode_kanban(tmp_path):
    """Discovery mode: kanban area hidden, log panel expanded, no task cards."""
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
            assert len(list(screen.query(".task-card"))) == 0


# ---------------------------------------------------------------------------
# New tests: AC-10
# ---------------------------------------------------------------------------


@pytest.mark.anyio(backends=["asyncio"])
async def test_awaiting_input_card(tmp_path):
    """AC-10: awaiting_input phase_status → task card with ⏸ label and status-awaiting_input class."""
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
            screen = pilot.app.screen
            cards = list(screen.query_one("#col-build").query(".task-card"))
            assert len(cards) == 1
            assert "⏸ Awaiting input" in str(cards[0].content)
            assert "status-awaiting_input" in cards[0].classes


@pytest.mark.anyio(backends=["asyncio"])
async def test_permission_denied_card(tmp_path):
    """AC-10: permission_denied phase_status → task card with ⚠ label and status-permission_denied class."""
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
            screen = pilot.app.screen
            cards = list(screen.query_one("#col-build").query(".task-card"))
            assert len(cards) == 1
            assert "⚠ Needs permission" in str(cards[0].content)
            assert "status-permission_denied" in cards[0].classes


@pytest.mark.anyio(backends=["asyncio"])
async def test_max_turns_card(tmp_path):
    """AC-10: max_turns phase_status → task card with ⚠ label and status-max_turns class."""
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
            screen = pilot.app.screen
            cards = list(screen.query_one("#col-build").query(".task-card"))
            assert len(cards) == 1
            assert "⚠ Max turns" in str(cards[0].content)
            assert "status-max_turns" in cards[0].classes


@pytest.mark.anyio(backends=["asyncio"])
async def test_phase_strip_content(tmp_path):
    """AC-10: phase strip shows ✓ for complete, ● for active, ○ for pending; 7 → separators."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(phase="build", phase_status="running")
    log_summary = _make_log_summary(phases=[
        PhaseRecord(name="spec", status="complete"),
        PhaseRecord(name="build", status="active"),
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
    """AC-10: phase strip shows ⏸ for awaiting_input phase, not ●."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(phase="build", phase_status="awaiting_input")
    log_summary = _make_log_summary(phases=[
        PhaseRecord(name="spec", status="complete"),
        PhaseRecord(name="build", status="active"),
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
    """AC-10: phase strip shows ✗ for a failed phase."""
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
    """AC-10: Calling refresh_data twice with same complete phase yields exactly 1 phase-card."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(phase="build", phase_status="complete", task_num=1, total_tasks=1)
    log_summary = _make_log_summary(phases=[
        PhaseRecord(name="build", status="complete", verdict="approved"),
    ])
    with (
        patch("buildcrew_dash.scanner.ProcessScanner.scan", return_value=[inst]),
        patch("buildcrew_dash.state_reader.read", return_value=state),
        patch("buildcrew_dash.log_parser.parse", return_value=log_summary),
    ):
        async with _KanbanTestApp(inst).run_test(size=(200, 50)) as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            await screen.refresh_data()
            assert len(list(screen.query(".phase-card"))) == 1


@pytest.mark.anyio(backends=["asyncio"])
async def test_auto_badge_shows_when_auto_mode_true(tmp_path):
    """AC-07: #auto-badge shows cyan AUTO when auto_mode=True."""
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
    """AC-08: #auto-badge is empty when auto_mode=False."""
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
    """AC-09: Running card label includes Turn N/M and tool info when activity is fresh."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(task_num=1, phase="build", phase_status="running")
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
            cards = list(screen.query(".task-card"))
            labels = [str(c.content) for c in cards]
            assert any("Turn 5/50" in lbl for lbl in labels), f"Expected 'Turn 5/50' in labels: {labels}"
            assert any("Read: src/foo.py" in lbl for lbl in labels), f"Expected 'Read: src/foo.py' in labels: {labels}"


@pytest.mark.anyio(backends=["asyncio"])
async def test_ac10_running_label_with_no_activity(tmp_path):
    """AC-10: Running card label is exactly 'Task N' (no suffix) when activity is None."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(task_num=1, phase="build", phase_status="running")
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
            cards = list(screen.query(".task-card"))
            labels = [str(c.content) for c in cards]
            assert any(lbl == f"Task {state.task_num}" for lbl in labels), (
                f"Expected exactly 'Task {state.task_num}' in labels: {labels}"
            )
            assert not any("Turn" in lbl for lbl in labels), f"Unexpected 'Turn' in labels: {labels}"


@pytest.mark.anyio(backends=["asyncio"])
async def test_ac11_stale_activity_ignored(tmp_path):
    """AC-11: Stale activity (timestamp 60s ago) is ignored — label has no Turn suffix."""
    inst = _make_instance(str(tmp_path))
    state = _make_state(task_num=1, phase="build", phase_status="running")
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
            cards = list(screen.query(".task-card"))
            labels = [str(c.content) for c in cards]
            assert not any("Turn" in lbl for lbl in labels), f"Unexpected 'Turn' in labels with stale activity: {labels}"
