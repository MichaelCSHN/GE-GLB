# Repository Instructions for Agents

## Read first

Before changing code, read `SPEC.md`, `PLAN.md`, and the applicable task document under
`docs/tasks/`. Treat them as normative unless the user explicitly changes the product definition.

## Architectural dependency rule

Allowed dependency direction:

```text
core <- capture
core <- tasks
core,capture,tasks <- workflows <- cli
products <- tasks
```

- `core` must not import `capture`, `tasks`, `workflows`, or `cli`.
- `capture` must not import a task processor.
- `tasks` may depend on `core` and product contracts, but not concrete backend modules.
- Task/backend composition belongs in `tasks/<task>/workflows` or top-level `workflows`.
- Compatibility modules at `src/geglb/*.py` may re-export new paths; do not add new logic there.

## Product boundaries

- Task 01 primary product: one complete nadir underbody image.
- Task 02 primary product: one 360 panorama.
- Task 03 primary product: one indexed multi-view LookAt image set.
- Do not reuse Task 01 BEV fusion for Task 02 or Task 03 merely because images share a backend.

## Source boundaries

- Blender and GE 3D are virtual capture backends.
- Real capture stays vendor-neutral until hardware and calibration are in scope.
- Task code consumes CaptureDataset fields and cannot inspect `source.kind` to choose algorithms.
- Backend-specific metadata belongs under `source.extras` or backend artifacts.

## Development discipline

1. Make the smallest coherent change; preserve unrelated user work.
2. Add or update tests for behavior, schemas, coordinates, CLI, and compatibility imports.
3. Use explicit units in names: `_m`, `_deg`, `_ns`, `_px`.
4. Use directional transform names such as `camera_to_vehicle`; never use an ambiguous `pose` matrix.
5. Persist relative artifact paths; reject absolute paths and `..` in datasets.
6. Never use hidden nadir ground truth as reconstruction input.
7. Never silently synthesize missing images or panorama coverage.
8. Record known limitations in result manifests.
9. Keep backend execution scripts thin; reusable logic belongs under `src/geglb/`.
10. New dependencies must be optional unless required by all commands.

## Required checks

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
python -m compileall -q src scripts tests
git diff --check
```

When changing packaging, also build/install into a temporary target. When changing KML or JSON,
parse the generated artifacts in tests. Hardware/GUI checks must be recorded as unverified rather
than represented as passing.

## Git discipline

- Work on an `agent/*` branch.
- Use terse conventional commits.
- Do not commit `build/`, image datasets, GLB assets, credentials, caches, or `*.egg-info`.
- Update the active PR description when scope or validation changes.
- Merge only after required CI succeeds and the user has authorized merge.
