import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from buildcrew_dash.scanner import BuildCrewInstance, ProcessMonitor, ProcessScanner

_LSOF_HEADER = "COMMAND   PID  USER   FD   TYPE DEVICE SIZE/OFF NODE NAME\n"


def _make_result(stdout="", returncode=0):
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    return m


def _lsof_output(cwd: str) -> str:
    return f"{_LSOF_HEADER}python  12345  user  cwd    DIR    8,1     4096    2 {cwd}\n"


def test_pgrep_no_results():
    # AC-01: rc != 0 → []
    with patch("buildcrew_dash.scanner.subprocess.run", side_effect=[
        _make_result(returncode=1),
    ]) as mock_run:
        result = ProcessScanner().scan()
        assert result == []
        assert mock_run.call_count == 1  # lsof not called

    # AC-01: rc=0 but whitespace-only stdout → []
    with patch("buildcrew_dash.scanner.subprocess.run", side_effect=[
        _make_result(stdout="   \n", returncode=0),
    ]) as mock_run:
        result = ProcessScanner().scan()
        assert result == []
        assert mock_run.call_count == 1  # lsof not called


def test_happy_path(tmp_path):
    log_dir = tmp_path / ".buildcrew" / "logs"
    log_dir.mkdir(parents=True)
    log_file = log_dir / "buildcrew-2024-01-15_10-00-00-12345.log"
    log_file.touch()

    with patch("buildcrew_dash.scanner.subprocess.run", side_effect=[
        _make_result(stdout="12345\n", returncode=0),          # pgrep
        _make_result(stdout=_lsof_output(str(tmp_path)), returncode=0),  # lsof
        _make_result(stdout="", returncode=0),                 # ps
    ]):
        result = ProcessScanner().scan()

    assert len(result) == 1
    instance = result[0]
    assert instance.pid == 12345
    assert instance.project_path == tmp_path
    assert instance.log_path == log_file


def test_own_pid_filtered():
    own_pid = os.getpid()
    with patch("buildcrew_dash.scanner.subprocess.run", side_effect=[
        _make_result(stdout=f"{own_pid}\n", returncode=0),
    ]) as mock_run:
        result = ProcessScanner().scan()
        assert result == []
        assert mock_run.call_count == 1  # no lsof call


def test_buildcrew_dash_filtered(tmp_path):
    log_dir = tmp_path / ".buildcrew" / "logs"
    log_dir.mkdir(parents=True)
    log_file = log_dir / "buildcrew-2024-01-15_10-00-00-12345.log"

    with patch("buildcrew_dash.scanner.subprocess.run", side_effect=[
        _make_result(stdout="12345\n", returncode=0),
        _make_result(stdout=_lsof_output(str(tmp_path)), returncode=0),
        _make_result(stdout="/path/to/buildcrew-dash/app.py", returncode=0),
    ]), patch("buildcrew_dash.scanner.glob", return_value=[str(log_file)]):
        result = ProcessScanner().scan()

    assert result == []


def test_lsof_failure():
    with patch("buildcrew_dash.scanner.subprocess.run", side_effect=[
        _make_result(stdout="12345\n", returncode=0),
        _make_result(returncode=1),
    ]) as mock_run:
        result = ProcessScanner().scan()
        assert result == []
        assert mock_run.call_count == 2  # no ps call


def test_no_log_file(tmp_path):
    with patch("buildcrew_dash.scanner.subprocess.run", side_effect=[
        _make_result(stdout="12345\n", returncode=0),
        _make_result(stdout=_lsof_output(str(tmp_path)), returncode=0),
    ]), patch("buildcrew_dash.scanner.glob", return_value=[]):
        result = ProcessScanner().scan()

    assert result == []


