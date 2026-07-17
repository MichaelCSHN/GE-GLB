from __future__ import annotations

import ast
import json
from pathlib import Path
import unittest

from geglb.products import (
    LookAtViewSetProduct,
    Panorama360Product,
    UnderbodyImageProduct,
)
from geglb.tasks.drone_lookat_set import DroneLookAtSpec, enumerate_hemisphere
from geglb.tasks.roof_360_pano import CaptureBand, Roof360Spec


ROOT = Path(__file__).resolve().parents[1]


class ArchitectureTests(unittest.TestCase):
    def test_legacy_imports_remain_available(self) -> None:
        from geglb.blender import build_blender_plan
        from geglb.dataset import validate_dataset
        from geglb.planner import build_plan

        self.assertTrue(callable(build_blender_plan))
        self.assertTrue(callable(validate_dataset))
        self.assertTrue(callable(build_plan))

    def test_core_has_no_upward_relative_imports(self) -> None:
        for path in (ROOT / "src" / "geglb" / "core").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertLessEqual(
                        node.level,
                        1,
                        f"core module {path.name} imports outside core: {node.module}",
                    )

    def test_product_contracts_are_distinct(self) -> None:
        products = [
            UnderbodyImageProduct(),
            Panorama360Product(),
            LookAtViewSetProduct(),
        ]
        schemas = {product.product_schema for product in products}
        artifacts = {product.primary_artifact for product in products}
        self.assertEqual(len(schemas), 3)
        self.assertEqual(
            artifacts, {"underbody.png", "panorama.png", "viewset.json"}
        )

    def test_roof_bands_and_hemisphere_specs_validate(self) -> None:
        roof = Roof360Spec(
            mast_height_m=4.5,
            bands=(
                CaptureBand("horizontal", 90.0, (0.0, 90.0, 180.0, 270.0)),
                CaptureBand("downward", 45.0, (0.0, 90.0, 180.0, 270.0)),
            ),
        )
        roof.validate()
        views = enumerate_hemisphere(
            DroneLookAtSpec(
                radius_m=250.0,
                azimuth_deg=(0.0, 90.0, 180.0, 270.0),
                elevation_deg=(30.0, 60.0, 90.0),
            )
        )
        self.assertEqual(len(views), 12)
        self.assertAlmostEqual(views[-1].offset_enu_m[2], 250.0)

    def test_all_json_schemas_parse(self) -> None:
        for path in (ROOT / "schemas").rglob("*.json"):
            with self.subTest(path=path):
                value = json.loads(path.read_text(encoding="utf-8"))
                self.assertIn("$schema", value)


if __name__ == "__main__":
    unittest.main()
