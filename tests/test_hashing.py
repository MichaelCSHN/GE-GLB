"""Tests for core content-hashing utilities."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from geglb.core.hashing import dir_sha256, file_sha256


class HashingTests(unittest.TestCase):
    def test_file_sha256_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "data.bin"
            p.write_bytes(b"hello world")
            h1 = file_sha256(p)
            h2 = file_sha256(p)
            self.assertEqual(h1, h2)
            self.assertTrue(h1.startswith("sha256:"))
            self.assertEqual(len(h1), len("sha256:") + 64)

    def test_file_sha256_differs_for_different_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "a.bin"
            b = Path(tmp) / "b.bin"
            a.write_bytes(b"alpha")
            b.write_bytes(b"beta")
            self.assertNotEqual(file_sha256(a), file_sha256(b))

    def test_dir_sha256_returns_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sub").mkdir()
            (root / "sub" / "f.txt").write_text("hello", encoding="utf-8")
            (root / "top.txt").write_text("world", encoding="utf-8")
            result = dir_sha256(root)
            self.assertIn("sub/f.txt", result)
            self.assertIn("top.txt", result)
            self.assertNotIn(str(root / "sub" / "f.txt"), result)
            self.assertNotIn(str(root / "top.txt"), result)


if __name__ == "__main__":
    unittest.main()
