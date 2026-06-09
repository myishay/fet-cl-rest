"""Query the installed fet-cl version (best-effort)."""

from __future__ import annotations

import functools
import re
import subprocess


@functools.lru_cache
def get_fet_cl_version(binary: str = "fet-cl") -> str:
    """Return the fet-cl version string, or 'unknown' if it can't be determined."""
    try:
        proc = subprocess.run(
            [binary, "--version"],
            capture_output=True, text=True, timeout=15,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return "unknown"
    text = (proc.stdout or "") + (proc.stderr or "")
    match = re.search(r"\b\d+\.\d+\.\d+\b", text)
    return match.group() if match else (text.strip().splitlines()[0] if text.strip() else "unknown")
