from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return default


@dataclass
class AgentActivity:
    tool: str = ""
    tool_input: str = ""
    turn: int = 0
    max_turns: int = 0
    status: str = ""
    timestamp: int = 0


def read(path: str | Path) -> AgentActivity | None:
    p = Path(path)
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

    return AgentActivity(
        tool=data.get("tool", ""),
        tool_input=data.get("tool_input", ""),
        turn=_safe_int(data.get("turn")),
        max_turns=_safe_int(data.get("max_turns")),
        status=data.get("status", ""),
        timestamp=_safe_int(data.get("timestamp")),
    )


@dataclass
class VerifyStatus:
    security: bool = False
    tests: bool = False
    outcome: bool = False


def _is_current(path: Path, phase_start: datetime | None) -> bool:
    """Check if file exists and was written during the current phase."""
    if not path.exists():
        return False
    if phase_start is None:
        return True
    return datetime.fromtimestamp(path.stat().st_mtime) >= phase_start


def read_verify_status(project_path: Path, phase_start: datetime | None = None) -> VerifyStatus:
    claude_dir = project_path / ".claude"
    return VerifyStatus(
        security=_is_current(claude_dir / "security-audit.md", phase_start),
        tests=_is_current(claude_dir / "verify-evidence.md", phase_start),
        outcome=_is_current(claude_dir / "outcome-report.md", phase_start),
    )
