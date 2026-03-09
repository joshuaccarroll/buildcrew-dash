"""Orphaned process detection and cleanup for buildcrew instances."""
from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class OrphanedInstance:
    project_path: Path
    lock_pid: int | None  # PID from lock file (None if corrupt)
    pids_to_kill: list[int]  # orphaned child processes
    files_to_remove: list[Path]  # stale state files
    summary: str  # pre-computed description for UI


@dataclass
class CleanResult:
    killed: int
    files_removed: int
    skipped_reason: str | None


_STALE_FILES = [
    ".buildcrew/.workflow-lock",
    ".buildcrew/.workflow-state",
    ".buildcrew/.agent-activity",
    ".buildcrew/.current-task",
    ".buildcrew/.stop-workflow",
    ".buildcrew/task-progress.json",
]


def _parse_lsof_cwd(lsof_stdout: str) -> str | None:
    """Extract cwd path from lsof output. Returns None if not found."""
    for line in lsof_stdout.splitlines()[1:]:
        tokens = line.split()
        if len(tokens) >= 4 and tokens[3] == "cwd":
            return tokens[-1]
    return None


def _cwd_matches_project(cwd: str, project_path: Path) -> bool:
    """Check if cwd matches or is under project_path."""
    project_str = str(project_path)
    return cwd == project_str or cwd.startswith(project_str + "/")


def _read_lock_pid(lock_path: Path) -> tuple[int | None, bool]:
    """Read PID from lock file. Returns (pid_or_None, is_stale)."""
    try:
        text = lock_path.read_text().strip()
    except (FileNotFoundError, PermissionError):
        return None, False  # file gone, not stale

    if not text or not text.isdigit():
        return None, True  # corrupt → stale

    pid = int(text)
    try:
        os.kill(pid, 0)
        return pid, False  # alive → not stale
    except ProcessLookupError:
        return pid, True  # dead → stale
    except PermissionError:
        return pid, False  # alive (different user) → not stale


