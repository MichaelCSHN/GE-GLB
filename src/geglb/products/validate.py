"""Unified product validation framework for all three GE-GLB tasks.

Exposes ``validate_product()`` — callable from the CLI or as a library —
and a ``ProductValidator`` registry that encodes schema paths, required
diagnostics, and type-specific quality checks.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA_ROOT = Path(__file__).resolve().parents[3] / "schemas"

PRODUCT_TYPE_TO_SCHEMA: dict[str, str] = {
    "underbody": "products/underbody-image.schema.json",
    "panorama": "products/panorama-360.schema.json",
    "lookat": "products/lookat-viewset.schema.json",
}

PRODUCT_TYPE_TO_ARTIFACT: dict[str, str] = {
    "underbody": "underbody.png",
    "panorama": "panorama.png",
    "lookat": "viewset.json",
}


# ── per-type quality checks ────────────────────────────────────────────


def _check_underbody(product_dir: Path, _manifest: dict) -> dict[str, object]:
    diag = product_dir / "diagnostics"
    diag_status = {
        "confidence.png": (diag / "confidence.png").is_file(),
        "coverage.png": (diag / "coverage.png").is_file(),
        "source-map.png": (diag / "source-map.png").is_file(),
    }
    warnings = [
        f"missing diagnostic: {name}" for name, present in diag_status.items() if not present
    ]
    return {"diagnostics": diag_status, "warnings": warnings}


def _check_panorama(product_dir: Path, manifest: dict) -> dict[str, object]:
    diag = product_dir / "diagnostics"
    diag_status = {
        "validity.png": (diag / "validity.png").is_file(),
        "coverage.png": (diag / "coverage.png").is_file(),
    }
    result: dict[str, object] = {"diagnostics": dict(diag_status)}
    for name, present in diag_status.items():
        if not present:
            result.setdefault("warnings", [])
            result["warnings"].append(f"missing diagnostic: {name}")  # type: ignore[index]
    # Check 2:1 aspect ratio if coverage info is available.
    panorama_result = product_dir / "result.json"
    if panorama_result.is_file():
        try:
            presult = json.loads(panorama_result.read_text(encoding="utf-8"))
            coverage = presult.get("coverage")
            if isinstance(coverage, (int, float)):
                result["quality"] = {"coverage": float(coverage)}
                if float(coverage) < 0.5:
                    result["warnings"] = result.get("warnings", [])
                    result["warnings"].append(  # type: ignore[union-attr]
                        f"low panorama coverage: {coverage}"
                    )
        except (json.JSONDecodeError, OSError):
            pass
    # Verify panorama dimensions if the PNG exists.
    pano_path = product_dir / "panorama.png"
    if pano_path.is_file():
        try:
            from PIL import Image

            with Image.open(pano_path) as im:
                w, h = im.size
            ratio = w / max(h, 1)
            if not (1.8 <= ratio <= 2.2):
                result.setdefault("warnings", [])
                result["warnings"].append(  # type: ignore[index]
                    f"panorama aspect ratio {ratio:.2f} outside 2:1 tolerance"
                )
        except ImportError:
            pass
    return result


def _check_lookat(product_dir: Path, _manifest: dict) -> dict[str, object]:
    diag = product_dir / "diagnostics"
    diag_status = {
        "completeness.json": (diag / "completeness.json").is_file(),
        "thumbnails/": (diag / "thumbnails").is_dir(),
        "contact-sheet.png": (diag / "contact-sheet.png").is_file(),
    }
    result: dict[str, object] = {"diagnostics": dict(diag_status)}
    for name, present in diag_status.items():
        if not present:
            result.setdefault("warnings", [])
            result["warnings"].append(f"missing diagnostic: {name}")  # type: ignore[index]
    comp_path = diag / "completeness.json"
    if comp_path.is_file():
        try:
            comp = json.loads(comp_path.read_text(encoding="utf-8"))
            result["quality"] = {
                "completeness": comp.get("completeness"),
                "planned_views": comp.get("planned_views"),
                "available_views": comp.get("available_views"),
                "missing_cameras": comp.get("missing_cameras", []),
            }
            if comp.get("completeness", 1.0) < 1.0:
                result.setdefault("warnings", [])
                missing = comp.get("missing_cameras", [])
                result["warnings"].append(  # type: ignore[index]
                    f"incomplete view set: {len(missing)} missing cameras"
                )
        except (json.JSONDecodeError, OSError):
            pass
    # Verify viewset.json has views.
    viewset_path = product_dir / "viewset.json"
    if viewset_path.is_file():
        try:
            vs = json.loads(viewset_path.read_text(encoding="utf-8"))
            views = vs.get("views", [])
            if not views:
                result.setdefault("warnings", [])
                result["warnings"].append("viewset.json has empty views array")  # type: ignore[index]
            result["quality"] = result.get("quality", {})
            result["quality"]["view_count"] = len(views)  # type: ignore[index]
        except (json.JSONDecodeError, OSError):
            pass
    return result


# ── ProductValidator registry ──────────────────────────────────────────


@dataclass(frozen=True)
class ProductValidator:
    product_type: str
    schema_relative: str
    primary_artifact: str
    custom_check: Callable[[Path, dict], dict[str, object]] = field(default=lambda _d, _m: {})


PRODUCT_VALIDATORS: dict[str, ProductValidator] = {
    "underbody": ProductValidator(
        product_type="underbody",
        schema_relative="products/underbody-image.schema.json",
        primary_artifact="underbody.png",
        custom_check=_check_underbody,
    ),
    "panorama": ProductValidator(
        product_type="panorama",
        schema_relative="products/panorama-360.schema.json",
        primary_artifact="panorama.png",
        custom_check=_check_panorama,
    ),
    "lookat": ProductValidator(
        product_type="lookat",
        schema_relative="products/lookat-viewset.schema.json",
        primary_artifact="viewset.json",
        custom_check=_check_lookat,
    ),
}


# ── public API ─────────────────────────────────────────────────────────


def validate_product(
    product_dir: str | Path,
    product_type: str,
) -> dict[str, object]:
    """Validate a product directory against its schema and quality criteria.

    Parameters
    ----------
    product_dir :
        Path to the product directory (containing ``manifest.json`` and
        the primary artifact).
    product_type :
        One of ``"underbody"``, ``"panorama"``, ``"lookat"``.

    Returns
    -------
    dict
        Structured validation report with keys ``valid``, ``errors``,
        ``warnings``, ``primary_artifact_ok``, ``diagnostics``, and
        ``quality``.
    """
    validator = PRODUCT_VALIDATORS.get(product_type)
    if validator is None:
        return {
            "valid": False,
            "product_type": product_type,
            "errors": [f"unknown product_type: {product_type!r}"],
            "warnings": [],
        }

    pd = Path(product_dir)
    errors: list[str] = []
    warnings: list[str] = []

    # 1. Schema validation
    manifest_path = pd / "manifest.json"
    schema_path = SCHEMA_ROOT / validator.schema_relative

    product_schema = ""
    try:
        from jsonschema import Draft202012Validator

        if not manifest_path.is_file():
            return {
                "valid": False,
                "product_type": product_type,
                "product_schema": "",
                "errors": ["manifest.json is missing"],
                "warnings": [],
                "primary_artifact": validator.primary_artifact,
                "primary_artifact_ok": False,
                "diagnostics": {},
            }

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        product_schema = str(manifest.get("product_schema", ""))

        if schema_path.is_file():
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            Draft202012Validator(schema).validate(manifest)
        else:
            warnings.append(f"schema file not found: {schema_path}")
    except ImportError:
        warnings.append("jsonschema not installed; skipping schema validation")
    except Exception as exc:
        errors.append(f"schema validation failed: {exc}")

    # 2. Primary artifact
    artifact_path = pd / validator.primary_artifact
    primary_ok = False
    if artifact_path.is_file():
        primary_ok = _verify_primary_artifact(artifact_path, product_type)
        if not primary_ok:
            errors.append(f"primary artifact {validator.primary_artifact} is corrupt")
    else:
        errors.append(f"primary artifact {validator.primary_artifact} is missing")

    # 3. Type-specific checks
    quality: dict[str, object] = {}
    diag_status: dict[str, bool] = {}
    try:
        manifest = (
            json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
        )
        extra = validator.custom_check(pd, manifest)
        for key in ("diagnostics", "quality", "warnings"):
            if key in extra:
                if key == "warnings":
                    warnings.extend(extra[key])  # type: ignore[arg-type]
                elif key == "diagnostics":
                    diag_status = extra[key]  # type: ignore[assignment]
                else:
                    quality = extra[key]  # type: ignore[assignment]
    except Exception as exc:
        errors.append(f"custom check failed: {exc}")

    # 4. Check for geglb_version
    if "geglb_version" not in manifest and manifest_path.is_file():
        warnings.append("manifest is missing geglb_version field")

    return {
        "valid": not errors,
        "product_type": product_type,
        "product_schema": product_schema,
        "errors": errors,
        "warnings": warnings,
        "primary_artifact": validator.primary_artifact,
        "primary_artifact_ok": primary_ok,
        "diagnostics": diag_status,
        "quality": quality,
    }


def _verify_primary_artifact(path: Path, product_type: str) -> bool:
    """Return True if *path* can be decoded as its expected format."""
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            json.loads(path.read_text(encoding="utf-8"))
            return True
        except (json.JSONDecodeError, OSError):
            return False
    if suffix == ".png":
        try:
            from PIL import Image

            with Image.open(path) as im:
                im.verify()
            return True
        except Exception:
            return False
    return True  # unknown format — assume ok
