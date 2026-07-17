from __future__ import annotations

import argparse
import json

from .config import load_config
from .planner import build_plan


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="geglb",
        description="Build Google Earth Pro capture plans for transparent-vehicle BEV experiments.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser(
        "plan", help="Generate poses, calibration, capture/fusion plans and KML tour"
    )
    plan.add_argument("--config", required=True, help="TOML project configuration")
    plan.add_argument("--route", required=True, help="KML file containing the ROUTE LineString")
    plan.add_argument("--out", required=True, help="Output directory")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "plan":
        summary = build_plan(load_config(args.config), args.route, args.out)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    raise AssertionError(f"unhandled command: {args.command}")
