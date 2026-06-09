"""Run ``fet-cl`` as a subprocess and classify its outcome.

fet-cl's exit codes are coarse: it returns 0 for a successful generation, an
impossible (over-constrained) problem, *and* a time-limit/interrupted run; it
returns 1 only for argument/setup errors. The real outcome therefore has to be
read from stdout (mirrored to ``logs/result.txt``). This module encapsulates
that classification so the web layer never parses CLI text itself.
"""

from __future__ import annotations

import asyncio
import os
import re
import signal
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from app.fet.options import FetOptions


class Outcome(str, Enum):
    SUCCESS = "success"
    IMPOSSIBLE = "impossible"
    TIMEOUT = "timeout"
    ERROR = "error"


# stdout markers (verbatim from FET) → outcome. Order matters: check the
# failure markers before success because a run can print progress lines too.
_MARKERS: list[tuple[re.Pattern[str], Outcome]] = [
    (re.compile(r"Generation successful", re.IGNORECASE), Outcome.SUCCESS),
    (re.compile(r"\bImpossible\b", re.IGNORECASE), Outcome.IMPOSSIBLE),
    (re.compile(r"Time\s*exceeded", re.IGNORECASE), Outcome.TIMEOUT),
    (re.compile(r"Generation\s*interrupted", re.IGNORECASE), Outcome.TIMEOUT),
]


def classify_stdout(stdout: str, exit_code: Optional[int]) -> Outcome:
    """Map fet-cl stdout (+ exit code) to an :class:`Outcome`.

    A failure marker (Impossible / Time exceeded) outranks a success marker, so
    the failure patterns return immediately while success is only used as a
    fallback once we know no failure marker is present.
    """
    saw_success = False
    for pattern, outcome in _MARKERS:
        if pattern.search(stdout):
            if outcome is Outcome.SUCCESS:
                saw_success = True
            else:
                return outcome
    if saw_success:
        return Outcome.SUCCESS
    return Outcome.ERROR


@dataclass
class RunResult:
    outcome: Outcome
    exit_code: Optional[int]
    stdout: str
    stderr: str
    output_dir: Path
    timetable_dir: Optional[Path] = None
    soft_conflicts: Optional[str] = None
    placed_activities: Optional[int] = None
    warnings: list[str] = field(default_factory=list)


class FetRunner:
    """Builds argv, runs fet-cl in a workdir, and reports a :class:`RunResult`."""

    def __init__(self, binary: str = "fet-cl", hard_timeout_buffer: int = 60):
        self.binary = binary
        # Wall-clock guard added on top of fet-cl's own --timelimitseconds so a
        # wedged process can't run forever.
        self.hard_timeout_buffer = hard_timeout_buffer

    def build_argv(self, input_file: Path, output_dir: Path,
                   options: FetOptions) -> list[str]:
        return [
            self.binary,
            f"--inputfile={input_file}",
            f"--outputdir={output_dir}",
            *options.to_args(),
        ]

    async def run(self, input_file: Path, workdir: Path,
                  options: FetOptions,
                  on_process: Optional[callable] = None) -> RunResult:
        """Run fet-cl. ``workdir`` holds the output; the input lives in it too.

        ``on_process`` (if given) is called with the live
        ``asyncio.subprocess.Process`` so callers can cancel it.
        """
        output_dir = workdir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        argv = self.build_argv(input_file, output_dir, options)

        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(workdir),
            start_new_session=True,  # own process group → clean SIGTERM
        )
        if on_process is not None:
            on_process(proc)

        wall_timeout = None
        if options.timelimitseconds is not None:
            wall_timeout = options.timelimitseconds + self.hard_timeout_buffer

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=wall_timeout
            )
        except asyncio.TimeoutError:
            self._terminate(proc)
            stdout_b, stderr_b = b"", b"hard wall-clock timeout exceeded"
            return RunResult(
                outcome=Outcome.TIMEOUT,
                exit_code=None,
                stdout=stdout_b.decode("utf-8", "replace"),
                stderr=stderr_b.decode("utf-8", "replace"),
                output_dir=output_dir,
            )

        stdout = stdout_b.decode("utf-8", "replace")
        stderr = stderr_b.decode("utf-8", "replace")
        exit_code = proc.returncode

        result_txt = output_dir / "logs" / "result.txt"
        if result_txt.exists():
            stdout = stdout + "\n" + result_txt.read_text("utf-8", "replace")

        outcome = classify_stdout(stdout, exit_code)
        result = RunResult(
            outcome=outcome,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            output_dir=output_dir,
        )
        self._enrich(result, input_file, output_dir)
        return result

    @staticmethod
    def _terminate(proc: "asyncio.subprocess.Process") -> None:
        if proc.returncode is not None:
            return
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            try:
                proc.terminate()
            except ProcessLookupError:
                pass

    def _enrich(self, result: RunResult, input_file: Path,
                output_dir: Path) -> None:
        """Attach soft-conflict text / placed-activity counts when available."""
        name = input_file.stem  # FET names the results folder after the input
        tt_dir = output_dir / "timetables" / name
        if tt_dir.is_dir():
            result.timetable_dir = tt_dir
            soft = tt_dir / "soft_conflicts.txt"
            if soft.exists():
                result.soft_conflicts = soft.read_text("utf-8", "replace")

        logs = output_dir / "logs"
        placed = logs / "max_placed_activities.txt"
        if placed.exists():
            m = re.search(r"\d+", placed.read_text("utf-8", "replace"))
            if m:
                result.placed_activities = int(m.group())

        warnings = logs / "warnings.txt"
        if warnings.exists():
            text = warnings.read_text("utf-8", "replace").strip()
            if text:
                result.warnings = [ln for ln in text.splitlines() if ln.strip()]
