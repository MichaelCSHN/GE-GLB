"""Tests for the MVP1 evaluation and UnderbodyImageProduct workflow."""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from geglb.core.config import CameraConfig, load_config
from geglb.core.dataset import read_jsonl, validate_dataset
from geglb.tasks.underbody_image.compositor import run_planar_stitcher
from geglb.tasks.underbody_image.evaluation import (
    compare_to_ground_truth,
    produce_underbody_product,
)
from geglb.tasks.underbody_image.workflows.blender import build_blender_plan

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "01-underbody-image"


class EvaluationTests(unittest.TestCase):
    """Synthetic-image tests for the ground-truth comparison."""

    def _make_synthetic_dataset(self, directory: Path) -> Path:
        """Build a small Blender-plan dataset with known synthetic images."""
        base = load_config(EXAMPLE / "mvp.toml")
        config = replace(
            base,
            cameras=(
                CameraConfig(
                    camera_id="front",
                    mount="custom",
                    position_m=(0.0, 0.0, 10.0),
                    yaw_deg=0.0,
                    tilt_deg=0.0,
                    roll_deg=0.0,
                    horizontal_fov_deg=90.0,
                ),
            ),
            ground_truth=replace(base.ground_truth, enabled=True),
            capture=replace(base.capture, image_width=64, image_height=64),
        )
        dataset = directory / "dataset"
        build_blender_plan(
            config,
            EXAMPLE / "route.kml",
            EXAMPLE / "minimal.gltf",
            dataset,
        )
        # Write synthetic images.
        try:
            import numpy as np
            from PIL import Image
        except ImportError:
            self.skipTest("stitching dependencies unavailable")

        for frame in read_jsonl(dataset / "frames.jsonl"):
            image_path = dataset / Path(str(frame["image"]))
            image_path.parent.mkdir(parents=True, exist_ok=True)
            gt = frame.get("ground_truth_only", False)
            colour = (80, 160, 240) if gt else (220, 30, 10)
            Image.fromarray(
                np.full((64, 64, 3), colour, dtype=np.uint8), mode="RGB"
            ).save(image_path)
        return dataset

    def test_compare_to_ground_truth_identical_images(self) -> None:
        try:
            import numpy as np
        except ImportError:
            self.skipTest("stitching dependencies unavailable")

        rgba = np.zeros((32, 32, 4), dtype=np.uint8)
        rgba[..., :3] = 128
        rgba[..., 3] = 255
        rgb = np.full((32, 32, 3), 128, dtype=np.uint8)
        mask = np.ones((32, 32), dtype=bool)

        metrics = compare_to_ground_truth(rgba, rgb, mask)
        self.assertEqual(metrics["psnr_db"], float("inf"))  # perfect match
        self.assertAlmostEqual(metrics["mean_error"], 0.0, places=5)

    def test_compare_to_ground_truth_worst_case(self) -> None:
        try:
            import numpy as np
        except ImportError:
            self.skipTest("stitching dependencies unavailable")

        rgba = np.zeros((32, 32, 4), dtype=np.uint8)
        rgba[..., :3] = 0
        rgba[..., 3] = 255
        rgb = np.full((32, 32, 3), 255, dtype=np.uint8)
        mask = np.ones((32, 32), dtype=bool)

        metrics = compare_to_ground_truth(rgba, rgb, mask)
        self.assertLess(metrics["psnr_db"], 10.0)
        self.assertAlmostEqual(metrics["mean_error"], 255.0, delta=1.0)
        self.assertEqual(metrics["coverage_overlap"], 1.0)

    def test_compare_no_coverage_returns_safe_defaults(self) -> None:
        try:
            import numpy as np
        except ImportError:
            self.skipTest("stitching dependencies unavailable")

        rgba = np.zeros((32, 32, 4), dtype=np.uint8)
        rgba[..., 3] = 0  # no coverage
        rgb = np.full((32, 32, 3), 128, dtype=np.uint8)
        mask = np.zeros((32, 32), dtype=bool)

        metrics = compare_to_ground_truth(rgba, rgb, mask)
        self.assertEqual(metrics["coverage_overlap"], 0.0)
        self.assertEqual(metrics["ground_truth_covered"], 0.0)

    def test_compare_with_mismatched_sizes_is_safe(self) -> None:
        try:
            import numpy as np
        except ImportError:
            self.skipTest("stitching dependencies unavailable")

        rgba = np.zeros((64, 64, 4), dtype=np.uint8)
        rgba[..., :3] = 100
        rgba[..., 3] = 255
        rgb = np.full((32, 32, 3), 100, dtype=np.uint8)
        mask = np.ones((32, 32), dtype=bool)

        metrics = compare_to_ground_truth(rgba, rgb, mask)
        self.assertGreater(metrics["psnr_db"], 40.0)

    def test_produce_underbody_product_creates_all_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = self._make_synthetic_dataset(root)
            output = root / "out"

            manifest = produce_underbody_product(
                dataset,
                output,
                target_frame_index=1,
                meters_per_pixel=0.5,
            )
            product_dir = output / "product"
            diagnostics = product_dir / "diagnostics"

            # Primary artifact.
            self.assertTrue((product_dir / "underbody.png").is_file())

            # Diagnostics.
            self.assertTrue((diagnostics / "coverage.png").is_file())
            self.assertTrue((diagnostics / "confidence.png").is_file())

            # Manifest matches the product schema.
            manifest_path = product_dir / "manifest.json"
            self.assertTrue(manifest_path.is_file())
            with open(manifest_path, encoding="utf-8") as stream:
                parsed = json.load(stream)
            self.assertEqual(parsed["product_schema"], "ge-glb.product.underbody-image/v1")
            self.assertEqual(parsed["primary_artifact"], "underbody.png")
            self.assertIn("ground_truth_metrics", parsed)

    def test_produce_missing_frame_raises(self) -> None:
        base = load_config(EXAMPLE / "mvp.toml")
        config = replace(
            base,
            cameras=(
                CameraConfig(
                    camera_id="front",
                    mount="custom",
                    position_m=(0.0, 0.0, 10.0),
                    yaw_deg=0.0,
                    tilt_deg=0.0,
                    roll_deg=0.0,
                    horizontal_fov_deg=90.0,
                ),
            ),
            ground_truth=replace(base.ground_truth, enabled=False),
            capture=replace(base.capture, image_width=64, image_height=64),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "dataset"
            build_blender_plan(
                config,
                EXAMPLE / "route.kml",
                EXAMPLE / "minimal.gltf",
                dataset,
            )
            try:
                import numpy as np
                from PIL import Image
            except ImportError:
                self.skipTest("stitching dependencies unavailable")
            for frame in read_jsonl(dataset / "frames.jsonl"):
                image_path = dataset / Path(str(frame["image"]))
                image_path.parent.mkdir(parents=True, exist_ok=True)
                Image.fromarray(
                    np.full((64, 64, 3), (220, 30, 10), dtype=np.uint8), mode="RGB"
                ).save(image_path)

            with self.assertRaisesRegex(ValueError, "only .* stitched frames"):
                produce_underbody_product(dataset, root / "out", target_frame_index=999)


if __name__ == "__main__":
    unittest.main()
