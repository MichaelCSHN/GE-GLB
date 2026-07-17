"""Neutral capture plan generator for Task 02 Roof 360 Panorama.

Consumes a ``Roof360Spec`` and vehicle dimensions, then produces a
``CaptureModel`` with one ``CameraState`` per band × azimuth × vehicle pose.
The generated plan is backend-agnostic — it contains no Blender or GE-3D
specific fields.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...core.camera import (
    CameraState,
    camera_to_vehicle_transform,
    intrinsics,
    state_as_dict,
)
from ...core.config import CaptureConfig
from ...core.coordinates import LocalFrame, body_offset_to_enu
from ...core.trajectory import VehiclePose
from .specification import CaptureBand, Roof360Spec

# ── default configuration ──────────────────────────────────────────────


def default_spec() -> Roof360Spec:
    """Return the default dual-band configuration for Task 02.

    Four equally-spaced azimuth samples per band.  This is the
    reference fixture — real configurations should be tuned per
    vehicle and scene.
    """
    return Roof360Spec(
        mast_height_m=2.0,
        bands=(
            CaptureBand(
                band_id="horizontal",
                tilt_from_nadir_deg=90.0,
                azimuth_deg=(0.0, 90.0, 180.0, 270.0),
            ),
            CaptureBand(
                band_id="downward",
                tilt_from_nadir_deg=50.0,
                azimuth_deg=(0.0, 90.0, 180.0, 270.0),
            ),
        ),
    )


# ── default origin pose ────────────────────────────────────────────────


def _default_pose() -> VehiclePose:
    """Single origin pose used when the caller does not supply one."""
    return VehiclePose(
        index=0,
        distance_m=0.0,
        longitude_deg=0.0,
        latitude_deg=0.0,
        heading_deg=0.0,
    )


# ── camera state helper ────────────────────────────────────────────────


def _roof_camera_state(
    pose: VehiclePose,
    camera_id: str,
    azimuth_deg: float,
    tilt_from_nadir_deg: float,
    horizontal_fov_deg: float,
    position_forward_m: float,
    position_left_m: float,
    position_up_m: float,
) -> CameraState:
    """Compute the world-space ``CameraState`` for a roof-mounted camera.

    Parameters
    ----------
    pose :
        Vehicle pose in world space (geodetic + heading).
    camera_id :
        Unique identifier, e.g. ``"horizontal_az0"``.
    azimuth_deg :
        Clockwise angle from vehicle forward, in degrees (0 = forward, 90 = left).
    tilt_from_nadir_deg :
        Tilt away from nadir, in degrees (0 = straight down, 90 = horizontal).
    horizontal_fov_deg :
        Horizontal field of view in degrees.
    position_forward_m / position_left_m / position_up_m :
        Camera mount offset in the vehicle frame (x-forward, y-left, z-up).
    """
    east_offset, north_offset = body_offset_to_enu(
        position_forward_m, position_left_m, pose.heading_deg
    )
    frame = LocalFrame(pose.longitude_deg, pose.latitude_deg)
    longitude, latitude, _ = frame.to_geodetic(east_offset, north_offset)
    return CameraState(
        camera_id=camera_id,
        longitude_deg=longitude,
        latitude_deg=latitude,
        altitude_relative_m=position_up_m,
        heading_deg=(pose.heading_deg + azimuth_deg) % 360.0,
        tilt_deg=tilt_from_nadir_deg,
        roll_deg=0.0,
        horizontal_fov_deg=horizontal_fov_deg,
    )


# ── overlap validation utility ─────────────────────────────────────────


def validate_band_overlap(band: CaptureBand, horizontal_fov_deg: float) -> tuple[bool, list[str]]:
    """Check that adjacent azimuth samples within a band provide
    positive horizontal overlap.

    Returns
    -------
    (ok, issues) — *ok* is ``True`` when every adjacent pair overlaps;
    *issues* lists human-readable diagnostics for gaps.
    """
    if len(band.azimuth_deg) < 2:
        return True, []

    issues: list[str] = []
    az_list = sorted(band.azimuth_deg)
    for idx in range(len(az_list)):
        a1 = az_list[idx]
        a2 = az_list[(idx + 1) % len(az_list)]
        # shortest angular distance (handles wrap-around)
        diff = abs(a2 - a1)
        diff = min(diff, 360.0 - diff)
        if diff >= horizontal_fov_deg - 0.01:  # small numeric tolerance
            issues.append(
                f"band {band.band_id!r}: azimuth {a1:.1f}→{a2:.1f} "
                f"gap {diff:.1f}° with horizontal FOV {horizontal_fov_deg:.1f}°"
            )
    if issues:
        return False, issues
    return True, []


# ── CaptureModel ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class CaptureModel:
    """Neutral capture plan for Task 02.

    Contains every observation required to build a roof 360 panorama,
    independent of any particular capture backend.
    """

    poses: list[VehiclePose]
    ordered_states: list[tuple[VehiclePose, CameraState]]
    entries: list[dict[str, object]]
    calibration: dict[str, object]


# ── main entry point ───────────────────────────────────────────────────


def build_capture_model(
    spec: Roof360Spec,
    bus_length_m: float,
    bus_width_m: float,
    bus_height_m: float,
    horizontal_fov_deg: float = 90.0,
    image_width: int = 1920,
    image_height: int = 1080,
    poses: list[VehiclePose] | None = None,
) -> CaptureModel:
    """Generate a backend-agnostic capture plan from a roof-360 specification.

    Parameters
    ----------
    spec :
        Band definition (tilt, azimuth samples) and mast height.
    bus_length_m / bus_width_m / bus_height_m :
        Vehicle dimensions in metres.  The camera is mounted on a mast
        centred on the roof at ``(0, 0, bus_height_m + spec.mast_height_m)``.
    horizontal_fov_deg :
        Horizontal field of view shared by every camera in the plan.
    image_width / image_height :
        Capture resolution in pixels.
    poses :
        Vehicle poses to sample.  When *None*, a single origin pose is used.

    Returns
    -------
    CaptureModel
        Ordered capture plan with calibration, entries, and camera states.
    """
    spec.validate()

    if bus_length_m <= 0 or bus_width_m <= 0 or bus_height_m <= 0:
        raise ValueError("bus dimensions must be positive")
    if not 1.0 < horizontal_fov_deg < 179.0:
        raise ValueError("horizontal_fov_deg must be between 1 and 179 degrees")
    if image_width <= 0 or image_height <= 0:
        raise ValueError("image dimensions must be positive")

    if poses is None:
        poses = [_default_pose()]

    mast_up_m = bus_height_m + spec.mast_height_m
    capture_cfg = CaptureConfig(
        image_width=image_width,
        image_height=image_height,
        fly_duration_s=0.0,
        settle_seconds=0.0,
        sunlight_enabled=False,
    )

    # Build ordered camera list: for each band × azimuth we create one
    # logical "camera".  Order is deterministic: bands in spec order,
    # then azimuths in the order they appear in the tuple.
    camera_specs: list[tuple[str, float, float]] = []  # (camera_id, azimuth_deg, tilt_deg)
    for band in spec.bands:
        for azimuth in band.azimuth_deg:
            camera_id = f"{band.band_id}_az{azimuth:.0f}"
            camera_specs.append((camera_id, azimuth, band.tilt_from_nadir_deg))

    ordered_states: list[tuple[VehiclePose, CameraState]] = []
    entries: list[dict[str, object]] = []
    calibration_cameras: list[dict[str, object]] = []
    sequence = 0

    for camera_id, azimuth, tilt in camera_specs:
        # Calibration — one entry per logical camera.
        calibration_cameras.append(
            {
                "id": camera_id,
                "model": "rectilinear",
                "vehicle_frame": {
                    "x_forward_m": 0.0,
                    "y_left_m": 0.0,
                    "z_up_m": mast_up_m,
                },
                "orientation": {
                    "yaw_clockwise_from_vehicle_forward_deg": azimuth,
                    "tilt_from_nadir_deg": tilt,
                    "roll_deg": 0.0,
                },
                "camera_to_vehicle": camera_to_vehicle_transform(
                    (0.0, 0.0, mast_up_m), azimuth, tilt, 0.0
                ),
                "intrinsics": intrinsics(horizontal_fov_deg, capture_cfg),
            }
        )

        for pose in poses:
            state = _roof_camera_state(
                pose=pose,
                camera_id=camera_id,
                azimuth_deg=azimuth,
                tilt_from_nadir_deg=tilt,
                horizontal_fov_deg=horizontal_fov_deg,
                position_forward_m=0.0,
                position_left_m=0.0,
                position_up_m=mast_up_m,
            )
            ordered_states.append((pose, state))
            entries.append(_entry(sequence, pose, state))
            sequence += 1

    calibration: dict[str, object] = {
        "schema_version": "ge-glb.rig/v1",
        "project": "task02_roof_360",
        "vehicle_frame": "x_forward_y_left_z_up",
        "camera_frame": "x_right_y_down_z_forward",
        "bus": {
            "length_m": bus_length_m,
            "width_m": bus_width_m,
            "height_m": bus_height_m,
        },
        "mast_height_m": spec.mast_height_m,
        "cameras": calibration_cameras,
    }

    return CaptureModel(
        poses=list(poses),
        ordered_states=ordered_states,
        entries=entries,
        calibration=calibration,
    )


# ── helpers ────────────────────────────────────────────────────────────


def _entry(
    sequence: int,
    pose: VehiclePose,
    state: CameraState,
) -> dict[str, object]:
    """Build a single capture entry in the backend-neutral format."""
    return {
        "sequence": sequence,
        "pose_index": pose.index,
        "distance_m": pose.distance_m,
        "camera_id": state.camera_id,
        "output": f"images/{state.camera_id}/{pose.index:06d}.png",
        "vehicle": {
            "longitude_deg": pose.longitude_deg,
            "latitude_deg": pose.latitude_deg,
            "heading_deg": pose.heading_deg,
        },
        "camera": state_as_dict(state),
    }
