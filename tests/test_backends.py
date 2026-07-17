from __future__ import annotations

import json
import py_compile
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from geglb.core.config import CameraConfig, load_config
from geglb.core.dataset import read_jsonl, validate_dataset
from geglb.core.results import PlanResult
from geglb.tasks.underbody_image.compositor import run_planar_stitcher
from geglb.tasks.underbody_image.stitch_plan import build_stitch_jobs
from geglb.tasks.underbody_image.workflows.blender import build_blender_plan
from geglb.tasks.underbody_image.workflows.ge3d import build_plan
from geglb.workflows.comparison import combine_datasets

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "01-underbody-image"


class BlenderBackendTests(unittest.TestCase):
    def test_prepares_headless_render_job(self) -> None:
        config = load_config(EXAMPLE / "mvp.toml")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "blender"
            summary = build_blender_plan(
                config,
                EXAMPLE / "route.kml",
                EXAMPLE / "minimal.gltf",
                output,
            )
            self.assertIsInstance(summary, PlanResult)
            self.assertEqual(summary.workflow_id, "MVP1")
            self.assertEqual(summary["mvp"], "MVP1")
            job = json.loads((output / "blender-job.json").read_text(encoding="utf-8"))
            self.assertEqual(job["schema_version"], "ge-glb.blender-job/v1")
            self.assertEqual(len(job["frames"]), summary["captures"])
            self.assertEqual(job["frames"][0]["camera_id"], "front")
            self.assertAlmostEqual(job["frames"][0]["camera_world"]["local_enu_m"]["up"], 3.05)
            validation = validate_dataset(output)
            self.assertTrue(validation["valid"], validation)
            self.assertEqual(validation["source_kind"], "blender")

    def test_blender_runner_is_valid_without_importing_bpy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            py_compile.compile(
                str(ROOT / "scripts" / "blender_capture.py"),
                cfile=str(Path(directory) / "runner.pyc"),
                doraise=True,
            )


class CombinedDatasetTests(unittest.TestCase):
    def test_pairs_blender_and_ge_pro_by_camera_and_distance(self) -> None:
        config = load_config(EXAMPLE / "mvp.toml")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            blender = root / "blender"
            ge_pro = root / "ge-pro"
            combined = root / "combined"
            build_blender_plan(
                config,
                EXAMPLE / "route.kml",
                EXAMPLE / "minimal.gltf",
                blender,
            )
            build_plan(config, EXAMPLE / "route.kml", ge_pro)
            summary = combine_datasets(blender, ge_pro, combined)
            self.assertEqual(summary["mvp"], "MVP3")
            self.assertEqual(summary["unmatched_primary_frames"], 0)
            pairs = read_jsonl(combined / "pairs.jsonl")
            self.assertEqual(len(pairs), 25 * 4)
            self.assertEqual(
                {pair["camera_id"] for pair in pairs},
                {"front", "rear", "left", "right"},
            )

    def test_stitch_jobs_do_not_depend_on_capture_source(self) -> None:
        config = load_config(EXAMPLE / "mvp.toml")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "dataset"
            output = root / "stitch"
            build_blender_plan(
                config,
                EXAMPLE / "route.kml",
                EXAMPLE / "minimal.gltf",
                dataset,
            )
            summary = build_stitch_jobs(dataset, output)
            self.assertTrue(summary["source_independent"])
            jobs = read_jsonl(output / "stitch-jobs.jsonl")
            self.assertEqual(len(jobs), 25)
            self.assertEqual(len(jobs[1]["inputs"]), 8)
            self.assertNotIn("gt_nadir", {item["camera_id"] for item in jobs[1]["inputs"]})

    def test_flat_ground_stitcher_consumes_standard_dataset(self) -> None:
        try:
            import numpy as np
            from PIL import Image
        except ImportError:
            self.skipTest("optional stitching dependencies are unavailable")
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
            output = root / "bev"
            build_blender_plan(
                config,
                EXAMPLE / "route.kml",
                EXAMPLE / "minimal.gltf",
                dataset,
            )
            for frame in read_jsonl(dataset / "frames.jsonl"):
                image_path = dataset / frame["image"]
                image_path.parent.mkdir(parents=True, exist_ok=True)
                Image.fromarray(
                    np.full((64, 64, 3), (220, 30, 10), dtype=np.uint8), mode="RGB"
                ).save(image_path)
            result = run_planar_stitcher(dataset, output, meters_per_pixel=0.5, max_frames=2)
            self.assertEqual(result["frames_rendered"], 2)
            self.assertGreater(result["mean_coverage"], 0.0)
            with Image.open(output / "bev" / "000001.png") as bev:
                pixels = np.asarray(bev)
            visible = pixels[..., 3] > 0
            self.assertTrue(visible.any())
            self.assertGreater(float(pixels[..., 0][visible].mean()), 200.0)

    def test_stitcher_rejects_missing_images_instead_of_synthesizing_them(self) -> None:
        config = load_config(EXAMPLE / "mvp.toml")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "dataset"
            build_blender_plan(
                config,
                EXAMPLE / "route.kml",
                EXAMPLE / "minimal.gltf",
                dataset,
            )
            with self.assertRaisesRegex(ValueError, "image files are missing"):
                run_planar_stitcher(dataset, root / "bev", max_frames=1)


if __name__ == "__main__":
    unittest.main()
