# GE-GLB

Google Earth Pro tooling for transparent-vehicle bird's-eye-view research.

The first module turns a path drawn with the Earth Pro **Add Path** tool into a deterministic
multi-camera capture plan for a parameterized bus. A rendered bus model is intentionally not used:
the bus is represented by dimensions and a rigid camera rig, allowing a hidden nadir camera to
produce evaluation-only ground truth.

## Module 01 status

Implemented:

- KML `ROUTE` parsing.
- Distance-based route resampling.
- Vehicle heading calculation.
- Parameterized bus and roof-edge camera mounts.
- Rectilinear camera intrinsics.
- Four surround cameras plus an evaluation-only nadir camera.
- Ordered JSON capture manifest.
- Per-target temporal fusion manifest using all cameras at `t_i` and `t_i-1`.
- Google Earth Pro KML Capture Tour with `FlyTo`, load wait, and a pause at every view.

Planned next:

- Earth Pro **Save Image** automation.
- Current-frame inverse perspective mapping and surround-view stitching.
- World-referenced temporal ground atlas.
- Causal and offline underbody reconstruction.
- Camera-count, placement, FOV, and sampling-distance optimization.

See [the module design](docs/module-01-transparent-bus.md) for coordinate conventions and the
human/program boundary.

## Requirements

- Python 3.11 or newer.
- Google Earth Pro for opening the generated Capture Tour.

The planner itself uses only the Python standard library.

## Quick start

1. In Google Earth Pro, use **Add Path** to draw a route.
2. Name the path `ROUTE` and save it as KML.
3. Generate the capture artifacts:

```powershell
python -m pip install -e .
geglb plan --config examples/mvp.toml --route examples/route.kml --out build/mvp
```

Open `build/mvp/capture-tour.kml` in Earth Pro. Start `CAPTURE_TOUR`; it waits for imagery and
pauses after every camera view. The ordered intended filenames are in `capture-plan.json`.

Generated files:

```text
build/mvp/
├─ calibration.json
├─ capture-plan.json
├─ capture-tour.kml
├─ fusion-plan.json
└─ poses.csv
```

## Test

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

## Research and imagery note

This project is intended for small-scale algorithm prototyping. Google Earth imagery is not a
physical automotive-sensor simulator, and generated results must retain required attribution and
comply with the applicable Google Earth terms. Do not use this module as a safety-validation tool.
