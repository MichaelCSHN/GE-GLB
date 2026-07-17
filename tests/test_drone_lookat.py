"""Tests for Task 03 drone LookAt neutral capture plan generator."""

from __future__ import annotations

import unittest

from geglb.core.trajectory import VehiclePose
from geglb.tasks.drone_lookat_set.capture_plan import (
    build_capture_model,
    default_spec,
)
from geglb.tasks.drone_lookat_set.specification import DroneLookAtSpec


class DefaultSpecTests(unittest.TestCase):
    def test_default_spec_is_valid(self) -> None:
        spec = default_spec()
        spec.validate()  # must not raise

    def test_observer_count_matches_azimuth_times_elevation(self) -> None:
        spec = default_spec()
        model = build_capture_model(spec)
        expected = len(spec.azimuth_deg) * len(spec.elevation_deg)  # 8 × 3 = 24
        self.assertEqual(len(model.entries), expected)
        self.assertEqual(len(model.ordered_states), expected)


class CaptureModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = DroneLookAtSpec(
            radius_m=100.0,
            azimuth_deg=(0.0, 90.0, 180.0, 270.0),
            elevation_deg=(30.0, 60.0),
        )
        self.model = build_capture_model(
            self.spec, horizontal_fov_deg=90.0, image_width=800, image_height=600
        )

    def test_each_entry_has_correct_camera_id_pattern(self) -> None:
        for entry in self.model.entries:
            cid = str(entry["camera_id"])
            self.assertRegex(cid, r"^az\d+_el\d+$")

    def test_each_entry_has_camera_world_fields(self) -> None:
        for entry in self.model.entries:
            self.assertIn("camera_id", entry)
            self.assertIn("output", entry)
            self.assertTrue(
                str(entry["output"]).startswith("images/"),
                f"output should start with images/: {entry['output']}",
            )
            camera = entry["camera"]
            self.assertIsInstance(camera, dict)
            for key in (
                "camera_id",
                "longitude_deg",
                "latitude_deg",
                "altitude_relative_m",
                "heading_deg",
                "tilt_deg",
                "roll_deg",
                "horizontal_fov_deg",
            ):
                self.assertIn(key, camera, f"missing {key} in camera state")

    def test_observer_tilt_points_toward_vehicle(self) -> None:
        # Tilt should be < 90° (above horizon, looking down at vehicle).
        for _pose, state in self.model.ordered_states:
            self.assertLess(state.tilt_deg, 90.0, f"{state.camera_id} tilt >= 90")

        # Higher elevation → smaller tilt (closer to nadir).
        # Compare same azimuth, different elevations.
        el30_states = [s for _p, s in self.model.ordered_states if s.camera_id.endswith("_el30")]
        el60_states = [s for _p, s in self.model.ordered_states if s.camera_id.endswith("_el60")]
        self.assertTrue(len(el30_states) > 0)
        self.assertTrue(len(el60_states) > 0)
        for s30, s60 in zip(el30_states, el60_states):
            self.assertGreater(
                s30.tilt_deg,
                s60.tilt_deg,
                f"el30 {s30.tilt_deg} > el60 {s60.tilt_deg} for {s30.camera_id}",
            )

    def test_deterministic_order(self) -> None:
        def _sequence_ids(spec: DroneLookAtSpec) -> list[str]:
            model = build_capture_model(spec)
            return [str(e["camera_id"]) for e in model.entries]

        first = _sequence_ids(self.spec)
        second = _sequence_ids(self.spec)
        self.assertEqual(first, second)

    def test_heading_changes_with_azimuth(self) -> None:
        # For a fixed vehicle pose, different azimuths give different headings.
        headings_by_az: dict[str, set[float]] = {}
        for _pose, state in self.model.ordered_states:
            # camera_id like "az0_el30" — extract azimuth part
            parts = state.camera_id.split("_")
            az_part = parts[0]  # e.g. "az0"
            headings_by_az.setdefault(az_part, set()).add(state.heading_deg)

        # Each azimuth group should have consistent heading across elevations.
        for az_part, headings in headings_by_az.items():
            self.assertEqual(
                len(headings),
                1,
                f"{az_part} has {len(headings)} different headings: {headings}",
            )


class MultiPoseTests(unittest.TestCase):
    def test_multi_pose_produces_correct_count(self) -> None:
        spec = default_spec()
        poses = [
            VehiclePose(
                index=0, distance_m=0.0, longitude_deg=0.0, latitude_deg=0.0, heading_deg=0.0
            ),
            VehiclePose(
                index=1, distance_m=10.0, longitude_deg=0.0, latitude_deg=0.00009, heading_deg=90.0
            ),
        ]
        model = build_capture_model(spec, poses=poses)
        views_per_pose = len(spec.azimuth_deg) * len(spec.elevation_deg)  # 24
        expected = len(poses) * views_per_pose
        self.assertEqual(len(model.entries), expected)
        self.assertEqual(len(model.ordered_states), expected)
        pose_indices = {int(e["pose_index"]) for e in model.entries}
        self.assertEqual(pose_indices, {0, 1})


class CalibrationTests(unittest.TestCase):
    def test_calibration_has_shared_intrinsics(self) -> None:
        spec = default_spec()
        model = build_capture_model(spec)
        cameras = model.calibration["cameras"]
        self.assertEqual(len(cameras), 24)

        # All calibration entries share the same intrinsics values.
        first_fx = cameras[0]["intrinsics"]["fx"]
        for cam in cameras[1:]:
            self.assertEqual(cam["intrinsics"]["fx"], first_fx)


if __name__ == "__main__":
    unittest.main()
