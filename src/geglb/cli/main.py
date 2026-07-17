from __future__ import annotations

import argparse
import json
from collections.abc import Mapping

from ..capture.registry import describe_backends
from ..core.config import load_config
from ..core.dataset import validate_dataset
from ..tasks.registry import describe_tasks
from ..tasks.underbody_image.compositor import run_planar_stitcher
from ..tasks.underbody_image.evaluation import produce_underbody_product
from ..tasks.underbody_image.stitch_plan import build_stitch_jobs
from ..tasks.underbody_image.workflows.blender import build_blender_plan
from ..tasks.underbody_image.workflows.ge3d import build_plan
from ..workflows.comparison import combine_datasets


def _capture_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", required=True, help="TOML project configuration")
    parser.add_argument("--route", required=True, help="KML file containing the ROUTE LineString")
    parser.add_argument("--out", required=True, help="Output dataset directory")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="geglb",
        description="Pluggable capture and dataset tools for transparent-vehicle BEV research.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("tasks", help="List tasks and their primary product contracts")
    commands.add_parser("backends", help="List capture adapters and their contracts")

    legacy = commands.add_parser("plan", help="Alias for 'ge-pro plan'")
    _capture_arguments(legacy)

    blender = commands.add_parser("blender", help="MVP1 Blender capture backend")
    blender_commands = blender.add_subparsers(dest="backend_command", required=True)
    blender_plan = blender_commands.add_parser("plan", help="Prepare a Blender render job")
    _capture_arguments(blender_plan)
    blender_plan.add_argument("--scene", required=True, help="Input .glb/.gltf scene")
    blender_plan.add_argument("--engine", default="BLENDER_EEVEE_NEXT")
    blender_plan.add_argument("--samples", type=int, default=32)
    blender_plan.add_argument("--transparent-background", action="store_true")

    ge_pro = commands.add_parser("ge-pro", help="MVP2 Google Earth Pro capture backend")
    ge_commands = ge_pro.add_subparsers(dest="backend_command", required=True)
    ge_plan = ge_commands.add_parser("plan", help="Generate a KML tour and capture dataset")
    _capture_arguments(ge_plan)

    validate = commands.add_parser("validate", help="Validate a standard capture dataset")
    validate.add_argument("dataset")
    validate.add_argument("--require-images", action="store_true")

    combine = commands.add_parser("combine", help="MVP3 pair two standard datasets")
    combine.add_argument("--primary", required=True)
    combine.add_argument("--secondary", required=True)
    combine.add_argument("--out", required=True)
    combine.add_argument("--max-distance-m", type=float, default=0.25)

    stitch = commands.add_parser("stitch", help="Source-independent stitching workflow")
    stitch_commands = stitch.add_subparsers(dest="stitch_command", required=True)
    stitch_plan = stitch_commands.add_parser("plan", help="Build per-frame stitching jobs")
    stitch_plan.add_argument("--dataset", required=True)
    stitch_plan.add_argument("--out", required=True)
    stitch_run = stitch_commands.add_parser("run", help="Run the flat-ground IPM baseline")
    stitch_run.add_argument("--dataset", required=True)
    stitch_run.add_argument("--out", required=True)
    stitch_run.add_argument("--meters-per-pixel", type=float, default=0.1)
    stitch_run.add_argument("--max-frames", type=int)

    product = commands.add_parser("product", help="MVP1 product and evaluation")
    product_commands = product.add_subparsers(dest="product_command", required=True)
    p_underbody = product_commands.add_parser(
        "underbody", help="Produce UnderbodyImageProduct from a captured dataset"
    )
    p_underbody.add_argument("--dataset", required=True)
    p_underbody.add_argument("--target-frame", type=int, required=True)
    p_underbody.add_argument("--out", required=True)
    p_underbody.add_argument("--meters-per-pixel", type=float, default=0.1)

    p_panorama = product_commands.add_parser(
        "panorama", help="Produce Panorama360Product from a captured dataset"
    )
    p_panorama.add_argument("--dataset", required=True)
    p_panorama.add_argument("--out", required=True)
    p_panorama.add_argument("--width", type=int, default=640)

    p_lookat = product_commands.add_parser(
        "lookat", help="Produce LookAtViewSetProduct from a captured dataset"
    )
    p_lookat.add_argument("--dataset", required=True)
    p_lookat.add_argument("--out", required=True)

    # blender plan-v2
    blender_v2 = blender_commands.add_parser("plan-v2", help="Prepare a v2 Blender render job")
    _capture_arguments(blender_v2)
    blender_v2.add_argument("--scene", required=True, help="Input .glb/.gltf scene")

    # run
    run_cmd = commands.add_parser("run", help="Run an end-to-end task pipeline")
    run_sub = run_cmd.add_subparsers(dest="run_task", required=True)
    for rtask, rhelp in [
        ("underbody", "Task 01 — underbody image"),
        ("panorama", "Task 02 — roof 360 panorama"),
        ("lookat", "Task 03 — drone LookAt view set"),
    ]:
        rp = run_sub.add_parser(rtask, help=rhelp)
        rp.add_argument("--config", help="TOML project configuration (underbody only)")
        rp.add_argument("--route", help="KML route file (underbody only)")
        rp.add_argument("--scene", help="Input .glb/.gltf scene")
        rp.add_argument("--spec", help="TOML spec file (panorama and lookat only)")
        rp.add_argument("--out", required=True, help="Output directory")
        rp.add_argument("--blender-exec", help="Path to Blender executable")
        rp.add_argument("--resume", action="store_true", help="Resume from previous run")
        rp.add_argument(
            "--existing",
            action="store_true",
            help="Skip plan step, use existing dataset",
        )

    validate_product_p = commands.add_parser(
        "validate-product", help="Validate a product directory"
    )
    validate_product_p.add_argument("product_dir")
    validate_product_p.add_argument(
        "--type",
        required=True,
        dest="product_type",
        choices=["underbody", "panorama", "lookat"],
    )

    serve_cmd = commands.add_parser("serve", help="Start the GE-GLB web dashboard")
    serve_cmd.add_argument("--port", type=int, default=8080)
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--dir", default="build", help="Root directory to scan for builds")
    return parser


