"""V2 capture-dataset writer with provenance, hashing, and resumable state.

Produces the shared ``ge-glb.capture-dataset/v2`` run layout defined in
SPEC.md.  Coexists with the v1 ``write_standard_dataset`` writer.
"""

from __future__ import annotations

import datetime
import math
import subprocess
from pathlib import Path

from .coordinates import LocalFrame
from .dataset import DATASET_V2_SCHEMA, write_json, write_jsonl
from .hashing import file_sha256

# published alongside __version__ in __init__.py
_GEGLB_VERSION = "0.3.0"


# ── public API ──────────────────────────────────────────────────────────


def write_capture_dataset_v2(
    output_dir: str | Path,
    task_id: str,
    product_schema: str,
    source_kind: str,
    source_backend: str,
    source_metadata: dict[str, object],
    model: object,
    config_snapshot: dict[str, object],
    dependency_hashes: dict[str, str],
) -> dict[str, object]:
    """Write a complete ``ge-glb.capture-dataset/v2`` run directory.

    Parameters
    ----------
    output_dir :
        Root of the run directory (will be created).
    task_id :
        One of ``"task01_underbody"``, ``"task02_roof_360"``,
        ``"task03_drone_lookat"``.
    product_schema :
        Product schema URI, e.g. ``"ge-glb.product.underbody-image/v1"``.
    source_kind :
        Human-readable source label (``"blender"``, ``"ge3d"``).
    source_backend :
        Normalised backend key (``"blender"``, ``"ge3d"``, ``"real"``).
    source_metadata :
        Backend-specific metadata merged into ``run.json``.
    model :
        A ``CaptureModel`` instance from any task.  Must expose
        ``.poses``, ``.entries``, and ``.calibration``.
    config_snapshot :
        Key/value snapshot of the capture configuration.
    dependency_hashes :
        Mapping of input file path → SHA-256 digest, recorded in
        provenance.

    Returns
    -------
    dict
        Summary containing ``run_dir``, ``status``, ``files``, and
        ``hashes``.
    """
    run_dir = Path(output_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    created_at = _utc_now()
    git_commit = _detect_git_commit()

    # ── directory scaffolding ────────────────────────────────────────
    capture_dir = run_dir / "capture"
    rigs_dir = capture_dir / "rigs"
    trajectories_dir = capture_dir / "trajectories"
    images_dir = capture_dir / "images"
    logs_dir = run_dir / "logs"
    for d in (capture_dir, rigs_dir, trajectories_dir, images_dir, logs_dir):
        d.mkdir(parents=True, exist_ok=True)

    origin = model.poses[0]
    frame = LocalFrame(origin.longitude_deg, origin.latitude_deg)
    pose_by_index = {p.index: p for p in model.poses}

    # ── trajectory ----------------------------------------------------
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
    write_jsonl(trajectories_dir / "trajectory.jsonl", trajectory)

    # ── observations --------------------------------------------------
    observations: list[dict[str, object]] = []
    for entry in model.entries:
        pose_idx = int(entry["pose_index"])
        pose = pose_by_index[pose_idx]
        state = entry["camera"]
        cam_east, cam_north, _ = frame.to_local(
            float(state["longitude_deg"]), float(state["latitude_deg"])
        )
        obs_id = f"{task_id}/{pose.index:06d}/{entry['camera_id']}"

        heading_deg = float(state["heading_deg"])
        tilt_deg = float(state["tilt_deg"])
        roll_deg = float(state.get("roll_deg", 0.0))

        observations.append(
            {
                "observation_id": obs_id,
                "sequence": entry["sequence"],
                "frame_index": pose_idx,
                "camera_id": entry["camera_id"],
                "image": entry["output"],
                "status": entry.get("status", "planned"),
                "ground_truth_only": bool(entry.get("ground_truth_only", False)),
                "camera_world": {
                    "local_enu_m": {
                        "east": cam_east,
                        "north": cam_north,
                        "up": float(state["altitude_relative_m"]),
                    },
                    "heading_deg": heading_deg,
                    "tilt_from_nadir_deg": tilt_deg,
                    "roll_deg": roll_deg,
                    "horizontal_fov_deg": state["horizontal_fov_deg"],
                },
                "camera_to_world": _camera_to_world_matrix(
                    cam_east,
                    cam_north,
                    float(state["altitude_relative_m"]),
                    heading_deg,
                    tilt_deg,
                    roll_deg,
                ),
            }
        )
    write_jsonl(capture_dir / "observations.jsonl", observations)

    # ── rig -----------------------------------------------------------
    write_json(rigs_dir / "rig.json", dict(model.calibration))

    # ── capture-plan.json ---------------------------------------------
    # Serialise the capture plan in a backend-neutral form.
    plan: dict[str, object] = {
        "poses": len(model.poses),
        "entries": len(model.entries),
        "calibration_camera_count": len(model.calibration.get("cameras", [])),
    }
    # Preserve bus / observer metadata when available.
    for key in ("bus", "observer"):
        if key in model.calibration:
            plan[key] = model.calibration[key]
    write_json(run_dir / "capture-plan.json", plan)

    # ── capture/manifest.json -----------------------------------------
    v2_manifest: dict[str, object] = {
        "schema_version": DATASET_V2_SCHEMA,
        "task": {
            "task_id": task_id,
            "product_schema": product_schema,
        },
        "source": {
            "mode": "virtual" if source_backend != "real" else "real",
            "backend": source_backend,
        },
        "status": "planned",
        "files": {
            "rigs": ["rigs/rig.json"],
            "trajectories": ["trajectories/trajectory.jsonl"],
            "observations": "observations.jsonl",
            "images_root": "images/",
        },
    }
    write_json(capture_dir / "manifest.json", v2_manifest)

    # ── hashes of written files ───────────────────────────────────────
    file_hashes: dict[str, str] = {
        "capture/manifest.json": file_sha256(capture_dir / "manifest.json"),
        "capture/observations.jsonl": file_sha256(capture_dir / "observations.jsonl"),
        "capture/rigs/rig.json": file_sha256(rigs_dir / "rig.json"),
        "capture/trajectories/trajectory.jsonl": file_sha256(trajectories_dir / "trajectory.jsonl"),
    }

    # ── run.json ──────────────────────────────────────────────────────
    total_frames = len(observations)
    run_json: dict[str, object] = {
        "schema_version": "ge-glb.run/v2",
        "task_id": task_id,
        "created_at": created_at,
        "geglb_version": _GEGLB_VERSION,
        "git_commit": git_commit,
        "source": {
            "kind": source_kind,
            **source_metadata,
        },
        "configuration": config_snapshot,
        "provenance": {
            "hashes": file_hashes,
            "dependencies": [
                {"path": path, "hash": h, "role": _infer_role(path)}
                for path, h in dependency_hashes.items()
            ],
        },
        "execution": {
            "status": "complete",
            "started_at": created_at,
            "completed_at": created_at,
            "frames_total": total_frames,
            "frames_captured": 0,
            "frames_failed": 0,
        },
    }
    write_json(run_dir / "run.json", run_json)

    return {
        "run_dir": str(run_dir.resolve()),
        "schema_version": DATASET_V2_SCHEMA,
        "status": "complete",
        "task_id": task_id,
        "files": [
            "run.json",
            "capture-plan.json",
            "capture/manifest.json",
            "capture/observations.jsonl",
            "capture/rigs/rig.json",
            "capture/trajectories/trajectory.jsonl",
        ],
        "hashes": file_hashes,
        "observations": total_frames,
        "trajectory_frames": len(model.poses),
    }


# ── helpers ────────────────────────────────────────────────────────────


def _utc_now() -> str:
    """ISO-8601 UTC timestamp with seconds precision."""
    return datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat()


def _detect_git_commit() -> str:
    """Return the short Git commit hash or ``"unknown"``."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, FileNotFoundError):
        pass
    return "unknown"


def _infer_role(path: str) -> str:
    """Guess the dependency role from its extension or name."""
    lower = path.lower()
    if lower.endswith((".glb", ".gltf")):
        return "scene_geometry"
    if lower.endswith(".kml"):
        return "trajectory_input"
    if lower.endswith(".toml"):
        return "configuration"
    return "unknown"


def _vehicle_to_world(pose: object, east: float, north: float) -> list[list[float]]:
    """4×4 vehicle-to-world transform (ENU, Z-up)."""
    heading = math.radians(float(pose.heading_deg))
    return [
        [math.sin(heading), -math.cos(heading), 0.0, east],
        [math.cos(heading), math.sin(heading), 0.0, north],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _camera_to_world_matrix(
    east: float,
    north: float,
    up: float,
    heading_deg: float,
    tilt_deg: float,
    roll_deg: float,
) -> list[list[float]]:
    """4×4 camera-to-world homogeneous matrix.

    The rotation block maps camera-frame coordinates (x-right, y-down,
    z-forward) to world ENU (east, north, up).  The translation column
    is the camera position in ENU.
    """
    h = math.radians(heading_deg)
    t = math.radians(tilt_deg)
    r = math.radians(roll_deg)

    # Camera axes in world space (see compositor.py for derivation).
    zx = math.sin(h) * math.sin(t)
    zy = math.cos(h) * math.sin(t)
    zz = -math.cos(t)

    xx = math.cos(h)
    xy = -math.sin(h)
    xz = 0.0

    # y_axis = z_axis × x_axis  (cross product)
    yx = zy * xz - zz * xy
    yy = zz * xx - zx * xz
    yz = zx * xy - zy * xx

    # Apply roll around z.
    cos_r = math.cos(r)
    sin_r = math.sin(r)
    xf_x = xx * cos_r + yx * sin_r
    xf_y = xy * cos_r + yy * sin_r
    xf_z = xz * cos_r + yz * sin_r

    yf_x = -xx * sin_r + yx * cos_r
    yf_y = -xy * sin_r + yy * cos_r
    yf_z = -xz * sin_r + yz * cos_r

    return [
        [xf_x, yf_x, zx, east],
        [xf_y, yf_y, zy, north],
        [xf_z, yf_z, zz, up],
        [0.0, 0.0, 0.0, 1.0],
    ]
