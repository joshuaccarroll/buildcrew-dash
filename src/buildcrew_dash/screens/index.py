import time
from datetime import timedelta
from pathlib import Path

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Static

from buildcrew_dash.scanner import ProcessMonitor, ProcessScanner
from buildcrew_dash import activity_reader, backlog_reader, log_parser, manifest_reader, state_reader
from buildcrew_dash import stop_control


class IndexScreen(Screen):
    BINDINGS = [
        ("enter", "open", "Open"),
        ("right", "open", "Open"),
        ("q", "quit", "Quit"),
        ("s", "toggle_stop", "Stop/Cancel"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._monitor = ProcessMonitor(ProcessScanner())

    def compose(self) -> ComposeResult:
        yield DataTable(cursor_type="row")
        yield Footer()

    async def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_column("Project", key="project")
        table.add_column("Mode", key="mode")
        table.add_column("Phase", key="phase")
        table.add_column("Task", key="task")
        table.add_column("Duration", key="duration")
        table.add_column("Health", key="health")
        table.add_column("Budget", key="budget")
        table.add_column("Status", key="status")
        await self.refresh_data()
        self.set_interval(1.0, self.refresh_data)

    async def refresh_data(self) -> None:
        try:
            await self._monitor.poll()
            table = self.query_one(DataTable)

            if len(self._monitor._known) == 0:
                table.display = False
                try:
                    empty_msg = self.query_one("#empty-msg")
                    empty_msg.display = True
                except Exception:
                    await self.mount(Static("No buildcrew instances running.", id="empty-msg"))
            else:
                try:
                    empty_msg = self.query_one("#empty-msg")
                    empty_msg.display = False
                except Exception:
                    pass
                table.display = True

                # Build desired dict
                desired: dict[str, tuple] = {}
                for instance in self._monitor._known.values():
                    try:
                        active_key = f"{str(instance.log_path)}::active"
                        desired[active_key] = self._compute_cells(instance)
                        _state = state_reader.read(instance.project_path / ".buildcrew" / ".workflow-state")
                        if _state is None or _state.phase != "batch":
                            pending = backlog_reader.read_pending_tasks(instance.project_path)
                            for n, task in enumerate(pending[1:]):
                                queued_key = f"{str(instance.log_path)}::queued::{n}"
                                desired[queued_key] = self._compute_queued_cells(instance, task)
                    except Exception:
                        prefix = f"{str(instance.log_path)}::"
                        for k in list(desired.keys()):
                            if k.startswith(prefix):
                                del desired[k]
                        continue

                # Remove absent rows
                for row_key in list(table.rows.keys()):
                    if row_key.value not in desired:
                        table.remove_row(row_key)

                # Add missing rows
                existing_keys = {rk.value for rk in table.rows.keys()}
                for k, cells in desired.items():
                    if k not in existing_keys:
                        table.add_row(*cells, key=k)

                # Update all rows
                col_keys = ["project", "mode", "phase", "task", "duration", "health", "budget", "status"]
                for k, cells in desired.items():
                    for col_key, value in zip(col_keys, cells):
                        table.update_cell(k, col_key, value)
        except Exception as e:
            self.notify(str(e), severity="warning")

    def _compute_cells(self, instance) -> tuple:
        state = state_reader.read(instance.project_path / ".buildcrew" / ".workflow-state")
        log_summary = log_parser.parse(instance.log_path)

        project = instance.project_path.name

        if state:
            mode = "auto" if state.auto_mode else "—"
            phase = state.phase
            activity = activity_reader.read(instance.project_path / ".buildcrew" / ".agent-activity")
            if (activity is not None and activity.turn > 0
                    and int(time.time()) - activity.timestamp < 30
                    and state.phase_status == "running"):
                phase = f"{state.phase} T{activity.turn}/{activity.max_turns}"
            if state.phase == "batch":
                batch = manifest_reader.read(instance.project_path)
                if batch is not None:
                    parts = batch.summary_parts(rich=True)
                    task = f"Batch: {', '.join(parts)}" if parts else f"Batch: {batch.total} tasks"
                else:
                    task = f"Batch: {state.total_tasks} tasks (parallel)"
            else:
                task_name = state.task_name
                words = task_name.split()
                first_words = " ".join(words[:4])
                task = f"Task {state.task_num}/{state.total_tasks}: {first_words}..."
            if state.phase_status == "awaiting_input":
                health = "[yellow]⏸[/yellow]"
            elif state.phase_status == "permission_denied":
                health = "[yellow]⚠[/yellow]"
            elif state.phase_status == "max_turns":
                health = "[red]⚠[/red]"
            else:
                age = int(time.time()) - state.timestamp
                if age < 10:
                    health = "[green]●[/green]"
                elif age <= 30:
                    health = "[yellow]●[/yellow]"
                else:
                    health = "[red]●[/red]"
            if state.phase in {"discovery", "batch"}:
                budget = "—"
            else:
                budget = f"{state.display_invocation_count}/{state.max_invocations}"
        else:
            mode = "—"
            phase = "—"
            task = "—"
            health = "[red]●[/red]"
            budget = "—"

        if log_summary and log_summary.start_time:
            elapsed = int(time.time()) - int(log_summary.start_time.timestamp())
            duration = str(timedelta(seconds=elapsed))
        else:
            duration = "—"

        if stop_control.is_stop_pending(instance.project_path):
            status = "[yellow]Stopping...[/yellow]"
        else:
            status = ""

        return (project, mode, phase, task, duration, health, budget, status)

    def _compute_queued_cells(self, instance, task_name: str) -> tuple:
        project = instance.project_path.name
        mode = "[dim]—[/dim]"
        phase = "[dim]queued[/dim]"
        words = task_name.split()
        if len(words) == 0:
            task = "[dim]—[/dim]"
        elif len(words) > 4:
            task = f"[dim]{' '.join(words[:4])}...[/dim]"
        else:
            task = f"[dim]{task_name}[/dim]"
        duration = "[dim]—[/dim]"
        health = "[dim]○[/dim]"
        budget = "[dim]—[/dim]"
        if stop_control.is_stop_pending(instance.project_path):
            status = "[yellow]Stopping...[/yellow]"
        else:
            status = ""
        return (project, mode, phase, task, duration, health, budget, status)

    def action_open(self) -> None:
        table = self.query_one(DataTable)
        if table.row_count == 0:
            return
        row_key: str = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        log_path_str = row_key.split("::")[0]
        if Path(log_path_str) not in self._monitor._known:
            self.notify("Instance no longer running")
            return
        from buildcrew_dash.screens.kanban import KanbanScreen  # noqa: PLC0415
        self.app.push_screen(KanbanScreen(self._monitor._known[Path(log_path_str)]))

    def action_toggle_stop(self) -> None:
        table = self.query_one(DataTable)
        if table.row_count == 0:
            return
        row_key: str = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        log_path_str = row_key.split("::")[0]
        if Path(log_path_str) not in self._monitor._known:
            self.notify("Instance no longer running")
            return
        instance = self._monitor._known[Path(log_path_str)]
        try:
            if stop_control.is_stop_pending(instance.project_path):
                stop_control.cancel_stop(instance.project_path)
                self.notify("Stop cancelled")
            else:
                stop_control.request_stop(instance.project_path)
                self.notify("Stop requested")
        except OSError as e:
            self.notify(f"Stop failed: {e}")

    def action_quit(self) -> None:
        self.app.exit()
