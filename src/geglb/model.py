from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import ProjectConfig
from .fusion import build_fusion_plan
from .rig import (
    CameraState,
    camera_calibration,
    camera_state_for_pose,
    ground_truth_state_for_pose,
    intrinsics,
    camera_to_vehicle_transform,
    state_as_dict,
)
from .route import RoutePoint, VehiclePose, load_route_kml, resample_route


@dataclass(frozen=True)
class CaptureModel:
    route_points: list[RoutePoint]
    poses: list[VehiclePose]
    ordered_states: list[tuple[VehiclePose, CameraState]]
    entries: list[dict[str, object]]
    calibration: dict[str, object]
    fusion_plan: dict[str, object]


def build_capture_model(config: ProjectConfig, route_kml: str | Path) -> CaptureModel:
    points = load_route_kml(route_kml, config.route.placemark_name)
    poses = resample_route(points, config.route.capture_spacing_m)

    ordered_states: list[tuple[VehiclePose, CameraState]] = []
    entries: list[dict[str, object]] = []
    sequence = 0
    for pose in poses:
        for camera in config.cameras:
            state = camera_state_for_pose(pose, camera, config.bus)
            ordered_states.append((pose, state))
            entries.append(_entry(sequence, pose, state, ground_truth_only=False))
            sequence += 1
        if config.ground_truth.enabled:
            state = ground_truth_state_for_pose(pose, config.ground_truth)
            ordered_states.append((pose, state))
            entries.append(_entry(sequence, pose, state, ground_truth_only=True))
            sequence += 1

    calibration: dict[str, object] = {
        "schema_version": "ge-glb.rig/v1",
        "project": config.name,
        "vehicle_frame": "x_forward_y_left_z_up",
        "camera_frame": "x_right_y_down_z_forward",
        "bus": {
            "length_m": config.bus.length_m,
            "width_m": config.bus.width_m,
            "height_m": config.bus.height_m,
        },
        "cameras": [
            camera_calibration(camera, config.bus, config.capture)
            for camera in config.cameras
        ],
    }
    if config.ground_truth.enabled:
        calibration["ground_truth"] = {
            "id": config.ground_truth.camera_id,
            "vehicle_frame": {
                "x_forward_m": 0.0,
                "y_left_m": 0.0,
                "z_up_m": config.ground_truth.height_m,
            },
            "orientation": {"tilt_from_nadir_deg": 0.0, "roll_deg": 0.0},
            "camera_to_vehicle": camera_to_vehicle_transform(
                (0.0, 0.0, config.ground_truth.height_m), 0.0, 0.0, 0.0
            ),
            "intrinsics": intrinsics(
                config.ground_truth.horizontal_fov_deg, config.capture
            ),
            "use_for_reconstruction": False,
        }

    return CaptureModel(
        route_points=points,
        poses=poses,
        ordered_states=ordered_states,
        entries=entries,
        calibration=calibration,
        fusion_plan=build_fusion_plan(poses, config.cameras, config.fusion),
    )


def _entry(
    sequence: int,
    pose: VehiclePose,
    state: CameraState,
    ground_truth_only: bool,
) -> dict[str, object]:
    result: dict[str, object] = {
        "sequence": sequence,
        "pose_index": pose.index,
        "distance_m": pose.distance_m,
        "camera_id": state.camera_id,
        "output": f"images/{state.camera_id}/{pose.index:06d}.png",
        "vehicle": {
            "longitude_deg": pose.longitude_deg,
            "latitude_deg": pose.latitude_deg,
            "heading_deg": pose.heading_deg,
        },
        "camera": state_as_dict(state),
    }
    if ground_truth_only:
        result["ground_truth_only"] = True
    return result
