from __future__ import annotations

import json
from pathlib import Path

from .config import ProjectConfig
from .dataset import write_json, write_standard_dataset
from .model import build_capture_model


def build_blender_plan(
    config: ProjectConfig,
    route_kml: str | Path,
    scene_glb: str | Path,
    output_dir: str | Path,
    render_engine: str = "BLENDER_EEVEE_NEXT",
    samples: int = 32,
    transparent_background: bool = False,
) -> dict[str, object]:
    """MVP1: prepare a deterministic job for Blender's bundled Python runtime."""

    scene = Path(scene_glb).expanduser().resolve()
    if samples <= 0:
        raise ValueError("samples must be positive")
    if scene.suffix.lower() not in {".glb", ".gltf"}:
        raise ValueError("Blender scene must be a .glb or .gltf file")
    if not scene.is_file():
        raise FileNotFoundError(scene)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    model = build_capture_model(config, route_kml)
    write_standard_dataset(
        output,
        config,
        model,
        source_kind="blender",
        source_metadata={
            "adapter": "blender_python",
            "scene_glb": str(scene),
        },
        backend_artifacts=["blender-job.json", "capture-report.jsonl"],
    )

    standard_frames = []
    for line in (output / "frames.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            standard_frames.append(json.loads(line))
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
    return {
        "mvp": "MVP1",
        "source_kind": "blender",
        "output_dir": str(output.resolve()),
        "scene_glb": str(scene),
        "poses": len(model.poses),
        "captures": len(model.entries),
        "fusion_targets": len(model.fusion_plan["targets"]),
    }
