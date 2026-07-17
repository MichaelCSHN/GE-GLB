# GE-GLB Product Specification

## Mission

GE-GLB generates vehicle-centered visual products from virtual or real image acquisition. It has
three tasks with deliberately different primary products:

1. `task01_underbody`: one complete nadir underbody image.
2. `task02_roof_360`: one equirectangular 360 panorama.
3. `task03_drone_lookat`: one indexed multi-view LookAt image set.

The common boundary is acquisition, not the final product. Blender, GE 3D, and future real capture
must emit a common CaptureDataset. Task processors consume that dataset and emit task-specific
products.

## System flow

```text
TaskSpec -> CapturePlan -> CaptureBackend -> CaptureDataset -> TaskProcessor -> Product
```

Task code must not call `bpy`, generate KML, automate Earth Pro, or depend on device SDKs.
Backends must not implement temporal underbody fusion, panorama stitching, or LookAt-set policy.

## Capture modes

- `virtual/blender`: import GLB, construct observers, render deterministic frames.
- `virtual/ge3d`: convert observers to KML/GE views and acquire imagery.
- `real`: reserved vendor-neutral boundary for timestamped images, calibration, and trajectories.

## Coordinate conventions

- World: local ENU in meters, anchored by a WGS84 origin when georeferenced.
- Vehicle: x forward, y left, z up.
- Camera: x right, y down, z forward.
- Heading: clockwise from north.
- KML tilt: 0 degrees nadir, 90 degrees horizon.
- Every persisted matrix is row-major and named by direction, for example `camera_to_world`.

## Task products

### Task 01 — Underbody image

Inputs are current and temporal surround-camera observations. The atomic product is one image,
`underbody.png`, with optional confidence, coverage, and source-map diagnostics. Batch processing
may create multiple atomic products, but does not change the product type.

### Task 02 — Roof 360 panorama

Inputs are horizontal and downward capture bands from an elevated vehicle-mounted rig. The primary
product is one equirectangular `panorama.png`; uncovered spherical regions must be represented by an
alpha/validity mask, never invented silently.

### Task 03 — Drone LookAt view set

Inputs are observer poses sampled on a hemisphere around the vehicle center. The product is an
indexed set of original views plus exact radius, azimuth, elevation, camera pose, and LookAt target.
These views are not panorama-stitched.

## Run layout

```text
run/
├─ run.json
├─ capture-plan.json
├─ capture/
│  ├─ manifest.json
│  ├─ rigs/
│  ├─ trajectories/
│  ├─ observations.jsonl
│  └─ images/
├─ product/
├─ diagnostics/
└─ logs/
```

The current Task 01 v1 files remain supported while the shared v2 run layout is introduced. New
tasks must target the shared run layout and their own product schema.

## Versioned contracts

- Current capture compatibility: `ge-glb.dataset/v1`.
- Target common run/capture contract: `ge-glb.capture-dataset/v2`.
- `ge-glb.product.underbody-image/v1`.
- `ge-glb.product.panorama-360/v1`.
- `ge-glb.product.lookat-viewset/v1`.

Schema changes require an explicit version change, migration note, validator update, fixture, and
backward-compatibility decision.

## Acceptance principles

- Identical task specs produce identical planned observation identifiers.
- Ground-truth sensors are never reconstruction inputs.
- Missing observations remain explicit.
- Task processors branch on declared capabilities, never backend names.
- Real data can replace virtual data without modifying task algorithms.
- Every product is traceable to its CaptureDataset and TaskSpec.