def test_dedup_keeps_first_pid(tmp_path):
    assert os.getpid() not in (11111, 22222)

    log_dir = tmp_path / ".buildcrew" / "logs"
    log_dir.mkdir(parents=True)
    shared_log = str(log_dir / "buildcrew-2024-01-15_10-00-00-11111.log")

    with patch("buildcrew_dash.scanner.subprocess.run", side_effect=[
        _make_result(stdout="11111\n22222\n", returncode=0),          # pgrep
        _make_result(stdout=_lsof_output(str(tmp_path)), returncode=0),  # lsof for 11111
        _make_result(stdout="", returncode=0),                         # ps for 11111
        _make_result(stdout=_lsof_output(str(tmp_path)), returncode=0),  # lsof for 22222
        _make_result(stdout="", returncode=0),                         # ps for 22222
    ]), patch("buildcrew_dash.scanner.glob", return_value=[shared_log]):
        result = ProcessScanner().scan()

    assert len(result) == 1
    assert result[0].pid == 11111


def test_lsof_header_only():
    with patch("buildcrew_dash.scanner.subprocess.run", side_effect=[
        _make_result(stdout="12345\n", returncode=0),
        _make_result(stdout=_LSOF_HEADER, returncode=0),
    ]) as mock_run:
        result = ProcessScanner().scan()
        assert result == []
        assert mock_run.call_count == 2  # no ps call


def test_ps_nonzero_keeps_pid(tmp_path):
    log_dir = tmp_path / ".buildcrew" / "logs"
    log_dir.mkdir(parents=True)
    log_file = log_dir / "buildcrew-2024-01-15_10-00-00-12345.log"

    with patch("buildcrew_dash.scanner.subprocess.run", side_effect=[
        _make_result(stdout="12345\n", returncode=0),
        _make_result(stdout=_lsof_output(str(tmp_path)), returncode=0),
        _make_result(stdout="", returncode=1),
    ]), patch("buildcrew_dash.scanner.glob", return_value=[str(log_file)]):
        result = ProcessScanner().scan()

    assert len(result) == 1
    assert result[0].pid == 12345


@pytest.mark.anyio
async def test_monitor_first_poll_one_instance():
    inst = BuildCrewInstance(pid=1, project_path=Path("/proj"), log_path=Path("/proj/.buildcrew/logs/buildcrew-plan-1.log"))
    mock_scanner = MagicMock(spec=ProcessScanner)
    mock_scanner.scan = MagicMock(return_value=[inst])
    mock_loop = MagicMock()
    mock_loop.run_in_executor = AsyncMock(side_effect=lambda ex, fn: fn())

    with patch("buildcrew_dash.scanner.asyncio.get_running_loop", return_value=mock_loop):
        monitor = ProcessMonitor(mock_scanner)
        # AC-01: assert init state before any poll
        assert monitor._scanner is mock_scanner
        assert monitor._known == {}
        assert len(monitor._known) == 0
        assert mock_scanner.scan.call_count == 0
        added, removed = await monitor.poll()

    assert added == [inst]
    assert removed == []
    assert len(monitor._known) == 1
    assert monitor._known[inst.log_path] is inst
    assert mock_loop.run_in_executor.call_count == 1
    assert mock_loop.run_in_executor.call_args == call(None, mock_scanner.scan)
    assert mock_scanner.scan.call_count == 1


@pytest.mark.anyio
async def test_monitor_second_poll_empty():
    inst = BuildCrewInstance(pid=1, project_path=Path("/proj"), log_path=Path("/proj/.buildcrew/logs/buildcrew-plan-1.log"))
    mock_scanner = MagicMock(spec=ProcessScanner)
    mock_scanner.scan = MagicMock(return_value=[inst])
    mock_loop = MagicMock()
    mock_loop.run_in_executor = AsyncMock(side_effect=lambda ex, fn: fn())

    with patch("buildcrew_dash.scanner.asyncio.get_running_loop", return_value=mock_loop):
        monitor = ProcessMonitor(mock_scanner)
        await monitor.poll()  # pre-populate _known
        mock_scanner.scan.return_value = []
        added, removed = await monitor.poll()

    assert added == []
    assert removed == [inst]
    assert monitor._known == {}


