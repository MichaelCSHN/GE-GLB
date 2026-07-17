"""Content hashing utilities for GE-GLB datasets and provenance."""

from __future__ import annotations

import hashlib
from pathlib import Path


def file_sha256(path: str | Path) -> str:
    """Return the SHA-256 hex digest of *path*.

    The result is prefixed ``"sha256:"`` for schema compatibility::

        >>> file_sha256("rig.json")
        "sha256:abc123..."
    """
    p = Path(path)
    sha = hashlib.sha256()
    with p.open("rb") as stream:
        while True:
            chunk = stream.read(1 << 20)  # 1 MiB
            if not chunk:
                break
            sha.update(chunk)
    return f"sha256:{sha.hexdigest()}"


def dir_sha256(path: str | Path) -> dict[str, str]:
    """Return a mapping of relative-path → SHA-256 for every regular
    file under *path* (recursive).

    Paths use forward slashes as separators.
    """
    root = Path(path)
    result: dict[str, str] = {}
    for entry in sorted(root.rglob("*")):
        if not entry.is_file():
            continue
        relative = entry.relative_to(root).as_posix()
        result[relative] = file_sha256(entry)
    return result
