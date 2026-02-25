from dataclasses import dataclass
from pathlib import Path


@dataclass
class WorkflowState:
    task_num: int
    total_tasks: int
    task_name: str
    phase: str
    phase_status: str
    invocation_count: int
    max_invocations: int
    timestamp: int

    @property
    def display_invocation_count(self) -> int:
        if self.phase_status == "running":
            return self.invocation_count + 1
        return self.invocation_count


def read(path: str | Path) -> WorkflowState | None:
    p = Path(path)
    if not p.exists():
        return None

    try:
        text = p.read_text()
    except FileNotFoundError:
        return None
    except PermissionError:
        return None

    data: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.lower()] = value

    return WorkflowState(
        task_num=int(data["task_num"]),
        total_tasks=int(data["total_tasks"]),
        task_name=data["task_name"],
        phase=data["phase"],
        phase_status=data["phase_status"],
        invocation_count=int(data["invocation_count"]),
        max_invocations=int(data["max_invocations"]),
        timestamp=int(data["timestamp"]),
    )