def _print(value: Mapping[str, object]) -> None:
    print(json.dumps(dict(value), ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "tasks":
        _print(describe_tasks())
        return 0
    if args.command == "backends":
        _print(describe_backends())
        return 0
    if args.command == "plan" or args.command == "ge-pro":
        _print(build_plan(load_config(args.config), args.route, args.out))
        return 0
    if args.command == "blender":
        if getattr(args, "backend_command", None) == "plan-v2":
            from ..tasks.underbody_image.workflows.blender_v2 import (
                build_blender_plan_v2,
            )

            _print(
                build_blender_plan_v2(
                    load_config(args.config),
                    args.route,
                    args.scene,
                    args.out,
                ).as_dict()
            )
        else:
            _print(
                build_blender_plan(
                    load_config(args.config),
                    args.route,
                    args.scene,
                    args.out,
                    render_engine=args.engine,
                    samples=args.samples,
                    transparent_background=args.transparent_background,
                )
            )
        return 0
    if args.command == "validate":
        result = validate_dataset(args.dataset, require_images=args.require_images)
        _print(result)
        return 0 if result["valid"] else 2
    if args.command == "combine":
        _print(
            combine_datasets(
                args.primary,
                args.secondary,
                args.out,
                max_distance_m=args.max_distance_m,
            )
        )
        return 0
    if args.command == "stitch":
        if args.stitch_command == "plan":
            _print(build_stitch_jobs(args.dataset, args.out))
        else:
            _print(
                run_planar_stitcher(
                    args.dataset,
                    args.out,
                    meters_per_pixel=args.meters_per_pixel,
                    max_frames=args.max_frames,
                )
            )
        return 0
    if args.command == "product":
        if args.product_command == "underbody":
            _print(
                produce_underbody_product(
                    args.dataset,
                    args.out,
                    target_frame_index=args.target_frame,
                    meters_per_pixel=args.meters_per_pixel,
                )
            )
        elif args.product_command == "panorama":
            from ..tasks.roof_360_pano.compositor import build_panorama

            _print(build_panorama(args.dataset, args.out, panorama_width=args.width))
        elif args.product_command == "lookat":
            from ..tasks.drone_lookat_set.product_writer import write_viewset_product

            _print(write_viewset_product(args.dataset, args.out))
        return 0
    if args.command == "validate-product":
        from ..products.validate import validate_product

        report = validate_product(args.product_dir, args.product_type)
        _print(report)
        return 0 if report["valid"] else 2
    if args.command == "serve":
        from ..server import run_server

        run_server(host=args.host, port=args.port, scan_dir=args.dir)
        return 0
    if args.command == "run":
        from ..workflows.runner import run_task

        task_map = {
            "underbody": "task01_underbody",
            "panorama": "task02_roof_360",
            "lookat": "task03_drone_lookat",
        }
        # Validate required args per task.
        task = str(args.run_task)
        if task == "underbody":
            if not args.config:
                print("error: --config is required for underbody", file=__import__("sys").stderr)
                return 1
            if not args.route:
                print("error: --route is required for underbody", file=__import__("sys").stderr)
                return 1
        if task in ("panorama", "lookat"):
            if not args.spec:
                print(
                    f"error: --spec is required for {task}",
                    file=__import__("sys").stderr,
                )
                return 1
        if not args.scene and not args.existing:
            print("error: --scene is required (or use --existing)", file=__import__("sys").stderr)
            return 1

        return run_task(
            task_id=task_map[task],
            out_dir=args.out,
            config_path=args.config,
            route_kml=args.route,
            scene_glb=args.scene,
            spec_toml=args.spec,
            blender_exec=args.blender_exec,
            resume=bool(args.resume),
            existing=bool(args.existing),
        )
    raise AssertionError(f"unhandled command: {args.command}")
