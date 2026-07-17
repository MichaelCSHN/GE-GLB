"""V2 run-configuration loader for the ``geglb run`` command.

Consumes a TOML file and produces a ``RunConfig`` that bundles
task identity, bus dimensions, capture settings, and task-specific
spec parameters.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .config import BusConfig, CaptureConfig

_VALID_TASKS = ("underbody", "panorama", "lookat")


@dataclass(frozen=True)
class RunConfig:
    task: str
    project_name: str
    bus: BusConfig | None
    spec: dict[str, object]
    capture: CaptureConfig


def load_run_config(path: str | Path, task: str = "") -> RunConfig:
    """Parse a ``geglb run`` TOML configuration file.

    *task* may be omitted if the TOML contains a top-level ``task`` key.
    When provided it takes precedence.
    """
    config_path = Path(path)
    with config_path.open("rb") as stream:
        raw = tomllib.load(stream)

    task = task or str(raw.get("task", ""))
    if task not in _VALID_TASKS:
        raise ValueError(f"task must be one of {_VALID_TASKS}, got {task!r}")

    proj = raw.get("project", {})
    project_name = str(proj.get("name", config_path.stem))

    # Bus (underbody and panorama need it).
    bus: BusConfig | None = None
    bus_raw = raw.get("bus")
    if bus_raw is not None:
        bus = BusConfig(
            length_m=_positive("bus.length_m", float(bus_raw["length_m"])),
            width_m=_positive("bus.width_m", float(bus_raw["width_m"])),
            height_m=_positive("bus.height_m", float(bus_raw["height_m"])),
        )

    # Capture config.
    cap_raw = raw.get("capture", {})
    capture = CaptureConfig(
        image_width=int(cap_raw.get("image_width", 1920)),
        image_height=int(cap_raw.get("image_height", 1080)),
        fly_duration_s=max(0.0, float(cap_raw.get("fly_duration_s", 0.0))),
        settle_seconds=max(0.0, float(cap_raw.get("settle_seconds", 0.0))),
        sunlight_enabled=bool(cap_raw.get("sunlight_enabled", False)),
    )
    if capture.image_width <= 0 or capture.image_height <= 0:
        raise ValueError("capture image dimensions must be positive")

    # Spec — everything under [spec] plus the raw [[spec.bands]] arrays.
    spec: dict[str, object] = dict(raw.get("spec", {}))
    # Preserve nested tables-of-arrays that tomllib already parsed.
    for key in list(raw.keys()):
        if key.startswith("spec."):
            spec[key] = raw[key]

    return RunConfig(
        task=task,
        project_name=project_name,
        bus=bus,
        spec=spec,
        capture=capture,
    )


def _positive(name: str, value: float) -> float:
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")
    return value
