from __future__ import annotations

import csv
import json
from pathlib import Path

from .config import ProjectConfig
from .dataset import write_json, write_standard_dataset
from .kml import build_capture_tour
from .model import CaptureModel, build_capture_model


def _write_legacy_files(output: Path, config: ProjectConfig, model: CaptureModel) -> None:
    with (output / "poses.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["index", "distance_m", "longitude_deg", "latitude_deg", "heading_deg"],
        )
        writer.writeheader()
        for pose in model.poses:
            writer.writerow(
                {
                    "index": pose.index,
                    "distance_m": f"{pose.distance_m:.4f}",
                    "longitude_deg": f"{pose.longitude_deg:.10f}",
                    "latitude_deg": f"{pose.latitude_deg:.10f}",
                    "heading_deg": f"{pose.heading_deg:.8f}",
                }
            )

    # Compatibility aliases from the first prototype.
    write_json(output / "calibration.json", model.calibration)
    plan = {
        "schema_version": 1,
        "project": config.name,
        "route_spacing_m": config.route.capture_spacing_m,
        "pose_count": len(model.poses),
        "capture_count": len(model.entries),
        "entries": model.entries,
    }
    write_json(output / "capture-plan.json", plan)


def build_plan(
    config: ProjectConfig,
    route_kml: str | Path,
    output_dir: str | Path,
) -> dict[str, object]:
    """MVP2: build a GE Pro tour plus the source-independent dataset skeleton."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    model = build_capture_model(config, route_kml)
    write_standard_dataset(
        output,
        config,
        model,
        source_kind="ge_pro",
        source_metadata={
            "adapter": "ge_pro_kml_tour",
            "capture_method": "earth_pro_save_image",
        },
        backend_artifacts=["capture-tour.kml", "capture-plan.json"],
    )
    _write_legacy_files(output, config, model)

    tour = build_capture_tour(config.name, model.poses, model.ordered_states, config.capture)
    tour.write(output / "capture-tour.kml", encoding="utf-8", xml_declaration=True)

    return {
        "mvp": "MVP2",
        "source_kind": "ge_pro",
        "output_dir": str(output.resolve()),
        "route_points": len(model.route_points),
        "poses": len(model.poses),
        "captures": len(model.entries),
        "fusion_targets": len(model.fusion_plan["targets"]),
        "camera_ids": [camera.camera_id for camera in config.cameras]
        + ([config.ground_truth.camera_id] if config.ground_truth.enabled else []),
    }
