from __future__ import annotations

import bisect
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from .coordinates import LocalFrame, heading_from_delta


@dataclass(frozen=True)
class RoutePoint:
    longitude_deg: float
    latitude_deg: float
    altitude_m: float = 0.0


@dataclass(frozen=True)
class VehiclePose:
    index: int
    distance_m: float
    longitude_deg: float
    latitude_deg: float
    heading_deg: float


def _parse_coordinates(text: str) -> list[RoutePoint]:
    points: list[RoutePoint] = []
    for token in text.replace("\n", " ").split():
        values = token.split(",")
        if len(values) < 2:
            continue
        points.append(
            RoutePoint(
                longitude_deg=float(values[0]),
                latitude_deg=float(values[1]),
                altitude_m=float(values[2]) if len(values) > 2 and values[2] else 0.0,
            )
        )
    return points


def load_route_kml(path: str | Path, placemark_name: str = "ROUTE") -> list[RoutePoint]:
    root = ET.parse(path).getroot()
    available: list[str] = []
    for placemark in root.findall(".//{*}Placemark"):
        name_node = placemark.find("./{*}name")
        name = (name_node.text or "").strip() if name_node is not None else ""
        line = placemark.find(".//{*}LineString")
        if line is None:
            continue
        available.append(name or "<unnamed>")
        if name != placemark_name:
            continue
        coordinates = line.find("./{*}coordinates")
        if coordinates is None or not coordinates.text:
            raise ValueError(f"Placemark {placemark_name!r} has no coordinates")
        points = _parse_coordinates(coordinates.text)
        if len(points) < 2:
            raise ValueError(f"Placemark {placemark_name!r} needs at least two route points")
        return points
    raise ValueError(
        f"No LineString Placemark named {placemark_name!r}; "
        f"available: {', '.join(available) or 'none'}"
    )


def resample_route(points: list[RoutePoint], spacing_m: float) -> list[VehiclePose]:
    if len(points) < 2:
        raise ValueError("route needs at least two points")
    if spacing_m <= 0:
        raise ValueError("spacing_m must be positive")

    frame = LocalFrame(points[0].longitude_deg, points[0].latitude_deg, points[0].altitude_m)
    local = [frame.to_local(p.longitude_deg, p.latitude_deg, p.altitude_m)[:2] for p in points]
    cumulative = [0.0]
    for previous, current in zip(local, local[1:]):
        segment = math.hypot(current[0] - previous[0], current[1] - previous[1])
        if segment > 1e-6:
            cumulative.append(cumulative[-1] + segment)
        else:
            cumulative.append(cumulative[-1])
    total = cumulative[-1]
    if total <= 1e-6:
        raise ValueError("route has zero length")

    sample_distances: list[float] = []
    distance = 0.0
    while distance < total:
        sample_distances.append(distance)
        distance += spacing_m
    if not sample_distances or total - sample_distances[-1] > 1e-6:
        sample_distances.append(total)

    sampled_xy: list[tuple[float, float]] = []
    for sample in sample_distances:
        segment_index = max(
            0,
            min(len(cumulative) - 2, bisect.bisect_right(cumulative, sample) - 1),
        )
        start_distance = cumulative[segment_index]
        end_distance = cumulative[segment_index + 1]
        span = end_distance - start_distance
        fraction = 0.0 if span <= 1e-9 else (sample - start_distance) / span
        start = local[segment_index]
        end = local[segment_index + 1]
        sampled_xy.append(
            (
                start[0] + fraction * (end[0] - start[0]),
                start[1] + fraction * (end[1] - start[1]),
            )
        )

    poses: list[VehiclePose] = []
    for index, ((east, north), sample) in enumerate(zip(sampled_xy, sample_distances)):
        before = sampled_xy[max(0, index - 1)]
        after = sampled_xy[min(len(sampled_xy) - 1, index + 1)]
        heading = heading_from_delta(after[0] - before[0], after[1] - before[1])
        longitude, latitude, _ = frame.to_geodetic(east, north)
        poses.append(
            VehiclePose(
                index=index,
                distance_m=sample,
                longitude_deg=longitude,
                latitude_deg=latitude,
                heading_deg=heading,
            )
        )
    return poses
