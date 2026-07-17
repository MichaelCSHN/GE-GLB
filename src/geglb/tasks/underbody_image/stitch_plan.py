from __future__ import annotations

import json
from pathlib import Path

from ...core.dataset import read_jsonl, validate_dataset, write_json, write_jsonl


def build_stitch_jobs(dataset_dir: str | Path, output_dir: str | Path) -> dict[str, object]:
    """Create source-agnostic stitching jobs from any compliant image sequence."""

    dataset = Path(dataset_dir).resolve()
    validation = validate_dataset(dataset, require_images=False)
    if not validation["valid"]:
        raise ValueError(f"invalid dataset: {validation['errors']}")
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    fusion = json.loads((dataset / "fusion-plan.json").read_text(encoding="utf-8"))
    frames = read_jsonl(dataset / "frames.jsonl")
    frame_lookup = {
        (int(item["frame_index"]), str(item["camera_id"])): item
        for item in frames
        if not item.get("ground_truth_only")
    }

    jobs: list[dict[str, object]] = []
    for target in fusion["targets"]:
        inputs: list[dict[str, object]] = []
        for observation in target["observations"]:
            key = (
                int(observation["source_pose_index"]),
                str(observation["camera_id"]),
            )
            frame = frame_lookup.get(key)
            if frame is None:
                raise ValueError(f"fusion plan references missing reconstruction frame {key}")
            inputs.append(
                {
                    "frame_index": key[0],
                    "camera_id": key[1],
                    "image": frame["image"],
                    "role": observation["role"],
                    "heuristic_prior": observation["heuristic_prior"],
                    "source_vehicle_in_target_frame": observation[
                        "source_vehicle_in_target_frame"
                    ],
                }
            )
        jobs.append(
            {
                "target_frame_index": target["target_pose_index"],
                "available_after_frame_index": target["available_after_pose_index"],
                "latency_frames": target["latency_frames"],
                "inputs": inputs,
                "output": f"bev/{int(target['target_pose_index']):06d}.png",
            }
        )

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    stitch_manifest = {
        "schema_version": "ge-glb.stitch-plan/v1",
        "dataset": str(dataset),
        "source_kind_for_information_only": manifest["source"]["kind"],
        "source_independent": True,
        "algorithm_contract": {
            "projection": "camera_model+rig+vehicle_pose_to_ground_plane",
            "selection": "visibility_then_resolution_then_incidence_then_soft_prior",
            "temporal_policy": "current_all+previous_all; first_frame_future_bootstrap",
            "ground_truth_allowed_as_input": False,
        },
        "jobs": len(jobs),
        "files": {"jobs": "stitch-jobs.jsonl"},
    }
    write_json(output / "manifest.json", stitch_manifest)
    write_jsonl(output / "stitch-jobs.jsonl", jobs)
    return {
        "output_dir": str(output.resolve()),
        "jobs": len(jobs),
        "source_independent": True,
    }
