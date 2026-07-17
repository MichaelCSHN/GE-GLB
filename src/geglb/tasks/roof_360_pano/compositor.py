"""Spherical panorama stitcher for Task 02 Roof 360.

Consumes a standard ``ge-glb.dataset/v1`` dataset with roof-mounted camera
observations and produces an equirectangular ``panorama.png`` plus
diagnostic maps and a product manifest.

This is an intentionally small baseline. It does not model parallax,
photometric calibration, or seam-aware blending.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ...core.dataset import read_jsonl, write_json
from ...products.panorama import Panorama360Product


def _validate_roof_dataset(dataset: Path, require_images: bool) -> None:
    """Validate that *dataset* contains the files produced by the roof-360
    Blender workflow (manifest, rig, trajectory, frames)."""
    errors: list[str] = []
    manifest_path = dataset / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("manifest.json is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "ge-glb.dataset/v1":
        raise ValueError(f"unsupported schema_version: {manifest.get('schema_version')!r}")

    for relative in ("rig.json", "trajectory.jsonl", "frames.jsonl"):
        if not (dataset / relative).is_file():
            errors.append(f"{relative} is missing")

    if require_images:
        frames = read_jsonl(dataset / "frames.jsonl")
        missing = []
        for item in frames:
            img_path = dataset / Path(str(item["image"]))
            if not img_path.is_file():
                missing.append(str(item["image"]))
        if missing:
            errors.append(f"{len(missing)} image files are missing")

    if errors:
        raise ValueError(f"dataset is not ready for panorama stitching: {errors}")


def build_panorama(
    dataset_dir: str | Path,
    output_dir: str | Path,
    panorama_width: int = 640,
    track_source: bool = False,
) -> dict[str, object]:
    """Stitch roof-360 observations into an equirectangular panorama.

    Parameters
    ----------
    dataset_dir :
        Path to a validated, captured GE-GLB dataset (images must exist).
    output_dir :
        Where to write ``panorama.png``, diagnostics, and result manifest.
    panorama_width :
        Width of the output equirectangular image in pixels.  Height is
        ``panorama_width // 2`` (2:1 aspect ratio).
    track_source :
        When *True*, also write a per-pixel source-index map.

    Returns
    -------
    dict
        Manifest equivalent recording algorithm, parameters, and
        limitations.
    """
    try:
        import numpy as np
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(
            "install the stitching extra: python -m pip install -e .[stitch]"
        ) from exc

    if panorama_width < 2:
        raise ValueError("panorama_width must be at least 2")

    dataset = Path(dataset_dir).resolve()

    # Task 02 datasets don't carry fusion-plan.json — validate only the
    # files that the roof-360 blender workflow actually writes.
    _validate_roof_dataset(dataset, require_images=True)

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    # ── load dataset ─────────────────────────────────────────────────
    rig = json.loads((dataset / "rig.json").read_text(encoding="utf-8"))
    frames = read_jsonl(dataset / "frames.jsonl")

    # Index calibrations by camera_id.
    calibrations: dict[str, dict[str, object]] = {}
    for cam in rig["cameras"]:
        calibrations[str(cam["id"])] = cam

    # Filter to reconstruction frames; load images lazily.
    @lru_cache(maxsize=32)
    def _load_image(relative: str) -> np.ndarray:
        with Image.open(dataset / Path(relative)) as im:
            return np.asarray(im.convert("RGB"), dtype=np.float32)

    observations: list[dict[str, object]] = []
    for frame in frames:
        if frame.get("ground_truth_only"):
            continue
        if frame["status"] not in ("planned", "captured"):
            continue
        observations.append(frame)

    if not observations:
        raise ValueError("no reconstruction frames found in dataset")

    # ── output grid ──────────────────────────────────────────────────
    W = panorama_width
    H = max(1, panorama_width // 2)

    py = np.arange(H, dtype=np.float64)
    px = np.arange(W, dtype=np.float64)

    lon_rad = 2.0 * np.pi * (px + 0.5) / W
    lat_rad = np.pi / 2.0 - np.pi * (py + 0.5) / H

    lon_grid = lon_rad[None, :]
    lat_grid = lat_rad[:, None]

    cos_lat = np.cos(lat_grid)
    world_x = cos_lat * np.sin(lon_grid)  # east
    world_y = cos_lat * np.cos(lon_grid)  # north  (lon=0 → north)
    world_z = np.sin(lat_grid)  # up

    # ── accumulate ───────────────────────────────────────────────────
    color_sum = np.zeros((H, W, 3), dtype=np.float64)
    weight_sum = np.zeros((H, W), dtype=np.float64)
    valid_mask = np.zeros((H, W), dtype=bool)

    if track_source:
        best_weight = np.zeros((H, W), dtype=np.float64)
        source_idx = np.full((H, W), -1, dtype=np.int16)

    for obs_index, obs in enumerate(observations):
        camera_id = str(obs["camera_id"])
        calib = calibrations.get(camera_id)
        if calib is None:
            continue

        intr = calib["intrinsics"]
        fx = float(intr["fx"])
        fy = float(intr["fy"])
        cx = float(intr["cx"])
        cy = float(intr["cy"])

        cw = obs["camera_world"]
        heading_deg = float(cw["heading_deg"])
        tilt_deg = float(cw["tilt_from_nadir_deg"])
        roll_deg = float(cw.get("roll_deg", 0.0))

        h_rad = np.radians(heading_deg)
        t_rad = np.radians(tilt_deg)
        r_rad = np.radians(roll_deg)

        # Camera axes in world (ENU) space.
        z_axis = np.array(
            [np.sin(h_rad) * np.sin(t_rad), np.cos(h_rad) * np.sin(t_rad), -np.cos(t_rad)]
        )
        x_axis = np.array([np.cos(h_rad), -np.sin(h_rad), 0.0])
        y_axis = np.cross(z_axis, x_axis)

        cos_r = np.cos(r_rad)
        sin_r = np.sin(r_rad)
        x_rolled = x_axis * cos_r + y_axis * sin_r
        y_rolled = -x_axis * sin_r + y_axis * cos_r

        # Transform world directions to camera space.
        cam_x = world_x * x_rolled[0] + world_y * x_rolled[1] + world_z * x_rolled[2]
        cam_y = world_x * y_rolled[0] + world_y * y_rolled[1] + world_z * y_rolled[2]
        cam_z = world_x * z_axis[0] + world_y * z_axis[1] + world_z * z_axis[2]

        in_front = cam_z > 1e-6

        px_cam = fx * cam_x / np.where(in_front, cam_z, 1.0) + cx
        py_cam = fy * cam_y / np.where(in_front, cam_z, 1.0) + cy

        img_w = int(intr["width"])
        img_h = int(intr["height"])
        in_image = (
            (px_cam >= 0.0) & (px_cam <= img_w - 1.0) & (py_cam >= 0.0) & (py_cam <= img_h - 1.0)
        )
        visible = in_front & in_image

        if not visible.any():
            continue

        # Sample source image.
        image = _load_image(str(obs["image"]))
        px_int = np.clip(np.floor(px_cam).astype(np.int64), 0, img_w - 1)
        py_int = np.clip(np.floor(py_cam).astype(np.int64), 0, img_h - 1)

        sampled = image[py_int[visible], px_int[visible]]

        # Incidence weight: cam_z measures alignment with camera boresight.
        weight = cam_z[visible]

        # Edge feathering for pixels near image borders.
        edge_left = px_cam[visible]
        edge_right = img_w - 1.0 - px_cam[visible]
        edge_top = py_cam[visible]
        edge_bottom = img_h - 1.0 - py_cam[visible]
        edge_dist = np.minimum.reduce([edge_left, edge_right, edge_top, edge_bottom])
        feather = np.clip(edge_dist / max(4.0, min(img_w, img_h) * 0.05), 0.0, 1.0)
        weight = weight * feather

        vis_idx = np.where(visible)
        color_sum[vis_idx[0], vis_idx[1]] += sampled * weight[:, None]
        weight_sum[vis_idx[0], vis_idx[1]] += weight
        valid_mask[vis_idx[0], vis_idx[1]] = True

        if track_source:
            src_v = vis_idx
            better = weight > best_weight[src_v[0], src_v[1]]
            if better.any():
                bi = np.where(better)
                src_v0 = src_v[0][bi]
                src_v1 = src_v[1][bi]
                source_idx[src_v0, src_v1] = obs_index
                best_weight[src_v0, src_v1] = np.maximum(best_weight[src_v0, src_v1], weight[bi])

    # ── finalise output image ────────────────────────────────────────
    rgb = np.zeros((H, W, 3), dtype=np.uint8)
    valid_final = weight_sum > 1e-12
    rgb[valid_final] = np.clip(
        color_sum[valid_final] / weight_sum[valid_final, None], 0.0, 255.0
    ).astype(np.uint8)
    alpha = np.where(valid_final, 255, 0).astype(np.uint8)
    rgba = np.dstack((rgb, alpha))

    product_dir = output / "product"
    product_dir.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, mode="RGBA").save(product_dir / "panorama.png")

    # ── diagnostics ──────────────────────────────────────────────────
    diag_dir = product_dir / "diagnostics"
    diag_dir.mkdir(parents=True, exist_ok=True)

    # Coverage: fraction of valid pixels.
    coverage = float(valid_final.mean())

    # Validity mask.
    Image.fromarray(np.where(valid_final, 255, 0).astype(np.uint8), mode="L").save(
        diag_dir / "validity.png"
    )

    # Coverage intensity (normalised weight sum).
    if weight_sum.max() > 1e-12:
        cov_norm = np.clip(weight_sum / weight_sum.max() * 255.0, 0.0, 255.0).astype(np.uint8)
    else:
        cov_norm = np.zeros((H, W), dtype=np.uint8)
    Image.fromarray(cov_norm, mode="L").save(diag_dir / "coverage.png")

    # Source map.
    if track_source and valid_final.any():
        n_obs = len(observations)
        src_8u = np.where(
            source_idx >= 0,
            np.clip(source_idx * (255 // max(1, n_obs - 1)), 0, 255),
            0,
        ).astype(np.uint8)
        Image.fromarray(src_8u, mode="L").save(diag_dir / "seam-map.png")

    # ── result manifest ──────────────────────────────────────────────
    manifest = {
        "schema_version": "ge-glb.stitch-result/v1",
        "dataset": str(dataset),
        "algorithm": "equirectangular_spherical_weighted_blend",
        "limitations": [
            "no_parallax_compensation",
            "no_photometric_compensation",
            "no_seam_optimisation",
            "nearest_neighbour_sampling",
        ],
        "panorama": {
            "width": W,
            "height": H,
            "projection": "equirectangular",
        },
        "observations": len(observations),
        "coverage": round(coverage, 6),
    }
    if track_source:
        manifest["diagnostics"] = {
            "seam_map": "diagnostics/seam-map.png",
        }
    write_json(product_dir / "result.json", manifest)

    # ── product manifest ─────────────────────────────────────────────
    product = Panorama360Product(capture_dataset=str(dataset))
    product_manifest = product.as_dict()
    product_manifest["stitch_algorithm"] = "equirectangular_spherical_weighted_blend"
    write_json(product_dir / "manifest.json", product_manifest)

    return manifest
