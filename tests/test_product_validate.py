"""Tests for the unified product validation framework."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from geglb.products.validate import validate_product

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "01-underbody-image"


def _make_underbody_product(out_dir: Path) -> Path:
    """Produce a valid Task 01 product and return the product directory."""
    from geglb.core.config import load_config
    from geglb.tasks.underbody_image.evaluation import produce_underbody_product
    from geglb.tasks.underbody_image.workflows.blender import build_blender_plan

    dataset = out_dir / "dataset"
    config = load_config(EXAMPLES / "mvp.toml")
    build_blender_plan(config, EXAMPLES / "route.kml", EXAMPLES / "minimal.gltf", dataset)

    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        raise unittest.SkipTest("stitching deps unavailable")

    from geglb.core.dataset import read_jsonl

    for frame in read_jsonl(dataset / "frames.jsonl"):
        img_path = dataset / Path(str(frame["image"]))
        img_path.parent.mkdir(parents=True, exist_ok=True)
        colour = (80, 160, 240) if frame.get("ground_truth_only") else (220, 30, 10)
        Image.fromarray(np.full((64, 64, 3), colour, dtype=np.uint8), mode="RGB").save(img_path)

    produce_underbody_product(dataset, out_dir / "product_out", target_frame_index=1)
    return out_dir / "product_out" / "product"


def _make_panorama_product(out_dir: Path) -> Path:
    """Produce a valid Task 02 product and return the product directory."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        raise unittest.SkipTest("stitching deps unavailable")

    from geglb.core.dataset import read_jsonl
    from geglb.tasks.roof_360_pano.compositor import build_panorama
    from geglb.tasks.roof_360_pano.specification import CaptureBand, Roof360Spec
    from geglb.tasks.roof_360_pano.workflows.blender import build_blender_plan

    spec = Roof360Spec(
        mast_height_m=1.5,
        bands=(
            CaptureBand(
                band_id="horizontal",
                tilt_from_nadir_deg=90.0,
                azimuth_deg=(0.0, 180.0),
            ),
            CaptureBand(
                band_id="downward",
                tilt_from_nadir_deg=50.0,
                azimuth_deg=(90.0, 270.0),
            ),
        ),
    )
    dataset = out_dir / "dataset"
    build_blender_plan(
        spec,
        bus_length_m=8.0,
        bus_width_m=2.5,
        bus_height_m=3.0,
        scene_glb=EXAMPLES / "minimal.gltf",
        output_dir=dataset,
        image_width=64,
        image_height=64,
    )
    for frame in read_jsonl(dataset / "frames.jsonl"):
        img_path = dataset / Path(str(frame["image"]))
        img_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(np.full((64, 64, 3), (100, 150, 200), dtype=np.uint8), mode="RGB").save(
            img_path
        )

    build_panorama(dataset, out_dir / "product_out", panorama_width=100)
    return out_dir / "product_out" / "product"


def _make_lookat_product(out_dir: Path) -> Path:
    """Produce a valid Task 03 product and return the product directory."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        raise unittest.SkipTest("stitching deps unavailable")

    from geglb.core.dataset import read_jsonl
    from geglb.tasks.drone_lookat_set.capture_plan import default_spec
    from geglb.tasks.drone_lookat_set.product_writer import write_viewset_product
    from geglb.tasks.drone_lookat_set.workflows.blender import build_blender_plan

    spec = default_spec()
    dataset = out_dir / "dataset"
    build_blender_plan(
        spec,
        scene_glb=EXAMPLES / "minimal.gltf",
        output_dir=dataset,
        horizontal_fov_deg=60.0,
        image_width=64,
        image_height=48,
    )
    for frame in read_jsonl(dataset / "frames.jsonl"):
        img_path = dataset / Path(str(frame["image"]))
        img_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(np.full((48, 64, 3), (100, 150, 200), dtype=np.uint8), mode="RGB").save(
            img_path
        )

    write_viewset_product(dataset, out_dir / "product_out")
    return out_dir / "product_out" / "product"


class ProductValidateTests(unittest.TestCase):
    def test_validate_valid_underbody_product(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            product_dir = _make_underbody_product(Path(tmp))
            report = validate_product(product_dir, "underbody")
            self.assertTrue(report["valid"], f"errors: {report.get('errors')}")
            self.assertEqual(report["product_type"], "underbody")

    def test_validate_valid_panorama_product(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            product_dir = _make_panorama_product(Path(tmp))
            report = validate_product(product_dir, "panorama")
            self.assertTrue(report["valid"], f"errors: {report.get('errors')}")

    def test_validate_valid_lookat_product(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            product_dir = _make_lookat_product(Path(tmp))
            report = validate_product(product_dir, "lookat")
            self.assertTrue(report["valid"], f"errors: {report.get('errors')}")

    def test_validate_missing_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty"
            empty.mkdir()
            report = validate_product(empty, "underbody")
            self.assertFalse(report["valid"])
            self.assertIn("manifest.json is missing", report["errors"])

    def test_validate_wrong_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            product_dir = _make_underbody_product(Path(tmp))
            # Validate underbody product as panorama — should fail on schema.
            report = validate_product(product_dir, "panorama")
            # Primary artifact mismatch or schema error.
            self.assertFalse(report["valid"])

    def test_validate_degraded_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            product_dir = _make_underbody_product(Path(tmp))
            # Corrupt the primary artifact.
            (product_dir / "underbody.png").write_text("not a png", encoding="utf-8")
            report = validate_product(product_dir, "underbody")
            self.assertFalse(report["primary_artifact_ok"])
            self.assertFalse(report["valid"])

    def test_validate_missing_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            product_dir = _make_underbody_product(Path(tmp))
            # Remove a diagnostic image.
            diag = product_dir / "diagnostics" / "confidence.png"
            if diag.is_file():
                diag.unlink()
            report = validate_product(product_dir, "underbody")
            self.assertTrue(report["valid"])  # missing diag = warning, not error
            self.assertGreater(len(report["warnings"]), 0)

    def test_cli_validate_product(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            product_dir = _make_underbody_product(Path(tmp))
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "geglb",
                    "validate-product",
                    str(product_dir),
                    "--type",
                    "underbody",
                ],
                capture_output=True,
                text=True,
            )
            output = json.loads(result.stdout)
            self.assertTrue(output["valid"])
            self.assertEqual(result.returncode, 0)

            # Test invalid case.
            result2 = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "geglb",
                    "validate-product",
                    str(Path(tmp) / "nope"),
                    "--type",
                    "underbody",
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result2.returncode, 0)


if __name__ == "__main__":
    unittest.main()
