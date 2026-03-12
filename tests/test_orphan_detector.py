"""Tests for orphan_detector module."""
import os
import signal
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from buildcrew_dash.orphan_detector import (
    CleanResult,
    OrphanedInstance,
    _read_lock_pid,
    clean,
    scan,
    seed_projects,
)


_LSOF_HEADER = "COMMAND   PID  USER   FD   TYPE DEVICE SIZE/OFF NODE NAME\n"


def _make_result(stdout="", returncode=0):
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    return m


def _lsof_output(cwd: str) -> str:
    return f"{_LSOF_HEADER}python  12345  user  cwd    DIR    8,1     4096    2 {cwd}\n"


# ---------------------------------------------------------------------------
# _read_lock_pid
# ---------------------------------------------------------------------------

def test_stale_lock_dead_pid(tmp_path):
    """Stale lock with dead PID is detected."""
    lock = tmp_path / ".buildcrew" / ".workflow-lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("99999")
    with patch("buildcrew_dash.orphan_detector.os.kill", side_effect=ProcessLookupError):
        pid, stale = _read_lock_pid(lock)
    assert pid == 99999
    assert stale is True


def test_live_lock_pid_not_flagged(tmp_path):
    """Live lock PID is not flagged as stale."""
    lock = tmp_path / ".buildcrew" / ".workflow-lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("12345")
    with patch("buildcrew_dash.orphan_detector.os.kill", return_value=None):
        pid, stale = _read_lock_pid(lock)
    assert pid == 12345
    assert stale is False


def test_corrupt_lock_file(tmp_path):
    """Corrupt/empty lock file is treated as stale."""
    lock = tmp_path / ".buildcrew" / ".workflow-lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("")
    pid, stale = _read_lock_pid(lock)
    assert pid is None
    assert stale is True

    lock.write_text("notanumber")
    pid, stale = _read_lock_pid(lock)
    assert pid is None
    assert stale is True


def test_permission_error_on_kill(tmp_path):
    """PermissionError on os.kill → skip (not stale, process alive under different user)."""
    lock = tmp_path / ".buildcrew" / ".workflow-lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("12345")
    with patch("buildcrew_dash.orphan_detector.os.kill", side_effect=PermissionError):
        pid, stale = _read_lock_pid(lock)
    assert pid == 12345
    assert stale is False


# ---------------------------------------------------------------------------
# scan()
# ---------------------------------------------------------------------------

def test_scan_stale_lock_detected(tmp_path):
    """Stale lock → orphan detected with correct files."""
    bc = tmp_path / ".buildcrew"
    bc.mkdir()
    (bc / ".workflow-lock").write_text("99999")
    (bc / ".workflow-state").write_text("x")

    with patch("buildcrew_dash.orphan_detector.os.kill", side_effect=ProcessLookupError), \
         patch("buildcrew_dash.orphan_detector.subprocess.run", side_effect=[
             _make_result(returncode=1),  # pgrep: no results
         ]):
        result = scan({tmp_path})

    assert len(result) == 1
    assert result[0].lock_pid == 99999
    assert result[0].project_path == tmp_path
    assert (bc / ".workflow-lock") in result[0].files_to_remove
    assert (bc / ".workflow-state") in result[0].files_to_remove
    assert "Stale lock PID 99999" in result[0].summary


def test_scan_live_lock_skipped(tmp_path):
    """Live lock → no orphan."""
    bc = tmp_path / ".buildcrew"
    bc.mkdir()
    (bc / ".workflow-lock").write_text("12345")

    with patch("buildcrew_dash.orphan_detector.os.kill", return_value=None):
        result = scan({tmp_path})

    assert result == []


def test_scan_orphaned_process_detected(tmp_path):
    """Orphaned process (ppid=1, cwd matches) detected."""
    bc = tmp_path / ".buildcrew"
    bc.mkdir()
    (bc / ".workflow-lock").write_text("99999")

    own_pid = os.getpid()
    orphan_pid = "55555"
    assert own_pid != 55555

    with patch("buildcrew_dash.orphan_detector.os.kill", side_effect=ProcessLookupError), \
         patch("buildcrew_dash.orphan_detector.subprocess.run", side_effect=[
             # pgrep
             _make_result(stdout=f"{orphan_pid}\n", returncode=0),
             # ps for buildcrew-dash check
             _make_result(stdout="claude --some-arg", returncode=0),
             # lsof for cwd
             _make_result(stdout=_lsof_output(str(tmp_path)), returncode=0),
             # ps for ppid
             _make_result(stdout="1", returncode=0),
         ]):
        result = scan({tmp_path})

    assert len(result) == 1
    assert 55555 in result[0].pids_to_kill
    assert "1 detached proc" in result[0].summary


def test_scan_process_ppid_not_1_not_flagged(tmp_path):
    """Process with ppid != 1 is not flagged as orphaned."""
    bc = tmp_path / ".buildcrew"
    bc.mkdir()
    (bc / ".workflow-lock").write_text("99999")

    with patch("buildcrew_dash.orphan_detector.os.kill", side_effect=ProcessLookupError), \
         patch("buildcrew_dash.orphan_detector.subprocess.run", side_effect=[
             _make_result(stdout="55555\n", returncode=0),  # pgrep
             _make_result(stdout="claude --arg", returncode=0),  # ps args
             _make_result(stdout=_lsof_output(str(tmp_path)), returncode=0),  # lsof
             _make_result(stdout="1234", returncode=0),  # ppid != 1
         ]):
        result = scan({tmp_path})

    assert len(result) == 1
    assert result[0].pids_to_kill == []