@pytest.mark.anyio
async def test_monitor_second_poll_same_instance():
    inst = BuildCrewInstance(pid=1, project_path=Path("/proj"), log_path=Path("/proj/.buildcrew/logs/buildcrew-plan-1.log"))
    mock_scanner = MagicMock(spec=ProcessScanner)
    mock_scanner.scan = MagicMock(return_value=[inst])
    mock_loop = MagicMock()
    mock_loop.run_in_executor = AsyncMock(side_effect=lambda ex, fn: fn())

    with patch("buildcrew_dash.scanner.asyncio.get_running_loop", return_value=mock_loop):
        monitor = ProcessMonitor(mock_scanner)
        await monitor.poll()  # pre-populate _known
        added, removed = await monitor.poll()

    assert added == []
    assert removed == []
    assert len(monitor._known) == 1
    assert monitor._known[inst.log_path] is inst


# ---------------------------------------------------------------------------
# FileNotFoundError guards (ERR-01, ERR-02, EDGE-03, EDGE-04)
# ---------------------------------------------------------------------------


def test_pgrep_file_not_found():
    """ERR-01: pgrep FileNotFoundError sets _PGREP_UNAVAILABLE=True and returns []."""
    import buildcrew_dash.scanner as sm
    orig = sm._PGREP_UNAVAILABLE
    sm._PGREP_UNAVAILABLE = False
    try:
        with patch("buildcrew_dash.scanner.subprocess.run", side_effect=FileNotFoundError("pgrep not found")):
            result = ProcessScanner().scan()
        assert result == []
        assert sm._PGREP_UNAVAILABLE is True
    finally:
        sm._PGREP_UNAVAILABLE = orig


def test_lsof_file_not_found():
    """ERR-02: lsof FileNotFoundError sets _LSOF_UNAVAILABLE=True and skips PID; scan returns []."""
    import buildcrew_dash.scanner as sm
    orig = sm._LSOF_UNAVAILABLE
    sm._LSOF_UNAVAILABLE = False
    try:
        with patch("buildcrew_dash.scanner.subprocess.run", side_effect=[
            _make_result(stdout="12345\n", returncode=0),  # pgrep succeeds
            FileNotFoundError("lsof not found"),            # lsof raises
        ]):
            result = ProcessScanner().scan()
        assert result == []
        assert sm._LSOF_UNAVAILABLE is True
    finally:
        sm._LSOF_UNAVAILABLE = orig


def test_lsof_file_not_found_skips_all_pids():
    """EDGE-03: lsof FileNotFoundError with 2 PIDs — both skipped, _LSOF_UNAVAILABLE=True."""
    assert os.getpid() not in (11111, 22222)
    import buildcrew_dash.scanner as sm
    orig = sm._LSOF_UNAVAILABLE
    sm._LSOF_UNAVAILABLE = False
    try:
        with patch("buildcrew_dash.scanner.subprocess.run", side_effect=[
            _make_result(stdout="11111\n22222\n", returncode=0),  # pgrep: 2 PIDs
            FileNotFoundError("lsof not found"),                   # lsof for 11111
            FileNotFoundError("lsof not found"),                   # lsof for 22222
        ]):
            result = ProcessScanner().scan()
        assert result == []
        assert sm._LSOF_UNAVAILABLE is True
    finally:
        sm._LSOF_UNAVAILABLE = orig


def test_pgrep_file_not_found_no_lsof_call():
    """EDGE-04: pgrep FileNotFoundError causes immediate return — lsof is never called."""
    import buildcrew_dash.scanner as sm
    orig = sm._PGREP_UNAVAILABLE
    sm._PGREP_UNAVAILABLE = False
    call_count = 0

    def _side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise FileNotFoundError("pgrep not found")

    try:
        with patch("buildcrew_dash.scanner.subprocess.run", side_effect=_side_effect):
            result = ProcessScanner().scan()
        assert result == []
        assert call_count == 1  # only pgrep was attempted; lsof never reached
        assert sm._PGREP_UNAVAILABLE is True
    finally:
        sm._PGREP_UNAVAILABLE = orig
