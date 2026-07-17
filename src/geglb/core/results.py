from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PlanResult(Mapping[str, object]):
    """Typed result returned by capture-planning workflows.

    The mapping interface preserves the v0.x dictionary API while new code can use
    named fields. ``details`` is intentionally limited to backend-specific metadata;
    stable counts and artifacts have explicit fields.
    """

    workflow_id: str
    source_kind: str
    output_dir: str
    counts: Mapping[str, int] = field(default_factory=dict)
    artifacts: tuple[str, ...] = ()
    details: Mapping[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "mvp": self.workflow_id,
            "source_kind": self.source_kind,
            "output_dir": self.output_dir,
            **self.counts,
            **self.details,
        }
        if self.artifacts:
            result["artifacts"] = list(self.artifacts)
        return result

    def __getitem__(self, key: str) -> object:
        return self.as_dict()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.as_dict())

    def __len__(self) -> int:
        return len(self.as_dict())
