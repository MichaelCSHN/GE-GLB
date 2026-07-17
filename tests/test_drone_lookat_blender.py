"""Tests for Task 03 drone LookAt Blender capture workflow."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from geglb.core.dataset import read_jsonl
from geglb.core.trajectory import VehiclePose
from geglb.tasks.drone_lookat_set.capture_plan import default_spec
from geglb.tasks.drone_lookat_set.specification import DroneLookAtSpec
from geglb.tasks.drone_lookat_set.workflows.blender import build_blender_plan

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "01-underbody-image"


class BlenderJobTests(unittest.TestCase):
    """Tests that the generated blender-job.json is well-formed."""

    def setUp(self) -> None:
        self.spec = DroneLookAtSpec(
            radius_m=100.0,
            azimuth_deg=(0.0, 180.0),
            elevation_deg=(45.0,),
        )

    def test_generates_valid_blender_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "lookat"
            build_blender_plan(
                self.spec,
                scene_glb=EXAMPLES / "minimal.gltf",
                output_dir=out,
                horizontal_fov_deg=60.0,
                image_width=1024,
                image_height=768,
            )
            job_path = out / "blender-job.json"
            self.assertTrue(job_path.is_file(), "blender-job.json is missing")

            job = json.loads(job_path.read_text(encoding="utf-8"))
            self.assertEqual(job["schema_version"], "ge-glb.blender-job/v1")
            self.assertEqual(job["project"], "task03_drone_lookat")
            self.assertIn("scene_glb", job)
            self.assertIn("dataset_dir", job)

            render = job["render"]
            self.assertEqual(render["engine"], "BLENDER_EEVEE_NEXT")
            self.assertEqual(render["samples"], 32)
            self.assertEqual(render["width"], 1024)
            self.assertEqual(render["height"], 768)

            # 2 az × 1 el = 2 frames
            self.assertEqual(len(job["frames"]), 2)

            for frame in job["frames"]:
                self.assertIn("camera_world", frame)
                cw = frame["camera_world"]
                self.assertIn("local_enu_m", cw)
                self.assertIn("heading_deg", cw)
                self.assertIn("tilt_from_nadir_deg", cw)

    def test_dataset_files_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "lookat"
            build_blender_plan(
                self.spec,
                scene_glb=EXAMPLES / "minimal.gltf",
                output_dir=out,
            )

            self.assertTrue((out / "manifest.json").is_file())
            self.assertTrue((out / "rig.json").is_file())
            self.assertTrue((out / "trajectory.jsonl").is_file())
            self.assertTrue((out / "frames.jsonl").is_file())
            self.assertTrue((out / "blender-command.json").is_file())

            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], "ge-glb.dataset/v1")
            # No fusion_plan for Task 03.
            self.assertNotIn("fusion_plan", manifest.get("files", {}))

            frames = read_jsonl(out / "frames.jsonl")
            self.assertEqual(len(frames), 2)

    def test_camera_world_positions_are_reasonable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "lookat"
            build_blender_plan(
                self.spec,
                scene_glb=EXAMPLES / "minimal.gltf",
                output_dir=out,
            )
            frames = read_jsonl(out / "frames.jsonl")
            for frame in frames:
                cw = frame["camera_world"]
                up = float(cw["local_enu_m"]["up"])
                # Observer elevation 45° at radius 100 → height ≈ 100*sin(45°) ≈ 70.7
                self.assertGreater(up, 50.0)
                self.assertLess(up, 100.0)

                # Tilt should be < 90 (looking down at vehicle)
                self.assertLess(cw["tilt_from_nadir_deg"], 90.0)

    def test_plan_result_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "lookat"
            result = build_blender_plan(
                self.spec,
                scene_glb=EXAMPLES / "minimal.gltf",
                output_dir=out,
            )
            self.assertEqual(result.workflow_id, "TASK03_BLENDER")
            self.assertEqual(result.source_kind, "blender")
            self.assertTrue(Path(result.output_dir).is_dir())
            self.assertIn("poses", result.counts)
            self.assertIn("captures", result.counts)
            self.assertGreater(len(result.artifacts), 0)

    def test_rejects_invalid_scene_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "lookat"
            with self.assertRaises(FileNotFoundError):
                build_blender_plan(
                    self.spec,
                    scene_glb=Path(tmp) / "nope.glb",
                    output_dir=out,
                )

    def test_multi_pose_trajectory(self) -> None:
        spec = default_spec()
        poses = [
            VehiclePose(
                index=0, distance_m=0.0, longitude_deg=0.0, latitude_deg=0.0, heading_deg=0.0
            ),
            VehiclePose(
                index=1, distance_m=10.0, longitude_deg=0.0, latitude_deg=0.00009, heading_deg=0.0
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "lookat"
            build_blender_plan(
                spec,
                scene_glb=EXAMPLES / "minimal.gltf",
                output_dir=out,
                poses=poses,
            )
            trajectory = read_jsonl(out / "trajectory.jsonl")
            self.assertEqual(len(trajectory), 2)

            frames = read_jsonl(out / "frames.jsonl")
            # 24 views × 2 poses = 48 frames
            self.assertEqual(len(frames), 48)
            pose_indices = {int(f["frame_index"]) for f in frames}
            self.assertEqual(pose_indices, {0, 1})


if __name__ == "__main__":
    unittest.main()
