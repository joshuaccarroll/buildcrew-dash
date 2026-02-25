from dataclasses import dataclass
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
        data[key] = value

    return AgentActivity(
        tool=data.get("tool", ""),
        tool_input=data.get("tool_input", ""),
        turn=_safe_int(data.get("turn")),
        max_turns=_safe_int(data.get("max_turns")),
        status=data.get("status", ""),
        timestamp=_safe_int(data.get("timestamp")),
    )
