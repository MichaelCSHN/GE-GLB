from __future__ import annotations

import math
import unittest

from geglb.core.camera import camera_to_vehicle_transform
from geglb.core.coordinates import LocalFrame, body_offset_to_enu


def _dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


class CoordinateTests(unittest.TestCase):
    def test_local_frame_round_trip_preserves_small_area_coordinates(self) -> None:
        frame = LocalFrame(-5.6587797, 36.0573293, 24.0)
        expected = (-5.65791, 36.05802, 31.5)
        local = frame.to_local(*expected)
        actual = frame.to_geodetic(*local)
        for expected_value, actual_value in zip(expected, actual, strict=True):
            self.assertAlmostEqual(expected_value, actual_value, places=10)

    def test_body_axes_map_to_enu_for_cardinal_headings(self) -> None:
        self.assertEqual(body_offset_to_enu(10.0, 0.0, 0.0), (0.0, 10.0))
        east, north = body_offset_to_enu(10.0, 0.0, 90.0)
        self.assertAlmostEqual(east, 10.0)
        self.assertAlmostEqual(north, 0.0, places=12)
        east, north = body_offset_to_enu(0.0, 3.0, 0.0)
        self.assertAlmostEqual(east, -3.0)
        self.assertAlmostEqual(north, 0.0)

    def test_camera_rotation_is_right_handed_and_orthonormal(self) -> None:
        transform = camera_to_vehicle_transform(
            (2.0, -1.0, 3.2), yaw_deg=37.0, tilt_deg=54.0, roll_deg=-12.0
        )
        columns = [[transform[row][column] for row in range(3)] for column in range(3)]
        for index, column in enumerate(columns):
            self.assertAlmostEqual(_dot(column, column), 1.0, places=12)
            for other in columns[index + 1 :]:
                self.assertAlmostEqual(_dot(column, other), 0.0, places=12)
        determinant = (
            columns[0][0] * (columns[1][1] * columns[2][2] - columns[1][2] * columns[2][1])
            - columns[1][0] * (columns[0][1] * columns[2][2] - columns[0][2] * columns[2][1])
            + columns[2][0] * (columns[0][1] * columns[1][2] - columns[0][2] * columns[1][1])
        )
        self.assertTrue(math.isclose(determinant, 1.0, abs_tol=1e-12))


if __name__ == "__main__":
    unittest.main()
