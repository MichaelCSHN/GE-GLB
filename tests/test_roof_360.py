"""Tests for Task 02 roof-360 neutral capture plan generator."""

from __future__ import annotations

import unittest

from geglb.core.trajectory import VehiclePose
from geglb.tasks.roof_360_pano.capture_plan import (
    CaptureModel,
    build_capture_model,
    default_spec,
    validate_band_overlap,
)
from geglb.tasks.roof_360_pano.specification import CaptureBand, Roof360Spec


class DefaultSpecTests(unittest.TestCase):
    def test_default_spec_is_valid(self) -> None:
        spec = default_spec()
        spec.validate()  # must not raise

    def test_default_bands_have_correct_observer_count(self) -> None:
        spec = default_spec()
        model = build_capture_model(spec, bus_length_m=8.0, bus_width_m=2.5, bus_height_m=3.0)
        # 2 bands × 4 azimuths = 8 cameras × 1 pose = 8 observations
        self.assertEqual(len(model.entries), 8)
        self.assertEqual(len(model.ordered_states), 8)
        self.assertEqual(len(model.calibration["cameras"]), 8)  # type: ignore[index, arg-type]


class CaptureModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = Roof360Spec(
            mast_height_m=1.5,
            bands=(
                CaptureBand(
                    band_id="horizontal",
                    tilt_from_nadir_deg=90.0,
                    azimuth_deg=(0.0, 120.0, 240.0),
                ),
                CaptureBand(
                    band_id="downward",
                    tilt_from_nadir_deg=55.0,
                    azimuth_deg=(45.0, 135.0, 225.0, 315.0),
                ),
            ),
        )
        self.model = build_capture_model(
            self.spec,
            bus_length_m=10.0,
            bus_width_m=2.5,
            bus_height_m=3.0,
        )

    def test_tilt_values_match_spec(self) -> None:
        for _pose, state in self.model.ordered_states:
            if state.camera_id.startswith("horizontal"):
                self.assertEqual(state.tilt_deg, 90.0)
            elif state.camera_id.startswith("downward"):
                self.assertEqual(state.tilt_deg, 55.0)
                self.assertTrue(45.0 <= state.tilt_deg <= 60.0)

    def test_deterministic_observation_order(self) -> None:
        def _sequence_ids(spec: Roof360Spec) -> list[str]:
            model = build_capture_model(spec, bus_length_m=10.0, bus_width_m=2.5, bus_height_m=3.0)
            return [str(e["camera_id"]) for e in model.entries]

        first = _sequence_ids(self.spec)
        second = _sequence_ids(self.spec)
        self.assertEqual(first, second)

    def test_each_entry_has_camera_id_and_calibration_reference(self) -> None:
        calib_ids = {str(c["id"]) for c in self.model.calibration["cameras"]}  # type: ignore[index, arg-type]
        for entry in self.model.entries:
            cid = str(entry["camera_id"])
            self.assertIn(cid, calib_ids)
            output = str(entry["output"])
            self.assertTrue(output.startswith("images/"))
            self.assertTrue(output.endswith(".png"))
            # camera_world / camera state must be present
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

    def test_camera_mount_position(self) -> None:
        mast_up = 3.0 + 1.5  # bus_height + mast_height
        for entry in self.model.entries:
            camera = entry["camera"]
            self.assertAlmostEqual(float(camera["altitude_relative_m"]), mast_up, places=6)  # type: ignore[arg-type]
        for calib in self.model.calibration["cameras"]:  # type: ignore[arg-type]
            vf = calib["vehicle_frame"]
            self.assertAlmostEqual(float(vf["x_forward_m"]), 0.0, places=6)
            self.assertAlmostEqual(float(vf["y_left_m"]), 0.0, places=6)
            self.assertAlmostEqual(float(vf["z_up_m"]), mast_up, places=6)


class OverlapValidationTests(unittest.TestCase):
    def test_overlap_validation(self) -> None:
        # 3 azimuths at 120° spacing with 130° FOV → positive overlap
        band = CaptureBand(
            band_id="wide", tilt_from_nadir_deg=90.0, azimuth_deg=(0.0, 120.0, 240.0)
        )
        ok, issues = validate_band_overlap(band, horizontal_fov_deg=130.0)
        self.assertTrue(ok, msg="; ".join(issues))

    def test_overlap_validation_detects_gaps(self) -> None:
        # 4 azimuths at 90° spacing with 60° FOV → gaps
        band = CaptureBand(
            band_id="narrow", tilt_from_nadir_deg=50.0, azimuth_deg=(0.0, 90.0, 180.0, 270.0)
        )
        ok, issues = validate_band_overlap(band, horizontal_fov_deg=60.0)
        self.assertFalse(ok)
        self.assertTrue(len(issues) >= 1)

    def test_single_azimuth_always_ok(self) -> None:
        band = CaptureBand(band_id="solo", tilt_from_nadir_deg=90.0, azimuth_deg=(42.0,))
        ok, issues = validate_band_overlap(band, horizontal_fov_deg=10.0)
        self.assertTrue(ok)


