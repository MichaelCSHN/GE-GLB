"""Neutral capture plan generator for Task 03 Drone LookAt View Set.

Consumes a ``DroneLookAtSpec`` and vehicle poses, then produces a
``CaptureModel`` with one ``CameraState`` per hemisphere view × vehicle pose.
Every camera is oriented to look at the vehicle centre (LookAt constraint).
"""

from __future__ import annotations

import math
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
from .hemisphere import enumerate_hemisphere
from .specification import DroneLookAtSpec


def default_spec() -> DroneLookAtSpec:
    """Return the default hemisphere sampling configuration for Task 03.

    8 azimuths × 3 elevations = 24 views per vehicle pose.
    """
    return DroneLookAtSpec(
        radius_m=250.0,
        azimuth_deg=(0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0),
        elevation_deg=(30.0, 60.0, 90.0),
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


def _lookat_camera_state(
    pose: VehiclePose,
    camera_id: str,
    offset_enu_m: tuple[float, float, float],
    horizontal_fov_deg: float,
    frame: LocalFrame,
) -> CameraState:
    """Compute the world-space ``CameraState`` for a drone observer.

    The observer is placed at *offset_enu_m* relative to the vehicle
    (rotated by the vehicle heading), then oriented to look at the
    vehicle centre.

    Parameters
    ----------
    pose :
        Vehicle pose in world space.
    camera_id :
        Unique identifier, e.g. ``"az0_el30"``.
    offset_enu_m :
        (east, north, up) offset from the vehicle centre, expressed in
        the local ENU frame at heading 0°.
    horizontal_fov_deg :
        Horizontal field of view in degrees.
    frame :
        ``LocalFrame`` anchored at the route origin for ENU↔geodetic
        conversions.
    """
    off_east, off_north, off_up = offset_enu_m

    # Rotate the horizontal ENU offset by the vehicle heading so the
    # hemisphere rotates with the vehicle.
    #
    # At heading = 0°, vehicle forward = north, vehicle left = −east.
    # So forward_component = off_north, left_component = −off_east.
    fwd = off_north
    lft = -off_east

    rotated_east, rotated_north = body_offset_to_enu(fwd, lft, pose.heading_deg)

    veh_east, veh_north, veh_up = frame.to_local(pose.longitude_deg, pose.latitude_deg)

    obs_east = veh_east + rotated_east
    obs_north = veh_north + rotated_north
    obs_up = veh_up + off_up

    obs_lon, obs_lat, _ = frame.to_geodetic(obs_east, obs_north, obs_up)

    # LookAt direction: observer → vehicle centre.
    dx = veh_east - obs_east
    dy = veh_north - obs_north
    dz = veh_up - obs_up

    heading_deg = math.degrees(math.atan2(dx, dy)) % 360.0
    horizontal_dist = math.hypot(dx, dy)
    tilt_deg = math.degrees(math.atan2(horizontal_dist, -dz))

    return CameraState(
        camera_id=camera_id,
        longitude_deg=obs_lon,
        latitude_deg=obs_lat,
        altitude_relative_m=obs_up,
        heading_deg=heading_deg,
        tilt_deg=tilt_deg,
        roll_deg=0.0,
        horizontal_fov_deg=horizontal_fov_deg,
    )


# ── CaptureModel ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class CaptureModel:
    """Neutral capture plan for Task 03.

    Contains every observation required to build a drone LookAt view
    set, independent of any particular capture backend.
    """

    poses: list[VehiclePose]
    ordered_states: list[tuple[VehiclePose, CameraState]]
    entries: list[dict[str, object]]
    calibration: dict[str, object]


# ── main entry point ───────────────────────────────────────────────────


def build_capture_model(
    spec: DroneLookAtSpec,
    horizontal_fov_deg: float = 90.0,
    image_width: int = 1920,
    image_height: int = 1080,
    poses: list[VehiclePose] | None = None,
) -> CaptureModel:
    """Generate a backend-agnostic capture plan from a drone-LookAt spec.

    Parameters
    ----------
    spec :
        Hemisphere definition (radius, azimuths, elevations).
    horizontal_fov_deg :
        Horizontal field of view for every camera.
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

    if not 1.0 < horizontal_fov_deg < 179.0:
        raise ValueError("horizontal_fov_deg must be between 1 and 179 degrees")
    if image_width <= 0 or image_height <= 0:
        raise ValueError("image dimensions must be positive")

    if poses is None:
        poses = [_default_pose()]

    origin = poses[0]
    frame = LocalFrame(origin.longitude_deg, origin.latitude_deg)

    views = enumerate_hemisphere(spec)
    capture_cfg = CaptureConfig(
        image_width=image_width,
        image_height=image_height,
        fly_duration_s=0.0,
        settle_seconds=0.0,
        sunlight_enabled=False,
    )
    shared_intrinsics = intrinsics(horizontal_fov_deg, capture_cfg)

    # Build calibration — one entry per hemisphere view.
    # All views share the same intrinsics but differ in position and
    # orientation relative to the vehicle (computed at heading=0).
    calibration_cameras: list[dict[str, object]] = []
    for view in views:
        camera_id = f"az{view.azimuth_deg:.0f}_el{view.elevation_deg:.0f}"
        off_east, off_north, off_up = view.offset_enu_m

        # Vehicle-frame position at heading=0: forward=north, left=−east.
        vf_x = off_north
        vf_y = -off_east
        vf_z = off_up

        # LookAt direction at heading=0 (vehicle at origin, observer at offset).
        dx = -off_east
        dy = -off_north
        dz = -off_up
        base_heading = math.degrees(math.atan2(dx, dy)) % 360.0
        h_dist = math.hypot(dx, dy)
        base_tilt = math.degrees(math.atan2(h_dist, -dz))

        calibration_cameras.append(
            {
                "id": camera_id,
                "model": "rectilinear",
                "vehicle_frame": {
                    "x_forward_m": vf_x,
                    "y_left_m": vf_y,
                    "z_up_m": vf_z,
                },
                "orientation": {
                    "yaw_clockwise_from_vehicle_forward_deg": base_heading,
                    "tilt_from_nadir_deg": base_tilt,
                    "roll_deg": 0.0,
                },
                "camera_to_vehicle": camera_to_vehicle_transform(
                    (vf_x, vf_y, vf_z), base_heading, base_tilt, 0.0
                ),
                "intrinsics": shared_intrinsics,
            }
        )

    ordered_states: list[tuple[VehiclePose, CameraState]] = []
    entries: list[dict[str, object]] = []
    sequence = 0

    for view in views:
        camera_id = f"az{view.azimuth_deg:.0f}_el{view.elevation_deg:.0f}"
        for pose in poses:
            state = _lookat_camera_state(
                pose=pose,
                camera_id=camera_id,
                offset_enu_m=view.offset_enu_m,
                horizontal_fov_deg=horizontal_fov_deg,
                frame=frame,
            )
            ordered_states.append((pose, state))
            entries.append(_entry(sequence, pose, state))
            sequence += 1

    calibration: dict[str, object] = {
        "schema_version": "ge-glb.rig/v1",
        "project": "task03_drone_lookat",
        "vehicle_frame": "x_forward_y_left_z_up",
        "camera_frame": "x_right_y_down_z_forward",
        "observer": {
            "radius_m": spec.radius_m,
            "target_ref": spec.target_ref,
        },
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
