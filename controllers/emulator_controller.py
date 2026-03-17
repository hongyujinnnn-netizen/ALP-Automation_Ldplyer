from __future__ import annotations

from services.emulator_service import EmulatorService


class EmulatorController:
    """Controller for emulator-related UI coordination."""

    def __init__(self, emulator_service: EmulatorService) -> None:
        self.emulator_service = emulator_service

    def refresh_emulators(self) -> dict[str, str]:
        return self.emulator_service.refresh_mapping()

    def start_emulator(self, name: str, delay_between_starts: int = 10) -> bool:
        return self.emulator_service.start_ld(name, delay_between_starts=delay_between_starts)

    def stop_emulator(self, name: str) -> bool:
        return self.emulator_service.quit_ld(name)

    def is_running(self, name: str) -> bool:
        return self.emulator_service.is_ld_running(name)
