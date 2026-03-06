from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

UAT_STALE_THRESHOLD_SECS = 7200  # 2 hours


@dataclass
class UATState:
    phase: str  # stories|scenarios|harness|setup|execute|verdict|rebuild|complete|failed
    iteration: int
    status: str  # running|pass|fail|error
    timestamp: int
    project_name: str  # needed to locate ~/.buildcrew/uat-signals/<name>/verdict.json


@dataclass
class UATVerdict:
    status: str
    build_iteration: int
    total: int
    passed: int
    failed: int
    errored: int
    disputed: int
    scenarios: list[dict] = field(default_factory=list)


def read_state(project_path: str | Path) -> UATState | None:
    """Read .buildcrew/.uat-state key=value file. Returns None if missing, malformed, or stale."""
    p = Path(project_path) / ".buildcrew" / ".uat-state"
    try:
        text = p.read_text()
    except (FileNotFoundError, PermissionError):
        return None

    data: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key] = value

    try:
        timestamp = int(data["UAT_TIMESTAMP"])
        if time.time() - timestamp > UAT_STALE_THRESHOLD_SECS:
            return None
        return UATState(
            phase=data["UAT_PHASE"],
            iteration=int(data["UAT_ITERATION"]),
            status=data["UAT_STATUS"],
            timestamp=timestamp,
            project_name=data["UAT_PROJECT_NAME"],
        )
    except (KeyError, ValueError):
        return None


def read_verdict(project_name: str) -> UATVerdict | None:
    """Read ~/.buildcrew/uat-signals/<project_name>/verdict.json."""
    p = Path.home() / ".buildcrew" / "uat-signals" / project_name / "verdict.json"
    try:
        text = p.read_text()
    except (FileNotFoundError, PermissionError):
        return None

    try:
        data = json.loads(text)
        return UATVerdict(
            status=data["status"],
            build_iteration=data["build_iteration"],
            total=data["total"],
            passed=data["passed"],
            failed=data["failed"],
            errored=data["errored"],
            disputed=data["disputed"],
            scenarios=data.get("scenarios", []),
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
