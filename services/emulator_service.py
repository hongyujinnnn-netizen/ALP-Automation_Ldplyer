from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Sequence

from core.emulator import ControlEmulator
from services.adb_service import ADBService


@dataclass(slots=True)
class EmulatorServiceConfig:
    ldplayer_dir: str = r"C:\LDPlayer\LDPlayer9"
    facebook_package: str = "com.facebook.katana"


class EmulatorService:
    """
    Service facade for emulator operations.

    This wraps the legacy ControlEmulator so the GUI and task orchestration can
    depend on a service boundary while behavior is migrated incrementally.
    """

    def __init__(
        self,
        config: EmulatorServiceConfig | None = None,
        adb_service: ADBService | None = None,
        emulator: ControlEmulator | None = None,
    ) -> None:
        self.config = config or EmulatorServiceConfig()
        self.adb_service = adb_service or ADBService()
        self._emulator = emulator or ControlEmulator(
            ld_dir=self.config.ldplayer_dir,
            fb_package=self.config.facebook_package,
        )

    @property
    def name_to_serial(self) -> dict[str, str]:
        return self._emulator.name_to_serial

    @property
    def boot_delay(self) -> int:
        return self._emulator.boot_delay

    @boot_delay.setter
    def boot_delay(self, value: int) -> None:
        self._emulator.boot_delay = value

    @property
    def task_duration(self) -> int:
        return self._emulator.task_duration

    @task_duration.setter
    def task_duration(self, value: int) -> None:
        self._emulator.task_duration = value

    def _build_serial_mapping(self) -> None:
        self._emulator._build_serial_mapping()

    def refresh_mapping(self) -> dict[str, str]:
        self._build_serial_mapping()
        return dict(self.name_to_serial)

    def start_ld(self, name: str, delay_between_starts: int = 10) -> bool:
        return self._emulator.start_ld(name, delay_between_starts=delay_between_starts)

    def quit_ld(self, name: str) -> bool:
        return self._emulator.quit_ld(name)

    def run_adb_command(self, command: str | Sequence[str], timeout: int = 15) -> str:
        return self.adb_service.run_text_command(command, timeout=timeout)

    def is_ld_running(self, name: str) -> bool:
        serial = self.name_to_serial.get(name)
        if not serial:
            return False

        if self.adb_service.is_serial_online(serial):
            return True

        if ":" in serial:
            port = serial.split(":", 1)[1]
            for line in self.adb_service.devices_output(timeout=5).splitlines():
                if port in line and "\tdevice" in line:
                    return True
        return False

    def wait_for_ld_ready(self, name: str, timeout: int = 120, poll_interval: int = 2) -> bool:
        serial = self.name_to_serial.get(name)
        if not serial:
            return False

        deadline = time.time() + timeout
        while time.time() < deadline:
            self.adb_service.connect(serial, timeout=10)

            if not self.adb_service.is_serial_online(serial, timeout=5):
                time.sleep(poll_interval)
                continue

            try:
                boot = self.adb_service.shell(
                    serial,
                    ["getprop", "sys.boot_completed"],
                    timeout=8,
                )
                if boot.returncode == 0 and (boot.stdout or "").strip() == "1":
                    return True
            except OSError:
                pass

            time.sleep(poll_interval)

        return False

    def open_facebook(self, name: str) -> bool:
        serial = self.name_to_serial.get(name)
        if not serial:
            return False

        self.adb_service.connect(serial, timeout=10)
        if not self.wait_for_ld_ready(name, timeout=90, poll_interval=2):
            return False

        primary = self.adb_service.shell(
            serial,
            [
                "am",
                "start",
                "-n",
                f"{self.config.facebook_package}/{self.config.facebook_package}.LoginActivity",
            ],
            timeout=15,
        )
        if primary.returncode == 0:
            return True

        fallback = self.adb_service.shell(
            serial,
            [
                "monkey",
                "-p",
                self.config.facebook_package,
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
            ],
            timeout=15,
        )
        return fallback.returncode == 0

    def cleanup_adb(self) -> None:
        self.adb_service.kill_server(timeout=10)

    def verify_adb(self) -> bool:
        return self.adb_service.verify_available(self.config.ldplayer_dir)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._emulator, name)
