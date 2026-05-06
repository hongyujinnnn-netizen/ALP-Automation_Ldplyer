import time
from dataclasses import dataclass

from core.task_base import U2_AVAILABLE, u2
from core.tasks.handler.handle_create_page import CreatePageHandlerMixin
from core.tasks.reg_account import RegAccountTaskHandler
from utils.ip_guard import check_ld_ip_allowed


@dataclass(slots=True)
class PageProfile:
    name: str
    category: str = ""
    bio: str = ""


class CreatePageTaskHandler(CreatePageHandlerMixin, RegAccountTaskHandler):
    """Create a Facebook Page on a logged-in LDPlayer instance."""

    def execute(self, name, duration=300, **kwargs):
        if self.check_paused():
            return False

        profile = self._build_page_profile(kwargs)
        if not profile:
            self.log(f"Create-page skipped for {name}: missing page name")
            return False

        if not self.emulator.is_ld_running(name):
            if not self.emulator.start_ld(name):
                self.log(f"Failed to start LD: {name}")
                return False
            self.auto_arrange_ld_windows()
            self.log(f"Waiting for emulator ready: {name}")
            boot_timeout = max(90, int(getattr(self.emulator, "boot_delay", 20)) * 6)
            if not self.ensure_device_ready(name, timeout=boot_timeout):
                self.log(f"Device not ready after startup: {name}")
                return False

        if not self.ensure_device_ready(name, timeout=60):
            self.log(f"Device is not ready for create-page task: {name}")
            return False

        serial = self.emulator.name_to_serial.get(name)
        if not serial:
            self.log(f"No serial found for {name}")
            return False

        if not self._ensure_adb_connection(serial):
            self.log(f"Failed to connect to device {serial}")
            return False

        blocked_countries = getattr(self, "blocked_countries", None)
        if blocked_countries and not check_ld_ip_allowed(serial, blocked_countries, self.log, ld_name=name):
            try:
                if hasattr(self.emulator, "quit_ld"):
                    self.emulator.quit_ld(name)
            except Exception:
                pass
            return False

        try:
            if not U2_AVAILABLE:
                self.log("uiautomator2 not available. Cannot run create-page task.")
                return False
            d = u2.connect(serial)
        except Exception as exc:
            self.log(f"Failed to connect {serial}: {exc}")
            return False

        self.push_runtime_state(name, state="Running", task="Opening Facebook", progress=15)
        if not self.open_facebook(d):
            self.log(f"Failed to open Facebook on {name}")
            return False

        time.sleep(4)

        self.push_runtime_state(name, state="Running", task="Navigating to Pages", progress=40)
        if not self._run_create_page_steps_with_retry(d, name, profile):
            return False

        self.push_runtime_state(name, state="Running", task="Confirming creation", progress=80)
        time.sleep(6)

        status = self._detect_create_page_status(d)
        self.log(f"Create-page status for {name}: {status}")

        if status == "Blocked":
            self.log(f"Page creation blocked for {name}")
            return False

        if status != "Created" and not self._confirm_page_created(d, timeout=20):
            self.log(f"Could not confirm page creation for {name}")
            return False

        self._save_created_page(name, serial, profile)
        self.log(f"Page '{profile.name}' created on {name}")
        self.push_runtime_state(name, state="Completed", task="Page created", progress=100)
        return True
