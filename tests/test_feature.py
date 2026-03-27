from core.task_base import BaseTaskHandler


class TestFeatureTaskHandler(BaseTaskHandler):
    """Simple test task: start one LD, wait until ready, and open Facebook."""

    def execute(self, name, duration=None, **kwargs):
        if self.check_paused():
            return False

        try:
            if not self.emulator.is_ld_running(name):
                self.log(f"LD is not running, starting: {name}")
                if not self.emulator.start_ld(name):
                    self.log(f"Failed to start LD: {name}")
                    return False
                self.auto_arrange_ld_windows()

            self.log(f"Waiting for LD ready: {name}")
            if not self.ensure_device_ready(
                name,
                timeout=max(90, int(getattr(self.emulator, "boot_delay", 20)) * 6),
            ):
                self.log(f"LD not ready for test feature: {name}")
                return False

            self.log(f"Opening Facebook on LD: {name}")
            if not self.emulator.open_facebook(name):
                self.log(f"Failed to open Facebook on LD: {name}")
                self.push_runtime_state(
                    name,
                    phase="task",
                    state="Attention",
                    task="Facebook open failed",
                    progress=0,
                )
                return False

            self.log(f"Facebook opened successfully on LD: {name}")
            self.push_runtime_state(
                name,
                phase="task",
                state="Completed",
                task="Facebook opened",
                progress=100,
            )
            return True
        except Exception as exc:
            self.log(f"Test feature failed on {name}: {exc}")
            return False
