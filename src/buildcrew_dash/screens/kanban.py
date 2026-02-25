from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Collapsible, Footer, Header, Label, Log, Static
from textual.containers import ScrollableContainer, Vertical

from buildcrew_dash import log_parser, state_reader
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


class KanbanScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("left", "app.pop_screen", "Back"),
        ("l", "toggle_log", "Log"),
    ]

    CSS = (
        "#kanban-area { layout: horizontal; overflow-x: auto; overflow-y: hidden; height: 1fr; min-height: 8; }\n"
        ".task-card { background: $panel; padding: 0 1; margin-bottom: 1; }\n"
        ".phase-card { color: $success; padding: 0 1; margin-bottom: 1; }\n"
        ".status-awaiting_input { color: $warning; }\n"
        ".status-permission_denied { color: $error; }\n"
        ".status-max_turns { color: $error; }\n"
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
        yield Static("", id="phase-strip")
        with ScrollableContainer(id="kanban-area"):
            for col_id, label in COLUMNS:
                with Vertical(id=col_id):
                    yield Label(label)
        with Collapsible(title="Log", id="log-panel", collapsed=True):
            yield Log(id="log-widget")
        yield Footer()

    async def on_mount(self) -> None:
        self.set_interval(1.0, self.refresh_data)
        await self.refresh_data()

    async def refresh_data(self) -> None:
        try:
            if self._exited:
                return

            added, removed = await self._monitor.poll()

            if self.instance.log_path in [r.log_path for r in removed] and not self._exited:
                self._exited = True
                await self.query_one("#kanban-area").remove_children()
                await self.query_one("#kanban-area").mount(Static("Process exited", id="exit-banner"))
                self.query_one("#task-header", Static).update("")
                self.query_one("#phase-strip", Static).update("")
                self.set_timer(3.0, self.app.pop_screen)
                return

            try:
                state = state_reader.read(self.instance.project_path / ".buildcrew" / ".workflow-state")
            except (KeyError, ValueError):
                state = None

            log_summary = log_parser.parse(self.instance.log_path)

            # Update task header
            if state is not None:
                name = state.task_name
                suffix = "..." if len(name) > 50 else ""
                header_text = f"Task {state.task_num}/{state.total_tasks}: {name[:50]}{suffix}"
            else:
                header_text = ""
            self.query_one("#task-header", Static).update(header_text)

            # Update phase strip
            parts = []
            for _col_id, phase_label in COLUMNS:
                if phase_label not in PHASE_COL_IDS:
                    continue
                rec = None
                for r in reversed(log_summary.phases):
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
            self.query_one("#phase-strip", Static).update(" → ".join(parts))

            # Remove all existing task cards
            for widget in self.query(".task-card"):
                await widget.remove()

            # Remove all existing phase cards
            for widget in self.query(".phase-card"):
                await widget.remove()

            if state is not None and state.phase == "discovery":
                self.query_one("#kanban-area").display = False
                self.query_one("#log-panel", Collapsible).collapsed = False
                # NOTE: log write here is intentionally separate from the normal-path
                # log write at the end of this method (which does not clear first).
                log_widget = self.query_one("#log-widget", Log)
                log_widget.clear()
                log_widget.write_lines(log_summary.recent_lines)
                return
            else:
                self.query_one("#kanban-area").display = True

            # Rule 2: completed tasks
            i = 1
            for task_name in log_summary.completed_tasks:
                if state is None or task_name != state.task_name:
                    await self.query_one("#col-complete").mount(Static(f"Task {i}", classes="task-card"))
                    i += 1

            # Rule 3: active task (normal phase)
            if state is not None and state.phase_status in ACTIVE_STATUSES and state.phase != "replanning":
                if state.phase in PHASE_COL_IDS:
                    ps = state.phase_status
                    if ps == "awaiting_input":
                        label = f"Task {state.task_num}\n⏸ Awaiting input"
                    elif ps == "permission_denied":
                        label = f"Task {state.task_num}\n⚠ Needs permission"
                    elif ps == "max_turns":
                        label = f"Task {state.task_num}\n⚠ Max turns"
                    else:  # "running"
                        label = f"Task {state.task_num}"
                    await self.query_one(f"#col-{state.phase}").mount(
                        Static(label, classes=f"task-card status-{state.phase_status}")
                    )

            # Rule 4: active task (replanning)
            if state is not None and state.phase == "replanning":
                last_phase = None
                for rec in reversed(log_summary.phases):
                    if rec.status != "skipped" and rec.name != "replanning":
                        last_phase = rec
                        break
                if last_phase is not None and last_phase.name in PHASE_COL_IDS:
                    await self.query_one(f"#col-{last_phase.name}").mount(
                        Static(f"Task {state.task_num}\nReplanning...", classes="task-card")
                    )
                else:
                    await self.query_one("#col-build").mount(
                        Static(f"Task {state.task_num}\nReplanning...", classes="task-card")
                    )

            # Rule 7: verdict cards
            for rec in log_summary.phases:
                if rec.status == "complete" and rec.name in PHASE_COL_IDS:
                    await self.query_one(f"#col-{rec.name}").mount(
                        Static(f"✓ {rec.verdict or 'done'}", classes="phase-card")
                    )

            # Rule 5: future placeholder cards
            if state is not None:
                for n in range(state.task_num + 1, state.total_tasks + 1):
                    await self.query_one("#col-todo").mount(Static(f"Task {n}", classes="task-card"))

            # Rule 6: no state
            if state is None:
                await self.query_one("#col-todo").mount(Static("(unknown)", classes="task-card"))

            # Update log widget
            log_widget = self.query_one("#log-widget", Log)
            log_widget.clear()
            log_widget.write_lines(log_summary.recent_lines)
        except Exception as e:
            self.notify(str(e), severity="warning")

    def action_toggle_log(self) -> None:
        panel = self.query_one("#log-panel", Collapsible)
        panel.collapsed = not panel.collapsed
