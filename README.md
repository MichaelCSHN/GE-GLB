# GE-GLB

Pluggable acquisition and product pipelines for vehicle-centered visual research. Virtual capture
uses Blender or GE 3D; real capture is a vendor-neutral engineering-stage interface.

## Three tasks

| Task | Acquisition geometry | Primary product |
| --- | --- | --- |
| 01 Underbody | Vehicle-mounted front/rear/left/right cameras with temporal frames | One complete nadir underbody image |
| 02 Roof 360 | Elevated horizontal and downward capture bands | One equirectangular 360 panorama |
| 03 Drone LookAt | Hemisphere observers targeting the moving vehicle center | One indexed multi-view LookAt image set |

The common interface ends at CaptureDataset. Final products are versioned independently and must
not be forced into one representation.

Start with [SPEC.md](SPEC.md), [PLAN.md](PLAN.md), and [AGENTS.md](AGENTS.md). Task 01 design and its
three MVP gates are under [`docs/tasks/01-underbody-image/`](docs/tasks/01-underbody-image/).
Machine-readable contracts are under [`schemas/`](schemas/).

## Standard dataset

```text
dataset/
├─ manifest.json
├─ rig.json
├─ trajectory.jsonl
├─ frames.jsonl
├─ fusion-plan.json
└─ images/
   ├─ front/000000.png
   ├─ rear/000000.png
   ├─ left/000000.png
   └─ right/000000.png
```

Coordinates are explicit: local ENU world, `x_forward/y_left/z_up` vehicle, and
`x_right/y_down/z_forward` camera. The hidden nadir camera is evaluation-only and cannot appear in
a stitching job.

## Install

```powershell
python -m pip install -e ".[stitch]"
geglb tasks
geglb backends
```

The planning, validation, and pairing tools use Python 3.11+ and the standard library only.

## Task 01 MVP1: Blender

Prepare a dataset and render job:

```powershell
geglb blender plan `
  --config examples/01-underbody-image/mvp.toml `
  --route examples/01-underbody-image/route.kml `
  --scene D:\blender\assets\scenes\city.glb `
  --out build/mvp1
```

Run the job with Blender's bundled Python:

```powershell
blender --background `
  --python scripts/blender_capture.py `
  -- --job build/mvp1/blender-job.json
```

The GLB origin is the first route point; Blender world axes are X east, Y north, Z up, in meters.

## Task 01 MVP2: Google Earth Pro

```powershell
geglb ge-pro plan `
  --config examples/01-underbody-image/mvp.toml `
  --route examples/01-underbody-image/route.kml `
  --out build/mvp2
```

Open `build/mvp2/capture-tour.kml` in Earth Pro. The tour waits and pauses at every planned view;
`frames.jsonl` defines the intended image names. Automated Save Image control is the next
Windows-only slice.

## Source-independent stitching plan

```powershell
geglb stitch plan --dataset build/mvp1 --out build/stitch-mvp1
geglb stitch run --dataset build/mvp1 --out build/bev-mvp1 --meters-per-pixel 0.1
```

Each target uses all surround cameras at `t_i` and `t_i-1`. Frame `t_0` is released after `t_1`
using future observations. Soft priors favor the previous front view, but never discard side or
rear candidates before geometric visibility testing.

`stitch run` is a working flat-ground IPM/weighted-blend baseline. It deliberately reports its
limitations: no terrain model, explicit occlusion test, lens distortion, or exposure compensation.

## Task 01 MVP3: compare Blender and GE Pro

```powershell
geglb combine `
  --primary build/mvp1 `
  --secondary build/mvp2 `
  --out build/mvp3 `
  --max-distance-m 0.25
```

Pairs use camera ID plus nearest route distance and exclude nadir ground truth.

## Validate and test

```powershell
geglb validate build/mvp1
geglb validate build/mvp1 --require-images
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

## Research and imagery note

Google Earth imagery is not a physical automotive-sensor simulator. Results must retain required
attribution and comply with applicable Google Earth terms. This repository is not a vehicle safety
validation system.
