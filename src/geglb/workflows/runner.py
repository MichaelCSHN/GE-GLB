"""End-to-end orchestration for ``geglb run``.

Implements a resumable step state-machine that runs::

    plan → render → composite → product → validate

Each step is tracked in ``run.json`` so interrupted runs can resume.
"""

from __future__ import annotations

import datetime
import json
import subprocess
import sys
from pathlib import Path

from ..core.dataset import write_json


def _utc_now() -> str:
    return datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat()


# ── run.json helpers ───────────────────────────────────────────────────


def _load_run_state(out_dir: Path) -> dict[str, object]:
    run_path = out_dir / "run.json"
    if run_path.is_file():
        return json.loads(run_path.read_text(encoding="utf-8"))
    return {}


def _save_run_state(out_dir: Path, state: dict[str, object]) -> None:
    write_json(out_dir / "run.json", state)


def _init_run_state(task_id: str, out_dir: Path) -> dict[str, object]:
    steps: dict[str, object] = {}
    for name in ("plan", "render", "composite", "product", "validate"):
        steps[name] = {"status": "pending"}
    state: dict[str, object] = {
        "schema_version": "ge-glb.run/v1",
        "task_id": task_id,
        "steps": steps,
        "execution": {"started_at": _utc_now(), "completed_at": None},
    }
    _save_run_state(out_dir, state)
    return state


def _step_status(state: dict[str, object], step: str) -> str:
    return str(state.get("steps", {}).get(step, {}).get("status", "pending"))


def _set_step_status(state: dict[str, object], step: str, status: str, **extra: object) -> None:
    state["steps"][step] = {"status": status, **extra}  # type: ignore[index]
    _save_run_state(Path(state.get("_out_dir", ".")), state)  # type: ignore[arg-type]


# ── main entry point ───────────────────────────────────────────────────


