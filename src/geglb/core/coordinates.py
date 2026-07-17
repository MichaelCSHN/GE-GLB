from __future__ import annotations

from dataclasses import dataclass
import math


WGS84_A = 6_378_137.0
WGS84_E2 = 6.69437999014e-3


@dataclass(frozen=True)
class LocalFrame:
    """Small-area east/north/up frame anchored at a geodetic point."""

    longitude_deg: float
    latitude_deg: float
    altitude_m: float = 0.0

    @property
    def _radii(self) -> tuple[float, float, float]:
        latitude = math.radians(self.latitude_deg)
        sin_lat = math.sin(latitude)
        denominator = math.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
        prime_vertical = WGS84_A / denominator
        meridian = WGS84_A * (1.0 - WGS84_E2) / (denominator**3)
        return meridian, prime_vertical, math.cos(latitude)

    def to_local(
        self, longitude_deg: float, latitude_deg: float, altitude_m: float = 0.0
    ) -> tuple[float, float, float]:
        meridian, prime_vertical, cos_lat = self._radii
        east = math.radians(longitude_deg - self.longitude_deg) * (
            prime_vertical + self.altitude_m
        ) * cos_lat
        north = math.radians(latitude_deg - self.latitude_deg) * (
            meridian + self.altitude_m
        )
        up = altitude_m - self.altitude_m
        return east, north, up

    def to_geodetic(
        self, east_m: float, north_m: float, up_m: float = 0.0
    ) -> tuple[float, float, float]:
        meridian, prime_vertical, cos_lat = self._radii
        longitude = self.longitude_deg + math.degrees(
            east_m / ((prime_vertical + self.altitude_m) * cos_lat)
        )
        latitude = self.latitude_deg + math.degrees(
            north_m / (meridian + self.altitude_m)
        )
        return longitude, latitude, self.altitude_m + up_m


def body_offset_to_enu(
    forward_m: float, left_m: float, heading_deg: float
) -> tuple[float, float]:
    """Transform a vehicle-frame offset into east/north coordinates."""

    heading = math.radians(heading_deg)
    east = forward_m * math.sin(heading) - left_m * math.cos(heading)
    north = forward_m * math.cos(heading) + left_m * math.sin(heading)
    return east, north


def heading_from_delta(east_m: float, north_m: float) -> float:
    """Return KML heading: degrees clockwise from north."""

    return math.degrees(math.atan2(east_m, north_m)) % 360.0
