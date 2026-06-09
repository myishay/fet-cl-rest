"""Package a fet-cl run's output directory into a downloadable zip."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path


def zip_directory(root: Path) -> bytes:
    """Zip every file under ``root``, preserving paths relative to ``root``.

    Returns the archive as bytes (results are small — HTML/XML/CSV text), which
    keeps the API layer free of temp-file bookkeeping.
    """
    if not root.is_dir():
        raise FileNotFoundError(f"Output directory not found: {root}")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                zf.write(path, arcname=str(path.relative_to(root)))
    return buffer.getvalue()
