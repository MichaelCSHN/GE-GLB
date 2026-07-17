# GE-GLB

Pluggable image acquisition and stitching infrastructure for transparent-vehicle bird's-eye-view
research. A parameterized bus carries a synchronized front/rear/left/right camera rig. Every image
source emits the same dataset contract, so stitching does not know whether frames came from
Blender, Google Earth Pro, or a future real vehicle.

## Three MVPs

| MVP | Source | Purpose | Current implementation |
| --- | --- | --- | --- |
| MVP1 | Blender + GLB scene | Deterministic end-to-end algorithm development | Dataset planner and headless Blender runner |
| MVP2 | Google Earth Pro 3D | Geographic-scene validation | KML Camera Tour and standard dataset planner |
| MVP3 | MVP1 + MVP2 | Cross-source comparison and joint evaluation | Distance-aligned frame pairing |

Real capture is represented by a vendor-neutral adapter contract only. It must produce the same
`ge-glb.dataset/v1` layout before any stitching code can consume it.

See [the Chinese task design and development plan](docs/task-01-plan-zh.md).
Machine-readable contracts are in [`schemas/`](schemas/).

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
geglb backends
```

The planning, validation, and pairing tools use Python 3.11+ and the standard library only.

## MVP1: Blender

Prepare a dataset and render job:

```powershell
geglb blender plan `
  --config examples/mvp.toml `
  --route examples/route.kml `
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

## MVP2: Google Earth Pro

```powershell
geglb ge-pro plan `
  --config examples/mvp.toml `
  --route examples/route.kml `
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

## MVP3: combine Blender and GE Pro

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
