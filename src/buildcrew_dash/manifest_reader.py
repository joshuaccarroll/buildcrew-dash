from __future__ import annotations

import functools
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class BatchTask:
    index: int
    text: str
    slug: str
    branch: str
    worktree: str
    status: str  # pending, running, completed, failed, interrupted
    exit_code: int | None = None
    started_at: str | None = None
    completed_at: str | None = None


@dataclass
class BatchManifest:
    batch_id: str
    base_branch: str
    base_commit: str
    max_parallel: int
    started_at: str
    tasks: list[BatchTask] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.tasks)

    @functools.cached_property
    def _status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for t in self.tasks:
            counts[t.status] = counts.get(t.status, 0) + 1
        return counts

    @property
    def pending_count(self) -> int:
        return self._status_counts.get("pending", 0)

    @property
    def running_count(self) -> int:
        return self._status_counts.get("running", 0)

    @property
    def completed_count(self) -> int:
        return self._status_counts.get("completed", 0)

    @property
    def failed_count(self) -> int:
        return self._status_counts.get("failed", 0)

    @property
    def interrupted_count(self) -> int:
        return self._status_counts.get("interrupted", 0)

    @property
    def verify_failed_count(self) -> int:
        return self._status_counts.get("verify_failed", 0)

    @property
    def merge_conflict_count(self) -> int:
        return self._status_counts.get("merge_conflict", 0)

    def summary_parts(self, rich: bool = False) -> list[str]:
        """Return non-zero status counts as formatted strings."""
        entries = [
            (self.running_count, "running", None),
            (self.completed_count, "done", "green" if rich else None),
            (self.failed_count, "failed", "red" if rich else None),
            (self.verify_failed_count, "verify failed", "red" if rich else None),
            (self.merge_conflict_count, "conflict", "yellow" if rich else None),
            (self.interrupted_count, "interrupted", "yellow" if rich else None),
            (self.pending_count, "pending", None),
        ]
        parts = []
        for count, label, color in entries:
            if count:
                text = f"{count} {label}"
                parts.append(f"[{color}]{text}[/{color}]" if color else text)
        return parts


def read(project_path: str | Path) -> BatchManifest | None:
    """Read .buildcrew/batch/manifest.json. Returns None if missing/invalid."""
    p = Path(project_path) / ".buildcrew" / "batch" / "manifest.json"
    try:
        text = p.read_text()
    except (FileNotFoundError, PermissionError):
        return None

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None

    try:
        tasks = [
            BatchTask(
                index=t["index"],
                text=t["text"],
                slug=t["slug"],
                branch=t["branch"],
                worktree=t["worktree"],
                status=t["status"],
                exit_code=t.get("exit_code"),
                started_at=t.get("started_at"),
                completed_at=t.get("completed_at"),
            )
            for t in data["tasks"]
        ]
        return BatchManifest(
            batch_id=data["batch_id"],
            base_branch=data["base_branch"],
            base_commit=data["base_commit"],
            max_parallel=data["max_parallel"],
            started_at=data["started_at"],
            tasks=tasks,
        )
    except (KeyError, TypeError):
        return None
