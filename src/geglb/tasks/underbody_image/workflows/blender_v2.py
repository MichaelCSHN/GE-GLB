"""V2 Blender capture workflow for Task 01 Underbody Image.

Produces a ``ge-glb.capture-dataset/v2`` run directory plus a
``blender-job.json`` consumable by ``scripts/blender_capture.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

from ....core.config import ProjectConfig
from ....core.dataset_v2 import write_capture_dataset_v2
from ....core.results import PlanResult
from ..capture_plan import build_capture_model


def build_blender_plan_v2(
    config: ProjectConfig,
    route_kml: str | Path,
    scene_glb: str | Path,
    output_dir: str | Path,
    render_engine: str = "BLENDER_EEVEE_NEXT",
    samples: int = 32,
    transparent_background: bool = False,
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
    model = build_capture_model(config, route_kml)

    source_meta = {
        "adapter": "blender_python",
        "scene_glb": str(scene),
    }
    config_snapshot = {
        "capture_spacing_m": config.route.capture_spacing_m,
        "image_width": config.capture.image_width,
        "image_height": config.capture.image_height,
    }

    from ....core.hashing import file_sha256

    dep_hashes = {
        str(scene): file_sha256(scene),
        str(Path(route_kml).resolve()): file_sha256(route_kml),
    }

    write_capture_dataset_v2(
        output_dir=output,
        task_id="task01_underbody",
        product_schema="ge-glb.product.underbody-image/v1",
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

    from ....core.dataset import write_json

    job = {
        "schema_version": "ge-glb.blender-job/v1",
        "project": config.name,
        "scene_glb": str(scene),
        "dataset_dir": str(output.resolve()),
        "render": {
            "engine": render_engine,
            "samples": samples,
            "width": config.capture.image_width,
            "height": config.capture.image_height,
            "file_format": "PNG",
            "transparent_background": transparent_background,
            "add_default_sun_if_missing": True,
        },
        "frames": standard_frames,
    }
    write_json(output / "blender-job.json", job)

    return PlanResult(
        workflow_id="TASK01_BLENDER_V2",
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
