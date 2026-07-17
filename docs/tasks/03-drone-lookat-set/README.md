# Task 03 — Drone LookAt Multi-view Set

## Product and boundary

The product is an indexed set of original LookAt images sampled on a hemisphere around the moving
vehicle center. Each view preserves radius, azimuth, elevation, observer pose, target pose, and
intrinsics. The views are not panorama-stitched.

Virtual backends are Blender and GE 3D. Real capture is a reserved import interface for drone
telemetry, gimbal orientation, image timestamps, and calibration; it does not authorize vehicle or
drone control.

## Neutral capture model

- A vehicle sample provides the moving LookAt target in the common world frame.
- Radius, azimuth, and elevation deterministically define each observer offset.
- The camera optical axis targets the vehicle center; roll policy and FOV remain explicit.
- Stable view identifiers are derived from sample and hemisphere indices, not backend filenames.
- Capability checks declare whether a backend can realize requested altitude, roll, and FOV.

## Processing stages

1. Enumerate hemisphere samples in stable order.
2. Transform offsets into observer trajectories following the vehicle target.
3. Emit neutral observations for Blender, GE 3D, or a future telemetry importer.
4. Verify image completeness and pose metadata.
5. Write `viewset.json`, thumbnails/contact sheet, and completeness diagnostics.

## Delivery slices

1. Test radius/azimuth/elevation enumeration and pole deduplication policy.
2. Build observer trajectories for a moving vehicle fixture.
3. Implement Blender and GE 3D planning adapters.
4. Write and validate the first complete LookAt view-set product.
5. Reserve timestamp/gimbal alignment for real captures without adding flight control.

## Current verification boundary

The repository can enumerate hemisphere offsets and validate the product data model. It cannot yet
verify image acquisition, target tracking in Earth Pro, drone feasibility, or real-flight safety.
