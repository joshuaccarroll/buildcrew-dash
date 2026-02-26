from pathlib import Path


def is_stop_pending(project_path: Path) -> bool:
    return (project_path / ".buildcrew" / ".stop-workflow").exists()


def request_stop(project_path: Path) -> None:
    (project_path / ".buildcrew").mkdir(parents=True, exist_ok=True)
    (project_path / ".buildcrew" / ".stop-workflow").touch()


def cancel_stop(project_path: Path) -> None:
    (project_path / ".buildcrew" / ".stop-workflow").unlink(missing_ok=True)
