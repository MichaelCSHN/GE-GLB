from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from geglb.config import load_config
from geglb.dataset import read_jsonl, validate_dataset
from geglb.planner import build_plan
from geglb.route import RoutePoint, load_route_kml, resample_route
from geglb.rig import camera_to_vehicle_transform


ROOT = Path(__file__).resolve().parents[1]


class RouteTests(unittest.TestCase):
    def test_loads_named_route(self) -> None:
        points = load_route_kml(ROOT / "examples" / "route.kml", "ROUTE")
        self.assertEqual(len(points), 3)
        self.assertAlmostEqual(points[0].longitude_deg, -5.6587797)

    def test_resamples_and_preserves_endpoints(self) -> None:
        points = [RoutePoint(0.0, 0.0), RoutePoint(0.0, 0.0001)]
        poses = resample_route(points, 2.0)
        self.assertGreater(len(poses), 5)
        self.assertAlmostEqual(poses[0].distance_m, 0.0)
        self.assertAlmostEqual(poses[0].heading_deg, 0.0, places=5)
        self.assertAlmostEqual(poses[-1].latitude_deg, 0.0001, places=8)

    def test_nadir_camera_transform_uses_standard_camera_axes(self) -> None:
        transform = camera_to_vehicle_transform((0.0, 0.0, 10.0), 0.0, 0.0, 0.0)
        # Camera +Z looks down, +X points vehicle-right, and +Y points vehicle-rear.
        self.assertEqual([row[2] for row in transform[:3]], [0.0, -0.0, -1.0])
        self.assertEqual([row[0] for row in transform[:3]], [-0.0, -1.0, 0.0])
        self.assertEqual([row[1] for row in transform[:3]], [-1.0, 0.0, 0.0])


class PlannerTests(unittest.TestCase):
    def test_builds_capture_artifacts(self) -> None:
        config = load_config(ROOT / "examples" / "mvp.toml")
        with tempfile.TemporaryDirectory() as directory:
            summary = build_plan(config, ROOT / "examples" / "route.kml", directory)
            output = Path(directory)
            self.assertGreater(summary["poses"], 1)
            self.assertTrue((output / "poses.csv").is_file())
            self.assertTrue((output / "calibration.json").is_file())
            self.assertTrue((output / "capture-plan.json").is_file())
            self.assertTrue((output / "fusion-plan.json").is_file())
            self.assertTrue((output / "capture-tour.kml").is_file())
            self.assertTrue((output / "manifest.json").is_file())
            self.assertTrue((output / "rig.json").is_file())
            self.assertTrue((output / "trajectory.jsonl").is_file())
            self.assertTrue((output / "frames.jsonl").is_file())

            plan = json.loads((output / "capture-plan.json").read_text(encoding="utf-8"))
            self.assertEqual(plan["capture_count"], plan["pose_count"] * 5)
            self.assertTrue(any(entry.get("ground_truth_only") for entry in plan["entries"]))

            fusion = json.loads((output / "fusion-plan.json").read_text(encoding="utf-8"))
            first = fusion["targets"][0]
            second = fusion["targets"][1]
            self.assertEqual(first["status"], "one_frame_delayed")
            self.assertEqual(first["latency_frames"], 1)
            self.assertEqual(len(first["observations"]), 8)
            self.assertEqual(second["status"], "causal")
            self.assertEqual(len(second["observations"]), 8)
            current = [
                item
                for item in second["observations"]
                if item["role"] == "current_surround"
            ]
            self.assertTrue(all(item["heuristic_prior"] == 1.0 for item in current))
            previous = [
                item
                for item in second["observations"]
                if item["role"] == "past_underbody_candidate"
            ]
            self.assertEqual(
                {item["camera_id"] for item in previous},
                {"front", "rear", "left", "right"},
            )
            priorities = {item["camera_id"]: item["heuristic_prior"] for item in previous}
            self.assertGreater(priorities["front"], priorities["left"])
            self.assertGreater(priorities["left"], priorities["rear"])

            root = ET.parse(output / "capture-tour.kml").getroot()
            namespaces = {
                "kml": "http://www.opengis.net/kml/2.2",
                "gx": "http://www.google.com/kml/ext/2.2",
            }
            fly_tos = root.findall(".//gx:FlyTo", namespaces)
            pauses = root.findall(".//gx:TourControl", namespaces)
            self.assertEqual(len(fly_tos), plan["capture_count"])
            self.assertEqual(len(pauses), plan["capture_count"])

            validation = validate_dataset(output)
            self.assertTrue(validation["valid"], validation)
            self.assertEqual(validation["source_kind"], "ge_pro")
            self.assertEqual(validation["image_frames"], plan["capture_count"])
            frames = read_jsonl(output / "frames.jsonl")
            self.assertEqual(frames[0]["camera_id"], "front")


if __name__ == "__main__":
    unittest.main()
