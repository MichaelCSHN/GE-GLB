"""Tests for the v2 run-configuration loader."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from geglb.core.config_v2 import RunConfig, load_run_config

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _write_toml(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


class ConfigV2Tests(unittest.TestCase):
    def test_load_run_config_panorama(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            toml_path = Path(tmp) / "cfg.toml"
            _write_toml(
                toml_path,
                '[project]\nname = "test"\n'
                "[bus]\nlength_m = 10.0\nwidth_m = 2.5\nheight_m = 3.0\n"
                "[spec]\nmast_height_m = 1.5\n"
                '[[spec.bands]]\nband_id = "h"\n'
                "tilt_from_nadir_deg = 90.0\nazimuth_deg = [0.0, 180.0]\n"
                "[capture]\nimage_width = 800\nimage_height = 600\n"
                "horizontal_fov_deg = 60.0\n",
            )
            cfg = load_run_config(toml_path, "panorama")
            self.assertIsInstance(cfg, RunConfig)
            self.assertIsNotNone(cfg.bus)
            self.assertEqual(cfg.bus.length_m, 10.0)
            self.assertIn("mast_height_m", cfg.spec)

    def test_load_run_config_lookat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            toml_path = Path(tmp) / "cfg.toml"
            _write_toml(
                toml_path,
                '[project]\nname = "lookat-test"\n'
                "[spec]\nradius_m = 100.0\n"
                "azimuth_deg = [0.0, 90.0, 180.0, 270.0]\n"
                "elevation_deg = [30.0, 60.0]\n"
                "[capture]\nimage_width = 1024\nimage_height = 768\n",
            )
            cfg = load_run_config(toml_path, "lookat")
            self.assertIsNone(cfg.bus)
            self.assertEqual(cfg.spec["radius_m"], 100.0)

    def test_load_run_config_underbody(self) -> None:
        # Use the existing example TOML.
        cfg = load_run_config(EXAMPLES / "01-underbody-image" / "mvp.toml", "underbody")
        self.assertIsNotNone(cfg.bus)

    def test_rejects_invalid_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            toml_path = Path(tmp) / "cfg.toml"
            _write_toml(toml_path, 'task = "invalid"\n')
            with self.assertRaises(ValueError):
                load_run_config(toml_path)


if __name__ == "__main__":
    unittest.main()
