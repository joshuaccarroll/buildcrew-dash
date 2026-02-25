from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from dataclasses import dataclass
from glob import glob
from pathlib import Path


_PGREP_UNAVAILABLE: bool = False
_LSOF_UNAVAILABLE: bool = False


@dataclass
class BuildCrewInstance:
    pid: int
    project_path: Path
    log_path: Path


class ProcessScanner:
    def scan(self) -> list[BuildCrewInstance]:
        global _PGREP_UNAVAILABLE
        try:
            result = subprocess.run(["pgrep", "-f", "buildcrew"], capture_output=True, text=True)
        except FileNotFoundError:
            _PGREP_UNAVAILABLE = True
            return []
        if result.returncode != 0 or not result.stdout.strip():
            return []

        results: list[BuildCrewInstance] = []
        seen_logs: set[Path] = set()

        for pid_str in result.stdout.splitlines():
            pid_str = pid_str.strip()
            if not pid_str:
                continue
            try:
                if int(pid_str) == os.getpid():
                    continue

                try:
                    lsof_result = subprocess.run(
                        ["lsof", "-p", pid_str, "-a", "-d", "cwd"],
                        capture_output=True, text=True,
                    )
                except FileNotFoundError:
                    global _LSOF_UNAVAILABLE
                    _LSOF_UNAVAILABLE = True
                    continue
                if lsof_result.returncode != 0:
                    continue

                cwd = None
                lines = lsof_result.stdout.splitlines()
                for line in lines[1:]:
                    tokens = line.split()
                    if len(tokens) >= 4 and tokens[3] == "cwd":
                        cwd = tokens[-1]
                        break
                if cwd is None:
                    continue

                matches = sorted(glob(f"{cwd}/.buildcrew/logs/buildcrew-*-{pid_str}.log"))
                if not matches:
                    continue

                log_path = Path(matches[0])

                try:
                    ps_result = subprocess.run(
                        ["ps", "-p", pid_str, "-o", "args="],
                        capture_output=True, text=True,
                    )
                    if ps_result.returncode == 0 and "buildcrew-dash" in ps_result.stdout:
                        continue
                except Exception:
                    pass  # keep PID

                if log_path in seen_logs:
                    continue
                seen_logs.add(log_path)

                results.append(BuildCrewInstance(
                    pid=int(pid_str),
                    project_path=Path(cwd),
                    log_path=log_path,
                ))
            except Exception as e:
                print(e, file=sys.stderr)
                continue

        return results


class ProcessMonitor:
    def __init__(self, scanner: ProcessScanner) -> None:
        self._scanner = scanner
        self._known: dict[Path, BuildCrewInstance] = {}

    async def poll(self) -> tuple[list[BuildCrewInstance], list[BuildCrewInstance]]:
        new_results: list[BuildCrewInstance] = await asyncio.get_running_loop().run_in_executor(
            None, self._scanner.scan
        )
        added = [inst for inst in new_results if inst.log_path not in self._known]
        removed = [inst for inst in self._known.values() if inst.log_path not in {i.log_path for i in new_results}]
        self._known = {inst.log_path: inst for inst in new_results}
        return (added, removed)
