from __future__ import annotations

from dataclasses import asdict, dataclass

from .base import ProductManifest


@dataclass(frozen=True)
class LookAtView:
    image: str
    azimuth_deg: float
    elevation_deg: float
    radius_m: float
    target_ref: str


@dataclass(frozen=True)
class LookAtViewSetProduct(ProductManifest):
    product_schema: str = "ge-glb.product.lookat-viewset/v1"
    task_id: str = "task03_drone_lookat"
    capture_dataset: str = "../capture"
    primary_artifact: str = "viewset.json"
    views: tuple[LookAtView, ...] = ()

    def as_dict(self) -> dict[str, object]:
        result = super().as_dict()
        result["views"] = [asdict(view) for view in self.views]
        return result
