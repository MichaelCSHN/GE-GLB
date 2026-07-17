from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class BackendDescriptor:
    backend_id: str
    mvp: str
    implemented: bool
    required_inputs: tuple[str, ...]
    output_schema: str = "ge-glb.dataset/v1"
    notes: str = ""


BACKENDS = (
    BackendDescriptor(
        backend_id="blender",
        mvp="MVP1",
        implemented=True,
        required_inputs=("scene.glb", "route.kml", "project.toml"),
        notes="Headless Python renderer; deterministic virtual source.",
    ),
    BackendDescriptor(
        backend_id="ge_pro",
        mvp="MVP2",
        implemented=True,
        required_inputs=("route.kml", "project.toml"),
        notes="KML Tour planner; image saving still requires Earth Pro control.",
    ),
    BackendDescriptor(
        backend_id="real_capture",
        mvp="engineering",
        implemented=False,
        required_inputs=("rig.json", "trajectory.jsonl", "timestamped camera images"),
        notes="Reserved adapter contract for synchronized vehicle cameras.",
    ),
)


def describe_backends() -> dict[str, object]:
    return {"capture_backends": [asdict(item) for item in BACKENDS]}
