# Task 03 — Drone LookAt Multi-view Set

Primary product: an indexed set of original LookAt images sampled on a hemisphere around the moving
vehicle center. Each view preserves radius, azimuth, elevation, observer pose, target pose, and
intrinsics. The views are not panorama-stitched.

Virtual backends are Blender and GE 3D. Real capture is a reserved interface for drone telemetry,
gimbal orientation, image timestamps, and calibration; it does not authorize vehicle/drone control.
