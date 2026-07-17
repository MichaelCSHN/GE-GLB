from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CaptureBand:
    band_id: str
    tilt_from_nadir_deg: float
    azimuth_deg: tuple[float, ...]


@dataclass(frozen=True)
class Roof360Spec:
    mast_height_m: float
    bands: tuple[CaptureBand, ...]
    output_projection: str = "equirectangular"

    def validate(self) -> None:
        if self.mast_height_m <= 0:
            raise ValueError("mast_height_m must be positive")
        if self.output_projection != "equirectangular":
            raise ValueError("the v1 panorama product must be equirectangular")
        if not self.bands:
            raise ValueError("at least one capture band is required")
        for band in self.bands:
            if not band.azimuth_deg:
                raise ValueError(f"band {band.band_id!r} has no azimuth samples")
            if not 0.0 <= band.tilt_from_nadir_deg <= 180.0:
                raise ValueError(f"band {band.band_id!r} tilt is outside [0, 180]")
