from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DroneLookAtSpec:
    radius_m: float
    azimuth_deg: tuple[float, ...]
    elevation_deg: tuple[float, ...]
    target_ref: str = "vehicle_center"

    def validate(self) -> None:
        if self.radius_m <= 0:
            raise ValueError("radius_m must be positive")
        if not self.azimuth_deg or not self.elevation_deg:
            raise ValueError("azimuth and elevation samples are required")
        if any(not 0.0 <= value <= 90.0 for value in self.elevation_deg):
            raise ValueError("hemisphere elevation must be within [0, 90]")
