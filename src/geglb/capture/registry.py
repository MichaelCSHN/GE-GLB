from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class BackendDescriptor:
    backend_id: str
    mode: str
    implemented: bool
    required_inputs: tuple[str, ...]
    capabilities: tuple[str, ...]
    output_schema: str = "ge-glb.dataset/v1"
    notes: str = ""


BACKENDS = (
    BackendDescriptor(
        backend_id="blender",
        mode="virtual",
        implemented=True,
        required_inputs=("scene.glb", "route.kml", "project.toml"),
        capabilities=("camera_pose", "horizontal_fov", "roll", "deterministic_render"),
        notes="Headless Python renderer; deterministic virtual source.",
    ),
    BackendDescriptor(
        backend_id="ge3d",
        mode="virtual",
        implemented=True,
        required_inputs=("route.kml", "project.toml"),
        capabilities=("geodetic_pose", "camera_pose", "horizontal_fov", "kml_tour"),
        notes="KML Tour planner; image saving still requires Earth Pro control.",
    ),
    BackendDescriptor(
        backend_id="real_capture",
        mode="real",
        implemented=False,
        required_inputs=("rig.json", "trajectory.jsonl", "timestamped camera images"),
        capabilities=("import_only",),
        notes="Reserved adapter contract for synchronized vehicle cameras.",
    ),
)


def describe_backends() -> dict[str, object]:
    return {"capture_backends": [asdict(item) for item in BACKENDS]}
