# Task 02 — Roof 360 Panorama

## Product and boundary

The atomic product is one equirectangular `panorama.png` plus a validity mask and diagnostics.
Inputs are elevated horizontal and downward capture bands. This task owns spherical projection,
overlap, exposure, seam, and validity rules; it does not reuse the Task 01 BEV compositor.

Virtual backends are Blender and GE 3D. Real capture is a reserved interface for mast-camera
calibration and synchronization. Missing spherical coverage remains transparent/invalid and must
never be filled with invented imagery.

## Neutral capture model

- A parameterized mast height and sensor calibration are expressed in the vehicle frame.
- Each band declares elevation/tilt, azimuth samples, FOV, and required overlap.
- Every observation retains exact intrinsics and sensor-to-world transform.
- Horizontal and downward bands may use different sampling density, but share a timestamp/sample.

## Processing stages

1. Validate observations and calibrations without inspecting backend identity.
2. Project source pixels to a spherical surface.
3. Score overlap using resolution, incidence, exposure, and seam cost.
4. Blend valid samples and emit panorama, validity, seam, and source-map diagnostics.
5. Validate equirectangular dimensions, full azimuth continuity, and declared missing coverage.

## Delivery slices

1. Freeze band defaults and an overlap validator.
2. Generate backend-neutral observations for a tiny deterministic fixture.
3. Implement a Blender panorama baseline and product writer.
4. Add GE 3D capture planning without changing the processor.
5. Add exposure/seam optimization and reserve the synchronized real-mast importer.

## Implementation status

- [x] CaptureBand, Roof360Spec, and band validation (specification.py).
- [x] Neutral capture plan generator (capture_plan.py).
  - ``build_capture_model()`` produces backend-agnostic ``CaptureModel`` per band × azimuth × pose.
  - ``default_spec()`` provides the reference 4+4 dual-band fixture.
  - ``validate_band_overlap()`` checks horizontal FOV coverage between adjacent azimuths.
- [ ] Blender panorama baseline and product writer.
- [ ] GE 3D capture planning.
- [ ] Exposure/seam optimization.

## Current verification boundary

This repository can validate band specifications, product contracts, and the neutral capture plan
generator. It cannot yet verify a rendered panorama, Earth Pro image acquisition, or real
multi-camera synchronization.
