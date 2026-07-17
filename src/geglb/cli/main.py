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
        return 0
    raise AssertionError(f"unhandled command: {args.command}")
