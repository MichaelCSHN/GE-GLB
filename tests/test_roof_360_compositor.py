"""Tests for Task 02 roof-360 spherical panorama compositor."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from geglb.tasks.roof_360_pano.compositor import build_panorama
from geglb.tasks.roof_360_pano.specification import CaptureBand, Roof360Spec
from geglb.tasks.roof_360_pano.workflows.blender import build_blender_plan

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "01-underbody-image"


def _make_synthetic_dataset(directory: Path, spec: Roof360Spec) -> Path:
    """Write a Blender-plan dataset and replace images with solid colours."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        raise unittest.SkipTest("stitching dependencies unavailable")

    dataset = directory / "dataset"
    build_blender_plan(
        spec,
        bus_length_m=8.0,
        bus_width_m=2.5,
        bus_height_m=3.0,
        scene_glb=EXAMPLES / "minimal.gltf",
        output_dir=dataset,
        horizontal_fov_deg=90.0,
        image_width=64,
        image_height=64,
    )

    from geglb.core.dataset import read_jsonl

    for frame in read_jsonl(dataset / "frames.jsonl"):
        image_path = dataset / Path(str(frame["image"]))
        image_path.parent.mkdir(parents=True, exist_ok=True)
        # Horizontal band → red, downward band → blue.
        camera_id = str(frame["camera_id"])
        if "horizontal" in camera_id:
            colour = (220, 30, 10)
        else:
            colour = (30, 80, 220)
        Image.fromarray(np.full((64, 64, 3), colour, dtype=np.uint8), mode="RGB").save(image_path)

    return dataset


class PanoramaOutputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = Roof360Spec(
            mast_height_m=1.5,
            bands=(
                CaptureBand(
                    band_id="horizontal",
                    tilt_from_nadir_deg=90.0,
                    azimuth_deg=(0.0, 180.0),
                ),
                CaptureBand(
                    band_id="downward",
                    tilt_from_nadir_deg=50.0,
                    azimuth_deg=(90.0, 270.0),
                ),
            ),
        )

    def test_panorama_output_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset = _make_synthetic_dataset(root, self.spec)
            out = root / "out"
            build_panorama(dataset, out, panorama_width=640)

            try:
                from PIL import Image
            except ImportError:
                self.skipTest("PIL unavailable")
            with Image.open(out / "product" / "panorama.png") as pano:
                self.assertEqual(pano.size, (640, 320))
                self.assertEqual(pano.mode, "RGBA")

    def test_panorama_has_alpha_channel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset = _make_synthetic_dataset(root, self.spec)
            out = root / "out"
            build_panorama(dataset, out, panorama_width=200)

            try:
                import numpy as np
                from PIL import Image
            except ImportError:
                self.skipTest("stitching deps unavailable")

            with Image.open(out / "product" / "panorama.png") as im:
                pano = np.asarray(im.convert("RGBA"))
            self.assertEqual(pano.shape[2], 4)

            # Some pixels valid, some invalid.
            alpha = pano[..., 3]
            self.assertGreater(alpha.max(), 0, "expected at least one valid pixel")
            self.assertEqual(alpha.min(), 0, "expected at least one invalid pixel")

    def test_known_pixel_maps_to_correct_source(self) -> None:
        """A narrow horizontal camera at heading 0° only populates pixels
        near lon=0, lat=0 (north, horizon) in the equirectangular output."""
        narrow_spec = Roof360Spec(
            mast_height_m=1.5,
            bands=(
                CaptureBand(
                    band_id="horizontal",
                    tilt_from_nadir_deg=90.0,
                    azimuth_deg=(0.0,),
                ),
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            try:
                import numpy as np
                from PIL import Image
            except ImportError:
                self.skipTest("stitching deps unavailable")

            from geglb.core.dataset import read_jsonl

            # Build dataset with narrow FOV from the start so that
            # intrinsics (fx/fy) match the actual FOV.
            dataset = root / "dataset"
            build_blender_plan(
                narrow_spec,
                bus_length_m=8.0,
                bus_width_m=2.5,
                bus_height_m=3.0,
                scene_glb=EXAMPLES / "minimal.gltf",
                output_dir=dataset,
                horizontal_fov_deg=10.0,
                image_width=64,
                image_height=64,
            )
            for frame in read_jsonl(dataset / "frames.jsonl"):
                image_path = dataset / Path(str(frame["image"]))
                image_path.parent.mkdir(parents=True, exist_ok=True)
                Image.fromarray(np.full((64, 64, 3), (255, 0, 0), dtype=np.uint8), mode="RGB").save(
                    image_path
                )

            out = root / "out"
            build_panorama(dataset, out, panorama_width=360)

            with Image.open(out / "product" / "panorama.png") as im:
                pano = np.asarray(im.convert("RGBA"))
            h, w = pano.shape[:2]

            # Valid pixels should cluster near lon=0 and lat≈0 (equator).
            valid_y, valid_x = np.where(pano[..., 3] > 0)
            self.assertGreater(len(valid_y), 0, "no valid pixels")
            for px_val, py_val in zip(valid_x, valid_y):
                lon_deg = 360.0 * float(px_val) / w
                near_zero = min(lon_deg, 360.0 - lon_deg) < 30.0
                self.assertTrue(
                    near_zero,
                    f"pixel ({px_val},{py_val}) lon={lon_deg:.1f}° not near 0°",
                )
                lat_deg = 90.0 - 180.0 * float(py_val) / h
                self.assertLess(
                    abs(lat_deg),
                    30.0,
                    f"pixel ({px_val},{py_val}) lat={lat_deg:.1f}° not near 0°",
                )

    def test_deterministic_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset = _make_synthetic_dataset(root, self.spec)
            out_a = root / "out_a"
            out_b = root / "out_b"

            build_panorama(dataset, out_a, panorama_width=100)
            build_panorama(dataset, out_b, panorama_width=100)

            pano_a = (out_a / "product" / "panorama.png").read_bytes()
            pano_b = (out_b / "product" / "panorama.png").read_bytes()
            self.assertEqual(pano_a, pano_b)

    def test_limitations_declared_in_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset = _make_synthetic_dataset(root, self.spec)
            out = root / "out"
            result = build_panorama(dataset, out, panorama_width=100)
            self.assertIn("limitations", result)
            self.assertIsInstance(result["limitations"], list)
            self.assertGreater(len(result["limitations"]), 0)

    def test_rejects_incomplete_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset = _make_synthetic_dataset(root, self.spec)
            # Delete an image to make the dataset incomplete.
            from geglb.core.dataset import read_jsonl

            frames = read_jsonl(dataset / "frames.jsonl")
            img_path = dataset / Path(str(frames[0]["image"]))
            img_path.unlink()

            with self.assertRaises(ValueError):
                build_panorama(dataset, root / "out", panorama_width=100)

    def test_full_coverage_with_synthetic_data(self) -> None:
        """An all-sky spec with wide-FOV cameras achieves near-total coverage."""
        full_spec = Roof360Spec(
            mast_height_m=1.5,
            bands=(
                CaptureBand(
                    band_id="horizon",
                    tilt_from_nadir_deg=90.0,
                    azimuth_deg=(0.0, 90.0, 180.0, 270.0),
                ),
                CaptureBand(
                    band_id="upper",
                    tilt_from_nadir_deg=135.0,
                    azimuth_deg=(0.0, 120.0, 240.0),
                ),
                CaptureBand(
                    band_id="lower",
                    tilt_from_nadir_deg=45.0,
                    azimuth_deg=(0.0, 120.0, 240.0),
                ),
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            try:
                import numpy as np
                from PIL import Image
            except ImportError:
                self.skipTest("stitching deps unavailable")

            from geglb.core.dataset import read_jsonl, write_jsonl

            dataset = root / "dataset"
            build_blender_plan(
                full_spec,
                bus_length_m=8.0,
                bus_width_m=2.5,
                bus_height_m=3.0,
                scene_glb=EXAMPLES / "minimal.gltf",
                output_dir=dataset,
                horizontal_fov_deg=120.0,
                image_width=64,
                image_height=64,
            )
            # Update frames to match the FOV.
            frames = read_jsonl(dataset / "frames.jsonl")
            for f in frames:
                f["camera_world"]["horizontal_fov_deg"] = 120.0
            write_jsonl(dataset / "frames.jsonl", frames)
            # Update rig intrinsics to match the FOV.
            rig = json.loads((dataset / "rig.json").read_text(encoding="utf-8"))
            for cam in rig["cameras"]:
                cam["intrinsics"]["horizontal_fov_deg"] = 120.0
                cam["intrinsics"]["vertical_fov_deg"] = 120.0
            (dataset / "rig.json").write_text(json.dumps(rig, indent=2) + "\n", encoding="utf-8")

            # Write synthetic images.
            for frame in read_jsonl(dataset / "frames.jsonl"):
                image_path = dataset / Path(str(frame["image"]))
                image_path.parent.mkdir(parents=True, exist_ok=True)
                Image.fromarray(
                    np.full((64, 64, 3), (100, 150, 200), dtype=np.uint8), mode="RGB"
                ).save(image_path)

            out = root / "out"
            result = build_panorama(dataset, out, panorama_width=200)
            self.assertGreater(result["coverage"], 0.90)


if __name__ == "__main__":
    unittest.main()
