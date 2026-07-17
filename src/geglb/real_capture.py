from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RealCaptureInput:
    """Vendor-neutral boundary for the future engineering adapter.

    The importer must convert device timestamps and calibration into the standard
    GE-GLB dataset. Stitching code must never depend on this class.
    """

    rig_json: Path
    trajectory_jsonl: Path
    image_root: Path
    timestamp_unit: str = "nanoseconds"


class RealCaptureNotImplementedError(NotImplementedError):
    pass


def import_real_capture(_source: RealCaptureInput, _output_dir: str | Path) -> None:
    raise RealCaptureNotImplementedError(
        "real capture is an engineering-stage adapter; implement timestamp synchronization "
        "and device calibration conversion without changing the dataset schema"
    )
