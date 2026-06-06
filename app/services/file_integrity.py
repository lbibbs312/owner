"""File integrity helpers for uploaded packet media."""
from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path):
    """Return the SHA-256 hash for an existing file path."""
    file_path = Path(path)
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
