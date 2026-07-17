"""Tests for the GE-GLB web dashboard server."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from geglb.server import app

try:
    from fastapi.testclient import TestClient
except ImportError:
    TestClient = None  # type: ignore[assignment]


def _make_build_dir(root: Path) -> None:
    """Create a minimal build directory with one project."""
    proj = root / "mvp1"
    proj.mkdir(parents=True)
    manifest = {
        "schema_version": "ge-glb.dataset/v1",
        "source": {"kind": "blender"},
        "status": "complete",
        "counts": {"trajectory_frames": 5, "image_frames": 20},
    }
    (proj / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    (proj / "trajectory.jsonl").write_text(
        json.dumps(
            {
                "frame_index": 0,
                "distance_m": 0.0,
                "geodetic": {
                    "longitude_deg": 0.0,
                    "latitude_deg": 0.0,
                    "altitude_m": 0.0,
                },
                "local_enu_m": {"east": 0.0, "north": 0.0, "up": 0.0},
                "heading_deg": 0.0,
            },
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    prod_dir = proj / "product"
    prod_dir.mkdir()
    prod_manifest = {
        "product_schema": "ge-glb.product.underbody-image/v1",
        "task_id": "task01_underbody",
        "primary_artifact": "underbody.png",
    }
    (prod_dir / "manifest.json").write_text(
        json.dumps(prod_manifest, ensure_ascii=False), encoding="utf-8"
    )
    diag = prod_dir / "diagnostics"
    diag.mkdir()
    (diag / "confidence.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    (prod_dir / "underbody.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)


@unittest.skipIf(TestClient is None, "fastapi not installed")
class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.build_dir = Path(cls._tmp.name) / "build"
        _make_build_dir(cls.build_dir)

        # Configure the server's scan root.
        from fastapi.staticfiles import StaticFiles

        import geglb.server as server_mod

        server_mod._scan_root = cls.build_dir
        # Mount static files for the test (normally done in run_server).
        app.mount(
            "/static",
            StaticFiles(directory=str(cls.build_dir), html=True),
            name="static",
        )
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_app_creates(self) -> None:
        self.assertEqual(app.title, "GE-GLB Dashboard")

    def test_api_projects_returns_list(self) -> None:
        response = self.client.get("/api/projects")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("projects", data)
        self.assertEqual(len(data["projects"]), 1)
        self.assertEqual(data["projects"][0]["name"], "mvp1")

    def test_api_project_existing(self) -> None:
        response = self.client.get("/api/project/mvp1")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "mvp1")
        self.assertEqual(data["source_kind"], "blender")
        self.assertTrue(data["products"]["underbody"]["exists"])

    def test_api_project_not_found(self) -> None:
        response = self.client.get("/api/project/nope")
        self.assertEqual(response.status_code, 404)

    def test_static_file_serving(self) -> None:
        response = self.client.get("/static/mvp1/manifest.json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["source"]["kind"], "blender")

    def test_index_page_renders(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])

    def test_project_page_renders(self) -> None:
        response = self.client.get("/project/mvp1")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("mvp1", response.text)


if __name__ == "__main__":
    unittest.main()
