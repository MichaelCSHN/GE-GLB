from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class TaskDescriptor:
    task_id: str
    command: str
    primary_product: str
    product_schema: str
    implementation_status: str


TASKS = (
    TaskDescriptor(
        "task01_underbody",
        "underbody",
        "one complete nadir underbody image",
        "ge-glb.product.underbody-image/v1",
        "active: planning and flat-ground baseline implemented",
    ),
    TaskDescriptor(
        "task02_roof_360",
        "pano360",
        "one equirectangular 360 panorama",
        "ge-glb.product.panorama-360/v1",
        "contract only",
    ),
    TaskDescriptor(
        "task03_drone_lookat",
        "lookat-set",
        "one indexed multi-view LookAt image set",
        "ge-glb.product.lookat-viewset/v1",
        "hemisphere enumeration implemented; capture workflow pending",
    ),
)


def describe_tasks() -> dict[str, object]:
    return {"tasks": [asdict(item) for item in TASKS]}
