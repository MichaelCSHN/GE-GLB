from __future__ import annotations

import bisect
import json
from pathlib import Path

from ..core.dataset import DATASET_SCHEMA, read_jsonl, validate_dataset, write_json, write_jsonl


def _load(root: Path) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != DATASET_SCHEMA:
        raise ValueError(f"{root} is not a {DATASET_SCHEMA} dataset")
    return (
        manifest,
        read_jsonl(root / "trajectory.jsonl"),
        read_jsonl(root / "frames.jsonl"),
    )


def _nearest(candidates: list[dict[str, object]], distance_m: float) -> dict[str, object] | None:
    if not candidates:
        return None
    distances = [float(item["distance_m"]) for item in candidates]
    index = bisect.bisect_left(distances, distance_m)
    choices = candidates[max(0, index - 1) : min(len(candidates), index + 2)]
    return min(choices, key=lambda item: abs(float(item["distance_m"]) - distance_m))


def combine_datasets(
    primary_dir: str | Path,
    secondary_dir: str | Path,
    output_dir: str | Path,
    max_distance_m: float = 0.25,
) -> dict[str, object]:
    """MVP3: pair two source datasets without mixing source-specific capture logic."""

    if max_distance_m < 0:
        raise ValueError("max_distance_m cannot be negative")
    primary_root = Path(primary_dir).resolve()
    secondary_root = Path(secondary_dir).resolve()
    for root in (primary_root, secondary_root):
        validation = validate_dataset(root, require_images=False)
        if not validation["valid"]:
            raise ValueError(f"invalid dataset {root}: {validation['errors']}")
    primary_manifest, _primary_trajectory, primary_frames = _load(primary_root)
    secondary_manifest, _secondary_trajectory, secondary_frames = _load(secondary_root)

    by_camera: dict[str, list[dict[str, object]]] = {}
    for item in secondary_frames:
        if item.get("ground_truth_only"):
            continue
        by_camera.setdefault(str(item["camera_id"]), []).append(item)
    for items in by_camera.values():
        items.sort(key=lambda item: float(item["distance_m"]))

    pairs: list[dict[str, object]] = []
    unmatched = 0
    for primary in primary_frames:
        if primary.get("ground_truth_only"):
            continue
        camera_id = str(primary["camera_id"])
        match = _nearest(by_camera.get(camera_id, []), float(primary["distance_m"]))
        error = (
            None
            if match is None
            else abs(float(match["distance_m"]) - float(primary["distance_m"]))
        )
        if match is None or error is None or error > max_distance_m:
            unmatched += 1
            continue
        pairs.append(
            {
                "camera_id": camera_id,
                "distance_m": primary["distance_m"],
                "distance_error_m": error,
                "primary": {
                    "frame_index": primary["frame_index"],
                    "image": primary["image"],
                },
                "secondary": {
                    "frame_index": match["frame_index"],
                    "image": match["image"],
                },
            }
        )

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "ge-glb.combined/v1",
        "mvp": "MVP3",
        "primary": {
            "root": str(primary_root),
            "source": primary_manifest["source"],
        },
        "secondary": {
            "root": str(secondary_root),
            "source": secondary_manifest["source"],
        },
        "pairing": {
            "key": "camera_id+nearest_route_distance",
            "max_distance_m": max_distance_m,
            "pairs": len(pairs),
            "unmatched_primary_frames": unmatched,
            "ground_truth_excluded": True,
        },
        "files": {"pairs": "pairs.jsonl"},
    }
    write_json(output / "manifest.json", manifest)
    write_jsonl(output / "pairs.jsonl", pairs)
    return {
        "mvp": "MVP3",
        "output_dir": str(output.resolve()),
        "primary_source": primary_manifest["source"]["kind"],
        "secondary_source": secondary_manifest["source"]["kind"],
        "pairs": len(pairs),
        "unmatched_primary_frames": unmatched,
    }
