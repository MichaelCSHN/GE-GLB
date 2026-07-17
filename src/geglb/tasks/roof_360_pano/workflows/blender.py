"""Blender capture workflow for Task 02 Roof 360 Panorama.

Consumes a ``Roof360Spec``, vehicle dimensions, and vehicle poses, then
produces a complete ``ge-glb.dataset/v1`` dataset plus a ``blender-job.json``
that is consumable by ``scripts/blender_capture.py``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from ....core.coordinates import LocalFrame
from ....core.dataset import write_json, write_jsonl
from ....core.results import PlanResult
from ....core.trajectory import VehiclePose
from ..capture_plan import CaptureModel, build_capture_model
from ..specification import Roof360Spec


def build_blender_plan(
    spec: Roof360Spec,
    bus_length_m: float,
    bus_width_m: float,
    bus_height_m: float,
    scene_glb: str | Path,
    output_dir: str | Path,
    horizontal_fov_deg: float = 90.0,
    image_width: int = 1920,
    image_height: int = 1080,
    render_engine: str = "BLENDER_EEVEE_NEXT",
    samples: int = 32,
    transparent_background: bool = False,
    poses: list[VehiclePose] | None = None,
) -> PlanResult:
    """Prepare a deterministic Blender render job for a roof-360 panorama.

    Parameters
    ----------
    spec :
        Band definition and mast height.
    bus_length_m / bus_width_m / bus_height_m :
        Vehicle dimensions in metres.
    scene_glb :
        Path to the input ``.glb`` or ``.gltf`` scene file.
    output_dir :
        Directory where the dataset and Blender job are written.
    horizontal_fov_deg :
        Horizontal field of view for every camera in the plan.
    image_width / image_height :
        Capture resolution in pixels.
    render_engine :
        Blender render engine identifier (e.g. ``BLENDER_EEVEE_NEXT``).
    samples :
        Number of render samples.
    transparent_background :
        When *True*, renders include an alpha channel.
    poses :
        Vehicle poses to sample.  When *None* a single origin pose is used.

    Returns
    -------
    PlanResult
        Structured result with counts, artifact paths, and backend metadata.
    """
    scene = Path(scene_glb).expanduser().resolve()
    if samples <= 0:
        raise ValueError("samples must be positive")
    if scene.suffix.lower() not in {".glb", ".gltf"}:
        raise ValueError("Blender scene must be a .glb or .gltf file")
    if not scene.is_file():
        raise FileNotFoundError(scene)

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    model = build_capture_model(
        spec,
        bus_length_m=bus_length_m,
        bus_width_m=bus_width_m,
        bus_height_m=bus_height_m,
        horizontal_fov_deg=horizontal_fov_deg,
        image_width=image_width,
        image_height=image_height,
        poses=poses,
    )

    _write_roof_dataset(
        output,
        model,
        source_kind="blender",
        source_metadata={
            "adapter": "blender_python",
            "scene_glb": str(scene),
        },
        backend_artifacts=["blender-job.json", "capture-report.jsonl"],
    )

    # Re-read frames in the standard format for the Blender job.
    standard_frames = []
    for line in (output / "frames.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            standard_frames.append(json.loads(line))

    job = {
        "schema_version": "ge-glb.blender-job/v1",
        "project": "task02_roof_360",
        "scene_glb": str(scene),
        "dataset_dir": str(output.resolve()),
        "render": {
            "engine": render_engine,
            "samples": samples,
            "width": image_width,
            "height": image_height,
            "file_format": "PNG",
            "transparent_background": transparent_background,
            "add_default_sun_if_missing": True,
        },
        "frames": standard_frames,
    }
    write_json(output / "blender-job.json", job)
    write_json(
        output / "blender-command.json",
        {
            "executable": "blender",
            "arguments": [
                "--background",
                "--python",
                "scripts/blender_capture.py",
                "--",
                "--job",
                str((output / "blender-job.json").resolve()),
            ],
        },
    )

    return PlanResult(
        workflow_id="TASK02_BLENDER",
        source_kind="blender",
        output_dir=str(output.resolve()),
        counts={
            "poses": len(model.poses),
            "captures": len(model.entries),
        },
        artifacts=("blender-job.json", "blender-command.json"),
        details={"scene_glb": str(scene)},
    )


# ── dataset writer ─────────────────────────────────────────────────────


def _write_roof_dataset(
    output: Path,
    model: CaptureModel,
    source_kind: str,
    source_metadata: dict[str, object],
    backend_artifacts: list[str],
) -> dict[str, object]:
    """Write a ``ge-glb.dataset/v1`` tree for a Roof 360 capture model.

    Mirrors ``core.dataset.write_standard_dataset`` but adapted for the
    Task 02 ``CaptureModel`` which carries no ``route_points`` or
    ``fusion_plan``.
    """
    output.mkdir(parents=True, exist_ok=True)
    origin = model.poses[0]
    frame = LocalFrame(origin.longitude_deg, origin.latitude_deg)

    pose_by_index = {p.index: p for p in model.poses}

    # -- trajectory -------------------------------------------------------
    trajectory: list[dict[str, object]] = []
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

    # -- frames -----------------------------------------------------------
    frames: list[dict[str, object]] = []
    for entry in model.entries:
        pose_idx = int(entry["pose_index"])
        pose = pose_by_index[pose_idx]
        state = entry["camera"]
        cam_east, cam_north, _ = frame.to_local(
            float(state["longitude_deg"]), float(state["latitude_deg"])
        )
        frames.append(
            {
                "sequence": entry["sequence"],
                "frame_index": pose_idx,
                "distance_m": pose.distance_m,
                "camera_id": entry["camera_id"],
                "image": entry["output"],
                "status": "planned",
                "ground_truth_only": bool(entry.get("ground_truth_only", False)),
                "camera_world": {
                    "local_enu_m": {
                        "east": cam_east,
                        "north": cam_north,
                        "up": float(state["altitude_relative_m"]),
                    },
                    "heading_deg": state["heading_deg"],
                    "tilt_from_nadir_deg": state["tilt_deg"],
                    "roll_deg": state["roll_deg"],
                    "horizontal_fov_deg": state["horizontal_fov_deg"],
                },
            }
        )

    # -- calibration (rig) ------------------------------------------------
    rig = dict(model.calibration)

    # -- manifest ---------------------------------------------------------
    manifest = {
        "schema_version": "ge-glb.dataset/v1",
        "project": "task02_roof_360",
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
            "reconstruction_cameras": len(model.calibration["cameras"]),
        },
        "files": {
            "rig": "rig.json",
            "trajectory": "trajectory.jsonl",
            "frames": "frames.jsonl",
            "backend_artifacts": backend_artifacts,
        },
    }

    write_json(output / "manifest.json", manifest)
    write_json(output / "rig.json", rig)
    write_jsonl(output / "trajectory.jsonl", trajectory)
    write_jsonl(output / "frames.jsonl", frames)
    return manifest


# ── helpers ────────────────────────────────────────────────────────────


def _vehicle_to_world(pose: VehiclePose, east: float, north: float) -> list[list[float]]:
    """4×4 vehicle-to-world transform (ENU frame, Z-up)."""
    heading = math.radians(pose.heading_deg)
    return [
        [math.sin(heading), -math.cos(heading), 0.0, east],
        [math.cos(heading), math.sin(heading), 0.0, north],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
