from __future__ import annotations

from functools import lru_cache
import json
import math
from pathlib import Path

from .dataset import read_jsonl, validate_dataset, write_json
from .stitching import build_stitch_jobs


def run_planar_stitcher(
    dataset_dir: str | Path,
    output_dir: str | Path,
    meters_per_pixel: float = 0.1,
    margin_forward_m: float = 5.0,
    margin_rear_m: float = 5.0,
    margin_side_m: float = 3.0,
    max_frames: int | None = None,
) -> dict[str, object]:
    """Reference flat-ground IPM stitcher for any GE-GLB capture backend.

    This is an intentionally small baseline. It does not model terrain, lens distortion,
    photometric calibration, or explicit scene occlusion.
    """

    if meters_per_pixel <= 0:
        raise ValueError("meters_per_pixel must be positive")
    dataset = Path(dataset_dir).resolve()
    validation = validate_dataset(dataset, require_images=True)
    if not validation["valid"]:
        raise ValueError(f"dataset is not ready for stitching: {validation['errors']}")

    try:
        import numpy as np
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("install the stitching extra: python -m pip install -e .[stitch]") from exc

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    plan_dir = output / "plan"
    build_stitch_jobs(dataset, plan_dir)
    jobs = read_jsonl(plan_dir / "stitch-jobs.jsonl")
    if max_frames is not None:
        jobs = jobs[: max(0, max_frames)]

    rig = json.loads((dataset / "rig.json").read_text(encoding="utf-8"))
    calibrations = {str(item["id"]): item for item in rig["cameras"]}
    bus = rig["bus"]
    forward_extent = float(bus["length_m"]) / 2.0 + margin_forward_m
    rear_extent = float(bus["length_m"]) / 2.0 + margin_rear_m
    left_extent = float(bus["width_m"]) / 2.0 + margin_side_m
    right_extent = float(bus["width_m"]) / 2.0 + margin_side_m
    height = max(1, math.ceil((forward_extent + rear_extent) / meters_per_pixel))
    width = max(1, math.ceil((left_extent + right_extent) / meters_per_pixel))
    target_x = forward_extent - (np.arange(height, dtype=np.float64) + 0.5) * meters_per_pixel
    target_y = left_extent - (np.arange(width, dtype=np.float64) + 0.5) * meters_per_pixel
    grid_x, grid_y = np.meshgrid(target_x, target_y, indexing="ij")

    @lru_cache(maxsize=16)
    def load_image(relative: str):
        with Image.open(dataset / Path(relative)) as image:
            return np.asarray(image.convert("RGB"), dtype=np.float32)

    bev_dir = output / "bev"
    bev_dir.mkdir(parents=True, exist_ok=True)
    rendered = 0
    coverage_values: list[float] = []
    for job in jobs:
        color_sum = np.zeros((height, width, 3), dtype=np.float64)
        weight_sum = np.zeros((height, width), dtype=np.float64)
        for observation in job["inputs"]:
            camera_id = str(observation["camera_id"])
            calibration = calibrations[camera_id]
            image = load_image(str(observation["image"]))
            sampled, weight = _warp_observation(
                np,
                image,
                calibration,
                observation,
                grid_x,
                grid_y,
            )
            color_sum += sampled * weight[..., None]
            weight_sum += weight
        valid = weight_sum > 1e-12
        rgb = np.zeros((height, width, 3), dtype=np.uint8)
        rgb[valid] = np.clip(
            color_sum[valid] / weight_sum[valid, None], 0.0, 255.0
        ).astype(np.uint8)
        alpha = np.where(valid, 255, 0).astype(np.uint8)
        rgba = np.dstack((rgb, alpha))
        relative_output = Path(str(job["output"]))
        destination = output / relative_output
        destination.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(rgba, mode="RGBA").save(destination)
        rendered += 1
        coverage_values.append(float(valid.mean()))

    manifest = {
        "schema_version": "ge-glb.stitch-result/v1",
        "dataset": str(dataset),
        "algorithm": "flat_ground_ipm_weighted_blend",
        "limitations": [
            "flat_ground_only",
            "rectilinear_camera_only",
            "no_explicit_occlusion_test",
            "no_photometric_compensation",
        ],
        "grid": {
            "meters_per_pixel": meters_per_pixel,
            "width": width,
            "height": height,
            "forward_extent_m": forward_extent,
            "rear_extent_m": rear_extent,
            "left_extent_m": left_extent,
            "right_extent_m": right_extent,
        },
        "frames_rendered": rendered,
        "mean_coverage": (
            sum(coverage_values) / len(coverage_values) if coverage_values else 0.0
        ),
    }
    write_json(output / "result.json", manifest)
    return manifest


