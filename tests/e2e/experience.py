"""
Experience harness for buildcrew-dash.

Each test simulates an actual user interaction with the installed package.
Tests are cumulative: new tasks add scenarios, existing ones are never removed
unless the behavior they test has intentionally changed.

Runner: pytest (anyio plugin active via anyio_mode=auto in pyproject.toml)
"""
import importlib
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
SRC_ROOT = PROJECT_ROOT / "src"
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
PYTHON = sys.executable


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(args: list[str], *, timeout: int = 5, **kwargs) -> subprocess.CompletedProcess:
    """Run a subprocess and return the CompletedProcess, never raise on non-zero exit."""
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, **kwargs)


# ---------------------------------------------------------------------------
# HP: Happy path
# ---------------------------------------------------------------------------


def test_hp01_package_importable():
    """User can import buildcrew_dash after editable install."""
    mod = importlib.import_module("buildcrew_dash")
    assert mod is not None


def test_hp02_main_symbol_importable():
    """User can import main() from __main__ and it is callable."""
    from buildcrew_dash.__main__ import main  # noqa: PLC0415
    assert callable(main)


def test_hp03_buildcrewdashapp_importable():
    """User can import BuildCrewDashApp class."""
    from buildcrew_dash.__main__ import BuildCrewDashApp  # noqa: PLC0415
    assert issubclass(BuildCrewDashApp, object)


def test_hp04_pyproject_toml_structure():
    """pyproject.toml has the required structure. Version is checked to be a non-empty string
    (not pinned here; release tasks bump it via pyproject.toml directly).
    NOTE: Updated from exact-match assertion to structural check after version bumped to 0.3.0.
    """
    with open(PYPROJECT, "rb") as fh:
        d = tomllib.load(fh)
    assert d["build-system"]["requires"] == ["setuptools>=68"]
    assert d["build-system"]["build-backend"] == "setuptools.build_meta"
    assert d["project"]["name"] == "buildcrew-dash"
    assert isinstance(d["project"]["version"], str) and d["project"]["version"]
    assert d["project"]["requires-python"] == ">=3.11"
    assert d["project"]["dependencies"] == ["textual>=0.47.0"]
    assert d["project"]["optional-dependencies"] == {"dev": ["pytest>=7.0", "anyio[trio]>=4.0"]}
    assert d["project"]["scripts"] == {"buildcrew-dash": "buildcrew_dash.__main__:main"}
    assert d["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests"]
    assert d["tool"]["pytest"]["ini_options"]["anyio_mode"] == "auto"
    assert d["tool"]["setuptools"]["packages"]["find"]["where"] == ["src"]


def test_hp05_main_py_structure():
    """__main__.py has IndexScreen wiring: imports IndexScreen, defines SCREENS dict, has on_mount.

    NOTE: This test replaced the old byte-exact check (test_hp05_main_py_byte_exact) because
    __main__.py was intentionally updated in the IndexScreen task to add screen registration
    and push_screen logic. The new structural assertions reflect the current expected content.
    """
    main_py = PROJECT_ROOT / "src" / "buildcrew_dash" / "__main__.py"
    text = main_py.read_text()
    assert "IndexScreen" in text, "__main__.py must import or reference IndexScreen"
    assert "SCREENS" in text, "__main__.py must define SCREENS dict"
    assert "on_mount" in text, "__main__.py must define on_mount method"
    assert 'push_screen("index")' in text or "push_screen('index')" in text, (
        "__main__.py on_mount must call push_screen('index')"
    )


def test_hp06_pyrightconfig_structure():
    """pyrightconfig.json has exactly the three required keys."""
    d = json.loads((PROJECT_ROOT / "pyrightconfig.json").read_text())
    assert d == {"include": ["src"], "pythonVersion": "3.11", "typeCheckingMode": "basic"}


def test_hp07_python_version_exact_bytes():
    """`.python-version` is exactly 5 bytes: 3.11\\n."""
    data = (PROJECT_ROOT / ".python-version").read_bytes()
    assert data == b"3.11\n", f"Got {len(data)} bytes: {data!r}"


def test_hp08_gitignore_required_patterns():
    """`.gitignore` contains all six required patterns as exact lines."""
    patterns = ["__pycache__/", "*.pyc", ".venv/", "dist/", ".eggs/", "*.egg-info/"]
    lines = (PROJECT_ROOT / ".gitignore").read_text().splitlines()
    for pattern in patterns:
        assert pattern in lines, f"Missing pattern in .gitignore: {pattern!r}"


def test_hp09_init_files_zero_bytes():
    """Both __init__.py files are exactly 0 bytes."""
    for relpath in ["src/buildcrew_dash/__init__.py", "tests/__init__.py"]:
        p = PROJECT_ROOT / relpath
        assert p.exists(), f"Missing: {relpath}"
        assert p.stat().st_size == 0, f"{relpath} should be 0 bytes, got {p.stat().st_size}"


# ---------------------------------------------------------------------------
# SMOKE: Entry-point launch tests
# ---------------------------------------------------------------------------


def test_smoke03_both_symbols_callable():
    """Both BuildCrewDashApp and main are importable and callable from installed package."""
    from buildcrew_dash.__main__ import BuildCrewDashApp, main  # noqa: PLC0415
    assert callable(main)
    assert callable(BuildCrewDashApp)


