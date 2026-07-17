from __future__ import annotations

import math

from ...core.config import CameraConfig, FusionConfig
from ...core.coordinates import LocalFrame
from ...core.trajectory import VehiclePose


def _signed_angle(angle_deg: float) -> float:
    return (angle_deg + 180.0) % 360.0 - 180.0


def _relative_vehicle_pose(source: VehiclePose, target: VehiclePose) -> dict[str, float]:
    frame = LocalFrame(target.longitude_deg, target.latitude_deg)
    east, north, _ = frame.to_local(source.longitude_deg, source.latitude_deg)
    heading = math.radians(target.heading_deg)
    return {
        "x_forward_m": east * math.sin(heading) + north * math.cos(heading),
        "y_left_m": -east * math.cos(heading) + north * math.sin(heading),
        "yaw_deg": _signed_angle(source.heading_deg - target.heading_deg),
    }


def _temporal_prior(camera: CameraConfig, direction: str) -> float:
    """Heuristic only; geometric visibility and image quality make the final decision."""
    forwardness = math.cos(math.radians(camera.yaw_deg))
    if direction == "past":
        # A previous front view tends to contain ground now hidden by the vehicle.
        return 0.6 + 0.4 * forwardness
    # For the first-frame bootstrap, a future rear view tends to see the old footprint.
    return 0.6 - 0.4 * forwardness


def _observation(
    target: VehiclePose,
    source: VehiclePose,
    camera: CameraConfig,
    role: str,
    frame_offset: int,
) -> dict[str, object]:
    if frame_offset == 0:
        prior = 1.0
    else:
        prior = _temporal_prior(camera, "past" if frame_offset < 0 else "future")
    return {
        "source_pose_index": source.index,
        "frame_offset": frame_offset,
        "camera_id": camera.camera_id,
        "image": f"images/{camera.camera_id}/{source.index:06d}.png",
        "role": role,
        "heuristic_prior": round(prior, 6),
        "source_vehicle_in_target_frame": _relative_vehicle_pose(source, target),
    }


def build_fusion_plan(
    poses: list[VehiclePose],
    cameras: tuple[CameraConfig, ...],
    config: FusionConfig,
) -> dict[str, object]:
    targets: list[dict[str, object]] = []
    for target_index, target in enumerate(poses):
        observations = [
            _observation(target, target, camera, "current_surround", 0)
            for camera in cameras
        ]

        if target_index > 0:
            first_history = max(0, target_index - config.history_frames)
            for source_index in range(target_index - 1, first_history - 1, -1):
                source = poses[source_index]
                history_cameras = cameras if config.include_all_history_cameras else cameras[:1]
                observations.extend(
                    _observation(
                        target,
                        source,
                        camera,
                        "past_underbody_candidate",
                        source_index - target_index,
                    )
                    for camera in history_cameras
                )
            available_after = target_index
            status = "causal"
        elif config.bootstrap_first_frame_from_future and len(poses) > 1:
            source = poses[1]
            observations.extend(
                _observation(target, source, camera, "future_bootstrap_candidate", 1)
                for camera in cameras
            )
            available_after = 1
            status = "one_frame_delayed"
        else:
            available_after = target_index
            status = "history_incomplete"

        targets.append(
            {
                "target_pose_index": target.index,
                "available_after_pose_index": available_after,
                "latency_frames": available_after - target_index,
                "status": status,
                "observations": observations,
            }
        )

    return {
        "schema_version": 1,
        "policy": {
            "current_frame": "all_surround_cameras",
            "history_frames": config.history_frames,
            "history_cameras": (
                "all_surround_cameras" if config.include_all_history_cameras else "first_camera"
            ),
            "selection": "visibility_then_resolution_then_incidence; heuristic_prior_is_not_a_mask",
            "ground_truth_is_input": False,
        },
        "targets": targets,
    }
