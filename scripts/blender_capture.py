"""Run with Blender, not system Python.

blender --background --python scripts/blender_capture.py -- --job build/mvp1/blender-job.json
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a GE-GLB Blender capture job")
    parser.add_argument("--job", required=True)
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(arguments)


def _rotation(mathutils, heading_deg: float, tilt_deg: float, roll_deg: float):
    heading = math.radians(heading_deg)
    tilt = math.radians(tilt_deg)
    view = mathutils.Vector(
        (math.sin(heading) * math.sin(tilt), math.cos(heading) * math.sin(tilt), -math.cos(tilt))
    )
    right = mathutils.Vector((math.cos(heading), -math.sin(heading), 0.0))
    local_z = -view
    up = local_z.cross(right).normalized()
    rotation = mathutils.Matrix((right, up, local_z)).transposed().to_4x4()
    if roll_deg:
        rotation = rotation @ mathutils.Matrix.Rotation(math.radians(roll_deg), 4, "Z")
    return rotation.to_quaternion()


def _ensure_light(bpy) -> None:
    if any(obj.type == "LIGHT" for obj in bpy.context.scene.objects):
        return
    light_data = bpy.data.lights.new(name="GEGLB_DefaultSun", type="SUN")
    light_data.energy = 3.0
    light = bpy.data.objects.new(name="GEGLB_DefaultSun", object_data=light_data)
    bpy.context.collection.objects.link(light)
    light.rotation_euler = (math.radians(30.0), 0.0, math.radians(-25.0))


def _mark_complete(dataset: Path) -> None:
    frames_path = dataset / "frames.jsonl"
    updated = []
    for line in frames_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        frame = json.loads(line)
        if (dataset / Path(frame["image"])).is_file():
            frame["status"] = "captured"
        updated.append(frame)
    frames_path.write_text(
        "".join(json.dumps(frame, separators=(",", ":")) + "\n" for frame in updated),
        encoding="utf-8",
    )
    manifest_path = dataset / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "complete"
    manifest["capture"] = {
        "captured_frames": len(updated),
        "report": "capture-report.jsonl",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def run(job_path: Path) -> None:
    import bpy  # type: ignore
    import mathutils  # type: ignore

    job = json.loads(job_path.read_text(encoding="utf-8"))
    if job.get("schema_version") != "ge-glb.blender-job/v1":
        raise ValueError(f"unsupported Blender job: {job.get('schema_version')!r}")
    dataset = Path(job["dataset_dir"])
    scene_path = Path(job["scene_glb"])
    if not scene_path.is_file():
        raise FileNotFoundError(scene_path)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(scene_path))
    scene = bpy.context.scene
    render = job["render"]
    scene.render.engine = render["engine"]
    scene.render.resolution_x = int(render["width"])
    scene.render.resolution_y = int(render["height"])
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = render["file_format"]
    scene.render.film_transparent = bool(render["transparent_background"])
    if hasattr(scene, "eevee"):
        scene.eevee.taa_render_samples = int(render["samples"])
    if hasattr(scene, "cycles"):
        scene.cycles.samples = int(render["samples"])
    if render.get("add_default_sun_if_missing", True):
        _ensure_light(bpy)

    cameras = {}
    report_path = dataset / "capture-report.jsonl"
    with report_path.open("w", encoding="utf-8", newline="\n") as report:
        for item in job["frames"]:
            camera_id = str(item["camera_id"])
            camera = cameras.get(camera_id)
            if camera is None:
                camera_data = bpy.data.cameras.new(name=f"GEGLB_{camera_id}")
                camera = bpy.data.objects.new(name=f"GEGLB_{camera_id}", object_data=camera_data)
                bpy.context.collection.objects.link(camera)
                cameras[camera_id] = camera
            state = item["camera_world"]
            position = state["local_enu_m"]
            camera.location = (float(position["east"]), float(position["north"]), float(position["up"]))
            camera.rotation_mode = "QUATERNION"
            camera.rotation_quaternion = _rotation(
                mathutils,
                float(state["heading_deg"]),
                float(state["tilt_from_nadir_deg"]),
                float(state["roll_deg"]),
            )
            camera.data.type = "PERSP"
            camera.data.sensor_fit = "HORIZONTAL"
            camera.data.angle = math.radians(float(state["horizontal_fov_deg"]))
            scene.camera = camera
            scene.frame_set(int(item["frame_index"]) + 1)
            output = dataset / Path(item["image"])
            output.parent.mkdir(parents=True, exist_ok=True)
            scene.render.filepath = str(output)
            bpy.ops.render.render(write_still=True)
            result = {
                "sequence": item["sequence"],
                "frame_index": item["frame_index"],
                "camera_id": camera_id,
                "image": item["image"],
                "status": "captured",
                "bytes": output.stat().st_size,
            }
            report.write(json.dumps(result, separators=(",", ":")) + "\n")
            report.flush()
    _mark_complete(dataset)


if __name__ == "__main__":
    run(Path(_arguments().job).resolve())
