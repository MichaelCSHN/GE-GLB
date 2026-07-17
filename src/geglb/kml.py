from __future__ import annotations

import xml.etree.ElementTree as ET

from .config import CaptureConfig
from .rig import CameraState
from .route import VehiclePose


KML_NS = "http://www.opengis.net/kml/2.2"
GX_NS = "http://www.google.com/kml/ext/2.2"
ET.register_namespace("", KML_NS)
ET.register_namespace("gx", GX_NS)


def _kml(name: str) -> str:
    return f"{{{KML_NS}}}{name}"


def _gx(name: str) -> str:
    return f"{{{GX_NS}}}{name}"


def _text(parent: ET.Element, tag: str, value: object) -> ET.Element:
    node = ET.SubElement(parent, tag)
    node.text = str(value)
    return node


def _add_camera(parent: ET.Element, state: CameraState, capture: CaptureConfig) -> None:
    camera = ET.SubElement(parent, _kml("Camera"))
    viewer_options = ET.SubElement(camera, _gx("ViewerOptions"))
    ET.SubElement(
        viewer_options,
        _gx("option"),
        {"name": "sunlight", "enabled": str(capture.sunlight_enabled).lower()},
    )
    _text(camera, _gx("horizFov"), f"{state.horizontal_fov_deg:.8f}")
    _text(camera, _kml("longitude"), f"{state.longitude_deg:.10f}")
    _text(camera, _kml("latitude"), f"{state.latitude_deg:.10f}")
    _text(camera, _kml("altitude"), f"{state.altitude_relative_m:.4f}")
    _text(camera, _kml("heading"), f"{state.heading_deg:.8f}")
    _text(camera, _kml("tilt"), f"{state.tilt_deg:.8f}")
    _text(camera, _kml("roll"), f"{state.roll_deg:.8f}")
    _text(camera, _kml("altitudeMode"), "relativeToGround")


def build_capture_tour(
    project_name: str,
    poses: list[VehiclePose],
    states: list[tuple[VehiclePose, CameraState]],
    capture: CaptureConfig,
) -> ET.ElementTree:
    root = ET.Element(_kml("kml"))
    document = ET.SubElement(root, _kml("Document"))
    _text(document, _kml("name"), f"{project_name} capture plan")

    route = ET.SubElement(document, _kml("Placemark"))
    _text(route, _kml("name"), "RESAMPLED_ROUTE")
    line = ET.SubElement(route, _kml("LineString"))
    _text(line, _kml("tessellate"), "1")
    _text(line, _kml("altitudeMode"), "clampToGround")
    _text(
        line,
        _kml("coordinates"),
        "\n".join(f"{p.longitude_deg:.10f},{p.latitude_deg:.10f},0" for p in poses),
    )

    tour = ET.SubElement(document, _gx("Tour"))
    _text(tour, _kml("name"), "CAPTURE_TOUR")
    playlist = ET.SubElement(tour, _gx("Playlist"))
    for _pose, state in states:
        fly_to = ET.SubElement(playlist, _gx("FlyTo"))
        _text(fly_to, _gx("duration"), f"{capture.fly_duration_s:.3f}")
        _text(fly_to, _gx("flyToMode"), "smooth")
        _add_camera(fly_to, state, capture)

        wait = ET.SubElement(playlist, _gx("Wait"))
        _text(wait, _gx("duration"), f"{capture.settle_seconds:.3f}")

        pause = ET.SubElement(playlist, _gx("TourControl"))
        _text(pause, _gx("playMode"), "pause")

    ET.indent(root, space="  ")
    return ET.ElementTree(root)

