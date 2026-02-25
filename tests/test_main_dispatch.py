"""Unit tests for main() dispatch logic in buildcrew_dash.__main__.

Covers HP-01..HP-08, ERR-01..ERR-09, EDGE-01..EDGE-06, ADV-01..ADV-05
from .claude/current-test-plan.md.
"""
import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

from buildcrew_dash.__main__ import main

PROG = "buildcrew-dash"
EXACT_UPDATE_CMD = (
    "curl -fsSL https://raw.githubusercontent.com/joshuaccarroll/buildcrew-dash/main/install.sh"
    " | bash -s -- --upgrade"
)


# ---------------------------------------------------------------------------
# HP: Happy Path
# ---------------------------------------------------------------------------


def test_hp01_no_arg_calls_tui():
    """HP-01: No arg — BuildCrewDashApp().run() is called, sys.exit never called."""
    with patch("sys.argv", [PROG]), \
         patch("buildcrew_dash.__main__.BuildCrewDashApp") as mock_app_cls:
        mock_app = MagicMock()
        mock_app_cls.return_value = mock_app
        main()  # Must return normally, no SystemExit
        mock_app.run.assert_called_once()


def test_hp02_update_prints_message_before_subprocess():
    """HP-02: 'update' prints message before subprocess.run, then exits with returncode=0."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    call_order = []

    def fake_print(*args, **kwargs):
        call_order.append(("print", args[0] if args else ""))

    def fake_run(*args, **kwargs):
        call_order.append("subprocess")
        return mock_result

    with patch("sys.argv", [PROG, "update"]), \
         patch("subprocess.run", side_effect=fake_run), \
         patch("builtins.print", side_effect=fake_print):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 0
    assert call_order[0] == ("print", "Fetching latest buildcrew-dash...")
    assert call_order[1] == "subprocess"


def test_hp03_update_nonzero_returncode_propagated():
    """HP-03: 'update' subprocess returncode=42 → sys.exit(42)."""
    mock_result = MagicMock()
    mock_result.returncode = 42

    with patch("sys.argv", [PROG, "update"]), \
         patch("subprocess.run", return_value=mock_result), \
         patch("builtins.print"):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 42


def test_hp04_uninstall_y_removes_files(tmp_path):
    """HP-04: 'uninstall' + 'y' — rmtree + unlink called, 'buildcrew-dash uninstalled.' printed, exits 0."""
    bcd_dir = tmp_path / ".buildcrew-dash"
    bcd_dir.mkdir()
    bcd_bin = tmp_path / ".local" / "bin" / "buildcrew-dash"
    bcd_bin.parent.mkdir(parents=True)
    bcd_bin.touch()

    with patch("sys.argv", [PROG, "uninstall"]), \
         patch("builtins.input", return_value="y"), \
         patch("pathlib.Path.home", return_value=tmp_path):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 0
    assert not bcd_dir.exists(), "~/.buildcrew-dash/ should have been removed"
    assert not bcd_bin.exists(), "~/.local/bin/buildcrew-dash should have been removed"


def test_hp04_uninstall_y_prints_success(capsys):
    """HP-04: 'uninstall' + 'y' — prints 'buildcrew-dash uninstalled.'."""
    with patch("sys.argv", [PROG, "uninstall"]), \
         patch("builtins.input", return_value="y"), \
         patch("shutil.rmtree"), \
         patch("pathlib.Path.unlink"):
        with pytest.raises(SystemExit):
            main()

    captured = capsys.readouterr()
    assert "buildcrew-dash uninstalled." in captured.out


def test_hp05_uninstall_uppercase_y(capsys):
    """HP-05: 'uninstall' + 'Y' (uppercase) — confirms (strip+lower)."""
    with patch("sys.argv", [PROG, "uninstall"]), \
         patch("builtins.input", return_value="Y"), \
         patch("shutil.rmtree") as mock_rmtree, \
         patch("pathlib.Path.unlink"):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 0
    mock_rmtree.assert_called_once()


def test_hp06_uninstall_y_trailing_space(capsys):
    """HP-06: 'uninstall' + 'Y ' (trailing space) — confirms (strip removes space)."""
    with patch("sys.argv", [PROG, "uninstall"]), \
         patch("builtins.input", return_value="Y "), \
         patch("shutil.rmtree") as mock_rmtree, \
         patch("pathlib.Path.unlink"):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 0
    mock_rmtree.assert_called_once()


def test_hp07_uninstall_prints_removal_lines_in_order(capsys):
    """HP-07: 'uninstall' prints two removal lines as literal strings, in order, before input()."""
    call_order = []

    def fake_print(*args, **kwargs):
        call_order.append(("print", args[0] if args else ""))

    def fake_input(prompt):
        call_order.append("input")
        return "n"

    with patch("sys.argv", [PROG, "uninstall"]), \
         patch("builtins.print", side_effect=fake_print), \
         patch("builtins.input", side_effect=fake_input):
        with pytest.raises(SystemExit):
            main()

    msgs = [v[1] for v in call_order if isinstance(v, tuple) and v[0] == "print"]
    input_idx = call_order.index("input")
    line1_global = next(i for i, v in enumerate(call_order)
                        if isinstance(v, tuple) and "~/.buildcrew-dash/" in v[1])
    line2_global = next(i for i, v in enumerate(call_order)
                        if isinstance(v, tuple) and "~/.local/bin/buildcrew-dash" in v[1])

    assert call_order[line1_global][1] == "Will remove: ~/.buildcrew-dash/"
    assert call_order[line2_global][1] == "Will remove: ~/.local/bin/buildcrew-dash"
    assert line1_global < line2_global < input_idx


def test_hp08_uninstall_input_exact_prompt():
    """HP-08: 'uninstall' calls input() with exactly 'Continue? [y/N] ' (trailing space)."""
    with patch("sys.argv", [PROG, "uninstall"]), \
         patch("builtins.input", return_value="n") as mock_input, \
         patch("builtins.print"):
        with pytest.raises(SystemExit):
            main()

    mock_input.assert_called_once_with("Continue? [y/N] ")


# ---------------------------------------------------------------------------
# ERR: Error Handling
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("response", ["n", "", "yes", "YES"])
def test_err_uninstall_aborts_no_removal(response, capsys):
    """ERR-01..ERR-04: Non-confirming input → 'Aborted.', exits 0, rmtree/unlink never called."""
    with patch("sys.argv", [PROG, "uninstall"]), \
         patch("builtins.input", return_value=response), \
         patch("shutil.rmtree") as mock_rmtree, \
         patch("pathlib.Path.unlink") as mock_unlink:
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "Aborted." in captured.out
    mock_rmtree.assert_not_called()
    mock_unlink.assert_not_called()


def test_err05_eoferror_aborts(capsys):
    """ERR-05: EOFError from input() → treated as empty (aborted), exits 0, no file removal."""
    with patch("sys.argv", [PROG, "uninstall"]), \
         patch("builtins.input", side_effect=EOFError()), \
         patch("shutil.rmtree") as mock_rmtree, \
         patch("pathlib.Path.unlink") as mock_unlink:
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "Aborted." in captured.out
    mock_rmtree.assert_not_called()
    mock_unlink.assert_not_called()


@pytest.mark.parametrize("arg", ["--help", "-h", "help", "foo"])
def test_err_unknown_arg_exits_one(arg, capsys):
    """ERR-06..ERR-09: Unknown arg → usage error on stdout, exits 1."""
    with patch("sys.argv", [PROG, arg]):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert f"Unknown command: {arg}" in captured.out
    assert "Usage: buildcrew-dash [update|uninstall]" in captured.out


# ---------------------------------------------------------------------------
# EDGE: Edge Cases
# ---------------------------------------------------------------------------


def test_edge01_update_extra_args_ignored():
    """EDGE-01: 'update' with extra trailing args — behaves identically to no-extra-args."""
    mock_result = MagicMock()
    mock_result.returncode = 0

    with patch("sys.argv", [PROG, "update", "--verbose"]), \
         patch("subprocess.run", return_value=mock_result) as mock_run, \
         patch("builtins.print"):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 0
    mock_run.assert_called_once()


def test_edge02_uninstall_extra_args_ignored():
    """EDGE-02: 'uninstall' with extra trailing args — behaves identically to no-extra-args."""
    with patch("sys.argv", [PROG, "uninstall", "--force"]), \
         patch("builtins.input", return_value="y"), \
         patch("shutil.rmtree") as mock_rmtree, \
         patch("pathlib.Path.unlink"):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 0
    mock_rmtree.assert_called_once()


def test_edge03_rmtree_called_with_ignore_errors_true():
    """EDGE-03: shutil.rmtree called with ignore_errors=True (keyword arg must be present)."""
    with patch("sys.argv", [PROG, "uninstall"]), \
         patch("builtins.input", return_value="y"), \
         patch("shutil.rmtree") as mock_rmtree, \
         patch("pathlib.Path.unlink"):
        with pytest.raises(SystemExit):
            main()

    _, kwargs = mock_rmtree.call_args
    assert kwargs.get("ignore_errors") is True


def test_edge04_rmtree_called_on_correct_path():
    """EDGE-04: shutil.rmtree called on Path.home() / '.buildcrew-dash'."""
    with patch("sys.argv", [PROG, "uninstall"]), \
         patch("builtins.input", return_value="y"), \
         patch("shutil.rmtree") as mock_rmtree, \
         patch("pathlib.Path.unlink"):
        with pytest.raises(SystemExit):
            main()

    args, _ = mock_rmtree.call_args
    assert args[0] == Path.home() / ".buildcrew-dash"


def test_edge04_unlink_called_with_missing_ok_true(tmp_path):
    """EDGE-04: unlink called with missing_ok=True on the correct file path."""
    bcd_dir = tmp_path / ".buildcrew-dash"
    bcd_dir.mkdir()
    bcd_bin = tmp_path / ".local" / "bin" / "buildcrew-dash"
    bcd_bin.parent.mkdir(parents=True)
    bcd_bin.touch()

    # Use autospec so self (the Path object) is captured as first arg
    with patch("sys.argv", [PROG, "uninstall"]), \
         patch("builtins.input", return_value="y"), \
         patch("pathlib.Path.home", return_value=tmp_path), \
         patch.object(Path, "unlink", autospec=True) as mock_unlink, \
         patch("shutil.rmtree"):
        with pytest.raises(SystemExit):
            main()

    mock_unlink.assert_called_once()
    call_self, = mock_unlink.call_args[0]
    assert call_self == tmp_path / ".local" / "bin" / "buildcrew-dash"
    assert mock_unlink.call_args[1].get("missing_ok") is True


def test_edge05_success_print_after_removal_calls():
    """EDGE-05: 'buildcrew-dash uninstalled.' is printed only after both rmtree and unlink."""
    call_log = []

    def fake_rmtree(*args, **kwargs):
        call_log.append("rmtree")

    def fake_print(*args, **kwargs):
        call_log.append(("print", args[0] if args else ""))

    with patch("sys.argv", [PROG, "uninstall"]), \
         patch("builtins.input", return_value="y"), \
         patch("shutil.rmtree", side_effect=fake_rmtree), \
         patch("pathlib.Path.unlink", side_effect=lambda *a, **kw: call_log.append("unlink")), \
         patch("builtins.print", side_effect=fake_print):
        with pytest.raises(SystemExit):
            main()

    rmtree_idx = call_log.index("rmtree")
    unlink_idx = call_log.index("unlink")
    success_idx = next(
        i for i, entry in enumerate(call_log)
        if isinstance(entry, tuple) and entry[0] == "print"
        and entry[1] and "buildcrew-dash uninstalled." in entry[1]
    )
    assert rmtree_idx < success_idx, "rmtree must be called before success print"
    assert unlink_idx < success_idx, "unlink must be called before success print"


def test_edge06_update_subprocess_called_with_check_false():
    """EDGE-06: subprocess.run called with check=False (not check=True which would raise)."""
    mock_result = MagicMock()
    mock_result.returncode = 0

    with patch("sys.argv", [PROG, "update"]), \
         patch("subprocess.run", return_value=mock_result) as mock_run, \
         patch("builtins.print"):
        with pytest.raises(SystemExit):
            main()

    _, kwargs = mock_run.call_args
    assert kwargs.get("check") is False


def test_edge06_update_exact_subprocess_command():
    """EDGE-06b: subprocess.run called with the exact command list from spec."""
    mock_result = MagicMock()
    mock_result.returncode = 0

    with patch("sys.argv", [PROG, "update"]), \
         patch("subprocess.run", return_value=mock_result) as mock_run, \
         patch("builtins.print"):
        with pytest.raises(SystemExit):
            main()

    args, _ = mock_run.call_args
    assert args[0] == ["bash", "-c", EXACT_UPDATE_CMD]


# ---------------------------------------------------------------------------
# ADV: Adversarial / Unexpected Usage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("response", ["y\n", "  y  "])
def test_adv_uninstall_y_with_whitespace_confirms(response):
    """ADV-01..ADV-02: 'y' with trailing newline or surrounding spaces — confirms."""
    with patch("sys.argv", [PROG, "uninstall"]), \
         patch("builtins.input", return_value=response), \
         patch("shutil.rmtree") as mock_rmtree, \
         patch("pathlib.Path.unlink"), \
         patch("builtins.print"):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 0
    mock_rmtree.assert_called_once()


def test_adv03_padded_n_aborts():
    """ADV-03: ' N ' (padded N) — strip+lower='n' != 'y', so aborts."""
    with patch("sys.argv", [PROG, "uninstall"]), \
         patch("builtins.input", return_value=" N "), \
         patch("shutil.rmtree") as mock_rmtree, \
         patch("pathlib.Path.unlink") as mock_unlink, \
         patch("builtins.print"):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 0
    mock_rmtree.assert_not_called()
    mock_unlink.assert_not_called()


def test_adv04_large_returncode_propagated():
    """ADV-04: update subprocess returns returncode=255 → sys.exit(255)."""
    mock_result = MagicMock()
    mock_result.returncode = 255

    with patch("sys.argv", [PROG, "update"]), \
         patch("subprocess.run", return_value=mock_result), \
         patch("builtins.print"):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 255


def test_adv05_rmtree_never_called_on_abort():
    """ADV-05: rmtree is never called on the abort path — not even with wrong args."""
    with patch("sys.argv", [PROG, "uninstall"]), \
         patch("builtins.input", return_value="n"), \
         patch("shutil.rmtree") as mock_rmtree, \
         patch("pathlib.Path.unlink") as mock_unlink, \
         patch("builtins.print"):
        with pytest.raises(SystemExit):
            main()

    mock_rmtree.assert_not_called()
    mock_unlink.assert_not_called()
