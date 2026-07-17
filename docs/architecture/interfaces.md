# Interface Standards

## CaptureBackend

A backend consumes a neutral CapturePlan and emits a CaptureDataset plus backend artifacts. It
declares capabilities instead of being inspected by name. Typical capabilities include GLB scene
import, geodetic coordinates, roll, horizontal FOV, depth, segmentation, or resumable capture.

## CaptureDataset

Every observation needs a stable identifier, sensor ID, sample/time association, image path,
intrinsics reference, and directional sensor-to-world transform. Missing files and unavailable
capabilities are explicit. Artifact paths are relative to the dataset root.

## TaskProcessor

A processor accepts a validated dataset and TaskSpec, then emits one versioned task product. It may
reject a dataset that lacks declared capabilities, but it must not branch on backend identity.

## Products

- Underbody image: one primary raster plus confidence/coverage/source diagnostics.
- Panorama: one equirectangular raster plus validity/seam diagnostics.
- LookAt set: original view files plus an indexed `viewset.json`.

Product manifests reference their CaptureDataset and use immutable schema identifiers.

## Transform and unit rules

- Matrices use `<source>_to_<destination>` names and row-major persistence.
- Length is meters, angles are degrees at public interfaces, time is nanoseconds when timestamped.
- World/vehicle/camera axes are defined in `SPEC.md` and cannot vary by backend.
