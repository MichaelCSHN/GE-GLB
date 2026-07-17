"""Tests for the v2 capture-dataset writer and v2 blender workflows."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from geglb.core.dataset import DATASET_V2_SCHEMA, read_jsonl, write_jsonl
from geglb.core.dataset_v2 import write_capture_dataset_v2
from geglb.tasks.drone_lookat_set.capture_plan import (
    default_spec as lookat_default_spec,
)
from geglb.tasks.drone_lookat_set.workflows.blender_v2 import (
    build_blender_plan_v2 as lookat_v2,
)
from geglb.tasks.roof_360_pano.capture_plan import default_spec as roof_default_spec
from geglb.tasks.roof_360_pano.workflows.blender_v2 import (
    build_blender_plan_v2 as roof_v2,
)
from geglb.tasks.underbody_image.workflows.blender_v2 import (
    build_blender_plan_v2 as underbody_v2,
)

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "01-underbody-image"


def _make_minimal_model():
    """Return a minimal Task 02 CaptureModel for unit-testing the writer."""
    spec = roof_default_spec()
    from geglb.tasks.roof_360_pano.capture_plan import build_capture_model

    return build_capture_model(spec, bus_length_m=8.0, bus_width_m=2.5, bus_height_m=3.0)


class DatasetV2WriterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = _make_minimal_model()

    def test_writes_all_required_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            write_capture_dataset_v2(
                output_dir=out,
                task_id="task02_roof_360",
                product_schema="ge-glb.product.panorama-360/v1",
                source_kind="blender",
                source_backend="blender",
                source_metadata={"adapter": "blender_python"},
                model=self.model,
                config_snapshot={"width": 1920},
                dependency_hashes={},
            )
            self.assertTrue((out / "run.json").is_file())
            self.assertTrue((out / "capture-plan.json").is_file())
            self.assertTrue((out / "capture" / "manifest.json").is_file())
            self.assertTrue((out / "capture" / "observations.jsonl").is_file())
            self.assertTrue((out / "capture" / "rigs" / "rig.json").is_file())
            self.assertTrue((out / "capture" / "trajectories" / "trajectory.jsonl").is_file())

    def test_run_json_has_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            write_capture_dataset_v2(
                output_dir=out,
                task_id="task02_roof_360",
                product_schema="ge-glb.product.panorama-360/v1",
                source_kind="blender",
                source_backend="blender",
                source_metadata={"adapter": "blender_python"},
                model=self.model,
                config_snapshot={"width": 1920},
                dependency_hashes={},
            )
            run_json = json.loads((out / "run.json").read_text(encoding="utf-8"))
            self.assertIn("provenance", run_json)
            prov = run_json["provenance"]
            self.assertIn("hashes", prov)
            self.assertIsInstance(prov["hashes"], dict)
            self.assertGreater(len(prov["hashes"]), 0)
            self.assertIn("dependencies", prov)
            self.assertIn("git_commit", run_json)
            self.assertIsInstance(run_json["git_commit"], str)
            self.assertGreater(len(run_json["git_commit"]), 0)

    def test_run_json_has_execution_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            write_capture_dataset_v2(
                output_dir=out,
                task_id="task02_roof_360",
                product_schema="ge-glb.product.panorama-360/v1",
                source_kind="blender",
                source_backend="blender",
                source_metadata={},
                model=self.model,
                config_snapshot={},
                dependency_hashes={},
            )
            run_json = json.loads((out / "run.json").read_text(encoding="utf-8"))
            exec_block = run_json["execution"]
            self.assertEqual(exec_block["status"], "complete")
            self.assertIn("started_at", exec_block)
            self.assertIn("completed_at", exec_block)
            self.assertIn("frames_total", exec_block)
            self.assertGreater(exec_block["frames_total"], 0)

    def test_observations_have_camera_to_world(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            write_capture_dataset_v2(
                output_dir=out,
                task_id="task02_roof_360",
                product_schema="ge-glb.product.panorama-360/v1",
                source_kind="blender",
                source_backend="blender",
                source_metadata={},
                model=self.model,
                config_snapshot={},
                dependency_hashes={},
            )
            obs = read_jsonl(out / "capture" / "observations.jsonl")
            self.assertGreater(len(obs), 0)
            for item in obs:
                self.assertIn("observation_id", item)
                self.assertIn("camera_to_world", item)
                c2w = item["camera_to_world"]
                self.assertEqual(len(c2w), 4)
                self.assertEqual(len(c2w[0]), 4)

    def test_images_root_directory_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            write_capture_dataset_v2(
                output_dir=out,
                task_id="task02_roof_360",
                product_schema="ge-glb.product.panorama-360/v1",
                source_kind="blender",
                source_backend="blender",
                source_metadata={},
                model=self.model,
                config_snapshot={},
                dependency_hashes={},
            )
            images_dir = out / "capture" / "images"
            self.assertTrue(images_dir.is_dir())

    def test_v2_does_not_modify_v1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            # Pre-write a dummy v1 file next to where v2 would write.
            out.mkdir(parents=True)
            v1_dummy = out / "manifest.json"
            v1_dummy.write_text(
                json.dumps({"schema_version": "ge-glb.dataset/v1"}), encoding="utf-8"
            )
            write_capture_dataset_v2(
                output_dir=out,
                task_id="task02_roof_360",
                product_schema="ge-glb.product.panorama-360/v1",
                source_kind="blender",
                source_backend="blender",
                source_metadata={},
                model=self.model,
                config_snapshot={},
                dependency_hashes={},
            )
            # v2 does not touch the dummy v1 file.
            self.assertTrue(v1_dummy.is_file())
            self.assertEqual(
                json.loads(v1_dummy.read_text(encoding="utf-8"))["schema_version"],
                "ge-glb.dataset/v1",
            )

    def test_resumable_status_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "run"
            write_capture_dataset_v2(
                output_dir=out,
                task_id="task02_roof_360",
                product_schema="ge-glb.product.panorama-360/v1",
                source_kind="blender",
                source_backend="blender",
                source_metadata={},
                model=self.model,
                config_snapshot={},
                dependency_hashes={},
            )
            obs = read_jsonl(out / "capture" / "observations.jsonl")
            self.assertGreater(len(obs), 0)
            # Mark one frame as captured, one as failed.
            obs[0]["status"] = "captured"
            obs[1]["status"] = "failed"
            write_jsonl(out / "capture" / "observations.jsonl", obs)

            # Re-read and verify.
            reloaded = read_jsonl(out / "capture" / "observations.jsonl")
            self.assertEqual(reloaded[0]["status"], "captured")
            self.assertEqual(reloaded[1]["status"], "failed")


class Task01V2WorkflowTests(unittest.TestCase):
    def test_task01_v2_workflow(self) -> None:
        from geglb.core.config import load_config

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "run"
            config = load_config(EXAMPLES / "mvp.toml")
            result = underbody_v2(
                config=config,
                route_kml=EXAMPLES / "route.kml",
                scene_glb=EXAMPLES / "minimal.gltf",
                output_dir=out,
            )
            self.assertEqual(result.source_kind, "blender")

            run_json = json.loads((out / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(run_json["task_id"], "task01_underbody")
            self.assertEqual(run_json["schema_version"], "ge-glb.run/v2")
            self.assertIn("provenance", run_json)

            manifest = json.loads((out / "capture" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], DATASET_V2_SCHEMA)

            self.assertTrue((out / "blender-job.json").is_file())


class Task02V2WorkflowTests(unittest.TestCase):
    def test_task02_v2_workflow(self) -> None:
        spec = roof_default_spec()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "run"
            result = roof_v2(
                spec=spec,
                bus_length_m=8.0,
                bus_width_m=2.5,
                bus_height_m=3.0,
                scene_glb=EXAMPLES / "minimal.gltf",
                output_dir=out,
            )
            self.assertEqual(result.source_kind, "blender")

            run_json = json.loads((out / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(run_json["task_id"], "task02_roof_360")

            manifest = json.loads((out / "capture" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], DATASET_V2_SCHEMA)
            self.assertTrue((out / "blender-job.json").is_file())


class Task03V2WorkflowTests(unittest.TestCase):
    def test_task03_v2_workflow(self) -> None:
        spec = lookat_default_spec()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "run"
            result = lookat_v2(
                spec=spec,
                scene_glb=EXAMPLES / "minimal.gltf",
                output_dir=out,
            )
            self.assertEqual(result.source_kind, "blender")

            run_json = json.loads((out / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(run_json["task_id"], "task03_drone_lookat")

            manifest = json.loads((out / "capture" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], DATASET_V2_SCHEMA)
            self.assertTrue((out / "blender-job.json").is_file())


if __name__ == "__main__":
    unittest.main()
