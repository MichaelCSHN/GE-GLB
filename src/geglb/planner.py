from __future__ import annotations

import csv
import json
from pathlib import Path

from .config import ProjectConfig
from .fusion import build_fusion_plan
from .kml import build_capture_tour
from .rig import (
    camera_calibration,
    camera_state_for_pose,
    ground_truth_state_for_pose,
    intrinsics,
    state_as_dict,
)
from .route import load_route_kml, resample_route


def build_plan(config: ProjectConfig, route_kml: str | Path, output_dir: str | Path) -> dict[str, object]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    points = load_route_kml(route_kml, config.route.placemark_name)
    poses = resample_route(points, config.route.capture_spacing_m)

    ordered_states = []
    plan_entries: list[dict[str, object]] = []
    sequence = 0
    for pose in poses:
        for camera in config.cameras:
            state = camera_state_for_pose(pose, camera, config.bus)
            ordered_states.append((pose, state))
            plan_entries.append(
                {
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
            )
            sequence += 1
        if config.ground_truth.enabled:
            state = ground_truth_state_for_pose(pose, config.ground_truth)
            ordered_states.append((pose, state))
            plan_entries.append(
                {
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
                    "ground_truth_only": True,
                }
            )
            sequence += 1

    with (output / "poses.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["index", "distance_m", "longitude_deg", "latitude_deg", "heading_deg"],
        )
        writer.writeheader()
        for pose in poses:
            writer.writerow(
                {
                    "index": pose.index,
                    "distance_m": f"{pose.distance_m:.4f}",
                    "longitude_deg": f"{pose.longitude_deg:.10f}",
                    "latitude_deg": f"{pose.latitude_deg:.10f}",
                    "heading_deg": f"{pose.heading_deg:.8f}",
                }
            )

    calibration: dict[str, object] = {
        "schema_version": 1,
        "project": config.name,
        "vehicle_frame": "x_forward_y_left_z_up",
        "bus": {
            "length_m": config.bus.length_m,
            "width_m": config.bus.width_m,
            "height_m": config.bus.height_m,
        },
        "cameras": [camera_calibration(camera, config.bus, config.capture) for camera in config.cameras],
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
            "intrinsics": intrinsics(config.ground_truth.horizontal_fov_deg, config.capture),
            "use_for_reconstruction": False,
        }
    (output / "calibration.json").write_text(
        json.dumps(calibration, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    plan = {
        "schema_version": 1,
        "project": config.name,
        "route_spacing_m": config.route.capture_spacing_m,
        "pose_count": len(poses),
        "capture_count": len(plan_entries),
        "entries": plan_entries,
    }
    (output / "capture-plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    fusion_plan = build_fusion_plan(poses, config.cameras, config.fusion)
    (output / "fusion-plan.json").write_text(
        json.dumps(fusion_plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    tour = build_capture_tour(config.name, poses, ordered_states, config.capture)
    tour.write(output / "capture-tour.kml", encoding="utf-8", xml_declaration=True)

    return {
        "output_dir": str(output.resolve()),
        "route_points": len(points),
        "poses": len(poses),
        "captures": len(plan_entries),
        "fusion_targets": len(fusion_plan["targets"]),
        "camera_ids": [camera.camera_id for camera in config.cameras]
        + ([config.ground_truth.camera_id] if config.ground_truth.enabled else []),
    }