def test_scan_process_unrelated_cwd_not_flagged(tmp_path):
    """Process in unrelated cwd is not flagged."""
    bc = tmp_path / ".buildcrew"
    bc.mkdir()
    (bc / ".workflow-lock").write_text("99999")

    with patch("buildcrew_dash.orphan_detector.os.kill", side_effect=ProcessLookupError), \
         patch("buildcrew_dash.orphan_detector.subprocess.run", side_effect=[
             _make_result(stdout="55555\n", returncode=0),  # pgrep
             _make_result(stdout="claude --arg", returncode=0),  # ps args
             _make_result(stdout=_lsof_output("/some/other/path"), returncode=0),  # lsof: different cwd
         ]):
        result = scan({tmp_path})

    assert len(result) == 1
    assert result[0].pids_to_kill == []


# ---------------------------------------------------------------------------
# clean()
# ---------------------------------------------------------------------------

def test_clean_sigterm_then_sigkill(tmp_path):
    """Cleanup: SIGTERM then SIGKILL for survivors."""
    bc = tmp_path / ".buildcrew"
    bc.mkdir()
    lock = bc / ".workflow-lock"
    lock.write_text("99999")
    state_file = bc / ".workflow-state"
    state_file.write_text("x")

    orphan = OrphanedInstance(
        project_path=tmp_path,
        lock_pid=99999,
        pids_to_kill=[55555],
        files_to_remove=[lock, state_file],
        summary="test",
    )

    kill_calls = []

    def mock_kill(pid, sig):
        kill_calls.append((pid, sig))
        if sig == 0:
            return  # alive
        if sig == signal.SIGTERM:
            return  # sent
        if sig == signal.SIGKILL:
            return  # sent

    with patch("buildcrew_dash.orphan_detector.os.kill", side_effect=mock_kill), \
         patch("buildcrew_dash.orphan_detector.subprocess.run", side_effect=[
             _make_result(stdout="1", returncode=0),  # ppid check
             _make_result(stdout=_lsof_output(str(tmp_path)), returncode=0),  # lsof cwd
         ]), \
         patch("buildcrew_dash.orphan_detector.time.sleep"):
        result = clean(orphan)

    assert result.killed == 1
    assert result.files_removed == 2
    assert result.skipped_reason is None
    # Check signals sent: os.kill(55555, 0), SIGTERM, os.kill(55555, 0), SIGKILL
    assert (55555, 0) in kill_calls
    assert (55555, signal.SIGTERM) in kill_calls


def test_clean_race_guard_lock_changed(tmp_path):
    """Race guard: lock content changed → abort."""
    bc = tmp_path / ".buildcrew"
    bc.mkdir()
    lock = bc / ".workflow-lock"
    lock.write_text("11111")  # different from orphan.lock_pid

    orphan = OrphanedInstance(
        project_path=tmp_path,
        lock_pid=99999,
        pids_to_kill=[55555],
        files_to_remove=[lock],
        summary="test",
    )

    result = clean(orphan)
    assert result.skipped_reason == "lock PID changed"
    assert result.killed == 0
    assert result.files_removed == 0


def test_clean_pid_reuse_guard(tmp_path):
    """PID reuse guard: different cwd → not killed."""
    bc = tmp_path / ".buildcrew"
    bc.mkdir()
    lock = bc / ".workflow-lock"
    lock.write_text("99999")

    orphan = OrphanedInstance(
        project_path=tmp_path,
        lock_pid=99999,
        pids_to_kill=[55555],
        files_to_remove=[lock],
        summary="test",
    )

    with patch("buildcrew_dash.orphan_detector.os.kill", return_value=None), \
         patch("buildcrew_dash.orphan_detector.subprocess.run", side_effect=[
             _make_result(stdout="1", returncode=0),  # ppid
             _make_result(stdout=_lsof_output("/different/path"), returncode=0),  # cwd differs
         ]):
        result = clean(orphan)

    assert result.killed == 0
    assert result.files_removed == 1  # lock file still removed


# ---------------------------------------------------------------------------
# seed_projects()
# ---------------------------------------------------------------------------

def test_seed_projects_finds_lock_files(tmp_path):
    """Cold-start seeding finds lock files."""
    proj = tmp_path / "myproject"
    bc = proj / ".buildcrew"
    bc.mkdir(parents=True)
    (bc / ".workflow-lock").write_text("123")

    with patch("buildcrew_dash.orphan_detector.Path.cwd", return_value=tmp_path):
        result = seed_projects()

    assert proj in result


def test_seed_projects_env_var(tmp_path):
    """BUILDCREW_PROJECTS env var paths are scanned."""
    proj = tmp_path / "envproject"
    bc = proj / ".buildcrew"
    bc.mkdir(parents=True)
    (bc / ".workflow-lock").write_text("123")

    with patch("buildcrew_dash.orphan_detector.Path.cwd", return_value=Path("/nonexistent")), \
         patch.dict(os.environ, {"BUILDCREW_PROJECTS": str(proj)}):
        result = seed_projects()

    assert proj in result
