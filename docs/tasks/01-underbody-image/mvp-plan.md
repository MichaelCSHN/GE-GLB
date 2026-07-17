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

## Metrics policy

Numerical pass/fail thresholds will be frozen only after the first calibrated straight and curved
Blender fixtures establish a baseline distribution. Until then every run must report metric value,
unit, fixture, and algorithm version rather than claiming an arbitrary threshold.

| Metric | Unit/definition | Applicable source |
| --- | --- | --- |
| Blind-region coverage | valid pixels / declared underbody region | Blender and GE Pro |
| Reprojection error | pixels and ground-plane centimeters | calibrated Blender; GE when control points exist |
| Image agreement | aligned SSIM/PSNR against no-vehicle nadir truth | Blender only |
| Seam energy | gradient discontinuity along selected source boundaries | Blender and GE Pro |
| Acquisition completeness | captured valid observations / planned observations | all sources |
| End-to-end latency | frames and wall-clock time | all sources |

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

### What this repository can verify

It can verify deterministic plans, coordinate transforms, dataset/schema conformance, missing-image
failure, and the synthetic planar compositor. A workstation with the target Blender version and a
real city GLB is required to verify scale, materials, rendering, visibility masks, and truth-based
quality metrics.

## MVP2 — GE Pro

### Goal

Run the same task and product contract against Google Earth 3D imagery without changing the
underbody processor.

### Implemented in repository

- KML Camera Tour generation, wait, pause, intended file names, and standard dataset skeleton.
- The same rig, trajectory, temporal policy, and Task 01 stitch plan used by Blender.

### Remaining work

1. Complete the Windows controller technical spike below, then implement tour resume and Save Image.
2. Lock window size, UI scale, image dimensions, layers, sunlight, and attribution handling.
3. Add cache warm-up, LOD stability checks, timeouts, retries, and resume state.
4. Verify near-ground camera height/FOV behavior in several Available 3D Areas.
5. Run the unchanged Task 01 compositor and document GE-specific limitations.

### Exit criteria

- Every planned observation is captured or explicitly failed and retryable.
- Repeated captures stay within a declared viewpoint tolerance.
- The dataset passes the common validator.
- The processor contains no GE-specific conditional path.

### Windows controller technical plan

The controller is a resumable state machine, not a timed sequence of screen clicks:

```text
START -> IDENTIFY_WINDOW -> NORMALIZE_UI -> WARM_CACHE -> NAVIGATE_VIEW
      -> WAIT_STABLE -> SAVE_IMAGE -> VERIFY_FILE -> RECORD_RESULT -> NEXT/RETRY
```

- Prefer Windows UI Automation through `pywinauto` for named controls and Win32 APIs for process,
  focus, viewport, and file verification. Use coordinate/pixel automation only as a documented
  fallback after a target-version spike.
- Record Earth Pro version, monitor/DPI, window rectangle, viewport, layers, sunlight, terrain,
  KML view identifier, expected file, attempts, timing, and terminal status.
- Consider a view complete only after the expected file exists, is decodable, has the configured
  dimensions, and remains unchanged for a stability interval.
- Treat cache/LOD stability as observable state with bounded timeout. On failure, retain the
  planned frame as `missing` or `invalid`; never manufacture an image.
- Persist controller state after every view so restart resumes at the first non-terminal item.

The spike must compare UI Automation coverage on the supported Earth Pro version before selecting
specific libraries or freezing selectors.

### What this repository can verify

It can generate and parse the KML tour, verify intended names, validate controller state fixtures,
and test retry logic without Earth Pro. Windows GUI control, cache convergence, viewpoint
repeatability, attribution, and Save Image output require a declared target-machine run.

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

### What this repository can verify

It can validate and pair pre-existing datasets, exclude ground truth, and calculate future
cross-domain reports. It cannot establish cross-domain quality or parameter robustness until both
MVP1 and MVP2 produce captures of corresponding routes.

## Dependency path

```text
shared contracts + geometry
        |
        +--> MVP1 Blender capture --> truth metrics --+
        |                                             |
        +--> MVP2 GE Pro controller --> stability ----+--> MVP3 pairing/optimization
        |
        +--> source-independent compositor -----------+
```

MVP3 depends on usable outputs from both acquisition branches. Compositor and contract development
can proceed in parallel with target-machine controller work, but joint thresholds cannot be frozen
before the calibrated fixtures exist.

## Risk register

| Risk | Impact | Mitigation/evidence gate |
| --- | --- | --- |
| GLB scale/origin or camera-axis mismatch | invalid geometry despite plausible images | calibration fixture, axis markers, matrix tests |
| Flat-ground model fails on relief/curbs | holes and misregistration | depth/geometry upgrade path and limitation flag |
| Vehicle/scene occlusion not modelled | false road pixels | depth/mesh visibility masks before quality claim |
| Earth Pro GUI or selector changes | interrupted or misnamed capture | versioned selectors, state machine, file verification, resume |
| Earth Pro cache/LOD changes between views | unstable comparison | warm-up/stability checks and repeatability report |
| Arbitrary metric thresholds overfit one fixture | misleading exit decision | baseline distributions before threshold freeze |
| Ground truth leaks into reconstruction | invalid evaluation | explicit flag, planner exclusion, regression test |
| Licensed imagery/assets enter Git | redistribution risk | ignore generated data and review artifact provenance |

## Design decisions

### ADR-001 — Initial temporal window

- **Decision:** start with `history_frames=1` and retain every surround camera at `t_i` and
  `t_i-1`.
- **Why:** it closes the smallest causal temporal loop while allowing a long vehicle to benefit
  from side and rear evidence as well as the previous front view.
- **Status:** configurable baseline hypothesis, not a proven optimum.
- **Evidence needed:** coverage/quality versus speed, sampling interval, curvature, and larger
  history windows.

### ADR-002 — Initial camera tilt and soft priors

- **Decision:** example configurations use 50 degrees from nadir and source-role priors only as
  blend weights after geometric visibility.
- **Why:** these values create a usable first fixture without hard-selecting a camera by name.
- **Status:** heuristic defaults; they are not acceptance thresholds or production calibration.
- **Evidence needed:** parameter search over camera count, mount, FOV, tilt, spacing, and scene type.

### ADR-003 — Flat-ground IPM baseline

- **Decision:** keep a small source-independent planar projector as the first executable baseline.
- **Why:** it exposes calibration, temporal selection, missing inputs, and product plumbing before
  adding scene geometry.
- **Consequence:** every result declares flat-ground and visibility limitations; it cannot support
  a production-quality claim until the staged geometry/occlusion roadmap is implemented.
