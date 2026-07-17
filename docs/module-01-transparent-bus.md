# Module 01: Transparent-bus capture planning

## Goal

Create reproducible Google Earth Pro camera sequences for a parameterized bus rig. The first slice
generates exact route poses, virtual camera calibration, a frame manifest, and a KML Capture Tour.
It also creates a hidden nadir camera for evaluation; ground-truth frames must never be used as an
input to reconstruction.

## Coordinate conventions

- Vehicle frame: `x` forward, `y` left, `z` up.
- KML heading: clockwise from north.
- KML camera tilt: zero is nadir and 90 degrees is the horizon.
- Camera yaw in configuration: clockwise from vehicle forward.
- Route sampling is distance-based, not time-based.

## Human/program boundary

| Step | Owner |
| --- | --- |
| Select a stable, relatively flat Google Earth Pro scene | Human |
| Draw a `ROUTE` with the Add Path toolbar and save KML | Human |
| Disable sunlight and distracting layers for the baseline | Human |
| Resample the route and calculate vehicle headings | Program |
| Resolve all camera positions and intrinsics | Program |
| Generate the Capture Tour and ordered frame manifest | Program |
| Play the tour, wait for imagery, invoke Save Image, resume | Automation (next slice) |
| Approve image quality and attribution | Human |

## Temporal reconstruction model

For target frame `t_i`, the baseline now admits every surround image from both `t_i` and `t_i-1`.
The previous front view has the strongest heuristic prior for newly hidden ground, side views remain
useful around the long body, and the previous rear view is retained at low priority instead of being
discarded. Actual selection is per ground cell, using visibility, projected resolution, incidence
angle, and image quality; the heuristic prior is never treated as a hard mask.

At dense route spacing, different longitudinal strips of the current footprint may have been seen
at different earlier frames, so `history_frames` is parameterized even though the MVP value is one.
Frame `t_0` has no history and is emitted one frame late using all `t_1` cameras, with the rear view
receiving the strongest bootstrap prior. The evaluation-only nadir camera is excluded from every
fusion input.

## Generated artifacts

- `poses.csv`: distance-sampled vehicle poses.
- `calibration.json`: parameterized bus dimensions and camera intrinsics/extrinsics.
- `capture-plan.json`: exact capture order and intended file names.
- `fusion-plan.json`: current/previous candidate images, relative poses, latency, and soft priors.
- `capture-tour.kml`: Earth Pro tour with one pause after every camera view.

## Next slices

1. Windows Earth Pro controller for tour resume and Save Image.
2. Image validation and cache warm-up pass.
3. Self-occlusion masks for the parameterized bus body.
4. Inverse perspective mapping and current-frame surround BEV.
5. World ground atlas and causal/offline underbody reconstruction.
6. Hidden-nadir metrics and camera-count/FOV optimization.
