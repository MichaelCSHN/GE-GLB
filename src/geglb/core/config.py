from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BusConfig:
    length_m: float
    width_m: float
    height_m: float


@dataclass(frozen=True)
class CameraConfig:
    camera_id: str
    mount: str
    yaw_deg: float
    tilt_deg: float
    roll_deg: float
    horizontal_fov_deg: float
    z_offset_from_roof_m: float = -0.15
    position_m: tuple[float, float, float] | None = None


@dataclass(frozen=True)
class GroundTruthConfig:
    enabled: bool
    camera_id: str
    height_m: float
    horizontal_fov_deg: float


@dataclass(frozen=True)
class RouteConfig:
    placemark_name: str
    capture_spacing_m: float


@dataclass(frozen=True)
class CaptureConfig:
    image_width: int
    image_height: int
    fly_duration_s: float
    settle_seconds: float
    sunlight_enabled: bool


@dataclass(frozen=True)
class FusionConfig:
    history_frames: int
    include_all_history_cameras: bool
    bootstrap_first_frame_from_future: bool


@dataclass(frozen=True)
class ProjectConfig:
    name: str
    bus: BusConfig
    cameras: tuple[CameraConfig, ...]
    ground_truth: GroundTruthConfig
    route: RouteConfig
    capture: CaptureConfig
    fusion: FusionConfig


def _positive(name: str, value: float) -> float:
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")
    return value


def load_config(path: str | Path) -> ProjectConfig:
    config_path = Path(path)
    with config_path.open("rb") as stream:
        raw = tomllib.load(stream)

    bus_raw = raw["bus"]
    bus = BusConfig(
        length_m=_positive("bus.length_m", float(bus_raw["length_m"])),
        width_m=_positive("bus.width_m", float(bus_raw["width_m"])),
        height_m=_positive("bus.height_m", float(bus_raw["height_m"])),
    )

    camera_items: list[CameraConfig] = []
    seen_ids: set[str] = set()
    for item in raw.get("cameras", []):
        camera_id = str(item["id"])
        if camera_id in seen_ids:
            raise ValueError(f"duplicate camera id: {camera_id}")
        seen_ids.add(camera_id)
        position = item.get("position_m")
        camera_items.append(
            CameraConfig(
                camera_id=camera_id,
                mount=str(item.get("mount", "custom")),
                yaw_deg=float(item.get("yaw_deg", 0.0)),
                tilt_deg=float(item.get("tilt_deg", 50.0)),
                roll_deg=float(item.get("roll_deg", 0.0)),
                horizontal_fov_deg=float(item.get("horizontal_fov_deg", 100.0)),
                z_offset_from_roof_m=float(item.get("z_offset_from_roof_m", -0.15)),
                position_m=tuple(float(v) for v in position) if position else None,
            )
        )
    if not camera_items:
        raise ValueError("at least one [[cameras]] entry is required")
    for camera in camera_items:
        if not 1.0 < camera.horizontal_fov_deg < 179.0:
            raise ValueError(f"camera {camera.camera_id} FOV must be between 1 and 179 degrees")
        if camera.position_m is not None and len(camera.position_m) != 3:
            raise ValueError(f"camera {camera.camera_id} position_m must contain x, y, z")

    gt_raw = raw.get("ground_truth", {})
    ground_truth = GroundTruthConfig(
        enabled=bool(gt_raw.get("enabled", True)),
        camera_id=str(gt_raw.get("id", "gt_nadir")),
        height_m=_positive("ground_truth.height_m", float(gt_raw.get("height_m", 25.0))),
        horizontal_fov_deg=float(gt_raw.get("horizontal_fov_deg", 60.0)),
    )
    if not 1.0 < ground_truth.horizontal_fov_deg < 179.0:
        raise ValueError("ground_truth.horizontal_fov_deg must be between 1 and 179 degrees")

    route_raw = raw.get("route", {})
    route = RouteConfig(
        placemark_name=str(route_raw.get("placemark_name", "ROUTE")),
        capture_spacing_m=_positive(
            "route.capture_spacing_m", float(route_raw.get("capture_spacing_m", 0.5))
        ),
    )

    capture_raw = raw.get("capture", {})
    capture = CaptureConfig(
        image_width=int(capture_raw.get("image_width", 1920)),
        image_height=int(capture_raw.get("image_height", 1080)),
        fly_duration_s=max(0.0, float(capture_raw.get("fly_duration_s", 0.15))),
        settle_seconds=max(0.0, float(capture_raw.get("settle_seconds", 2.5))),
        sunlight_enabled=bool(capture_raw.get("sunlight_enabled", False)),
    )
    if capture.image_width <= 0 or capture.image_height <= 0:
        raise ValueError("capture image dimensions must be positive")

    fusion_raw = raw.get("fusion", {})
    fusion = FusionConfig(
        history_frames=int(fusion_raw.get("history_frames", 1)),
        include_all_history_cameras=bool(fusion_raw.get("include_all_history_cameras", True)),
        bootstrap_first_frame_from_future=bool(
            fusion_raw.get("bootstrap_first_frame_from_future", True)
        ),
    )
    if fusion.history_frames < 1:
        raise ValueError("fusion.history_frames must be at least 1")

    return ProjectConfig(
        name=str(raw.get("project", {}).get("name", config_path.stem)),
        bus=bus,
        cameras=tuple(camera_items),
        ground_truth=ground_truth,
        route=route,
        capture=capture,
        fusion=fusion,
    )
