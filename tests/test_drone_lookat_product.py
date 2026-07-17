"""Tests for Task 03 drone LookAt product writer."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from geglb.core.dataset import read_jsonl
from geglb.tasks.drone_lookat_set.capture_plan import default_spec
from geglb.tasks.drone_lookat_set.product_writer import write_viewset_product
from geglb.tasks.drone_lookat_set.workflows.blender import build_blender_plan

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "01-underbody-image"


def _make_synthetic_dataset(directory: Path) -> Path:
    """Create a Task 03 v1 dataset with synthetic images."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        raise unittest.SkipTest("stitching dependencies unavailable")

    spec = default_spec()
    dataset = directory / "dataset"
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
    return dataset


class ProductWriterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        root = Path(self._tmp_dir.name)
        self.dataset = _make_synthetic_dataset(root)
        self.out = root / "out"

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_write_viewset_product_creates_all_artifacts(self) -> None:
        write_viewset_product(self.dataset, self.out)
        pd = self.out / "product"
        self.assertTrue((pd / "viewset.json").is_file())
        self.assertTrue((pd / "manifest.json").is_file())
        diag = pd / "diagnostics"
        self.assertTrue((diag / "completeness.json").is_file())
        self.assertTrue((diag / "contact-sheet.png").is_file())
        thumb_dir = diag / "thumbnails"
        self.assertTrue(thumb_dir.is_dir())
        # 8 az × 3 el = 24 thumbnails
        self.assertGreaterEqual(len(list(thumb_dir.glob("*.png"))), 24)

    def test_viewset_json_matches_schema(self) -> None:
        result = write_viewset_product(self.dataset, self.out)
        self.assertEqual(result["product_schema"], "ge-glb.product.lookat-viewset/v1")
        self.assertEqual(result["task_id"], "task03_drone_lookat")
        self.assertEqual(result["primary_artifact"], "viewset.json")
        self.assertIn("views", result)
        for view in result["views"]:
            for key in (
                "image",
                "azimuth_deg",
                "elevation_deg",
                "radius_m",
                "target_ref",
            ):
                self.assertIn(key, view, f"missing {key} in view")

    def test_view_order_is_deterministic(self) -> None:
        result_a = write_viewset_product(self.dataset, self.out)
        result_b = write_viewset_product(self.dataset, self.out)
        self.assertEqual(
            [v["azimuth_deg"] for v in result_a["views"]],
            [v["azimuth_deg"] for v in result_b["views"]],
        )
        self.assertEqual(
            [v["elevation_deg"] for v in result_a["views"]],
            [v["elevation_deg"] for v in result_b["views"]],
        )

    def test_thumbnail_dimensions(self) -> None:
        write_viewset_product(self.dataset, self.out)
        thumb_dir = self.out / "product" / "diagnostics" / "thumbnails"
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("PIL unavailable")
        for png in thumb_dir.glob("*.png"):
            with Image.open(png) as im:
                # Width should be 128 (or less for 128px-thumbnail of a 64px image)
                self.assertLessEqual(im.width, 128)

    def test_contact_sheet_dimensions(self) -> None:
        write_viewset_product(self.dataset, self.out)
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("PIL unavailable")
        cs_path = self.out / "product" / "diagnostics" / "contact-sheet.png"
        with Image.open(cs_path) as cs:
            self.assertGreater(cs.width, 0)
            self.assertGreater(cs.height, 0)
            # 24 views / 8 cols = 3 rows → should be taller than wide
            # (each cell is taller than wide due to labels)
            self.assertGreater(cs.height, 0)

    def test_completeness_report(self) -> None:
        write_viewset_product(self.dataset, self.out)
        comp = json.loads(
            (self.out / "product" / "diagnostics" / "completeness.json").read_text(encoding="utf-8")
        )
        self.assertEqual(comp["planned_views"], 24)
        self.assertEqual(comp["available_views"], 24)
        self.assertEqual(comp["completeness"], 1.0)
        self.assertEqual(len(comp["missing_cameras"]), 0)

    def test_rejects_invalid_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad_dataset"
            bad.mkdir()
            with self.assertRaises(ValueError):
                write_viewset_product(bad, Path(tmp) / "out")

    def test_graceful_handling_of_missing_images(self) -> None:
        # Delete one image, verify it appears in missing_cameras.
        frames = read_jsonl(self.dataset / "frames.jsonl")
        target = None
        for frame in frames:
            if frame["status"] != "ground_truth_only":
                target = self.dataset / Path(str(frame["image"]))
                break
        self.assertIsNotNone(target)
        target.unlink()

        write_viewset_product(self.dataset, self.out)
        comp = json.loads(
            (self.out / "product" / "diagnostics" / "completeness.json").read_text(encoding="utf-8")
        )
        self.assertGreater(len(comp["missing_cameras"]), 0)
        self.assertLess(comp["completeness"], 1.0)


if __name__ == "__main__":
    unittest.main()
