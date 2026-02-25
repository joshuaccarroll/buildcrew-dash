import time
from datetime import timedelta
from pathlib import Path

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Static

from buildcrew_dash.scanner import ProcessMonitor, ProcessScanner
from buildcrew_dash import log_parser, state_reader


class IndexScreen(Screen):
    BINDINGS = [
        ("enter", "open", "Open"),
        ("right", "open", "Open"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._monitor = ProcessMonitor(ProcessScanner())

    def compose(self) -> ComposeResult:
        yield DataTable(cursor_type="row")

    async def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_column("Project", key="project")
        table.add_column("Phase", key="phase")
        table.add_column("Task", key="task")
        table.add_column("Duration", key="duration")
        table.add_column("Health", key="health")
        table.add_column("Budget", key="budget")
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

                # Remove stale rows
                known_str_keys = {str(p) for p in self._monitor._known.keys()}
                stale = [k for k in table.rows.keys() if k.value not in known_str_keys]
                for k in stale:
                    table.remove_row(k)

                # Add new rows
                existing_keys = {k.value for k in table.rows.keys()}
                for instance in self._monitor._known.values():
                    row_key_str = str(instance.log_path)
                    if row_key_str not in existing_keys:
                        try:
                            cells = self._compute_cells(instance)
                            table.add_row(*cells, key=row_key_str)
                        except Exception:
                            continue

                # Update all rows
                for row_key in list(table.rows.keys()):
                    try:
                        instance = self._monitor._known[Path(row_key.value)]
                        cells = self._compute_cells(instance)
                        col_keys = ["project", "phase", "task", "duration", "health", "budget"]
                        for col_key, value in zip(col_keys, cells):
                            table.update_cell(row_key, col_key, value)
                    except Exception:
                        continue
        except Exception as e:
            self.notify(str(e), severity="warning")

    def _compute_cells(self, instance) -> tuple:
        state = state_reader.read(instance.project_path / ".buildcrew" / ".workflow-state")
        log_summary = log_parser.parse(instance.log_path)

        project = instance.project_path.name

        if state:
            phase = state.phase
            task_name = state.task_name
            task = (task_name[:40] + "…") if len(task_name) > 40 else task_name
            age = int(time.time()) - state.timestamp
            if age < 10:
                health = "[green]●[/green]"
            elif age <= 30:
                health = "[yellow]●[/yellow]"
            else:
                health = "[red]●[/red]"
            if state.phase == "discovery":
                budget = "—"
            else:
                budget = f"{state.display_invocation_count}/{state.max_invocations}"
        else:
            phase = "—"
            task = "—"
            health = "[red]●[/red]"
            budget = "—"

        if log_summary and log_summary.start_time:
            elapsed = int(time.time()) - int(log_summary.start_time.timestamp())
            duration = str(timedelta(seconds=elapsed))
        else:
            duration = "—"

        return (project, phase, task, duration, health, budget)

    def action_open(self) -> None:
        table = self.query_one(DataTable)
        if table.row_count == 0:
            return
        row_key: str = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        if Path(row_key) not in self._monitor._known:
            self.notify("Instance no longer running")
            return
        from buildcrew_dash.screens.kanban import KanbanScreen  # noqa: PLC0415
        self.app.push_screen(KanbanScreen(self._monitor._known[Path(row_key)]))

    def action_quit(self) -> None:
        self.app.exit()
