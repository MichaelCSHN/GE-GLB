from __future__ import annotations

from dataclasses import dataclass
import math

from .specification import DroneLookAtSpec


@dataclass(frozen=True)
class HemisphereView:
    azimuth_deg: float
    elevation_deg: float
    radius_m: float
    offset_enu_m: tuple[float, float, float]
    target_ref: str


def enumerate_hemisphere(spec: DroneLookAtSpec) -> list[HemisphereView]:
    spec.validate()
    result: list[HemisphereView] = []
    for elevation_deg in spec.elevation_deg:
        elevation = math.radians(elevation_deg)
        horizontal = spec.radius_m * math.cos(elevation)
        up = spec.radius_m * math.sin(elevation)
        for azimuth_deg in spec.azimuth_deg:
            azimuth = math.radians(azimuth_deg)
            result.append(
                HemisphereView(
                    azimuth_deg=azimuth_deg % 360.0,
                    elevation_deg=elevation_deg,
                    radius_m=spec.radius_m,
                    offset_enu_m=(
                        horizontal * math.sin(azimuth),
                        horizontal * math.cos(azimuth),
                        up,
                    ),
                    target_ref=spec.target_ref,
                )
            )
    return result
