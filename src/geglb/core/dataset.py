from __future__ import annotations

import json
import math
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .config import ProjectConfig
from .coordinates import LocalFrame


DATASET_SCHEMA = "ge-glb.dataset/v1"


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, records: Iterable[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def read_jsonl(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON in {path}:{line_number}: {exc}") from exc
    return records


def _vehicle_to_world(pose: object, east: float, north: float) -> list[list[float]]:
    heading = math.radians(float(getattr(pose, "heading_deg")))
    return [
        [math.sin(heading), -math.cos(heading), 0.0, east],
        [math.cos(heading), math.sin(heading), 0.0, north],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def write_standard_dataset(
    output: Path,
    config: ProjectConfig,
    model: Any,
    source_kind: str,
    source_metadata: dict[str, object],
    backend_artifacts: list[str],
) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=True)
    origin = model.poses[0]
    frame = LocalFrame(origin.longitude_deg, origin.latitude_deg)

    trajectory: list[dict[str, object]] = []
    pose_by_index = {pose.index: pose for pose in model.poses}
    for pose in model.poses:
        east, north, up = frame.to_local(pose.longitude_deg, pose.latitude_deg)
        trajectory.append(
            {
                "frame_index": pose.index,
                "distance_m": pose.distance_m,
                "geodetic": {
                    "longitude_deg": pose.longitude_deg,
                    "latitude_deg": pose.latitude_deg,
                    "altitude_m": 0.0,
                },
                "local_enu_m": {"east": east, "north": north, "up": up},
                "heading_deg": pose.heading_deg,
                "vehicle_to_world": _vehicle_to_world(pose, east, north),
            }
        )

    frames: list[dict[str, object]] = []
    for entry in model.entries:
        pose_index = int(entry["pose_index"])
        pose = pose_by_index[pose_index]
        state = entry["camera"]
        if not isinstance(state, dict):
            raise TypeError("capture entry camera must be a mapping")
        east, north, _ = frame.to_local(
            float(state["longitude_deg"]), float(state["latitude_deg"])
        )
        frames.append(
            {
                "sequence": entry["sequence"],
                "frame_index": pose_index,
                "distance_m": pose.distance_m,
                "camera_id": entry["camera_id"],
                "image": entry["output"],
                "status": "planned",
                "ground_truth_only": bool(entry.get("ground_truth_only", False)),
                "camera_world": {
                    "local_enu_m": {
                        "east": east,
                        "north": north,
                        "up": float(state["altitude_relative_m"]),
                    },
                    "heading_deg": state["heading_deg"],
                    "tilt_from_nadir_deg": state["tilt_deg"],
                    "roll_deg": state["roll_deg"],
                    "horizontal_fov_deg": state["horizontal_fov_deg"],
                },
            }
        )

    manifest = {
        "schema_version": DATASET_SCHEMA,
        "project": config.name,
        "source": {"kind": source_kind, **source_metadata},
        "status": "planned",
        "coordinate_system": {
            "world": "local_enu_m",
            "vehicle": "x_forward_y_left_z_up",
            "camera": "x_right_y_down_z_forward",
            "origin": {
                "longitude_deg": origin.longitude_deg,
                "latitude_deg": origin.latitude_deg,
                "altitude_m": 0.0,
            },
        },
        "counts": {
            "trajectory_frames": len(trajectory),
            "image_frames": len(frames),
            "reconstruction_cameras": len(config.cameras),
        },
        "files": {
            "rig": "rig.json",
            "trajectory": "trajectory.jsonl",
            "frames": "frames.jsonl",
            "fusion_plan": "fusion-plan.json",
            "backend_artifacts": backend_artifacts,
        },
    }
    write_json(output / "manifest.json", manifest)
    write_json(output / "rig.json", model.calibration)
    write_jsonl(output / "trajectory.jsonl", trajectory)
    write_jsonl(output / "frames.jsonl", frames)
    write_json(output / "fusion-plan.json", model.fusion_plan)
    return manifest


def validate_dataset(dataset_dir: str | Path, require_images: bool = False) -> dict[str, object]:
    root = Path(dataset_dir)
    errors: list[str] = []
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return {"valid": False, "errors": ["manifest.json is missing"], "warnings": []}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != DATASET_SCHEMA:
        errors.append(f"unsupported schema_version: {manifest.get('schema_version')!r}")

    required = ["rig.json", "trajectory.jsonl", "frames.jsonl", "fusion-plan.json"]
    for relative in required:
        if not (root / relative).is_file():
            errors.append(f"{relative} is missing")
    if errors:
        return {"valid": False, "errors": errors, "warnings": []}

    rig = json.loads((root / "rig.json").read_text(encoding="utf-8"))
    trajectories = read_jsonl(root / "trajectory.jsonl")
    frames = read_jsonl(root / "frames.jsonl")
    camera_ids = {str(item["id"]) for item in rig.get("cameras", [])}
    ground_truth = rig.get("ground_truth")
    if isinstance(ground_truth, dict):
        camera_ids.add(str(ground_truth["id"]))
    trajectory_ids = {int(item["frame_index"]) for item in trajectories}
    seen: set[tuple[int, str]] = set()
    missing_images: list[str] = []
    for item in frames:
        key = (int(item["frame_index"]), str(item["camera_id"]))
        if key in seen:
            errors.append(f"duplicate frame/camera pair: {key}")
        seen.add(key)
        if key[0] not in trajectory_ids:
            errors.append(f"frame {key} has no trajectory pose")
        if key[1] not in camera_ids:
            errors.append(f"frame {key} uses an unknown camera")
        image = PurePosixPath(str(item["image"]))
        if image.is_absolute() or ".." in image.parts:
            errors.append(f"unsafe image path: {image}")
        elif not (root / Path(*image.parts)).is_file():
            missing_images.append(str(image))
    if require_images and missing_images:
        errors.append(f"{len(missing_images)} image files are missing")

    warnings = [] if not missing_images else [f"{len(missing_images)} planned images are not present"]
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "source_kind": manifest.get("source", {}).get("kind"),
        "trajectory_frames": len(trajectories),
        "image_frames": len(frames),
        "missing_images": len(missing_images),
    }
