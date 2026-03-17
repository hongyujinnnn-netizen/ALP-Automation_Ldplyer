from __future__ import annotations

import os
import shlex
import subprocess
from typing import Sequence


class ADBService:
    """Centralized ADB command execution and parsing."""

    def __init__(self, adb_executable: str = "adb") -> None:
        self.adb_executable = adb_executable

    def normalize_command(self, command: str | Sequence[str]) -> list[str]:
        if isinstance(command, str):
            if not command.strip():
                raise ValueError("ADB command cannot be empty")
            cmd = shlex.split(command.strip(), posix=False)
        else:
            cmd = [str(part) for part in command if str(part).strip()]

        if not cmd:
            raise ValueError("ADB command cannot be empty")

        if cmd[0].lower() != self.adb_executable.lower():
            cmd.insert(0, self.adb_executable)

        return cmd

    def run(self, command: str | Sequence[str], timeout: int = 15) -> subprocess.CompletedProcess:
        return subprocess.run(
            self.normalize_command(command),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def run_text_command(self, command: str | Sequence[str], timeout: int = 15) -> str:
        result = self.run(command, timeout=timeout)
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()

        parts: list[str] = []
        if stdout:
            parts.append(stdout)
        if stderr:
            parts.append(stderr)
        if not parts:
            if result.returncode == 0:
                parts.append("(no output)")
            else:
                parts.append(f"Command failed with exit code {result.returncode}")

        return "\n".join(parts)

    def verify_available(self, ld_dir: str | None = None) -> bool:
        ld_adb_path = os.path.join(ld_dir, "adb.exe") if ld_dir else None
        if ld_dir and ld_adb_path and os.path.exists(ld_adb_path):
            os.environ["PATH"] = ld_dir + os.pathsep + os.environ["PATH"]

        try:
            result = self.run([self.adb_executable, "version"], timeout=10)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            if ld_adb_path and os.path.exists(ld_adb_path):
                try:
                    subprocess.run([ld_adb_path, "start-server"], timeout=10, check=False)
                    return True
                except OSError:
                    return False
            return False

    def devices_output(self, timeout: int = 10) -> str:
        result = self.run([self.adb_executable, "devices"], timeout=timeout)
        return result.stdout or ""

    def connect(self, serial: str, timeout: int = 10) -> bool:
        result = self.run([self.adb_executable, "connect", serial], timeout=timeout)
        output = f"{result.stdout or ''}\n{result.stderr or ''}".lower()
        return "connected" in output or "already connected" in output

    def is_serial_online(self, serial: str, timeout: int = 5) -> bool:
        for line in self.devices_output(timeout=timeout).splitlines():
            line = line.strip()
            if not line or line.startswith("List of devices"):
                continue
            if serial in line and "\tdevice" in line:
                return True
        return False

    def shell(self, serial: str, args: Sequence[str], timeout: int = 15) -> subprocess.CompletedProcess:
        return self.run([self.adb_executable, "-s", serial, "shell", *args], timeout=timeout)

    def kill_server(self, timeout: int = 10) -> bool:
        try:
            self.run([self.adb_executable, "kill-server"], timeout=timeout)
            return True
        except OSError:
            return False
