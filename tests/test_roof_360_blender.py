"""Tests for Task 02 roof-360 Blender capture workflow."""

from __future__ import annotations

import json
import py_compile
import tempfile
import unittest
from pathlib import Path

from geglb.core.dataset import read_jsonl
from geglb.core.trajectory import VehiclePose
from geglb.tasks.roof_360_pano.capture_plan import default_spec
from geglb.tasks.roof_360_pano.specification import CaptureBand, Roof360Spec
from geglb.tasks.roof_360_pano.workflows.blender import build_blender_plan

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "01-underbody-image"


class BlenderJobTests(unittest.TestCase):
    """Tests that the generated blender-job.json is well-formed."""

    def setUp(self) -> None:
        self.spec = Roof360Spec(
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

    def test_generates_valid_blender_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "roof360"
            build_blender_plan(
                self.spec,
                bus_length_m=8.0,
                bus_width_m=2.5,
                bus_height_m=3.0,
                scene_glb=EXAMPLES / "minimal.gltf",
                output_dir=out,
            )
            job_path = out / "blender-job.json"
            self.assertTrue(job_path.is_file(), "blender-job.json is missing")

            job = json.loads(job_path.read_text(encoding="utf-8"))
            self.assertEqual(job["schema_version"], "ge-glb.blender-job/v1")
            self.assertEqual(job["project"], "task02_roof_360")
            self.assertIn("scene_glb", job)
            self.assertIn("dataset_dir", job)

            render = job["render"]
            self.assertEqual(render["engine"], "BLENDER_EEVEE_NEXT")
            self.assertEqual(render["samples"], 32)
            self.assertEqual(render["width"], 1920)
            self.assertEqual(render["height"], 1080)
            self.assertEqual(render["file_format"], "PNG")
            self.assertIs(render["transparent_background"], False)
            self.assertIs(render["add_default_sun_if_missing"], True)

            # 2 bands × 2 azimuths = 4 frames
            self.assertEqual(len(job["frames"]), 4)

            for frame in job["frames"]:
                self.assertIn("camera_world", frame)
                cw = frame["camera_world"]
                self.assertIn("local_enu_m", cw)
                self.assertIn("heading_deg", cw)
                self.assertIn("tilt_from_nadir_deg", cw)
                self.assertIn("roll_deg", cw)
                self.assertIn("horizontal_fov_deg", cw)

    def test_blender_runner_script_compiles_without_bpy(self) -> None:
        runner = Path(__file__).resolve().parents[1] / "scripts" / "blender_capture.py"
        self.assertTrue(runner.is_file(), "blender_capture.py not found")
        # Must compile in isolation — bpy is NOT available in this Python.
        py_compile.compile(runner, doraise=True)

    def test_dataset_files_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "roof360"
            build_blender_plan(
                self.spec,
                bus_length_m=8.0,
                bus_width_m=2.5,
                bus_height_m=3.0,
                scene_glb=EXAMPLES / "minimal.gltf",
                output_dir=out,
            )

            manifest_path = out / "manifest.json"
            self.assertTrue(manifest_path.is_file())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], "ge-glb.dataset/v1")
            self.assertEqual(manifest["status"], "planned")
            # No fusion_plan reference for Task 02.
            self.assertNotIn("fusion_plan", manifest.get("files", {}))

            self.assertTrue((out / "rig.json").is_file())
            self.assertTrue((out / "trajectory.jsonl").is_file())
            self.assertTrue((out / "frames.jsonl").is_file())
            self.assertTrue((out / "blender-command.json").is_file())

            trajectory = read_jsonl(out / "trajectory.jsonl")
            self.assertEqual(len(trajectory), 1)
            for item in trajectory:
                self.assertIn("vehicle_to_world", item)
                v2w = item["vehicle_to_world"]
                self.assertEqual(len(v2w), 4)
                self.assertEqual(len(v2w[0]), 4)

            frames = read_jsonl(out / "frames.jsonl")
            self.assertEqual(len(frames), 4)

    def test_each_frame_has_correct_camera_world(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "roof360"
            build_blender_plan(
                self.spec,
                bus_length_m=8.0,
                bus_width_m=2.5,
                bus_height_m=3.0,
                scene_glb=EXAMPLES / "minimal.gltf",
                output_dir=out,
            )

            frames = read_jsonl(out / "frames.jsonl")
            mast_up = 3.0 + 1.5  # bus_height + mast_height
            for frame in frames:
                cw = frame["camera_world"]
                # Camera is at origin in ENU for single-pose fixture.
                self.assertAlmostEqual(float(cw["local_enu_m"]["east"]), 0.0, places=6)
                self.assertAlmostEqual(float(cw["local_enu_m"]["north"]), 0.0, places=6)
                self.assertAlmostEqual(float(cw["local_enu_m"]["up"]), mast_up, places=6)
                self.assertEqual(cw["roll_deg"], 0.0)
                self.assertTrue(1.0 < cw["horizontal_fov_deg"] < 179.0)

    def test_plan_result_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "roof360"
            result = build_blender_plan(
                self.spec,
                bus_length_m=8.0,
                bus_width_m=2.5,
                bus_height_m=3.0,
                scene_glb=EXAMPLES / "minimal.gltf",
                output_dir=out,
            )
            self.assertEqual(result.workflow_id, "TASK02_BLENDER")
            self.assertEqual(result.source_kind, "blender")
            self.assertTrue(Path(result.output_dir).is_dir())
            self.assertIn("poses", result.counts)
            self.assertIn("captures", result.counts)
            self.assertGreater(len(result.artifacts), 0)
            dict_form = result.as_dict()
            self.assertEqual(dict_form["mvp"], "TASK02_BLENDER")
            self.assertEqual(dict_form["source_kind"], "blender")

    def test_rejects_invalid_scene_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "roof360"
            with self.assertRaises(FileNotFoundError):
                build_blender_plan(
                    self.spec,
                    bus_length_m=8.0,
                    bus_width_m=2.5,
                    bus_height_m=3.0,
                    scene_glb=Path(tmp) / "nope.glb",
                    output_dir=out,
                )

    def test_rejects_wrong_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "roof360"
            bad = Path(tmp) / "scene.blend"
            bad.write_text("not a scene", encoding="utf-8")
            with self.assertRaises(ValueError):
                build_blender_plan(
                    self.spec,
                    bus_length_m=8.0,
                    bus_width_m=2.5,
                    bus_height_m=3.0,
                    scene_glb=bad,
                    output_dir=out,
                )


class MultiPoseBlenderTests(unittest.TestCase):
    def test_multi_pose_trajectory(self) -> None:
        spec = default_spec()
        poses = [
            VehiclePose(
                index=0, distance_m=0.0, longitude_deg=0.0, latitude_deg=0.0, heading_deg=0.0
            ),
            VehiclePose(
                index=1, distance_m=5.0, longitude_deg=0.0, latitude_deg=0.000045, heading_deg=0.0
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "roof360"
            build_blender_plan(
                spec,
                bus_length_m=8.0,
                bus_width_m=2.5,
                bus_height_m=3.0,
                scene_glb=EXAMPLES / "minimal.gltf",
                output_dir=out,
                poses=poses,
            )
            trajectory = read_jsonl(out / "trajectory.jsonl")
            self.assertEqual(len(trajectory), 2)
            # Second pose should have non-zero ENU.
            self.assertGreater(float(trajectory[1]["local_enu_m"]["north"]), 0.0)

            frames = read_jsonl(out / "frames.jsonl")
            # 8 cameras × 2 poses = 16 frames
            self.assertEqual(len(frames), 16)
            pose_indices = {int(f["frame_index"]) for f in frames}
            self.assertEqual(pose_indices, {0, 1})


class BlenderCommandTests(unittest.TestCase):
    def test_command_file_is_valid(self) -> None:
        spec = default_spec()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "roof360"
            build_blender_plan(
                spec,
                bus_length_m=8.0,
                bus_width_m=2.5,
                bus_height_m=3.0,
                scene_glb=EXAMPLES / "minimal.gltf",
                output_dir=out,
            )
            cmd = json.loads((out / "blender-command.json").read_text(encoding="utf-8"))
            self.assertEqual(cmd["executable"], "blender")
            self.assertIn("--background", cmd["arguments"])
            self.assertIn("--python", cmd["arguments"])
            self.assertIn("scripts/blender_capture.py", cmd["arguments"])


if __name__ == "__main__":
    unittest.main()
