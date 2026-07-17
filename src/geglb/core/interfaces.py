from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .config import ProjectConfig
from .results import PlanResult


class CaptureBackend(Protocol):
    """A pluggable image source that emits a GE-GLB dataset."""

    backend_id: str

    def plan(
        self,
        config: ProjectConfig,
        route: str | Path,
        output_dir: str | Path,
    ) -> PlanResult: ...