def _warp_observation(np, image, calibration, observation, grid_x, grid_y):
    relative = observation["source_vehicle_in_target_frame"]
    delta = math.radians(float(relative["yaw_deg"]))
    cosine = math.cos(delta)
    sine = math.sin(delta)
    shifted_x = grid_x - float(relative["x_forward_m"])
    shifted_y = grid_y - float(relative["y_left_m"])
    source_x = cosine * shifted_x - sine * shifted_y
    source_y = sine * shifted_x + cosine * shifted_y

    transform = np.asarray(calibration["camera_to_vehicle"], dtype=np.float64)
    rotation = transform[:3, :3]
    translation = transform[:3, 3]
    dx = source_x - translation[0]
    dy = source_y - translation[1]
    dz = -translation[2]
    camera_x = rotation[0, 0] * dx + rotation[1, 0] * dy + rotation[2, 0] * dz
    camera_y = rotation[0, 1] * dx + rotation[1, 1] * dy + rotation[2, 1] * dz
    camera_z = rotation[0, 2] * dx + rotation[1, 2] * dy + rotation[2, 2] * dz

    intrinsics = calibration["intrinsics"]
    safe_z = np.where(camera_z > 1e-6, camera_z, 1.0)
    pixel_x = float(intrinsics["fx"]) * camera_x / safe_z + float(intrinsics["cx"])
    pixel_y = float(intrinsics["fy"]) * camera_y / safe_z + float(intrinsics["cy"])
    image_height, image_width = image.shape[:2]
    valid = (
        (camera_z > 1e-6)
        & (pixel_x >= 0.0)
        & (pixel_x <= image_width - 1.0)
        & (pixel_y >= 0.0)
        & (pixel_y <= image_height - 1.0)
    )
    sampled = _bilinear(np, image, pixel_x, pixel_y, valid)
    edge = np.minimum.reduce(
        (pixel_x, image_width - 1.0 - pixel_x, pixel_y, image_height - 1.0 - pixel_y)
    )
    feather = np.clip(edge / max(8.0, min(image_width, image_height) * 0.05), 0.0, 1.0)
    incidence = max(0.05, abs(float(rotation[2, 2])))
    depth_weight = 1.0 / np.maximum(camera_z, 1.0) ** 2
    weight = (
        valid
        * (0.1 + 0.9 * feather)
        * depth_weight
        * incidence
        * float(observation["heuristic_prior"])
    )
    return sampled, weight


def _bilinear(np, image, pixel_x, pixel_y, valid):
    height, width = image.shape[:2]
    x0 = np.clip(np.floor(pixel_x).astype(np.int64), 0, width - 1)
    y0 = np.clip(np.floor(pixel_y).astype(np.int64), 0, height - 1)
    x1 = np.clip(x0 + 1, 0, width - 1)
    y1 = np.clip(y0 + 1, 0, height - 1)
    wx = np.clip(pixel_x - x0, 0.0, 1.0)[..., None]
    wy = np.clip(pixel_y - y0, 0.0, 1.0)[..., None]
    top = image[y0, x0] * (1.0 - wx) + image[y0, x1] * wx
    bottom = image[y1, x0] * (1.0 - wx) + image[y1, x1] * wx
    sampled = top * (1.0 - wy) + bottom * wy
    sampled[~valid] = 0.0
    return sampled