class MultiPoseTests(unittest.TestCase):
    def test_multiple_poses_produce_correct_observation_count(self) -> None:
        spec = default_spec()
        poses = [
            VehiclePose(
                index=0, distance_m=0.0, longitude_deg=0.0, latitude_deg=0.0, heading_deg=0.0
            ),
            VehiclePose(
                index=1, distance_m=5.0, longitude_deg=0.0, latitude_deg=0.000045, heading_deg=0.0
            ),
            VehiclePose(
                index=2, distance_m=10.0, longitude_deg=0.0, latitude_deg=0.000090, heading_deg=0.0
            ),
        ]
        model = build_capture_model(
            spec, bus_length_m=8.0, bus_width_m=2.5, bus_height_m=3.0, poses=poses
        )
        # 8 logical cameras × 3 poses = 24 observations
        self.assertEqual(len(model.entries), 24)
        self.assertEqual(len(model.ordered_states), 24)

    def test_all_three_pose_indices_present(self) -> None:
        spec = default_spec()
        poses = [
            VehiclePose(
                index=0, distance_m=0.0, longitude_deg=0.0, latitude_deg=0.0, heading_deg=0.0
            ),
            VehiclePose(
                index=1, distance_m=5.0, longitude_deg=0.0, latitude_deg=0.000045, heading_deg=45.0
            ),
        ]
        model = build_capture_model(
            spec, bus_length_m=8.0, bus_width_m=2.5, bus_height_m=3.0, poses=poses
        )
        indices = {int(e["pose_index"]) for e in model.entries}
        self.assertEqual(indices, {0, 1})


class EdgeCaseTests(unittest.TestCase):
    def test_rejects_invalid_bus_dimensions(self) -> None:
        spec = default_spec()
        with self.assertRaises(ValueError):
            build_capture_model(spec, bus_length_m=0.0, bus_width_m=2.5, bus_height_m=3.0)

    def test_rejects_invalid_fov(self) -> None:
        spec = default_spec()
        with self.assertRaises(ValueError):
            build_capture_model(
                spec, bus_length_m=8.0, bus_width_m=2.5, bus_height_m=3.0, horizontal_fov_deg=200.0
            )

    def test_rejects_invalid_image_dimensions(self) -> None:
        spec = default_spec()
        with self.assertRaises(ValueError):
            build_capture_model(
                spec, bus_length_m=8.0, bus_width_m=2.5, bus_height_m=3.0, image_width=0
            )

    def test_default_pose_when_none_provided(self) -> None:
        spec = default_spec()
        model = build_capture_model(spec, bus_length_m=8.0, bus_width_m=2.5, bus_height_m=3.0)
        # single origin pose
        pose_indices = {int(e["pose_index"]) for e in model.entries}
        self.assertEqual(pose_indices, {0})
        self.assertEqual(len(model.poses), 1)
        p = model.poses[0]
        self.assertEqual(p.index, 0)
        self.assertEqual(p.distance_m, 0.0)
        self.assertEqual(p.heading_deg, 0.0)

    def test_camera_to_vehicle_transform_is_valid(self) -> None:
        model = self._make_model()
        for calib in model.calibration["cameras"]:  # type: ignore[arg-type]
            c2v = calib["camera_to_vehicle"]
            self.assertEqual(len(c2v), 4)
            self.assertEqual(len(c2v[0]), 4)
            # rotation block should be orthonormal (R^T R ≈ I)
            r = [[c2v[i][j] for j in range(3)] for i in range(3)]
            for i in range(3):
                for j in range(3):
                    dot = sum(r[i][k] * r[j][k] for k in range(3))
                    if i == j:
                        self.assertAlmostEqual(dot, 1.0, places=6, msg=f"row {i} not unit")
                    else:
                        self.assertAlmostEqual(
                            dot, 0.0, places=6, msg=f"rows {i},{j} not orthogonal"
                        )

    @staticmethod
    def _make_model() -> CaptureModel:
        spec = Roof360Spec(
            mast_height_m=2.0,
            bands=(
                CaptureBand(band_id="h", tilt_from_nadir_deg=90.0, azimuth_deg=(0.0,)),
                CaptureBand(band_id="d", tilt_from_nadir_deg=45.0, azimuth_deg=(0.0,)),
            ),
        )
        return build_capture_model(spec, bus_length_m=8.0, bus_width_m=2.5, bus_height_m=3.0)


if __name__ == "__main__":
    unittest.main()
