"""Product writer for Task 03 Drone LookAt View Set.

Consumes a standard ``ge-glb.dataset/v1`` dataset and produces the final
``LookAtViewSetProduct``: ``viewset.json``, per-view thumbnails, a
contact-sheet grid, and a completeness report.
"""

from __future__ import annotations

import json
from pathlib import Path

from ...core.dataset import read_jsonl, write_json
from ...products.viewset import LookAtView, LookAtViewSetProduct


def _validate_lookat_dataset(dataset: Path) -> None:
    """Validate that *dataset* contains the files produced by the drone
    LookAt Blender workflow (manifest, rig, frames)."""
    manifest_path = dataset / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("manifest.json is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "ge-glb.dataset/v1":
        raise ValueError(f"unsupported schema_version: {manifest.get('schema_version')!r}")
    errors: list[str] = []
    for relative in ("rig.json", "trajectory.jsonl", "frames.jsonl"):
        if not (dataset / relative).is_file():
            errors.append(f"{relative} is missing")
    if errors:
        raise ValueError(f"dataset is not ready for product generation: {errors}")


def write_viewset_product(
    dataset_dir: str | Path,
    output_dir: str | Path,
) -> dict[str, object]:
    """Generate the complete LookAtViewSet product from a captured dataset.

    Parameters
    ----------
    dataset_dir :
        Path to a validated, captured Task 03 dataset.
    output_dir :
        Where to write ``viewset.json``, thumbnails, contact sheet, and
        completeness report.

    Returns
    -------
    dict
        The ``LookAtViewSetProduct.as_dict()`` output.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise RuntimeError(
            "install the stitching extra: python -m pip install -e .[stitch]"
        ) from exc

    dataset = Path(dataset_dir).resolve()
    _validate_lookat_dataset(dataset)

    # ── load metadata ────────────────────────────────────────────────
    rig = json.loads((dataset / "rig.json").read_text(encoding="utf-8"))
    frames = read_jsonl(dataset / "frames.jsonl")
    observer = rig.get("observer", {})
    radius_m = float(observer.get("radius_m", 0.0))

    # ── parse views from frames ──────────────────────────────────────
    views_raw: list[dict[str, object]] = []
    seen: set[str] = set()
    for frame in frames:
        if frame.get("ground_truth_only"):
            continue
        camera_id = str(frame["camera_id"])
        if camera_id in seen:
            continue
        seen.add(camera_id)

        azimuth_deg, elevation_deg = _parse_camera_id(camera_id)

        views_raw.append(
            {
                "image": str(frame["image"]),
                "azimuth_deg": float(azimuth_deg),
                "elevation_deg": float(elevation_deg),
                "radius_m": radius_m,
                "target_ref": str(observer.get("target_ref", "vehicle_center")),
                "camera_id": camera_id,
            }
        )

    # Deterministic order: azimuth ascending, then elevation ascending.
    views_raw.sort(key=lambda v: (float(v["azimuth_deg"]), float(v["elevation_deg"])))

    # ── write output directories ─────────────────────────────────────
    output = Path(output_dir)
    product_dir = output / "product"
    diag_dir = product_dir / "diagnostics"
    thumb_dir = diag_dir / "thumbnails"
    for d in (product_dir, diag_dir, thumb_dir):
        d.mkdir(parents=True, exist_ok=True)

    # ── completeness check ───────────────────────────────────────────
    available_views: list[str] = []
    missing_cameras: list[str] = []
    for view in views_raw:
        img_path = dataset / Path(str(view["image"]))
        if img_path.is_file():
            available_views.append(view["camera_id"])
        else:
            missing_cameras.append(view["camera_id"])

    az_values = sorted({float(v["azimuth_deg"]) for v in views_raw})
    el_values = sorted({float(v["elevation_deg"]) for v in views_raw})
    completeness_data = {
        "planned_views": len(views_raw),
        "available_views": len(available_views),
        "completeness": (round(len(available_views) / max(len(views_raw), 1), 4)),
        "azimuth_range_deg": [min(az_values), max(az_values)] if az_values else [],
        "elevation_range_deg": [min(el_values), max(el_values)] if el_values else [],
        "radius_m": radius_m,
        "missing_cameras": missing_cameras,
    }
    write_json(diag_dir / "completeness.json", completeness_data)

    # ── thumbnails ───────────────────────────────────────────────────
    thumbnail_sizes: dict[str, tuple[int, int]] = {}
    for view in views_raw:
        img_path = dataset / Path(str(view["image"]))
        if not img_path.is_file():
            continue
        with Image.open(img_path) as im:
            im.load()  # ensure file is read before resizing
            w, h = im.size
            aspect = h / w if w > 0 else 1.0
            thumb_w = 128
            thumb_h = max(1, int(128 * aspect))
            im.thumbnail((thumb_w, thumb_h), Image.LANCZOS)
            if im.mode not in ("RGBA", "RGB"):
                im = im.convert("RGBA")
            out_path = thumb_dir / f"{view['camera_id']}.png"
            im.save(out_path)
            thumbnail_sizes[view["camera_id"]] = (thumb_w, thumb_h)

    # ── contact sheet ────────────────────────────────────────────────
    COLS = 8
    rows = (len(views_raw) + COLS - 1) // COLS

    thumb_w = 128
    thumb_h_max = max(
        (thumbnail_sizes.get(v["camera_id"], (128, 96))[1] for v in views_raw),
        default=96,
    )
    label_h = 18
    margin = 4
    cell_w = thumb_w + 2 * margin
    cell_h = thumb_h_max + 2 * margin + label_h

    sheet_w = COLS * cell_w
    sheet_h = rows * cell_h

    font = ImageFont.load_default()
    sheet = Image.new("RGB", (sheet_w, sheet_h), "white")
    draw = ImageDraw.Draw(sheet)

    for idx, view in enumerate(views_raw):
        col = idx % COLS
        row = idx // COLS
        x = col * cell_w
        y = row * cell_h

        thumb_path = thumb_dir / f"{view['camera_id']}.png"
        if thumb_path.is_file():
            with Image.open(thumb_path) as thumb:
                thumb.load()
                tw, th = thumbnail_sizes.get(view["camera_id"], (thumb.width, thumb.height))
                tx = x + (cell_w - tw) // 2
                ty = y + margin + (thumb_h_max - th) // 2
                if thumb.mode == "RGBA":
                    sheet.paste(thumb, (tx, ty), thumb)
                else:
                    sheet.paste(thumb, (tx, ty))

        label = f"{view['azimuth_deg']:.0f}°/{view['elevation_deg']:.0f}°"
        bbox = draw.textbbox((0, 0), label, font=font)
        lw = bbox[2] - bbox[0]
        draw.text(
            (x + (cell_w - lw) // 2, y + cell_h - label_h + 2),
            label,
            fill="black",
            font=font,
        )

    sheet.save(diag_dir / "contact-sheet.png")

    # ── viewset.json ─────────────────────────────────────────────────
    lookup_views = [
        LookAtView(
            image=str(v["image"]),
            azimuth_deg=float(v["azimuth_deg"]),
            elevation_deg=float(v["elevation_deg"]),
            radius_m=float(v["radius_m"]),
            target_ref=str(v["target_ref"]),
        )
        for v in views_raw
    ]
    product = LookAtViewSetProduct(
        capture_dataset=str(dataset),
        views=tuple(lookup_views),
    )
    product_dict = product.as_dict()
    write_json(product_dir / "viewset.json", product_dict)
    write_json(product_dir / "manifest.json", product_dict)

    return product_dict


def _parse_camera_id(camera_id: str) -> tuple[int, int]:
    """Parse ``"az{azimuth}_el{elevation}"`` into integer degrees."""
    parts = camera_id.split("_")
    if len(parts) != 2:
        raise ValueError(f"unexpected camera_id format: {camera_id!r}")
    az_str = parts[0]
    el_str = parts[1]
    if not az_str.startswith("az") or not el_str.startswith("el"):
        raise ValueError(f"unexpected camera_id format: {camera_id!r}")
    return int(az_str[2:]), int(el_str[2:])
