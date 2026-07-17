# Task 01 MVP Plan — Complete Underbody Nadir Image

The task product is one `ge-glb.product.underbody-image/v1` image for a selected target sample.
Input acquisition may be a sequence; product identity remains a single image. Batch execution may
produce several independent product instances.

## Shared gates

- Parameterized bus and synchronized front/rear/left/right cameras.
- Current observations: all four cameras at `t_i`.
- Temporal observations: all four cameras at `t_i-1`.
- `t_0` may be released after `t_1` using future observations.
- Hidden nadir ground truth is evaluation-only.
- Output includes `underbody.png`; confidence, coverage, and source-map diagnostics are required
  before declaring the algorithm production-ready.

## MVP1 — Blender

### Goal

Close the deterministic loop from city GLB and route to a single underbody image with nadir truth.

### Implemented in repository

- KML route sampling, vehicle heading, bus rig, and calibration.
- Standard planned dataset and temporal candidates.
- Blender background job and renderer.
- Flat-ground inverse perspective mapping and weighted blending.
- Synthetic compositor integration test.

### Remaining work

1. Run a real city GLB smoke test on the target Blender version.
2. Confirm meters, scene origin, X-east/Y-north/Z-up, FOV, roll, and image orientation.
3. Add an invisible evaluation camera and no-vehicle nadir truth render.
4. Add explicit vehicle/body and scene visibility masks.
5. Produce confidence, coverage, and per-pixel source maps.
6. Add photometric compensation and seam-aware blending.
7. Evaluate straight and curved routes against truth.
8. Optimize camera count, placement, FOV, and route sampling interval.

### Exit criteria

- Repeat runs have identical plan IDs and complete image counts.
- The target product passes geometric orientation checks.
- No ground-truth observation appears in reconstruction inputs.
- Coverage/error metrics meet declared thresholds on straight and curved fixtures.

## MVP2 — GE Pro

### Goal

Run the same task and product contract against Google Earth 3D imagery without changing the
underbody processor.

### Implemented in repository

- KML Camera Tour generation, wait, pause, intended file names, and standard dataset skeleton.
- The same rig, trajectory, temporal policy, and Task 01 stitch plan used by Blender.

### Remaining work

1. Implement a Windows controller for tour resume and Save Image.
2. Lock window size, UI scale, image dimensions, layers, sunlight, and attribution handling.
3. Add cache warm-up, LOD stability checks, timeouts, retries, and resume state.
4. Verify near-ground camera height/FOV behavior in several Available 3D Areas.
5. Run the unchanged Task 01 compositor and document GE-specific limitations.

### Exit criteria

- Every planned observation is captured or explicitly failed and retryable.
- Repeated captures stay within a declared viewpoint tolerance.
- The dataset passes the common validator.
- The processor contains no GE-specific conditional path.

## MVP3 — Blender + GE Pro

### Goal

Compare controllable simulation and geographic imagery, then select robust Task 01 parameters. MVP3
does not blend Blender and GE pixels into one product.

### Implemented in repository

- Pairing by camera ID and nearest route distance.
- Pairing tolerance, unmatched count, and ground-truth exclusion.

### Remaining work

1. Add pair completeness and route-distance error reports.
2. Compare projected coverage, sharpness, color, texture, and seam stability.
3. Keep Blender truth metrics separate from GE no-truth stability metrics.
4. Run camera/FOV/spacing search on both domains and report Pareto choices.
5. Freeze a cross-domain baseline configuration and regression fixture.

### Exit criteria

- Both source datasets independently validate.
- Pairing rate and distance error satisfy declared thresholds.
- The same processor configuration runs on both sources.
- The selected configuration is justified by separate and joint metrics.
