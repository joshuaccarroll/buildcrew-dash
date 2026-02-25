import re
from pathlib import Path

_PENDING_RE = re.compile(r'^- \[ \] (.+)$')
_TAG_RE = re.compile(r'\s*\{(?:trivial|simple|standard)\}\s*$')


def read_pending_tasks(project_path: Path) -> list[str]:
    try:
        text = (project_path / "BACKLOG.md").read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return []

    tasks = []
    for line in text.splitlines():
        m = _PENDING_RE.match(line)
        if not m:
            continue
        name = _TAG_RE.sub('', m.group(1)).strip()
        if name:
            tasks.append(name)
    return tasks