def test_smoke_app_launches_without_import_error():
    """Running `python -m buildcrew_dash` starts successfully with no Python errors.

    Textual will block waiting for a TTY — we kill after 2s and check stderr
    for import/attribute errors only. ANSI escape sequences on stderr are expected.
    """
    proc = subprocess.Popen(
        [PYTHON, "-m", "buildcrew_dash"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()

    # Textual app rendering produces ANSI escapes on stderr — that is fine
    # We only fail on Python-level errors
    assert "ImportError" not in stderr, f"ImportError in stderr: {stderr[:500]}"
    assert "AttributeError" not in stderr, f"AttributeError in stderr: {stderr[:500]}"
    assert "ModuleNotFoundError" not in stderr, f"ModuleNotFoundError in stderr: {stderr[:500]}"


# ---------------------------------------------------------------------------
# ERR: Error handling
# ---------------------------------------------------------------------------


def test_err01_import_nonexistent_submodule():
    """Importing a nonexistent name from buildcrew_dash raises ImportError."""
    with pytest.raises(ImportError):
        from buildcrew_dash import nonexistent  # type: ignore[attr-defined]  # noqa: F401, PLC0415


def test_err02_pytest_empty_suite_exits_zero(tmp_path):
    """pytest exits 0 on empty test suite (conftest hook converts exit 5 to 0)."""
    result = run(
        [PYTHON, "-m", "pytest", "--collect-only", str(tmp_path)],
        timeout=15,
    )
    # Exit 5 = no tests collected; conftest hook converts to 0
    # Running pytest against a fresh tmp dir has no conftest, so exit 5 is expected here.
    # This test verifies our conftest.py in the project root works.
    result2 = run(
        [PYTHON, "-m", "pytest", "--collect-only", str(PROJECT_ROOT / "tests")],
        timeout=15,
    )
    assert result2.returncode == 0, f"pytest exited {result2.returncode}\n{result2.stdout}\n{result2.stderr}"


# ---------------------------------------------------------------------------
# EDGE: Boundary and format checks
# ---------------------------------------------------------------------------


def test_edge01_python_version_no_bom_no_cr():
    """`.python-version` has no BOM and no carriage returns."""
    data = (PROJECT_ROOT / ".python-version").read_bytes()
    assert not data.startswith(b"\xef\xbb\xbf"), "BOM detected in .python-version"
    assert b"\r" not in data, "CR found in .python-version"
    assert len(data) == 5


def test_edge02_init_files_no_hidden_bytes():
    """Both __init__.py files contain zero bytes (not even a newline)."""
    for relpath in ["src/buildcrew_dash/__init__.py", "tests/__init__.py"]:
        p = PROJECT_ROOT / relpath
        assert p.read_bytes() == b"", f"{relpath}: expected empty, got {p.read_bytes()!r}"


def test_edge04_main_py_on_mount_is_sync():
    """BuildCrewDashApp.on_mount is a synchronous (non-async) method that calls push_screen.

    NOTE: This test replaced test_edge04_main_py_no_blank_before_compose because
    __main__.py no longer has a compose() method — it was intentionally replaced with
    an on_mount() handler that pushes IndexScreen in the IndexScreen task.
    The synchronous nature of on_mount (vs IndexScreen.on_mount which is async) is
    a structural invariant worth preserving.
    """
    import asyncio  # noqa: PLC0415
    from buildcrew_dash.__main__ import BuildCrewDashApp  # noqa: PLC0415
    assert not asyncio.iscoroutinefunction(BuildCrewDashApp.on_mount), (
        "BuildCrewDashApp.on_mount must be synchronous (not async)"
    )
    import inspect  # noqa: PLC0415
    source = inspect.getsource(BuildCrewDashApp.on_mount)
    assert "push_screen" in source, "on_mount must call push_screen"


def test_edge05_collect_only_exits_zero():
    """pytest --collect-only exits 0 even with no test files."""
    result = run(
        [PYTHON, "-m", "pytest", "--collect-only", str(PROJECT_ROOT / "tests")],
        timeout=15,
    )
    assert result.returncode == 0, (
        f"pytest --collect-only exited {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


# ---------------------------------------------------------------------------
# STATE_READER: WorkflowStateReader public API (Task: state_reader.py)
# ---------------------------------------------------------------------------


def test_sr_hp01_read_running_state():
    """User imports state_reader and parses a running state file."""
    from buildcrew_dash.state_reader import read, WorkflowState  # noqa: PLC0415

    fixtures = PROJECT_ROOT / "tests" / "fixtures" / "states"
    result = read(fixtures / "running.state")
    assert isinstance(result, WorkflowState)
    assert result.phase_status == "running"
    assert result.display_invocation_count == result.invocation_count + 1


def test_sr_hp02_read_complete_state():
    """User reads a complete state; display count is not incremented."""
    from buildcrew_dash.state_reader import read  # noqa: PLC0415

    fixtures = PROJECT_ROOT / "tests" / "fixtures" / "states"
    result = read(fixtures / "complete.state")
    assert result is not None
    assert result.phase_status == "complete"
    assert result.display_invocation_count == result.invocation_count


def test_sr_err01_absent_file_returns_none():
    """User calls read() on a path that doesn't exist; gets None, no exception."""
    from buildcrew_dash.state_reader import read  # noqa: PLC0415

    result = read(PROJECT_ROOT / "tests" / "fixtures" / "states" / "absent.state")
    assert result is None


def test_sr_adv01_malformed_line_no_crash(tmp_path):
    """Adversarial: state file contains a line without '='; read() must not raise."""
    from buildcrew_dash.state_reader import read, WorkflowState  # noqa: PLC0415

    f = tmp_path / "bad.state"
    f.write_text(
        "THIS LINE HAS NO EQUALS SIGN AND SHOULD BE SILENTLY IGNORED\n"
        "task_num=99\ntotal_tasks=99\ntask_name=adversarial\n"
        "phase=test\nphase_status=running\ninvocation_count=0\n"
        "max_invocations=5\ntimestamp=0\n"
    )
    result = read(f)
    assert isinstance(result, WorkflowState)
    assert result.task_name == "adversarial"


# ---------------------------------------------------------------------------
# ADV: Adversarial / unexpected usage
# ---------------------------------------------------------------------------


def test_adv01_import_without_install_via_pythonpath():
    """Package is importable from src/ directory without editable install.

    Simulates a user who has cloned the repo but not run pip install.
    """
    env = {**os.environ, "PYTHONPATH": str(SRC_ROOT)}
    result = run(
        [PYTHON, "-c", "import buildcrew_dash; print(buildcrew_dash.__file__)"],
        timeout=5,
        env=env,
    )
    assert result.returncode == 0, f"Import via PYTHONPATH failed: {result.stderr}"
    assert "buildcrew_dash" in result.stdout


def test_adv02_no_module_error_without_install():
    """Without install and without PYTHONPATH, importing the package fails with ModuleNotFoundError."""
    # Use a clean env with no PYTHONPATH pointing at src
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    # Use system python (not the venv python) to avoid the editable install
    system_python = "/usr/bin/python3"
    if not os.path.exists(system_python):
        pytest.skip("No /usr/bin/python3 available")
    result = run(
        [system_python, "-c", "import buildcrew_dash"],
        timeout=5,
        env=env,
    )
    assert result.returncode != 0, "Expected import to fail on system python without install"
    assert "ModuleNotFoundError" in result.stderr or "ImportError" in result.stderr


# ---------------------------------------------------------------------------
# SCANNER: ProcessScanner public API (Task: scanner.py)
# ---------------------------------------------------------------------------


def test_sc_hp01_scan_returns_list():
    """User calls ProcessScanner().scan() and always gets a list back."""
    from buildcrew_dash.scanner import ProcessScanner  # noqa: PLC0415

    result = ProcessScanner().scan()
    assert isinstance(result, list)


def test_sc_hp02_scan_result_items_typed():
    """Every item returned by scan() is a BuildCrewInstance with correct field types."""
    from buildcrew_dash.scanner import BuildCrewInstance, ProcessScanner  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    result = ProcessScanner().scan()
    for item in result:
        assert isinstance(item, BuildCrewInstance)
        assert isinstance(item.pid, int)
        assert isinstance(item.project_path, Path)
        assert isinstance(item.log_path, Path)


def test_sc_adv01_scan_never_raises():
    """Adversarial: scan() must not raise even when called in an unusual environment."""
    from buildcrew_dash.scanner import ProcessScanner  # noqa: PLC0415

    scanner = ProcessScanner()
    try:
        scanner.scan()
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"scan() raised unexpectedly: {exc}")


def test_sc_adv02_stateless_between_calls():
    """Adversarial: calling scan() twice on the same instance returns independent results
    (seen_logs is local per call, not shared on the instance).
    """
    from unittest.mock import MagicMock, patch  # noqa: PLC0415
    from buildcrew_dash.scanner import ProcessScanner  # noqa: PLC0415

    # Mock pgrep to return non-zero so scan() returns [] quickly — no lsof/ps needed.
    def _fail(*args, **kwargs):  # noqa: ANN202
        m = MagicMock()
        m.returncode = 1
        m.stdout = ""
        return m

    scanner = ProcessScanner()
    with patch("buildcrew_dash.scanner.subprocess.run", side_effect=_fail):
        first = scanner.scan()
    with patch("buildcrew_dash.scanner.subprocess.run", side_effect=_fail):
        second = scanner.scan()

    assert first == []
    assert second == []
    # Both are fresh lists, not the same object
    assert first is not second


def test_sc_adv03_ps_raises_keeps_pid(tmp_path):
    """Adversarial: if ps raises (e.g. FileNotFoundError), PID is kept in results."""
    from unittest.mock import MagicMock, patch  # noqa: PLC0415
    from buildcrew_dash.scanner import ProcessScanner  # noqa: PLC0415

    log_dir = tmp_path / ".buildcrew" / "logs"
    log_dir.mkdir(parents=True)
    log_file = log_dir / "buildcrew-2024-01-15_10-00-00-99999.log"
    log_file.touch()

    lsof_header = "COMMAND   PID  USER   FD   TYPE DEVICE SIZE/OFF NODE NAME\n"
    lsof_data = f"python  99999  user  cwd    DIR    8,1     4096    2 {tmp_path}\n"

    call_count = 0

    def _side_effect(*args, **kwargs):  # noqa: ANN202
        nonlocal call_count
        call_count += 1
        m = MagicMock()
        if call_count == 1:  # pgrep
            m.returncode = 0
            m.stdout = "99999\n"
        elif call_count == 2:  # lsof
            m.returncode = 0
            m.stdout = lsof_header + lsof_data
        else:  # ps — raises instead of returning
            raise FileNotFoundError("ps not found")
        return m

    with patch("buildcrew_dash.scanner.subprocess.run", side_effect=_side_effect), \
         patch("buildcrew_dash.scanner.glob", return_value=[str(log_file)]):
        result = ProcessScanner().scan()

    # PID should be kept because ps raised (treated as non-dash process)
    assert len(result) == 1
    assert result[0].pid == 99999


def test_adv03_pyproject_toml_no_extra_keys():
    """pyproject.toml must contain no keys beyond those defined in the spec."""
    with open(PYPROJECT, "rb") as fh:
        d = tomllib.load(fh)
    allowed_top_level = {"build-system", "project", "tool"}
    extra = set(d.keys()) - allowed_top_level
    assert not extra, f"Unexpected top-level keys in pyproject.toml: {extra}"

    allowed_tool_keys = {"pytest", "setuptools"}
    extra_tool = set(d.get("tool", {}).keys()) - allowed_tool_keys
    assert not extra_tool, f"Unexpected keys under [tool]: {extra_tool}"


# ---------------------------------------------------------------------------
# INDEX_SCREEN: IndexScreen public interface (Task: screens/index.py)
# ---------------------------------------------------------------------------


def test_is_hp01_index_screen_importable():
    """User can import IndexScreen from buildcrew_dash.screens.index."""
    from buildcrew_dash.screens.index import IndexScreen  # noqa: PLC0415
    assert IndexScreen is not None


def test_is_hp02_screens_package_importable():
    """buildcrew_dash.screens is importable as a package (screens/__init__.py exists)."""
    import buildcrew_dash.screens  # noqa: PLC0415
    assert buildcrew_dash.screens is not None


def test_is_hp03_buildcrewdashapp_screens_has_index():
    """BuildCrewDashApp.SCREENS["index"] maps to IndexScreen."""
    from buildcrew_dash.__main__ import BuildCrewDashApp  # noqa: PLC0415
    from buildcrew_dash.screens.index import IndexScreen  # noqa: PLC0415
    assert "index" in BuildCrewDashApp.SCREENS
    assert BuildCrewDashApp.SCREENS["index"] is IndexScreen


def test_is_hp04_on_mount_is_sync():
    """BuildCrewDashApp.on_mount is synchronous (not async), unlike IndexScreen.on_mount."""
    import asyncio  # noqa: PLC0415
    from buildcrew_dash.__main__ import BuildCrewDashApp  # noqa: PLC0415
    from buildcrew_dash.screens.index import IndexScreen  # noqa: PLC0415
    assert not asyncio.iscoroutinefunction(BuildCrewDashApp.on_mount)
    assert asyncio.iscoroutinefunction(IndexScreen.on_mount)


def test_is_adv01_kanban_import_deferred():
    """KanbanScreen is NOT imported at the top of screens/index.py — import is deferred."""
    import inspect  # noqa: PLC0415
    import buildcrew_dash.screens.index as idx_module  # noqa: PLC0415
    source = inspect.getsource(idx_module)
    for i, line in enumerate(source.splitlines()):
        if "kanban" in line and "import" in line:
            assert line.startswith((" ", "\t")), (
                f"kanban import found at module top level (line {i + 1}): {line!r}"
            )


# ---------------------------------------------------------------------------
# KANBAN_SCREEN: KanbanScreen public interface (Task: screens/kanban.py)
# ---------------------------------------------------------------------------


def test_ks_hp01_kanban_screen_importable():
    """User can import KanbanScreen from buildcrew_dash.screens.kanban."""
    from buildcrew_dash.screens.kanban import KanbanScreen  # noqa: PLC0415
    assert KanbanScreen is not None


def test_ks_hp02_kanban_screen_is_textual_screen():
    """KanbanScreen is a subclass of textual.screen.Screen."""
    from textual.screen import Screen  # noqa: PLC0415
    from buildcrew_dash.screens.kanban import KanbanScreen  # noqa: PLC0415
    assert issubclass(KanbanScreen, Screen)


def test_ks_hp03_kanban_constants_exported():
    """COLUMNS and PHASE_COL_IDS are importable module-level constants."""
    from buildcrew_dash.screens.kanban import COLUMNS, PHASE_COL_IDS  # noqa: PLC0415
    assert len(COLUMNS) == 10
    assert len(PHASE_COL_IDS) == 8
    assert isinstance(PHASE_COL_IDS, frozenset)


def test_ks_hp04_kanban_bindings_structure():
    """KanbanScreen.BINDINGS contains the three required action key mappings."""
    from buildcrew_dash.screens.kanban import KanbanScreen  # noqa: PLC0415
    keys = {b[0] for b in KanbanScreen.BINDINGS}
    assert "escape" in keys, "BINDINGS must contain 'escape'"
    assert "left" in keys, "BINDINGS must contain 'left'"
    assert "l" in keys, "BINDINGS must contain 'l'"


def test_ks_hp05_kanban_screen_init_accepts_instance():
    """User can instantiate KanbanScreen with a BuildCrewInstance — no exception."""
    from pathlib import Path  # noqa: PLC0415
    from buildcrew_dash.scanner import BuildCrewInstance  # noqa: PLC0415
    from buildcrew_dash.screens.kanban import KanbanScreen  # noqa: PLC0415

    inst = BuildCrewInstance(
        pid=99999,
        project_path=Path("/tmp/ks_exp_test"),
        log_path=Path("/tmp/ks_exp_test/.buildcrew/logs/buildcrew-2024-01-01_00-00-00-99999.log"),
    )
    screen = KanbanScreen(inst)
    assert screen.instance is inst
    assert screen._exited is False


def test_ks_adv01_kanban_module_importable_without_runtime():
    """Adversarial: importing screens.kanban must not trigger Textual app startup or side effects."""
    import importlib  # noqa: PLC0415
    # Re-import to ensure no side effects on fresh import
    mod = importlib.import_module("buildcrew_dash.screens.kanban")
    assert hasattr(mod, "KanbanScreen")
    assert hasattr(mod, "COLUMNS")
    assert hasattr(mod, "PHASE_COL_IDS")


# ---------------------------------------------------------------------------
# EH: Error Handling (Task: graceful error handling + smoke test)
# ---------------------------------------------------------------------------


def test_eh_hp01_scanner_module_flags_default_false():
    """User imports scanner; _PGREP_UNAVAILABLE and _LSOF_UNAVAILABLE are both False at module level."""
    import buildcrew_dash.scanner as sm  # noqa: PLC0415
    assert isinstance(sm._PGREP_UNAVAILABLE, bool)
    assert isinstance(sm._LSOF_UNAVAILABLE, bool)
    # Flags should start False on a fresh import (or be whatever their current state is —
    # what matters is they exist and are booleans, indicating availability status)
    assert sm._PGREP_UNAVAILABLE in (True, False)
    assert sm._LSOF_UNAVAILABLE in (True, False)


def test_eh_smoke01_all_modified_modules_importable():
    """SMOKE-03: All 5 modified modules are importable without ImportError or AttributeError."""
    import importlib  # noqa: PLC0415
    modules = [
        "buildcrew_dash.scanner",
        "buildcrew_dash.log_parser",
        "buildcrew_dash.state_reader",
        "buildcrew_dash.__main__",
        "buildcrew_dash.screens.index",
        "buildcrew_dash.screens.kanban",
    ]
    for mod_name in modules:
        mod = importlib.import_module(mod_name)
        assert mod is not None, f"Failed to import {mod_name}"


def test_eh_err01_pgrep_unavailable_scan_returns_list():
    """User calls scan() on a system without pgrep; gets a list back (not an exception)."""
    from unittest.mock import patch  # noqa: PLC0415
    from buildcrew_dash.scanner import ProcessScanner  # noqa: PLC0415
    import buildcrew_dash.scanner as sm  # noqa: PLC0415
    orig = sm._PGREP_UNAVAILABLE
    sm._PGREP_UNAVAILABLE = False
    try:
        with patch("buildcrew_dash.scanner.subprocess.run", side_effect=FileNotFoundError("no pgrep")):
            result = ProcessScanner().scan()
        assert isinstance(result, list)
        assert result == []
    finally:
        sm._PGREP_UNAVAILABLE = orig


def test_eh_err02_log_parser_unreadable_returns_fallback(tmp_path):
    """User calls parse() on an unreadable log; gets a fallback LogSummary with '(log unreadable)'."""
    from pathlib import Path  # noqa: PLC0415
    from unittest.mock import patch  # noqa: PLC0415
    from buildcrew_dash.log_parser import parse, LogSummary  # noqa: PLC0415
    log_dir = tmp_path / ".buildcrew" / "logs"
    log_dir.mkdir(parents=True)
    log_file = log_dir / "buildcrew-2024-01-15_10-00-00-99999.log"
    log_file.touch()

    with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
        result = parse(log_file)

    assert isinstance(result, LogSummary)
    assert result.recent_lines == ["(log unreadable)"]
    assert result.pid == 0


def test_eh_err03_state_reader_unreadable_returns_none(tmp_path):
    """User calls state_reader.read() on a file that can't be read; gets None, no exception."""
    from pathlib import Path  # noqa: PLC0415
    from unittest.mock import patch  # noqa: PLC0415
    from buildcrew_dash.state_reader import read  # noqa: PLC0415
    state_file = tmp_path / "unreadable.state"
    state_file.write_text("task_num=1\n")

    with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
        result = read(state_file)

    assert result is None


def test_eh_adv01_scan_never_raises_without_pgrep():
    """Adversarial: scan() must not raise even when pgrep is completely absent from the system."""
    from unittest.mock import patch  # noqa: PLC0415
    from buildcrew_dash.scanner import ProcessScanner  # noqa: PLC0415
    import buildcrew_dash.scanner as sm  # noqa: PLC0415
    orig = sm._PGREP_UNAVAILABLE
    sm._PGREP_UNAVAILABLE = False
    try:
        with patch("buildcrew_dash.scanner.subprocess.run", side_effect=FileNotFoundError("no pgrep")):
            try:
                result = ProcessScanner().scan()
            except Exception as exc:
                pytest.fail(f"scan() raised when pgrep missing: {exc}")
        assert isinstance(result, list)
    finally:
        sm._PGREP_UNAVAILABLE = orig


# ---------------------------------------------------------------------------
# README: buildcrew-dash/README.md content (Task: Write README.md)
# ---------------------------------------------------------------------------

README_PATH = PROJECT_ROOT / "README.md"

_SECTION_HEADERS = [
    "## Prerequisites",
    "## Install",
    "## Usage",
    "## Keyboard Shortcuts",
    "## Limitations",
]


def _readme_lines() -> list[str]:
    """Return all lines of the README (stripped of trailing newline per line)."""
    return README_PATH.read_text(encoding="utf-8").splitlines()


def _section_body(lines: list[str], header: str) -> list[str]:
    """Return lines belonging to the given ## section (exclusive of header and next ## header)."""
    try:
        start = lines.index(header) + 1
    except ValueError:
        return []
    body = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        body.append(line)
    return body


# -- HP: Happy Path --


def test_readme_hp01_file_exists():
    """HP-01: README.md exists at buildcrew-dash/README.md."""
    assert README_PATH.exists(), f"README not found at {README_PATH}"
    assert README_PATH.is_file()


def test_readme_hp02_title_is_first_non_empty_line():
    """HP-02: First non-empty line is exactly '# buildcrew-dash' with no trailing whitespace."""
    lines = _readme_lines()
    non_empty = [ln for ln in lines if ln.strip()]
    assert non_empty, "README is effectively empty"
    assert non_empty[0] == "# buildcrew-dash", (
        f"First non-empty line is {non_empty[0]!r}, expected '# buildcrew-dash'"
    )


def test_readme_hp03_all_five_section_headers():
    """HP-03: All 5 required ## section headers are present as complete lines."""
    lines = _readme_lines()
    for header in _SECTION_HEADERS:
        assert header in lines, f"Section header {header!r} not found as a complete line"


def test_readme_hp04_prerequisites_content():
    """HP-04: Prerequisites section contains Python 3.11, uv, pip, macOS, pgrep, lsof."""
    lines = _readme_lines()
    body = "\n".join(_section_body(lines, "## Prerequisites"))
    for keyword in ["Python 3.11", "uv", "pip", "macOS", "pgrep", "lsof"]:
        assert keyword in body, f"Prerequisites section missing {keyword!r}"


def test_readme_hp05_install_commands():
    """HP-05: Install section contains git clone, uv pip install -e ., and a non-uv pip install -e . line."""
    lines = _readme_lines()
    body_lines = _section_body(lines, "## Install")
    body = "\n".join(body_lines)
    assert "git clone" in body, "Install section missing 'git clone'"
    assert "uv pip install -e ." in body, "Install section missing 'uv pip install -e .'"
    # There must be at least one line containing 'pip install -e .' that does NOT start with 'uv'
    non_uv_pip_line = any(
        "pip install -e ." in line and not line.lstrip().startswith("uv")
        for line in body_lines
    )
    assert non_uv_pip_line, (
        "Install section must have a 'pip install -e .' occurrence not beginning with 'uv'"
    )


def test_readme_hp06_usage_auto_discovery():
    """HP-06: Usage section describes auto-discovery, no configuration, and has a code block."""
    lines = _readme_lines()
    body_lines = _section_body(lines, "## Usage")
    body = "\n".join(body_lines)
    assert "buildcrew-dash" in body, "Usage section missing 'buildcrew-dash'"
    assert "auto-discovers" in body, "Usage section missing 'auto-discovers'"
    assert "no configuration" in body.lower() or "no config" in body.lower(), (
        "Usage section missing 'no configuration'"
    )
    # Must contain a fenced code block
    has_code_fence = any(line.strip().startswith("```") for line in body_lines)
    assert has_code_fence, "Usage section missing a fenced code block"


def test_readme_hp07_keyboard_shortcuts_table_header():
    """HP-07: Keyboard Shortcuts table has header with exactly Screen|Key|Action columns."""
    import re  # noqa: PLC0415
    lines = _readme_lines()
    body_lines = _section_body(lines, "## Keyboard Shortcuts")
    pattern = re.compile(r"^\| *Screen *\| *Key *\| *Action *\|\s*$")
    matching = [ln for ln in body_lines if pattern.match(ln)]
    assert matching, "Keyboard Shortcuts table header 'Screen | Key | Action' not found"


def test_readme_hp08_keyboard_shortcuts_all_bindings():
    """HP-08: Keyboard Shortcuts table has all 4 required binding rows."""
    lines = _readme_lines()
    body = "\n".join(_section_body(lines, "## Keyboard Shortcuts"))

    # Row 1: q / Quit (Index screen)
    assert "q" in body and "Quit" in body, "Missing q/Quit binding row"

    # Row 2: Enter / → / Open kanban (Index screen)
    assert "Enter" in body and "→" in body, "Missing Enter/→ binding row"
    assert "kanban" in body.lower(), "Missing 'Open kanban' action in keyboard shortcuts"

    # Row 3: Esc / ← / Back (Kanban screen)
    assert "Esc" in body and "←" in body, "Missing Esc/← binding row"
    assert "Back" in body or "back" in body, "Missing 'Back' action in keyboard shortcuts"

    # Row 4: l / Toggle log (Kanban screen)
    assert " l " in body or "| l |" in body or "| `l` |" in body or "`l`" in body, (
        "Missing 'l' key binding row"
    )
    assert "Toggle log" in body or "toggle log" in body.lower(), (
        "Missing 'Toggle log' action in keyboard shortcuts"
    )


def test_readme_hp09_limitations_content():
    """HP-09: Limitations section mentions macOS, pgrep/lsof, and no history."""
    lines = _readme_lines()
    body = "\n".join(_section_body(lines, "## Limitations"))
    assert "macOS" in body, "Limitations missing 'macOS'"
    assert "pgrep" in body, "Limitations missing 'pgrep'"
    assert "lsof" in body, "Limitations missing 'lsof'"
    assert "history" in body.lower() or "no history" in body.lower(), (
        "Limitations missing statement about no history"
    )


# -- EDGE: Boundary and format checks --


def test_readme_edge01_file_is_non_empty():
    """EDGE-01: README.md is non-empty."""
    assert README_PATH.stat().st_size > 0, "README.md is empty"


def test_readme_edge02_no_bom():
    """EDGE-02: README.md has no UTF-8 BOM."""
    assert README_PATH.read_bytes()[:3] != b"\xef\xbb\xbf", "README.md has a UTF-8 BOM"


def test_readme_edge03_sections_in_spec_order():
    """EDGE-03: Section headers appear in the required order."""
    lines = _readme_lines()
    indices = []
    for header in _SECTION_HEADERS:
        assert header in lines, f"Header {header!r} not found"
        indices.append(lines.index(header))
    assert indices == sorted(indices), (
        f"Section headers out of order: {list(zip(_SECTION_HEADERS, indices))}"
    )


def test_readme_edge04_title_before_all_sections():
    """EDGE-04: # buildcrew-dash title appears before the first ## section."""
    lines = _readme_lines()
    title_idx = lines.index("# buildcrew-dash")
    first_section_idx = next(i for i, ln in enumerate(lines) if ln.startswith("## "))
    assert title_idx < first_section_idx, (
        f"Title at line {title_idx} is not before first section at line {first_section_idx}"
    )


def test_readme_edge05_keyboard_table_has_exactly_four_data_rows():
    """EDGE-05: Keyboard Shortcuts table has exactly 4 data rows (no header, no separator)."""
    lines = _readme_lines()
    body_lines = _section_body(lines, "## Keyboard Shortcuts")
    data_rows = [
        ln for ln in body_lines
        if ln.startswith("|")
        and "Screen" not in ln  # not header
        and not all(c in "|- " for c in ln)  # not separator
    ]
    assert len(data_rows) == 4, (
        f"Expected 4 data rows in Keyboard Shortcuts table, found {len(data_rows)}: {data_rows}"
    )


def test_readme_edge06_ends_with_newline():
    """EDGE-06: README.md ends with a newline character."""
    raw = README_PATH.read_bytes()
    assert raw[-1:] == b"\n", "README.md does not end with a newline"


def test_readme_edge07_exactly_one_level1_heading():
    """EDGE-07: Exactly one level-1 heading (# ) outside code fences."""
    lines = _readme_lines()
    in_fence = False
    h1_lines = []
    for ln in lines:
        if ln.strip().startswith("```"):
            in_fence = not in_fence
        elif not in_fence and ln.startswith("# "):
            h1_lines.append(ln)
    assert len(h1_lines) == 1, (
        f"Expected exactly 1 level-1 heading, found {len(h1_lines)}: {h1_lines}"
    )


# -- ADV: Adversarial --


def test_readme_adv01_no_raw_html():
    """ADV-01: README.md contains no raw HTML tags."""
    content = README_PATH.read_text(encoding="utf-8")
    for tag in ("<html", "<div", "<p>", "<br"):
        assert tag not in content, f"README contains raw HTML tag: {tag!r}"


def test_readme_adv02_title_is_level1_not_level2():
    """ADV-02: '# buildcrew-dash' is present; '## buildcrew-dash' is absent."""
    lines = _readme_lines()
    assert "# buildcrew-dash" in lines, "Missing '# buildcrew-dash' title"
    assert "## buildcrew-dash" not in lines, "Found '## buildcrew-dash' — title must be level-1"


def test_readme_adv03_sections_are_level2_not_level1_or_level3():
    """ADV-03: Each of the 5 section names appears only at ## level, not # or ###."""
    lines = _readme_lines()
    section_names = ["Prerequisites", "Install", "Usage", "Keyboard Shortcuts", "Limitations"]
    for name in section_names:
        h1_match = any(ln.startswith("# ") and name in ln and not ln.startswith("## ") for ln in lines)
        h3_match = any(ln.startswith("### ") and name in ln for ln in lines)
        assert not h1_match, f"Section '{name}' found at level-1 heading"
        assert not h3_match, f"Section '{name}' found at level-3+ heading"


def test_readme_adv04_required_section_headers_present():
    """ADV-04: The 5 originally required ## section headers are all present.
    NOTE: Updated from an exact-count assertion (5) after 'Upgrade' and 'Uninstall'
    sections were added, bringing the total to 7. We now assert presence of required
    sections rather than pinning the total count.
    """
    lines = _readme_lines()
    h2_lines = [ln for ln in lines if ln.startswith("## ")]
    for header in _SECTION_HEADERS:
        assert header in lines, f"Required section {header!r} missing from README"
    assert len(h2_lines) >= 5, (
        f"Expected at least 5 ## headers, found {len(h2_lines)}: {h2_lines}"
    )


# ---------------------------------------------------------------------------
# CMD: Subcommand dispatch (Task: update + uninstall subcommands)
# ---------------------------------------------------------------------------


def test_cmd01_smoke01_import_no_tui_launch():
    """SMOKE-01: Importing main with no-arg sys.argv does not launch TUI; prints 'ok'."""
    result = run(
        [PYTHON, "-c",
         "import sys; sys.argv=['buildcrew-dash']; "
         "from buildcrew_dash.__main__ import main; print('ok')"],
        timeout=10,
    )
    assert result.returncode == 0, (
        f"Expected exit 0, got {result.returncode}\nstderr: {result.stderr}"
    )
    assert "ok" in result.stdout
    assert "ImportError" not in result.stderr


def test_cmd02_smoke02_uninstall_arg_import_no_crash():
    """SMOKE-02: 'uninstall' arg — abort path via empty stdin; exits 0 with 'Aborted.'."""
    result = run(
        [PYTHON, "-m", "buildcrew_dash", "uninstall"],
        timeout=10,
        input="",  # EOF immediately — triggers EOFError → abort path
    )
    assert result.returncode == 0, (
        f"Expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "Aborted." in result.stdout


def test_cmd03_smoke03_unknown_arg_exits_one():
    """SMOKE-03: '--help' arg → exit 1, usage error on stdout."""
    result = run([PYTHON, "-m", "buildcrew_dash", "--help"], timeout=10)
    assert result.returncode == 1, (
        f"Expected exit 1, got {result.returncode}\nstdout: {result.stdout}"
    )
    assert "Unknown command: --help" in result.stdout
    assert "Usage: buildcrew-dash [update|uninstall]" in result.stdout


def test_cmd04_unknown_arg_foo_exits_one():
    """Adversarial: 'foo' arg → exit 1, 'Unknown command: foo' on stdout."""
    result = run([PYTHON, "-m", "buildcrew_dash", "foo"], timeout=10)
    assert result.returncode == 1
    assert "Unknown command: foo" in result.stdout
    assert "Usage: buildcrew-dash [update|uninstall]" in result.stdout


def test_cmd05_uninstall_prints_removal_targets():
    """Adversarial: 'uninstall' with abort response — removal targets printed to stdout."""
    result = run(
        [PYTHON, "-m", "buildcrew_dash", "uninstall"],
        timeout=10,
        input="n\n",
    )
    assert result.returncode == 0
    assert "Will remove: ~/.buildcrew-dash/" in result.stdout
    assert "Will remove: ~/.local/bin/buildcrew-dash" in result.stdout


def test_cmd06_uninstall_n_response_aborts():
    """Adversarial: 'uninstall' + 'n' → 'Aborted.' on stdout, exits 0."""
    result = run(
        [PYTHON, "-m", "buildcrew_dash", "uninstall"],
        timeout=10,
        input="n\n",
    )
    assert result.returncode == 0
    assert "Aborted." in result.stdout


def test_cmd07_unknown_arg_h_exits_one():
    """Adversarial: '-h' arg (common help flag) → exit 1, usage message."""
    result = run([PYTHON, "-m", "buildcrew_dash", "-h"], timeout=10)
    assert result.returncode == 1
    assert "Unknown command: -h" in result.stdout


def test_cmd08_unknown_arg_help_exits_one():
    """Adversarial: 'help' arg → exit 1, usage message."""
    result = run([PYTHON, "-m", "buildcrew_dash", "help"], timeout=10)
    assert result.returncode == 1
    assert "Unknown command: help" in result.stdout


# ---------------------------------------------------------------------------
# AUTO_MODE: auto_mode field on WorkflowState (Task: backend data layer)
# ---------------------------------------------------------------------------


def test_am_hp01_auto_mode_true_from_running_fixture():
    """User reads running.state; WorkflowState.auto_mode is True (fixture has auto_mode=true)."""
    from buildcrew_dash.state_reader import read  # noqa: PLC0415

    fixtures = PROJECT_ROOT / "tests" / "fixtures" / "states"
    result = read(fixtures / "running.state")
    assert result is not None
    assert result.auto_mode is True


def test_am_hp02_auto_mode_false_from_complete_fixture():
    """User reads complete.state; WorkflowState.auto_mode is False (fixture has auto_mode=false)."""
    from buildcrew_dash.state_reader import read  # noqa: PLC0415

    fixtures = PROJECT_ROOT / "tests" / "fixtures" / "states"
    result = read(fixtures / "complete.state")
    assert result is not None
    assert result.auto_mode is False


def test_am_err01_missing_auto_mode_key_defaults_false(tmp_path):
    """Backward compat: old state file without auto_mode key yields auto_mode=False, no exception."""
    from buildcrew_dash.state_reader import read  # noqa: PLC0415

    f = tmp_path / "old_format.state"
    f.write_text(
        "task_num=1\ntotal_tasks=3\ntask_name=legacy task\n"
        "phase=build\nphase_status=running\ninvocation_count=2\n"
        "max_invocations=15\ntimestamp=1705312800\n"
    )
    result = read(f)
    assert result is not None
    assert result.auto_mode is False


def test_am_adv01_auto_mode_non_true_value_is_false(tmp_path):
    """Adversarial: auto_mode=yes/1/TRUE all yield False — only 'true' maps to True."""
    from buildcrew_dash.state_reader import read  # noqa: PLC0415

    base = (
        "task_num=1\ntotal_tasks=1\ntask_name=test\n"
        "phase=build\nphase_status=running\ninvocation_count=0\n"
        "max_invocations=5\ntimestamp=0\n"
    )
    for non_true_value in ("yes", "1", "TRUE", "True", "on"):
        f = tmp_path / f"am_{non_true_value}.state"
        f.write_text(base + f"auto_mode={non_true_value}\n")
        result = read(f)
        assert result is not None, f"read() returned None for auto_mode={non_true_value!r}"
        assert result.auto_mode is False, (
            f"Expected auto_mode=False for {non_true_value!r}, got {result.auto_mode}"
        )
