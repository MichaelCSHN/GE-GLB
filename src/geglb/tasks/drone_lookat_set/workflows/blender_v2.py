"""V2 Blender capture workflow for Task 03 Drone LookAt View Set.

Produces a ``ge-glb.capture-dataset/v2`` run directory plus a
``blender-job.json`` consumable by ``scripts/blender_capture.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

from ....core.dataset import write_json
from ....core.dataset_v2 import write_capture_dataset_v2
from ....core.hashing import file_sha256
from ....core.results import PlanResult
from ....core.trajectory import VehiclePose
from ..capture_plan import build_capture_model
from ..specification import DroneLookAtSpec


def build_blender_plan_v2(
    spec: DroneLookAtSpec,
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
    """Prepare a deterministic Blender render job using the v2 run layout."""
    scene = Path(scene_glb).expanduser().resolve()
    if samples <= 0:
        raise ValueError("samples must be positive")
    if scene.suffix.lower() not in {".glb", ".gltf"}:
        raise ValueError("Blender scene must be a .glb or .gltf file")
    if not scene.is_file():
        raise FileNotFoundError(scene)

    output = Path(output_dir)
    model = build_capture_model(
        spec,
        horizontal_fov_deg=horizontal_fov_deg,
        image_width=image_width,
        image_height=image_height,
        poses=poses,
    )

    source_meta = {
        "adapter": "blender_python",
        "scene_glb": str(scene),
    }
    config_snapshot = {
        "image_width": image_width,
        "image_height": image_height,
        "horizontal_fov_deg": horizontal_fov_deg,
        "radius_m": spec.radius_m,
    }

    dep_hashes = {str(scene): file_sha256(scene)}

    write_capture_dataset_v2(
        output_dir=output,
        task_id="task03_drone_lookat",
        product_schema="ge-glb.product.lookat-viewset/v1",
        source_kind="blender",
        source_backend="blender",
        source_metadata=source_meta,
        model=model,
        config_snapshot=config_snapshot,
        dependency_hashes=dep_hashes,
    )

    # Read observations for blender-job.json.
    obs_path = output / "capture" / "observations.jsonl"
    standard_frames = []
    for line in obs_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            standard_frames.append(json.loads(line))

    job = {
        "schema_version": "ge-glb.blender-job/v1",
        "project": "task03_drone_lookat",
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

    return PlanResult(
        workflow_id="TASK03_BLENDER_V2",
        source_kind="blender",
        output_dir=str(output.resolve()),
        counts={
            "poses": len(model.poses),
            "captures": len(model.entries),
        },
        artifacts=("blender-job.json",),
        details={
            "schema": "ge-glb.capture-dataset/v2",
            "scene_glb": str(scene),
        },
    )
