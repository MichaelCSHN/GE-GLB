from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .config import ProjectConfig


class CaptureBackend(Protocol):
    """A pluggable image source that emits a GE-GLB dataset."""

    backend_id: str

    def plan(
        self,
        config: ProjectConfig,
        route: str | Path,
        output_dir: str | Path,
    ) -> dict[str, object]: ...


class StitchBackend(Protocol):
    """A source-independent consumer of a validated GE-GLB dataset."""

    stitcher_id: str

    def run(self, dataset_dir: str | Path, output_dir: str | Path) -> dict[str, object]: ...
