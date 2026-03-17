from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class EmulatorInstance:
    name: str
    serial: str
    status: str = "Inactive"
    account: str = "No account"


@dataclass(slots=True)
class DeviceRuntimeState:
    state: str = "Idle"
    task: str = "Waiting for next run"
    progress: int = 0
    queue_label: str = "-"
    metadata: dict[str, str] = field(default_factory=dict)
