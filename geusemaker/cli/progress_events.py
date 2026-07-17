"""UI-neutral deployment progress contract."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol

Stage = Literal["validate", "vpc", "sg", "efs", "iam", "ec2", "spot", "userdata", "alb", "cdn", "health", "finalize"]
ProgressLevel = Literal["debug", "info", "warn", "error"]


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    stage: Stage
    message: str
    level: ProgressLevel = "info"
    resource_id: str | None = None
    ts: datetime = field(default_factory=lambda: datetime.now(UTC))


class ProgressCallback(Protocol):
    def __call__(self, event: ProgressEvent) -> None: ...


__all__ = ["ProgressCallback", "ProgressEvent", "ProgressLevel", "Stage"]
