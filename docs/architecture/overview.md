# Architecture Overview

GE-GLB separates what to capture, how to capture it, and what product to create.

```text
tasks -> neutral plans -> capture backends -> datasets -> task processors -> products
```

Top-level packages have stable responsibilities:

- `core`: coordinates, camera/trajectory models, contracts, serialization, validation.
- `capture`: Blender, GE 3D, and real-source adapters.
- `tasks`: task-specific sampling and processing.
- `products`: versioned final-product manifests.
- `workflows`: cross-layer composition and comparison.
- `cli`: argument parsing only.

Current flat `geglb.*` modules are compatibility re-exports. New code belongs in the layered
packages. A compatibility wrapper must never become the owner of new behavior. These imports are
marked deprecated but remain available throughout v0.x; removal requires an explicit v1.0 decision
and migration note.
