from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Collapsible, DataTable, Footer, Header, Log, Static
from textual.containers import ScrollableContainer

from buildcrew_dash import activity_reader, log_parser, manifest_reader, state_reader
from buildcrew_dash import stop_control
from buildcrew_dash.manifest_reader import BatchTask
from buildcrew_dash.scanner import BuildCrewInstance, ProcessMonitor, ProcessScanner


PHASE_COL_IDS = frozenset({"spec", "research", "review", "build", "codereview", "test", "outcome", "verify"})
ACTIVE_STATUSES = {"running", "awaiting_input", "permission_denied", "max_turns"}

COLUMNS = [
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

BATCH_COLUMNS = [
    ("batch-idx", "#"),
    ("batch-task", "Task"),
    ("batch-status", "Status"),
    ("batch-phase", "Phase"),
    ("batch-elapsed", "Elapsed"),
]


class KanbanScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("left", "app.pop_screen", "Back"),
        ("s", "toggle_stop", "Stop/Cancel"),
        ("l", "toggle_log", "Log"),
    ]

    CSS = (
        "#kanban-area { layout: horizontal; overflow-x: auto; overflow-y: hidden; height: 1fr; min-height: 8; }\n"
        "#task-table { height: 1fr; }\n"
        "#batch-area { height: 1fr; min-height: 8; display: none; }\n"
        "#batch-table { height: 1fr; }\n"
        "#auto-badge { padding: 0 1; }\n"
        "#phase-strip { padding: 0 1; color: $text-muted; }\n"
        "#task-header { padding: 0 1; text-style: bold; }\n"
        "#log-panel { max-height: 24; }\n"
        "#log-widget { height: 20; }"
    )

    def __init__(self, instance: BuildCrewInstance) -> None:
        self.instance = instance
        self._exited: bool = False
        self._monitor = ProcessMonitor(ProcessScanner())
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="task-header")
        yield Static("", id="auto-badge")
        yield Static("", id="phase-strip")
        with ScrollableContainer(id="kanban-area"):
            yield DataTable(id="task-table", cursor_type="none")
        with ScrollableContainer(id="batch-area"):
            yield DataTable(id="batch-table", cursor_type="none")
        with Collapsible(title="Log", id="log-panel", collapsed=True):
            yield Log(id="log-widget")
        yield Footer()

    async def on_mount(self) -> None:
        self._setup_table()
        self._setup_batch_table()
        self.set_interval(1.0, self.refresh_data)
        await self.refresh_data()

    def _setup_table(self) -> None:
        table = self.query_one("#task-table", DataTable)
        for col_id, col_label in COLUMNS:
            table.add_column(col_label, key=col_id)

    def _setup_batch_table(self) -> None:
        table = self.query_one("#batch-table", DataTable)
        for col_id, col_label in BATCH_COLUMNS:
            table.add_column(col_label, key=col_id)

    def _phase_cell(self, col_key: str, col_label: str, task_row_num: int, state, task_phases: list) -> str:
        # 1: active task + active phase column
        if state is not None and task_row_num == state.task_num:
            if col_key == f"col-{state.phase}":
                if state.phase_status == "running":
                    return f"Task {state.task_num}"
                elif state.phase_status == "awaiting_input":
                    return f"[yellow]Task {state.task_num} ⏸[/yellow]"
                elif state.phase_status in {"max_turns", "permission_denied"}:
                    return f"[red]Task {state.task_num} ⚠[/red]"
            # 2: active task + replanning
            if state.phase == "replanning":
                last_non_skipped = None
                for rec in reversed(task_phases):
                    if rec.status != "skipped" and rec.name != "replanning":
                        last_non_skipped = rec
                        break
                target = f"col-{last_non_skipped.name}" if last_non_skipped else "col-build"
                if col_key == target:
                    return f"[yellow]Task {state.task_num} replan[/yellow]"
        # 3-5: phase record (active-task checks above must precede these)
        for rec in task_phases:
            if col_key == f"col-{rec.name}" and rec.task_num == task_row_num:
                if rec.status == "complete":
                    return f"[green]✓ {rec.verdict}[/green]"
                elif rec.status == "skipped":
                    return "[dim]- skipped[/dim]"
                elif rec.status == "failed":
                    return f"[red]✗ {rec.verdict}[/red]"
        # 6: completed task → complete column
        if state is not None and task_row_num < state.task_num and col_key == "col-complete":
            return f"Task {task_row_num}"
        # 7: pending task → todo column
        if state is not None and task_row_num > state.task_num and col_key == "col-todo":
            return f"Task {task_row_num}"
        # 8: empty
        return ""

    def _build_row(self, task_row_num: int, state, log_summary) -> tuple:
        task_phases = [p for p in log_summary.phases if p.task_num == task_row_num]
        return tuple(
            self._phase_cell(col_id, col_label, task_row_num, state, task_phases)
            for col_id, col_label in COLUMNS
        )

    @staticmethod
    def _format_batch_status(task: BatchTask) -> str:
        if task.status == "pending":
            return "[dim]pending[/dim]"
        elif task.status == "running":
            return "[bold cyan]running[/bold cyan]"
        elif task.status == "completed":
            return "[green]completed[/green]"
        elif task.status == "failed":
            ec = f" ({task.exit_code})" if task.exit_code is not None else ""
            return f"[red]failed{ec}[/red]"
        elif task.status == "interrupted":
            return "[yellow]interrupted[/yellow]"
        return task.status

    @staticmethod
    def _get_batch_task_phase(task: BatchTask, wt_states: dict) -> str:
        if task.status != "running":
            return ""
        wt_state = wt_states.get(task.index)
        if wt_state is not None:
            return wt_state.phase
        return "starting"

    @staticmethod
    def _format_batch_elapsed(task: BatchTask, now: datetime | None = None) -> str:
        if task.started_at is None:
            return "[dim]--[/dim]"
        try:
            start = datetime.fromisoformat(task.started_at)
        except ValueError:
            return "[dim]--[/dim]"
        if task.status == "running":
            elapsed = (now or datetime.now(timezone.utc).replace(tzinfo=None)) - start
        elif task.completed_at is not None:
            try:
                end = datetime.fromisoformat(task.completed_at)
            except ValueError:
                return "[dim]--[/dim]"
            elapsed = end - start
        else:
            return "[dim]--[/dim]"
        total_seconds = int(elapsed.total_seconds())
        if total_seconds < 0:
            return "[dim]--[/dim]"
        minutes, seconds = divmod(total_seconds, 60)
        if minutes >= 60:
            hours, minutes = divmod(minutes, 60)
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    def _update_log(self, log_summary) -> None:
        log_widget = self.query_one("#log-widget", Log)
        log_widget.clear()
        log_widget.write_lines(log_summary.recent_lines)

    async def refresh_data(self) -> None:
        try:
            if self._exited:
                return

            added, removed = await self._monitor.poll()

            if self.instance.log_path in [r.log_path for r in removed] and not self._exited:
                self._exited = True
                await self.query_one("#kanban-area").remove_children()
                self.query_one("#kanban-area").display = False
                self.query_one("#batch-area").display = False
                await self.mount(Static("Process exited", id="exit-banner"), before="#log-panel")
                self.query_one("#task-header", Static).update("")
                self.query_one("#auto-badge", Static).update("")
                self.query_one("#phase-strip", Static).update("")
                self.set_timer(3.0, self.app.pop_screen)
                return

            try:
                state = state_reader.read(self.instance.project_path / ".buildcrew" / ".workflow-state")
            except (KeyError, ValueError):
                state = None

            activity = activity_reader.read(self.instance.project_path / ".buildcrew" / ".agent-activity")

            log_summary = log_parser.parse(self.instance.log_path)

            # Update task header (batch mode sets its own header in the batch branch below)
            if state is not None:
                if state.phase == "batch":
                    header_text = ""  # set by batch branch below
                else:
                    header_text = f"Task {state.task_num}/{state.total_tasks}: {state.task_name[:50]}"
                    if (state.phase_status == "running" and activity is not None
                            and int(time.time()) - activity.timestamp < 30):
                        header_text += (
                            f"  · Turn {activity.turn}/{activity.max_turns}"
                            f" · {activity.tool}: {activity.tool_input[:30]}"
                        )
            else:
                header_text = ""
            # Batch mode sets its own header in the batch branch below
            if state is None or state.phase != "batch":
                if stop_control.is_stop_pending(self.instance.project_path):
                    header_text = "[yellow]Stopping...[/yellow]  " + header_text
                self.query_one("#task-header", Static).update(header_text)

            # Update auto badge
            auto_text = "[bold cyan]AUTO[/bold cyan]" if (state is not None and state.auto_mode) else ""
            self.query_one("#auto-badge", Static).update(auto_text)

            # Update phase strip (filtered to current task)
            phases_for_strip = (
                [p for p in log_summary.phases if p.task_num == state.task_num]
                if state is not None
                else log_summary.phases
            )
            parts = []
            for _col_id, phase_label in COLUMNS:
                if phase_label not in PHASE_COL_IDS:
                    continue
                rec = None
                for r in reversed(phases_for_strip):
                    if r.name == phase_label:
                        rec = r
                        break
                if rec is None:
                    if state is not None and state.phase == phase_label:
                        sym = "⏸" if state.phase_status == "awaiting_input" else "●"
                    else:
                        sym = "○"
                else:
                    if rec.status == "complete":
                        sym = "✓"
                    elif rec.status == "failed":
                        sym = "✗"
                    elif rec.status == "skipped":
                        sym = "-"
                    else:  # "active"
                        sym = "⏸" if (state is not None and state.phase_status == "awaiting_input") else "●"
                parts.append(f"{sym} {phase_label}")
            if state is None or state.phase != "batch":
                self.query_one("#phase-strip", Static).update(" → ".join(parts))

            # Discovery mode: hide kanban area, show log
            if state is not None and state.phase == "discovery":
                self.query_one("#kanban-area").display = False
                self.query_one("#batch-area").display = False
                self.query_one("#log-panel", Collapsible).collapsed = False
                self._update_log(log_summary)
                return
            # Batch mode: show batch task table
            elif state is not None and state.phase == "batch":
                self.query_one("#kanban-area").display = False
                self.query_one("#batch-area").display = True

                batch = manifest_reader.read(self.instance.project_path)
                if batch is None:
                    # Fallback: no manifest yet, show log only
                    header_text = f"Batch: {state.total_tasks} tasks (parallel)"
                    self.query_one("#task-header", Static).update(
                        "[yellow]Stopping...[/yellow]  " + header_text
                        if stop_control.is_stop_pending(self.instance.project_path)
                        else header_text
                    )
                    self.query_one("#phase-strip", Static).update("● batch")
                    self._update_log(log_summary)
                    return

                # Read per-worktree state for running tasks
                wt_states: dict = {}
                for task in batch.tasks:
                    if task.status == "running":
                        try:
                            wt_states[task.index] = state_reader.read(
                                Path(self.instance.project_path) / task.worktree / ".buildcrew" / ".workflow-state"
                            )
                        except (KeyError, ValueError):
                            wt_states[task.index] = None

                # Update batch table (cell-update to avoid flicker)
                batch_table = self.query_one("#batch-table", DataTable)
                existing_keys = {rk.value for rk in batch_table.rows.keys()}
                desired_keys = set()
                now = datetime.now(timezone.utc).replace(tzinfo=None)

                for task in batch.tasks:
                    row_key = f"batch-{task.index}"
                    desired_keys.add(row_key)
                    phase = self._get_batch_task_phase(task, wt_states)
                    elapsed = self._format_batch_elapsed(task, now)
                    status_cell = self._format_batch_status(task)
                    task_label = task.text[:40] + ("..." if len(task.text) > 40 else "")
                    cells = (str(task.index), task_label, status_cell, phase, elapsed)

                    if row_key not in existing_keys:
                        batch_table.add_row(*cells, key=row_key)
                    else:
                        for (col_key, _), value in zip(BATCH_COLUMNS, cells):
                            batch_table.update_cell(row_key, col_key, value)

                # Remove rows for tasks that disappeared
                for rk in list(batch_table.rows.keys()):
                    if rk.value not in desired_keys:
                        batch_table.remove_row(rk)

                # Update header with counts
                if batch.total == 0:
                    header_text = "Batch (0): initializing"
                else:
                    hdr_parts = batch.summary_parts()
                    header_text = f"Batch ({batch.total}): {', '.join(hdr_parts)}" if hdr_parts else f"Batch ({batch.total})"
                if stop_control.is_stop_pending(self.instance.project_path):
                    header_text = "[yellow]Stopping...[/yellow]  " + header_text
                self.query_one("#task-header", Static).update(header_text)

                # Update phase strip
                strip_parts = [f"● batch  {batch.completed_count}/{batch.total} done"]
                if batch.running_count:
                    strip_parts.append(f"{batch.running_count} active")
                if batch.failed_count:
                    strip_parts.append(f"{batch.failed_count} failed")
                if batch.interrupted_count:
                    strip_parts.append(f"{batch.interrupted_count} interrupted")
                self.query_one("#phase-strip", Static).update("  ".join(strip_parts))

                # Update log widget
                self._update_log(log_summary)
                return
            else:
                self.query_one("#kanban-area").display = True
                self.query_one("#batch-area").display = False

            # Rebuild DataTable
            table = self.query_one("#task-table", DataTable)
            table.clear()
            if state is None:
                table.add_row("(unknown)", *[""] * 9, key="row-unknown")
            else:
                for n in range(1, state.total_tasks + 1):
                    table.add_row(*self._build_row(n, state, log_summary), key=f"task-{n}")

            # Update log widget
            self._update_log(log_summary)
        except Exception as e:
            self.notify(str(e), severity="warning")

    def action_toggle_log(self) -> None:
        panel = self.query_one("#log-panel", Collapsible)
        panel.collapsed = not panel.collapsed

    def action_toggle_stop(self) -> None:
        if self._exited:
            return
        try:
            if stop_control.is_stop_pending(self.instance.project_path):
                stop_control.cancel_stop(self.instance.project_path)
                self.notify("Stop cancelled")
            else:
                stop_control.request_stop(self.instance.project_path)
                self.notify("Stop requested")
        except OSError as exc:
            self.notify(f"Stop failed: {exc}")
