import time
from abc import ABC, abstractmethod

# Import uiautomator2
try:
    import uiautomator2 as u2
    U2_AVAILABLE = True
except Exception as e:
    u2 = None
    U2_AVAILABLE = False

class BaseTaskHandler(ABC):
    """Abstract base class for task handlers"""
    def __init__(self, emulator, log_func, pause_event, running_flag):
        self.emulator = emulator
        self.log = log_func
        self.pause_event = pause_event
        self.running_flag = running_flag
        self._last_runtime_state = {}
    
    @abstractmethod
    def execute(self, name, duration=None, **kwargs):
        pass
    
    def check_paused(self):
        """Check if operations should be paused - blocks if paused"""
        while not self.pause_event.is_set() and self.running_flag():
            time.sleep(0.5)
        return not self.running_flag()

    def push_runtime_state(self, name, **payload):
        callback = getattr(self, "state_callback", None)
        if not callable(callback):
            return

        previous_payload = self._last_runtime_state.get(name)
        self._last_runtime_state[name] = dict(payload)

        # Some UI updates are occasionally dropped when the background task
        # thread posts a single state update. Resend changed payloads once.
        attempts = 2 if previous_payload != payload else 1
        retry_delay = float(getattr(self, "runtime_state_retry_delay", 0.15) or 0.0)

        for attempt in range(attempts):
            try:
                callback(name, dict(payload))
            except Exception:
                if attempt == attempts - 1:
                    break
            if attempt < attempts - 1 and retry_delay > 0:
                time.sleep(retry_delay)

    def ensure_device_ready(self, name, timeout=120):
        """
        Wait for emulator/device readiness.
        Prefers emulator.wait_for_ld_ready when available.
        """
        wait_fn = getattr(self.emulator, "wait_for_ld_ready", None)
        if callable(wait_fn):
            try:
                return bool(wait_fn(name, timeout=timeout, poll_interval=2))
            except TypeError:
                # Backward compatibility if signature differs
                return bool(wait_fn(name))
            except Exception as exc:
                self.log(f"Readiness check failed for {name}: {exc}")
                return False

        # Fallback for older emulator implementations
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.emulator.is_ld_running(name):
                    return True
            except Exception:
                pass
            time.sleep(2)
        return False

    def _click_prompt_selector(self, d, selectors, timeout=2):
        deadline = time.time() + timeout
        while time.time() < deadline:
            for selector in selectors:
                try:
                    obj = d(**selector)
                    exists = obj.exists
                    if callable(exists):
                        exists = exists(timeout=0.5)
                    if exists:
                        obj.click()
                        return True
                except Exception:
                    continue
            time.sleep(0.3)
        return False

    def auto_arrange_ld_windows(self):
        """Arrange LD windows when enabled in settings."""
        if not bool(getattr(self, "auto_arrange_ld", False)):
            return
        try:
            self.emulator.sort_window()
            self.log("Auto arranged LD windows")
        except Exception as exc:
            self.log(f"Failed to auto arrange LD windows: {exc}")
