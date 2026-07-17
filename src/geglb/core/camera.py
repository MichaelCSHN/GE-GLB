from __future__ import annotations

from dataclasses import asdict, dataclass
import math

from .config import BusConfig, CameraConfig, CaptureConfig, GroundTruthConfig
from .coordinates import LocalFrame, body_offset_to_enu
from .trajectory import VehiclePose


@dataclass(frozen=True)
class CameraState:
    camera_id: str
    longitude_deg: float
    latitude_deg: float
    altitude_relative_m: float
    heading_deg: float
    tilt_deg: float
    roll_deg: float
    horizontal_fov_deg: float


def resolve_mount(camera: CameraConfig, bus: BusConfig) -> tuple[float, float, float]:
    if camera.position_m is not None:
        return camera.position_m
    z = bus.height_m + camera.z_offset_from_roof_m
    mounts = {
        "front_center": (bus.length_m / 2.0, 0.0, z),
        "rear_center": (-bus.length_m / 2.0, 0.0, z),
        "left_center": (0.0, bus.width_m / 2.0, z),
        "right_center": (0.0, -bus.width_m / 2.0, z),
        "front_left": (bus.length_m / 2.0, bus.width_m / 2.0, z),
        "front_right": (bus.length_m / 2.0, -bus.width_m / 2.0, z),
        "rear_left": (-bus.length_m / 2.0, bus.width_m / 2.0, z),
        "rear_right": (-bus.length_m / 2.0, -bus.width_m / 2.0, z),
    }
    try:
        return mounts[camera.mount]
    except KeyError as exc:
        raise ValueError(
            f"unknown mount {camera.mount!r} for {camera.camera_id}; use position_m for custom mounts"
        ) from exc


def camera_state_for_pose(
    pose: VehiclePose, camera: CameraConfig, bus: BusConfig
) -> CameraState:
    forward, left, up = resolve_mount(camera, bus)
    east_offset, north_offset = body_offset_to_enu(forward, left, pose.heading_deg)
    frame = LocalFrame(pose.longitude_deg, pose.latitude_deg)
    longitude, latitude, _ = frame.to_geodetic(east_offset, north_offset)
    return CameraState(
        camera_id=camera.camera_id,
        longitude_deg=longitude,
        latitude_deg=latitude,
        altitude_relative_m=up,
        heading_deg=(pose.heading_deg + camera.yaw_deg) % 360.0,
        tilt_deg=camera.tilt_deg,
        roll_deg=camera.roll_deg,
        horizontal_fov_deg=camera.horizontal_fov_deg,
    )


def ground_truth_state_for_pose(pose: VehiclePose, config: GroundTruthConfig) -> CameraState:
    return CameraState(
        camera_id=config.camera_id,
        longitude_deg=pose.longitude_deg,
        latitude_deg=pose.latitude_deg,
        altitude_relative_m=config.height_m,
        heading_deg=pose.heading_deg,
        tilt_deg=0.0,
        roll_deg=0.0,
        horizontal_fov_deg=config.horizontal_fov_deg,
    )


def intrinsics(horizontal_fov_deg: float, capture: CaptureConfig) -> dict[str, float | int]:
    fov = math.radians(horizontal_fov_deg)
    fx = (capture.image_width / 2.0) / math.tan(fov / 2.0)
    fy = fx
    vertical_fov = math.degrees(2.0 * math.atan((capture.image_height / 2.0) / fy))
    return {
        "width": capture.image_width,
        "height": capture.image_height,
        "fx": fx,
        "fy": fy,
        "cx": capture.image_width / 2.0,
        "cy": capture.image_height / 2.0,
        "horizontal_fov_deg": horizontal_fov_deg,
        "vertical_fov_deg": vertical_fov,
    }


def camera_calibration(
    camera: CameraConfig, bus: BusConfig, capture: CaptureConfig
) -> dict[str, object]:
    forward, left, up = resolve_mount(camera, bus)
    return {
        "id": camera.camera_id,
        "model": "rectilinear",
        "vehicle_frame": {"x_forward_m": forward, "y_left_m": left, "z_up_m": up},
        "orientation": {
            "yaw_clockwise_from_vehicle_forward_deg": camera.yaw_deg,
            "tilt_from_nadir_deg": camera.tilt_deg,
            "roll_deg": camera.roll_deg,
        },
        "camera_to_vehicle": camera_to_vehicle_transform(
            (forward, left, up),
            camera.yaw_deg,
            camera.tilt_deg,
            camera.roll_deg,
        ),
        "intrinsics": intrinsics(camera.horizontal_fov_deg, capture),
    }


def camera_to_vehicle_transform(
    position: tuple[float, float, float],
    yaw_deg: float,
    tilt_deg: float,
    roll_deg: float,
) -> list[list[float]]:
    """Transform x-right/y-down/z-forward camera coordinates into the vehicle frame."""

    yaw = math.radians(yaw_deg)
    tilt = math.radians(tilt_deg)
    roll = math.radians(roll_deg)
    camera_z = (
        math.cos(yaw) * math.sin(tilt),
        -math.sin(yaw) * math.sin(tilt),
        -math.cos(tilt),
    )
    unrolled_x = (-math.sin(yaw), -math.cos(yaw), 0.0)
    unrolled_y = (
        camera_z[1] * unrolled_x[2] - camera_z[2] * unrolled_x[1],
        camera_z[2] * unrolled_x[0] - camera_z[0] * unrolled_x[2],
        camera_z[0] * unrolled_x[1] - camera_z[1] * unrolled_x[0],
    )
    camera_x = tuple(
        unrolled_x[index] * math.cos(roll) + unrolled_y[index] * math.sin(roll)
        for index in range(3)
    )
    camera_y = tuple(
        -unrolled_x[index] * math.sin(roll) + unrolled_y[index] * math.cos(roll)
        for index in range(3)
    )
    return [
        [camera_x[0], camera_y[0], camera_z[0], position[0]],
        [camera_x[1], camera_y[1], camera_z[1], position[1]],
        [camera_x[2], camera_y[2], camera_z[2], position[2]],
        [0.0, 0.0, 0.0, 1.0],
    ]


def state_as_dict(state: CameraState) -> dict[str, object]:
    return asdict(state)
