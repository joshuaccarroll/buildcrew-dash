# buildcrew-dash

Terminal dashboard for monitoring running [buildcrew](https://github.com/joshuaccarroll/buildcrew) processes.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/joshuaccarroll/buildcrew-dash/main/install.sh | bash
```

Then restart your shell (or run `source ~/.zshrc` / `source ~/.bashrc`).

## Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/joshuaccarroll/buildcrew-dash/main/uninstall.sh | bash
```

## Upgrade

```bash
curl -fsSL https://raw.githubusercontent.com/joshuaccarroll/buildcrew-dash/main/install.sh | bash -s -- --upgrade
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
| Kanban | `Esc` / `←` | Back to index |
| Kanban | `l` | Toggle log panel |

## Limitations

- macOS only — process discovery relies on `pgrep` and `lsof`, which are not available on Linux or Windows.
- Only currently-running processes are shown — there is no history of completed or past runs.

## Prerequisites

- Python 3.11+ (install via `brew install python@3.12` if needed)
- macOS

## Dev Setup

```bash
git clone https://github.com/joshuaccarroll/buildcrew-dash.git
cd buildcrew-dash
uv pip install -e .
# or: pip install -e .
```
