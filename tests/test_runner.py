"""Tests for outcome classification and argv building."""

import asyncio
import shutil
from pathlib import Path

import pytest

from app.fet.options import FetOptions
from app.fet.runner import FetRunner, Outcome, classify_stdout

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_classify_success():
    assert classify_stdout(_read("stdout_success.txt"), 0) is Outcome.SUCCESS


def test_classify_impossible():
    assert classify_stdout(_read("stdout_impossible.txt"), 0) is Outcome.IMPOSSIBLE


def test_classify_timeout():
    assert classify_stdout(_read("stdout_timeout.txt"), 0) is Outcome.TIMEOUT


def test_classify_failure_marker_outranks_success():
    # A run that printed a progress "successful" line but ended impossible.
    text = "Generation successful so far...\nImpossible to schedule.\n"
    assert classify_stdout(text, 0) is Outcome.IMPOSSIBLE


def test_classify_no_marker_is_error():
    assert classify_stdout("nothing useful here", 1) is Outcome.ERROR
    assert classify_stdout("", 0) is Outcome.ERROR


def test_build_argv_includes_managed_and_user_flags():
    runner = FetRunner(binary="fet-cl")
    argv = runner.build_argv(
        Path("/work/data.fet"),
        Path("/work/output"),
        FetOptions(timelimitseconds=60),
    )
    assert argv[0] == "fet-cl"
    assert "--inputfile=/work/data.fet" in argv
    assert "--outputdir=/work/output" in argv
    assert "--timelimitseconds=60" in argv


@pytest.mark.integration
def test_real_fet_cl_runs(tmp_path):
    """Runs the real fet-cl binary on the bundled sample, if available."""
    if shutil.which("fet-cl") is None:
        pytest.skip("fet-cl binary not on PATH")
    sample = Path(__file__).resolve().parents[1] / "examples" / "sample.fet"
    workdir = tmp_path / "job"
    workdir.mkdir()
    shutil.copy(sample, workdir / "sample.fet")

    runner = FetRunner()
    result = asyncio.run(runner.run(
        input_file=workdir / "sample.fet",
        workdir=workdir,
        options=FetOptions(timelimitseconds=30),
    ))
    assert result.outcome in {Outcome.SUCCESS, Outcome.IMPOSSIBLE, Outcome.TIMEOUT}
    assert result.output_dir.is_dir()
