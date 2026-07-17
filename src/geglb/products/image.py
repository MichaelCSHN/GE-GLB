from __future__ import annotations

from dataclasses import dataclass

from .base import ProductManifest


@dataclass(frozen=True)
class UnderbodyImageProduct(ProductManifest):
    product_schema: str = "ge-glb.product.underbody-image/v1"
    task_id: str = "task01_underbody"
    capture_dataset: str = "../capture"
    primary_artifact: str = "underbody.png"
    confidence_artifact: str = "diagnostics/confidence.png"
    source_map_artifact: str = "diagnostics/source-map.png"
