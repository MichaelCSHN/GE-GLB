from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from geglb.core.config import load_config
from geglb.core.dataset import read_jsonl
from geglb.products import (
    LookAtView,
    LookAtViewSetProduct,
    Panorama360Product,
    UnderbodyImageProduct,
)
from geglb.tasks.underbody_image.workflows.blender import build_blender_plan

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "01-underbody-image"


def _schema(relative: str) -> dict[str, object]:
    return json.loads((ROOT / "schemas" / relative).read_text(encoding="utf-8"))


class SchemaTests(unittest.TestCase):
    def test_all_schemas_are_valid_draft_2020_12(self) -> None:
        for path in (ROOT / "schemas").rglob("*.json"):
            with self.subTest(path=path):
                Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))

    def test_generated_v1_manifest_and_frames_match_active_schemas(self) -> None:
        config = load_config(EXAMPLE / "mvp.toml")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            build_blender_plan(
                config,
                EXAMPLE / "route.kml",
                EXAMPLE / "minimal.gltf",
                output,
            )
            Draft202012Validator(_schema("manifest.schema.json")).validate(
                json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            )
            frame_validator = Draft202012Validator(_schema("frame.schema.json"))
            for frame in read_jsonl(output / "frames.jsonl"):
                frame_validator.validate(frame)

    def test_product_dataclasses_match_product_schemas(self) -> None:
        products = (
            (UnderbodyImageProduct(), "products/underbody-image.schema.json"),
            (Panorama360Product(), "products/panorama-360.schema.json"),
            (
                LookAtViewSetProduct(
                    views=(
                        LookAtView(
                            image="views/az000-el045.png",
                            azimuth_deg=0.0,
                            elevation_deg=45.0,
                            radius_m=250.0,
                            target_ref="vehicle/000001",
                        ),
                    )
                ),
                "products/lookat-viewset.schema.json",
            ),
        )
        for product, schema_path in products:
            with self.subTest(schema=schema_path):
                Draft202012Validator(_schema(schema_path)).validate(product.as_dict())


if __name__ == "__main__":
    unittest.main()
