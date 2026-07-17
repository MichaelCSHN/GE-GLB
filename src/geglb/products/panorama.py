from __future__ import annotations

from dataclasses import dataclass

from .base import ProductManifest


@dataclass(frozen=True)
class Panorama360Product(ProductManifest):
    product_schema: str = "ge-glb.product.panorama-360/v1"
    task_id: str = "task02_roof_360"
    capture_dataset: str = "../capture"
    primary_artifact: str = "panorama.png"
    projection: str = "equirectangular"
