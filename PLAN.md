# GE-GLB Development Plan

## Repository foundation

- [x] Separate `core`, `capture`, `tasks`, `products`, `workflows`, and `cli`.
- [x] Preserve Task 01 compatibility imports and commands.
- [x] Define three primary product contracts.
- [x] Reserve Blender, GE 3D, and real-capture backend boundaries.
- [ ] Introduce `ge-glb.capture-dataset/v2` alongside the v1 compatibility writer.
- [ ] Add run-level provenance, content hashes, and resumable execution state.

## Task 01 — Underbody image

Detailed MVP gates are in `docs/tasks/01-underbody-image/mvp-plan.md`.

- [x] Shared route, rig, calibration, temporal-candidate, and dataset planner.
- [x] Blender job generator and background render script.
- [x] GE Pro Camera Tour planner.
- [x] Source-independent stitch jobs and flat-ground IPM baseline.
- [x] Ground-truth comparison, diagnostics (confidence, coverage, source-map), and UnderbodyImageProduct writer.
- [x] CLI entry point for product output (`geglb product underbody`).
- [ ] Real GLB smoke test and camera-orientation calibration. (workstation-ready, see mvp-plan.md)
- [ ] Explicit body/scene occlusion, exposure compensation.
- [ ] Earth Pro Save Image controller and retry state machine.
- [ ] Blender/GE joint evaluation and parameter optimization.

## Task 02 — Roof 360 panorama

- [x] Product and capture-band specification boundary.
- [ ] Define horizontal/downward band defaults and overlap rules.
- [ ] Generate neutral observations for Blender and GE 3D.
- [ ] Implement spherical projection, seam selection, exposure compensation, and alpha validity.
- [ ] Add one-panorama product validator and quality metrics.
- [ ] Reserve real mast-camera synchronization/calibration importer.

## Task 03 — Drone LookAt view set

- [x] Product, hemisphere, and LookAt parameter boundary.
- [x] Deterministic hemisphere view enumeration.
- [ ] Convert hemisphere offsets to observer trajectories following vehicle poses.
- [ ] Generate Blender and GE 3D capture plans.
- [ ] Build `viewset.json`, thumbnails, contact sheet, and completeness metrics.
- [ ] Reserve real drone telemetry/gimbal/time synchronization importer.

## Delivery order

1. Finish Task 01 MVP1 on a real Blender/GLB workstation.
2. Improve Task 01 compositor against nadir ground truth.
3. Finish Task 01 MVP2 Earth Pro acquisition.
4. Complete Task 01 MVP3 joint evaluation.
5. Implement Task 02 neutral capture plan and panorama baseline.
6. Implement Task 03 observer trajectory and view-set builder.
7. Introduce real-capture implementations only when hardware contracts are known.
