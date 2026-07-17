"""MVP1 ground-truth evaluation and UnderbodyImageProduct generation.

After a dataset has been captured (images rendered by Blender or loaded from GE Pro),
this module runs the source-independent stitcher on a selected target frame, compares
the composited BEV to any available nadir ground truth, writes diagnostic maps
(confidence, source-map, coverage), and emits a versioned UnderbodyImageProduct.

CLI entry point (once Blender has completed rendering)::

    geglb product underbody \\
        --dataset build/mvp1 \\
        --target-frame 5 \\
        --out build/product-mvp1
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from ...core.dataset import read_jsonl, validate_dataset, write_json
from ...products.image import UnderbodyImageProduct
from .compositor import run_planar_stitcher


def _load_and_check(
    stitch_dir: Path,
    dataset_dir: Path,
    bev_relative: str,
) -> tuple[object, object] | None:
    """Load a stitched BEV and its corresponding nadir ground truth.

    Returns (bev_array, gt_array) or None if either is missing.
    """
    # Import lazily so stitching deps are only required when this function is called.
    try:
        import numpy as np
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(
            "install the stitching extra: python -m pip install -e .[stitch]"
        ) from exc

    bev_path = stitch_dir / bev_relative
    if not bev_path.is_file():
        return None

    # Find the corresponding ground-truth frame.
    frames = read_jsonl(dataset_dir / "frames.jsonl")
    gt_candidate = None
    for frame in frames:
        if frame.get("ground_truth_only") and int(frame["frame_index"]) == int(
            Path(bev_relative).stem
        ):
            gt_path = dataset_dir / Path(str(frame["image"]))
            if gt_path.is_file():
                gt_candidate = gt_path
            break

    if gt_candidate is None:
        return None

    with Image.open(bev_path) as im:
        beva = np.asarray(im.convert("RGBA"))
    with Image.open(gt_candidate) as im:
        gta = np.asarray(im.convert("RGB"))
    return beva, gta


def compare_to_ground_truth(
    composited: object,
    ground_truth: object,
    coverage_mask: object,
) -> dict[str, float]:
    """Compare a composited BEV against nadir ground truth and return metrics.

    Parameters
    ----------
    composited : np.ndarray
        RGBA array from the stitcher output.
    ground_truth : np.ndarray
        RGB array of the nadir ground-truth image.
    coverage_mask : np.ndarray
        Boolean array ― True where the composite has valid pixels.

    Returns
    -------
    dict with keys:
        psnr_db          ― peak signal-to-noise ratio (covered region only)
        mean_error       ― mean absolute pixel error (covered region)
        coverage_overlap ― fraction of ground-truth pixels that are also covered
        ground_truth_covered ― fraction of covered pixels that have ground truth
    """
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "install the stitching extra: python -m pip install -e .[stitch]"
        ) from exc

    # Ensure sizes are compatible ― crop to the smaller.
    h = min(composited.shape[0], ground_truth.shape[0])
    w = min(composited.shape[1], ground_truth.shape[1])
    comp = np.asarray(composited, dtype=np.float32)[:h, :w]
    gt = np.asarray(ground_truth, dtype=np.float32)[:h, :w]
    mask = np.asarray(coverage_mask, dtype=bool)[:h, :w]

    # If composited is RGBA, extract RGB; if coverage_mask is narrower than
    # composited, use alpha channel as the coverage signal.
    if comp.shape[2] == 4:
        comp_rgb = comp[..., :3]
        if not mask.any():
            mask = comp[..., 3] > 0
    else:
        comp_rgb = comp

    covered = mask & (gt.sum(axis=2) > 0)  # ground truth has content
    n_covered = int(covered.sum())
    n_gt = int((gt.sum(axis=2) > 0).sum())

    if n_covered == 0:
        return {
            "psnr_db": 0.0,
            "mean_error": float("inf"),
            "coverage_overlap": 0.0,
            "ground_truth_covered": 0.0,
        }

    diff = comp_rgb[covered] - gt[covered]
    mse = float((diff ** 2).mean())
    mae = float(np.abs(diff).mean())
    psnr = float("inf") if mse < 1e-12 else round(10.0 * math.log10((255.0 ** 2) / mse), 2)
    return {
        "psnr_db": round(psnr, 2),
        "mean_error": round(mae, 2),
        "coverage_overlap": round(n_covered / max(n_gt, 1), 4),
        "ground_truth_covered": round(n_covered / max(int(mask.sum()), 1), 4),
    }


def produce_underbody_product(
    dataset_dir: str | Path,
    output_dir: str | Path,
    target_frame_index: int,
    meters_per_pixel: float = 0.1,
) -> dict[str, object]:
    """Generate a complete UnderbodyImageProduct for one target frame.

    This is the MVP1 product-level entry point. It runs the source-independent
    flat-ground stitcher on *all* frames for consistency, then extracts the
    requested target frame as the primary artifact, compares against ground truth
    (if available), writes diagnostic images, and writes the product manifest.

    Parameters
    ----------
    dataset_dir :
        Path to a validated, captured GE-GLB dataset (images must exist).
    output_dir :
        Where to write the product manifest and artifact files.
    target_frame_index :
        Which frame (pose index) to produce the underbody image for.
    meters_per_pixel :
        Ground-sample distance passed to the planar stitcher.

    Returns
    -------
    dict equivalent to an ``UnderbodyImageProduct.as_dict()``.
    """
    try:
        import numpy as np
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(
            "install the stitching extra: python -m pip install -e .[stitch]"
        ) from exc

    dataset = Path(dataset_dir).resolve()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    product_dir = output / "product"
    diagnostics_dir = product_dir / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    # 1. Run the compositor for the requested target frame only.
    stitch_out = output / "stitch"
    result = run_planar_stitcher(
        dataset,
        stitch_out,
        meters_per_pixel=meters_per_pixel,
        max_frames=target_frame_index + 1,
        track_source=True,
    )
    if result["frames_rendered"] <= target_frame_index:
        raise ValueError(
            f"dataset has only {result['frames_rendered']} stitched frames; "
            f"cannot produce product for frame {target_frame_index}"
        )

    # 2. Read the stitched BEV and ground truth.
    bev_relative = f"bev/{target_frame_index:06d}.png"
    loaded = _load_and_check(stitch_out, dataset, bev_relative)
    if loaded is not None:
        beva, gta = loaded
        coverage_mask = beva[..., 3] > 0
        metrics = compare_to_ground_truth(beva, gta, coverage_mask)
    else:
        # Load the BEV alone if no ground truth is available.
        bev_path = stitch_out / Path(bev_relative)
        if not bev_path.is_file():
            raise ValueError(
                f"stitcher output missing: {bev_path} — cannot produce product"
            )
        with Image.open(bev_path) as im:
            beva = np.asarray(im.convert("RGBA"))
        metrics = None

    # 3. Write primary artifact: underbody.png
    primary_path = product_dir / "underbody.png"
    Image.fromarray(beva, mode="RGBA").save(primary_path)

    # 4. Write diagnostic maps.
    alpha = beva[..., 3]
    coverage_mask_img = Image.fromarray(alpha, mode="L")
    coverage_mask_img.save(diagnostics_dir / "coverage.png")

    # Confidence map = normalised coverage intensity (weight sum per pixel
    # approximates observation count and quality). Re-derive from the alpha
    # channel since we don't persist weight_sum across frames.
    confidence = alpha.astype(np.float32) / 255.0
    confidence_8u = np.clip(confidence * 255.0, 0, 255).astype(np.uint8)
    Image.fromarray(confidence_8u, mode="L").save(diagnostics_dir / "confidence.png")

    # Source map: copy from the stored diagnostic if available.
    src_map_path = stitch_out / "diagnostics" / f"source-map-{target_frame_index:06d}.png"
    if src_map_path.is_file():
        import shutil

        shutil.copy2(src_map_path, diagnostics_dir / "source-map.png")

    # 5. Write product manifest.
    product = UnderbodyImageProduct(
        capture_dataset=str(dataset),
    )
    manifest = product.as_dict()
    manifest["target_frame_index"] = target_frame_index
    manifest["algorithm"] = "flat_ground_ipm_weighted_blend"
    manifest["grid"] = {
        "meters_per_pixel": meters_per_pixel,
    }
    if metrics is not None:
        manifest["ground_truth_metrics"] = metrics
    write_json(product_dir / "manifest.json", manifest)

    return manifest


__all__ = ["compare_to_ground_truth", "produce_underbody_product"]