def _find_orphaned_pids(project_path: Path) -> tuple[list[int], str | None]:
    """Find orphaned child processes whose cwd is under project_path."""
    pids_to_kill: list[int] = []
    permission_note: str | None = None

    try:
        result = subprocess.run(
            ["pgrep", "-f", "claude|stream_processor|tail -f"],
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        return [], None
    if result.returncode != 0 or not result.stdout.strip():
        return [], None

    own_pid = os.getpid()
    project_str = str(project_path)

    for pid_str in result.stdout.splitlines():
        pid_str = pid_str.strip()
        if not pid_str or not pid_str.isdigit():
            continue
        pid = int(pid_str)
        if pid == own_pid:
            continue

        # Filter out buildcrew-dash processes
        try:
            ps_result = subprocess.run(
                ["ps", "-p", pid_str, "-o", "args="],
                capture_output=True, text=True,
            )
            if ps_result.returncode == 0 and "buildcrew-dash" in ps_result.stdout:
                continue
        except Exception:
            pass

        # Check cwd via lsof
        try:
            lsof_result = subprocess.run(
                ["lsof", "-p", pid_str, "-a", "-d", "cwd"],
                capture_output=True, text=True,
            )
        except FileNotFoundError:
            continue
        except PermissionError:
            permission_note = "some processes inaccessible"
            continue
        if lsof_result.returncode != 0:
            continue

        cwd = _parse_lsof_cwd(lsof_result.stdout)
        if cwd is None:
            continue

        # Check if cwd matches or is under the stale project
        if not _cwd_matches_project(cwd, project_path):
            continue

        # Check if ppid == 1 (orphaned/reparented)
        try:
            ppid_result = subprocess.run(
                ["ps", "-p", pid_str, "-o", "ppid="],
                capture_output=True, text=True,
            )
            if ppid_result.returncode != 0:
                continue
            ppid = ppid_result.stdout.strip()
            if ppid != "1":
                continue
        except Exception:
            continue

        pids_to_kill.append(pid)

    return pids_to_kill, permission_note


def scan(known_projects: set[Path]) -> list[OrphanedInstance]:
    """Scan known projects for orphaned instances with stale lock files."""
    orphans: list[OrphanedInstance] = []

    for project_path in known_projects:
        lock_path = project_path / ".buildcrew" / ".workflow-lock"
        if not lock_path.exists():
            continue

        lock_pid, is_stale = _read_lock_pid(lock_path)
        if not is_stale:
            continue

        # Collect stale files
        files_to_remove: list[Path] = []
        for rel in _STALE_FILES:
            f = project_path / rel
            if f.exists():
                files_to_remove.append(f)

        # Find orphaned child processes
        pids_to_kill, permission_note = _find_orphaned_pids(project_path)

        # Build summary
        parts: list[str] = []
        if lock_pid is not None:
            parts.append(f"Stale lock PID {lock_pid}")
        else:
            parts.append("Corrupt lock file")
        if pids_to_kill:
            parts.append(f"{len(pids_to_kill)} detached proc{'s' if len(pids_to_kill) != 1 else ''}")
        if permission_note:
            parts.append(permission_note)
        summary = ", ".join(parts)

        orphans.append(OrphanedInstance(
            project_path=project_path,
            lock_pid=lock_pid,
            pids_to_kill=pids_to_kill,
            files_to_remove=files_to_remove,
            summary=summary,
        ))

    return orphans


def clean(orphan: OrphanedInstance) -> CleanResult:
    """Clean up an orphaned instance. Re-verifies state before acting."""
    lock_path = orphan.project_path / ".buildcrew" / ".workflow-lock"

    # Re-check lock file
    if not lock_path.exists():
        return CleanResult(killed=0, files_removed=0, skipped_reason="lock file gone")

    try:
        text = lock_path.read_text().strip()
    except (FileNotFoundError, PermissionError):
        return CleanResult(killed=0, files_removed=0, skipped_reason="lock file inaccessible")

    if orphan.lock_pid is not None:
        if not text.isdigit() or int(text) != orphan.lock_pid:
            return CleanResult(killed=0, files_removed=0, skipped_reason="lock PID changed")
    else:
        # Was corrupt; if it now has a valid PID, abort
        if text.isdigit():
            return CleanResult(killed=0, files_removed=0, skipped_reason="lock PID changed")

    # Re-verify and kill PIDs
    verified_pids: list[int] = []
    for pid in orphan.pids_to_kill:
        try:
            os.kill(pid, 0)  # still alive?
        except (ProcessLookupError, PermissionError):
            continue

        # Check ppid still 1
        try:
            ppid_result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "ppid="],
                capture_output=True, text=True,
            )
            if ppid_result.returncode != 0 or ppid_result.stdout.strip() != "1":
                continue
        except Exception:
            continue

        # Check cwd still under project (PID reuse guard)
        try:
            lsof_result = subprocess.run(
                ["lsof", "-p", str(pid), "-a", "-d", "cwd"],
                capture_output=True, text=True,
            )
            if lsof_result.returncode != 0:
                continue
            cwd = _parse_lsof_cwd(lsof_result.stdout)
            if cwd is None:
                continue
            if not _cwd_matches_project(cwd, orphan.project_path):
                continue
        except Exception:
            continue

        verified_pids.append(pid)

    killed = 0
    for pid in verified_pids:
        try:
            os.kill(pid, signal.SIGTERM)
            killed += 1
        except (ProcessLookupError, PermissionError):
            pass

    if verified_pids:
        time.sleep(2)
        for pid in verified_pids:
            try:
                os.kill(pid, 0)  # still alive?
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

    # Delete stale files
    files_removed = 0
    for f in orphan.files_to_remove:
        try:
            f.unlink()
            files_removed += 1
        except (FileNotFoundError, PermissionError):
            pass

    return CleanResult(killed=killed, files_removed=files_removed, skipped_reason=None)


def seed_projects() -> set[Path]:
    """Cold-start seeding: find projects with lock files in common locations."""
    projects: set[Path] = set()

    # Children of cwd
    cwd = Path.cwd()
    try:
        for lock in cwd.glob("*/.buildcrew/.workflow-lock"):
            projects.add(lock.parent.parent)
    except OSError:
        pass

    # Children of parent of cwd
    parent = cwd.parent
    try:
        for lock in parent.glob("*/.buildcrew/.workflow-lock"):
            projects.add(lock.parent.parent)
    except OSError:
        pass

    # BUILDCREW_PROJECTS env var (colon-separated)
    env_projects = os.environ.get("BUILDCREW_PROJECTS", "")
    if env_projects:
        for p in env_projects.split(":"):
            p = p.strip()
            if p:
                path = Path(p)
                if (path / ".buildcrew" / ".workflow-lock").exists():
                    projects.add(path)

    return projects
