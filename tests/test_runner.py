"""Tests for the end-to-end runner and CLI product/blender-v2 commands."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class RunnerTests(unittest.TestCase):
    def test_run_plan_only(self) -> None:
        """geglb run underbody without blender → plan complete, render pending."""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            rc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "geglb",
                    "run",
                    "underbody",
                    "--config",
                    str(EXAMPLES / "01-underbody-image" / "mvp.toml"),
                    "--route",
                    str(EXAMPLES / "01-underbody-image" / "route.kml"),
                    "--scene",
                    str(EXAMPLES / "01-underbody-image" / "minimal.gltf"),
                    "--out",
                    str(out),
                ],
                capture_output=True,
                text=True,
            )
            # Exit 0 because plan succeeded, render is pending (not failed)
            self.assertEqual(rc.returncode, 0)
            run_json = json.loads((out / "run.json").read_text(encoding="utf-8"))
            steps = run_json["steps"]
            self.assertEqual(steps["plan"]["status"], "complete")
            self.assertEqual(steps["render"]["status"], "pending")

    def test_run_resume(self) -> None:
        """--resume skips completed steps."""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            # First run.
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "geglb",
                    "run",
                    "underbody",
                    "--config",
                    str(EXAMPLES / "01-underbody-image" / "mvp.toml"),
                    "--route",
                    str(EXAMPLES / "01-underbody-image" / "route.kml"),
                    "--scene",
                    str(EXAMPLES / "01-underbody-image" / "minimal.gltf"),
                    "--out",
                    str(out),
                ],
                capture_output=True,
            )
            # Second run with --resume.
            rc2 = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "geglb",
                    "run",
                    "underbody",
                    "--config",
                    str(EXAMPLES / "01-underbody-image" / "mvp.toml"),
                    "--route",
                    str(EXAMPLES / "01-underbody-image" / "route.kml"),
                    "--scene",
                    str(EXAMPLES / "01-underbody-image" / "minimal.gltf"),
                    "--out",
                    str(out),
                    "--resume",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(rc2.returncode, 0)

    def test_run_with_invalid_blender_exec(self) -> None:
        """--blender-exec pointing to non-existent path fails gracefully."""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            # First run the plan step.
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "geglb",
                    "run",
                    "underbody",
                    "--config",
                    str(EXAMPLES / "01-underbody-image" / "mvp.toml"),
                    "--route",
                    str(EXAMPLES / "01-underbody-image" / "route.kml"),
                    "--scene",
                    str(EXAMPLES / "01-underbody-image" / "minimal.gltf"),
                    "--out",
                    str(out),
                ],
                capture_output=True,
            )
            # Now run again with invalid blender exec.
            rc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "geglb",
                    "run",
                    "underbody",
                    "--config",
                    str(EXAMPLES / "01-underbody-image" / "mvp.toml"),
                    "--route",
                    str(EXAMPLES / "01-underbody-image" / "route.kml"),
                    "--scene",
                    str(EXAMPLES / "01-underbody-image" / "minimal.gltf"),
                    "--out",
                    str(out),
                    "--resume",
                    "--blender-exec",
                    "/nonexistent/blender",
                ],
                capture_output=True,
                text=True,
            )
            # Should fail at render step with non-zero exit
            self.assertNotEqual(rc.returncode, 0)

    def test_run_product_and_validate(self) -> None:
        """On an existing dataset, composite→product→validate succeeds."""
        from geglb.workflows.runner import run_task

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            # Generate dataset first.
            from geglb.core.config import load_config
            from geglb.tasks.underbody_image.workflows.blender import build_blender_plan

            config = load_config(EXAMPLES / "01-underbody-image" / "mvp.toml")
            build_blender_plan(
                config,
                EXAMPLES / "01-underbody-image" / "route.kml",
                EXAMPLES / "01-underbody-image" / "minimal.gltf",
                out,
            )
            # Write synthetic images so composite works.
            try:
                import numpy as np
                from PIL import Image
            except ImportError:
                self.skipTest("stitching deps unavailable")
            from geglb.core.dataset import read_jsonl

            for frame in read_jsonl(out / "frames.jsonl"):
                img_path = out / Path(str(frame["image"]))
                img_path.parent.mkdir(parents=True, exist_ok=True)
                colour = (80, 160, 240) if frame.get("ground_truth_only") else (220, 30, 10)
                Image.fromarray(np.full((64, 64, 3), colour, dtype=np.uint8), mode="RGB").save(
                    img_path
                )

            rc = run_task(
                task_id="task01_underbody",
                out_dir=out,
                existing=True,
            )
            self.assertEqual(rc, 0)
            run_json = json.loads((out / "run.json").read_text(encoding="utf-8"))
            steps = run_json["steps"]
            self.assertEqual(steps["plan"]["status"], "complete")
            self.assertEqual(steps["composite"]["status"], "complete")
            self.assertEqual(steps["product"]["status"], "complete")
            self.assertTrue((out / "product" / "underbody.png").is_file())


class CLISmokeTests(unittest.TestCase):
    def test_product_panorama_cli(self) -> None:
        """geglb product panorama generates output files."""
        try:
            import numpy as np
            from PIL import Image
        except ImportError:
            self.skipTest("stitching deps unavailable")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            from geglb.core.dataset import read_jsonl
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
            dataset = root / "dataset"
            build_blender_plan(
                spec,
                bus_length_m=8.0,
                bus_width_m=2.5,
                bus_height_m=3.0,
                scene_glb=EXAMPLES / "01-underbody-image" / "minimal.gltf",
                output_dir=dataset,
                image_width=64,
                image_height=64,
            )
            for frame in read_jsonl(dataset / "frames.jsonl"):
                img_path = dataset / Path(str(frame["image"]))
                img_path.parent.mkdir(parents=True, exist_ok=True)
                Image.fromarray(
                    np.full((64, 64, 3), (100, 150, 200), dtype=np.uint8), mode="RGB"
                ).save(img_path)

            rc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "geglb",
                    "product",
                    "panorama",
                    "--dataset",
                    str(dataset),
                    "--out",
                    str(root / "out"),
                    "--width",
                    "100",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(rc.returncode, 0)
            self.assertTrue((root / "out" / "product" / "panorama.png").is_file())

    def test_product_lookat_cli(self) -> None:
        """geglb product lookat generates output files."""
        try:
            import numpy as np
            from PIL import Image
        except ImportError:
            self.skipTest("stitching deps unavailable")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            from geglb.core.dataset import read_jsonl
            from geglb.tasks.drone_lookat_set.capture_plan import default_spec
            from geglb.tasks.drone_lookat_set.workflows.blender import build_blender_plan

            spec = default_spec()
            dataset = root / "dataset"
            build_blender_plan(
                spec,
                scene_glb=EXAMPLES / "01-underbody-image" / "minimal.gltf",
                output_dir=dataset,
                horizontal_fov_deg=60.0,
                image_width=64,
                image_height=48,
            )
            for frame in read_jsonl(dataset / "frames.jsonl"):
                img_path = dataset / Path(str(frame["image"]))
                img_path.parent.mkdir(parents=True, exist_ok=True)
                Image.fromarray(
                    np.full((48, 64, 3), (100, 150, 200), dtype=np.uint8), mode="RGB"
                ).save(img_path)

            rc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "geglb",
                    "product",
                    "lookat",
                    "--dataset",
                    str(dataset),
                    "--out",
                    str(root / "out"),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(rc.returncode, 0)
            self.assertTrue((root / "out" / "product" / "viewset.json").is_file())

    def test_blender_plan_v2_cli(self) -> None:
        """geglb blender plan-v2 generates a v2 run directory."""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            rc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "geglb",
                    "blender",
                    "plan-v2",
                    "--config",
                    str(EXAMPLES / "01-underbody-image" / "mvp.toml"),
                    "--route",
                    str(EXAMPLES / "01-underbody-image" / "route.kml"),
                    "--scene",
                    str(EXAMPLES / "01-underbody-image" / "minimal.gltf"),
                    "--out",
                    str(out),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(rc.returncode, 0)
            self.assertTrue((out / "run.json").is_file())
            self.assertTrue((out / "capture" / "manifest.json").is_file())


if __name__ == "__main__":
    unittest.main()
