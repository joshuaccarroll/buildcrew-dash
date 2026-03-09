# buildcrew-dash

Real-time terminal dashboard for monitoring running [buildcrew](https://github.com/joshuaccarroll/buildcrew) pipelines. Auto-discovers active processes, displays task progress through pipeline phases, and provides workflow control — all from a single terminal window.

Built with [Textual](https://textual.textualize.io/).

## What You See

**Index Screen** — all active buildcrew instances at a glance:
- Project name, current phase, active task, duration, and invocation budget
- Health indicator (green/yellow/red) based on last state write
- Mode column showing `auto` when running unattended
- Subagent activity (current turn and tool call)
- Queued backlog tasks shown as dimmed rows below the active task
- Orphaned process detection — stale locks and detached child processes surface as 💀 rows
- One-key cleanup of orphaned state and processes
- Stop/cancel control per process

**Kanban Screen** — detailed phase-by-phase view for a single process:
- Row-based table with 10 columns: `TODO → SPEC → RESEARCH → REVIEW → TDD-SCAFFOLD → BUILD → SIMPLIFY → CODEREVIEW → VERIFY → COMPLETE`
- Each row is a task; cells show phase status with color-coded verdicts (green checkmark for passed, red X for failed, dimmed dash for skipped)
- Phase strip showing progression across all phases with elapsed durations
- Collapsible log tail panel (last 20 lines, auto-scrolling)
- UAT panel showing test scenarios with per-scenario pass/fail/error status
- Auto mode badge when running with `--auto`

**Special modes:**
- **Discovery mode** — hides the kanban table and auto-expands the log panel, since discovery is an interactive PM conversation
- **Batch mode** — shows a parallel task table with per-task status, phase, elapsed time, health, and activity instead of the phase grid

## Prerequisites

- Python 3.11+
- `uv` or `pip` (for installation)
- macOS
- `pgrep` and `lsof` (required for process discovery; built-in on macOS)

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/joshuaccarroll/buildcrew-dash/main/install.sh | bash
```

### For development:

```bash
git clone https://github.com/joshuaccarroll/buildcrew-dash.git
cd buildcrew-dash
uv pip install -e .
# or: pip install -e .
```

## Usage

```bash
buildcrew-dash
```

Running `buildcrew-dash` auto-discovers any running `buildcrew` processes — no configuration needed. The dashboard polls for active processes and updates in real time.

## Keyboard Shortcuts

| Screen | Key | Action |
|--------|-----|--------|
| Index | `q` | Quit |
| Index | `Enter` / `→` | Open kanban for selected process |
| Index | `s` | Stop/cancel the selected workflow |
| Index | `c` | Clean up selected orphaned process |
| Kanban | `Esc` / `←` | Back to index |
| Kanban | `q` | Quit |
| Kanban | `s` | Stop/cancel the workflow |
| Kanban | `l` | Toggle log panel |

## Orphan Detection

buildcrew-dash automatically detects orphaned buildcrew processes — workflows whose orchestrator crashed or was killed, leaving behind child processes and stale state files. Orphaned instances appear as 💀 rows on the index screen. Press `c` on an orphan row to clean up its detached processes and stale lock/state files.

The dashboard also protects itself from becoming orphaned: if its terminal closes, it exits cleanly via SIGHUP handling, a TTY startup gate, and a periodic watchdog that detects reparenting to PID 1.

## Limitations

- macOS only — process discovery relies on `pgrep` and `lsof`, which are not available on Linux or Windows.
- Only currently-running processes are shown — there is no history of completed or past runs.

## Upgrade

```bash
buildcrew-dash update
```

Fallback (if the tool is broken):

```bash
curl -fsSL https://raw.githubusercontent.com/joshuaccarroll/buildcrew-dash/main/install.sh | bash -s -- --upgrade
```

## Uninstall

```bash
buildcrew-dash uninstall
```

Fallback (if the tool is broken):

```bash
curl -fsSL https://raw.githubusercontent.com/joshuaccarroll/buildcrew-dash/main/uninstall.sh | bash
```