def run_task(
    task_id: str,
    out_dir: str | Path,
    *,
    config_path: str | Path | None = None,
    route_kml: str | Path | None = None,
    scene_glb: str | Path | None = None,
    spec_toml: str | Path | None = None,
    blender_exec: str | None = None,
    resume: bool = False,
    existing: bool = False,
) -> int:
    """Run a full task pipeline end-to-end.

    Returns 0 on success, non-zero on failure.
    """
    output = Path(out_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    scene = Path(scene_glb).expanduser().resolve() if scene_glb else None

    # ── load or init state ───────────────────────────────────────────
    state = _load_run_state(output)
    if not state or not resume:
        state = _init_run_state(task_id, output)
    state["_out_dir"] = str(output)  # type: ignore[assignment]

    def _should_run(step: str) -> bool:
        return _step_status(state, step) not in ("complete", "skipped")

    # ── plan ─────────────────────────────────────────────────────────
    if existing:
        _set_step_status(state, "plan", "complete", note="--existing: using pre-built dataset")
        _set_step_status(state, "render", "skipped", note="--existing: using pre-built dataset")
    elif _should_run("plan"):
        _set_step_status(state, "plan", "running")
        try:
            _run_plan(task_id, output, config_path, route_kml, scene, spec_toml)
            _set_step_status(state, "plan", "complete", outputs=["blender-job.json"])
        except Exception as exc:
            _set_step_status(state, "plan", "failed", error=str(exc))
            _print_step_failed("plan", exc)
            return 1

    # ── render ───────────────────────────────────────────────────────
    if _should_run("render"):
        _set_step_status(state, "render", "running")
        blender_job = output / "blender-job.json"
        if not blender_job.is_file():
            _set_step_status(state, "render", "skipped", reason="blender-job.json not found")
        elif blender_exec:
            try:
                cmd = [
                    blender_exec,
                    "--background",
                    "--python",
                    "scripts/blender_capture.py",
                    "--",
                    "--job",
                    str(blender_job),
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    _set_step_status(state, "render", "complete")
                else:
                    _set_step_status(
                        state,
                        "render",
                        "failed",
                        error=result.stderr[:500],
                    )
                    _print_step_failed("render", result.stderr)
                    return 1
            except Exception as exc:
                _set_step_status(state, "render", "failed", error=str(exc))
                _print_step_failed("render", exc)
                return 1
        else:
            _set_step_status(
                state,
                "render",
                "pending",
                note=(
                    "run: blender --background "
                    "--python scripts/blender_capture.py "
                    f"-- --job {blender_job}"
                ),
            )
            print(
                "\n>>> Next step: run Blender manually, then re-run with --resume\n"
            )
            # Stop here — subsequent steps need rendered images.
            state["execution"] = {  # type: ignore[index]
                "started_at": state.get("execution", {}).get("started_at", _utc_now()),  # type: ignore[union-attr]
                "completed_at": None,
            }
            _save_run_state(output, state)
            return 0

    # ── composite ────────────────────────────────────────────────────
    if task_id in ("task01_underbody", "task02_roof_360") and _should_run("composite"):
        _set_step_status(state, "composite", "running")
        try:
            if task_id == "task01_underbody":
                from ..tasks.underbody_image.compositor import run_planar_stitcher

                run_planar_stitcher(output, output)
            else:
                from ..tasks.roof_360_pano.compositor import build_panorama

                build_panorama(output, output)
            _set_step_status(state, "composite", "complete")
        except ValueError as exc:
            # Missing images → pending.
            _set_step_status(
                state, "composite", "pending", reason=str(exc)[:200]
            )
        except Exception as exc:
            _set_step_status(state, "composite", "failed", error=str(exc))
            _print_step_failed("composite", exc)
            return 1
    elif task_id != "task01_underbody" and task_id != "task02_roof_360":
        _set_step_status(state, "composite", "skipped", reason="not applicable for this task")

    # ── product ──────────────────────────────────────────────────────
    if _should_run("product"):
        _set_step_status(state, "product", "running")
        try:
            _run_product(task_id, output)
            _set_step_status(state, "product", "complete")
        except Exception as exc:
            _set_step_status(state, "product", "failed", error=str(exc))
            _print_step_failed("product", exc)
            return 1

    # ── validate ─────────────────────────────────────────────────────
    if _should_run("validate"):
        _set_step_status(state, "validate", "running")
        try:
            from ..products.validate import validate_product

            ptype = {
                "task01_underbody": "underbody",
                "task02_roof_360": "panorama",
                "task03_drone_lookat": "lookat",
            }[task_id]
            report = validate_product(output / "product", ptype)
            if report["valid"]:
                _set_step_status(state, "validate", "complete", report=dict(report))
            else:
                _set_step_status(state, "validate", "failed", errors=report.get("errors", []))
                _print_step_failed("validate", report.get("errors", []))
                return 1
        except Exception as exc:
            _set_step_status(state, "validate", "failed", error=str(exc))
            _print_step_failed("validate", exc)
            return 1

    # ── finalise ─────────────────────────────────────────────────────
    state["execution"] = {  # type: ignore[index]
        "started_at": state.get("execution", {}).get("started_at", _utc_now()),  # type: ignore[union-attr]
        "completed_at": _utc_now(),
    }
    _save_run_state(output, state)
    print("Done.")
    return 0


# ── step implementations ───────────────────────────────────────────────


def _run_plan(
    task_id: str,
    output: Path,
    config_path,
    route_kml,
    scene,
    spec_toml,
) -> None:
    """Execute the *plan* step for the given task."""
    if task_id == "task01_underbody":
        from ..core.config import load_config
        from ..tasks.underbody_image.workflows.blender import build_blender_plan

        cfg = load_config(str(config_path))
        build_blender_plan(cfg, str(route_kml), str(scene), output)
    elif task_id == "task02_roof_360":
        _run_plan_panorama(output, scene, spec_toml)
    elif task_id == "task03_drone_lookat":
        _run_plan_lookat(output, scene, spec_toml)
    else:
        raise ValueError(f"unknown task: {task_id}")


def _run_plan_panorama(output: Path, scene, spec_toml) -> None:
    from ..tasks.roof_360_pano.specification import CaptureBand, Roof360Spec
    from ..tasks.roof_360_pano.workflows.blender import build_blender_plan

    raw = _read_toml(spec_toml)
    bus_raw = raw.get("bus", {})
    spec_raw = raw.get("spec", {})
    cap_raw = raw.get("capture", {})

    bands = []
    for b in spec_raw.get("bands", []):
        bands.append(
            CaptureBand(
                band_id=str(b["band_id"]),
                tilt_from_nadir_deg=float(b["tilt_from_nadir_deg"]),
                azimuth_deg=tuple(float(v) for v in b["azimuth_deg"]),
            )
        )
    spec = Roof360Spec(
        mast_height_m=float(spec_raw.get("mast_height_m", 2.0)),
        bands=tuple(bands),
    )
    build_blender_plan(
        spec,
        bus_length_m=float(bus_raw.get("length_m", 12.0)),
        bus_width_m=float(bus_raw.get("width_m", 2.55)),
        bus_height_m=float(bus_raw.get("height_m", 3.2)),
        scene_glb=str(scene),
        output_dir=output,
        horizontal_fov_deg=float(cap_raw.get("horizontal_fov_deg", 90.0)),
        image_width=int(cap_raw.get("image_width", 1920)),
        image_height=int(cap_raw.get("image_height", 1080)),
    )


def _run_plan_lookat(output: Path, scene, spec_toml) -> None:
    from ..tasks.drone_lookat_set.specification import DroneLookAtSpec
    from ..tasks.drone_lookat_set.workflows.blender import build_blender_plan

    raw = _read_toml(spec_toml)
    spec_raw = raw.get("spec", {})
    cap_raw = raw.get("capture", {})

    spec = DroneLookAtSpec(
        radius_m=float(spec_raw.get("radius_m", 250.0)),
        azimuth_deg=tuple(float(v) for v in spec_raw.get("azimuth_deg", [])),
        elevation_deg=tuple(float(v) for v in spec_raw.get("elevation_deg", [])),
    )
    build_blender_plan(
        spec,
        scene_glb=str(scene),
        output_dir=output,
        horizontal_fov_deg=float(cap_raw.get("horizontal_fov_deg", 90.0)),
        image_width=int(cap_raw.get("image_width", 1920)),
        image_height=int(cap_raw.get("image_height", 1080)),
    )


def _run_product(task_id: str, output: Path) -> None:
    if task_id == "task01_underbody":
        from ..tasks.underbody_image.evaluation import produce_underbody_product

        produce_underbody_product(output, output, target_frame_index=0)
    elif task_id == "task02_roof_360":
        from ..tasks.roof_360_pano.compositor import build_panorama

        build_panorama(output, output)
    elif task_id == "task03_drone_lookat":
        from ..tasks.drone_lookat_set.product_writer import write_viewset_product

        write_viewset_product(output, output)
    else:
        raise ValueError(f"unknown task: {task_id}")


# ── helpers ────────────────────────────────────────────────────────────


def _read_toml(path) -> dict:
    import tomllib

    with open(str(path), "rb") as stream:
        return tomllib.load(stream)


def _print_step_failed(step: str, detail: object) -> None:
    print(f"\n[{step}] FAILED: {detail}", file=sys.stderr)
