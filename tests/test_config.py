from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from geglb.core.config import load_config

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_CONFIG = ROOT / "examples" / "01-underbody-image" / "mvp.toml"


class ConfigTests(unittest.TestCase):
    def test_duplicate_camera_ids_are_rejected(self) -> None:
        config_text = EXAMPLE_CONFIG.read_text(encoding="utf-8").replace(
            'id = "rear"', 'id = "front"', 1
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate-camera.toml"
            path.write_text(config_text, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate camera id: front"):
                load_config(path)

    def test_invalid_route_spacing_is_rejected(self) -> None:
        config_text = EXAMPLE_CONFIG.read_text(encoding="utf-8").replace(
            "capture_spacing_m = 0.5", "capture_spacing_m = 0.0", 1
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid-spacing.toml"
            path.write_text(config_text, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "route.capture_spacing_m must be positive"):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
