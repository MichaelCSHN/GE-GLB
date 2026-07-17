from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ProductManifest:
    product_schema: str
    task_id: str
    capture_dataset: str
    primary_artifact: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)
