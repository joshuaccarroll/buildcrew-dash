from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal


@dataclass
class PhaseRecord:
    name: str
    status: Literal["active", "complete", "failed", "skipped"]
    verdict: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    task_num: int = 0


@dataclass
class LogSummary:
    pid: int
    project_path: Path
    start_time: datetime | None
    flags: dict[str, str]
    phases: list[PhaseRecord]
    completed_tasks: list[str]
    last_write_time: datetime
    recent_lines: list[str]


def parse(log_path: Path) -> LogSummary:
    if not log_path.exists():
        raise FileNotFoundError(log_path)

    pid = int(log_path.stem.rsplit("-", 1)[-1])
    project_path = log_path.resolve().parent.parent.parent

    try:
        last_write_time = datetime.fromtimestamp(log_path.stat().st_mtime)
        lines = log_path.read_text().splitlines()
    except (PermissionError, UnicodeDecodeError):
        return LogSummary(
            pid=0,
            project_path=log_path.resolve().parent.parent.parent,
            start_time=datetime.now(),
            flags={},
            phases=[],
            completed_tasks=[],
            last_write_time=datetime.now(),
            recent_lines=["(log unreadable)"],
        )

    start_time: datetime | None = None
    flags: dict[str, str] = {}
    phases: list[PhaseRecord] = []
    completed_tasks: list[str] = []
    flags_found = False
    start_time_found = False
    current_task_num = 1

    for line in lines:
        if not line.startswith("[") or "]" not in line:
            continue

        bracket_end = line.index("]")
        ts_str = line[1:bracket_end]
        content = line[bracket_end + 2:]

        ts = datetime.fromisoformat(ts_str)

        if not start_time_found and "BuildCrew started (PID=" in content:
            start_time = ts
            start_time_found = True
            continue

        if not flags_found and "Flags: " in content and "[INFO]" not in content:
            after_flags = content.split("Flags: ", 1)[1]
            for token in after_flags.split():
                if "=" in token:
                    k, v = token.split("=", 1)
                    flags[k] = v
            flags_found = True
            continue

        if "=== PHASE:" in content and " started " in content:
            name = content.split(" started ", 1)[0][11:]
            phases.append(PhaseRecord(name=name, status="active", started_at=ts, task_num=current_task_num))
            continue

        if "=== PHASE:" in content and " ended " in content:
            name = content.split(" ended ", 1)[0][11:]
            verdict = content.split("verdict: ", 1)[1].split(")", 1)[0]
            for rec in reversed(phases):
                if rec.name == name and rec.status == "active":
                    rec.status = "complete"
                    rec.verdict = verdict
                    rec.ended_at = ts
                    break
            continue

        if "=== PHASE:" in content and " retry " in content:
            continue

        if "[INFO] Skipping phase:" in content:
            name = content.split("Skipping phase: ", 1)[1].split()[0]
            phases.append(PhaseRecord(name=name, status="skipped", task_num=current_task_num))
            continue

        if content.startswith("[OK] Completed: "):
            text = content[len("[OK] Completed: "):].strip()
            if text not in completed_tasks:
                completed_tasks.append(text)
            current_task_num += 1

    recent_lines = [l for l in lines if l.strip()][-20:]

    return LogSummary(
        pid=pid,
        project_path=project_path,
        start_time=start_time,
        flags=flags,
        phases=phases,
        completed_tasks=completed_tasks,
        last_write_time=last_write_time,
        recent_lines=recent_lines,
    )
