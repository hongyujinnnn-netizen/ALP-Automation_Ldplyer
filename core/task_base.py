import random
import time
from abc import ABC, abstractmethod

FACEBOOK_PACKAGE = "com.facebook.katana"

# Import uiautomator2
try:
    import uiautomator2 as u2

    U2_AVAILABLE = True
except Exception:
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
        """Block while paused. Returns True if stop was requested during the wait."""
        while self.running_flag() and not self.pause_event.is_set():
            # Event.wait with timeout: instant wakeup on resume,
            # still notices running_flag flipping during pause.
            self.pause_event.wait(timeout=1.0)
        return not self.running_flag()

    def interruptible_sleep(self, seconds, poll=0.25):
        """Sleep up to `seconds` but break early on stop, and block while paused.

        Returns True if stop was requested during the wait (caller should bail out),
        False if the full duration elapsed normally.
        """
        if seconds <= 0:
            return not self.running_flag()
        deadline = time.time() + seconds
        while True:
            if not self.running_flag():
                return True
            if not self.pause_event.is_set():
                self.pause_event.wait(timeout=poll)
                deadline = time.time() + max(0.0, deadline - time.time())
                continue
            remaining = deadline - time.time()
            if remaining <= 0:
                return False
            time.sleep(min(poll, remaining))

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

    def connect_u2(self, serial):
        """Connect uiautomator2 to a device serial. Returns the Device or None."""
        if not U2_AVAILABLE:
            self.log("uiautomator2 not available")
            return None
        try:
            return u2.connect(serial)
        except Exception as exc:
            self.log(f"Failed to connect uiautomator2 to {serial}: {exc}")
            return None

    def open_facebook(self, d):
        """Launch Facebook on the connected device.

        Honors `facebook_start_delay_seconds` and uses interruptible_sleep so
        Stop/Pause stays responsive during the post-launch wait.
        """
        try:
            package = FACEBOOK_PACKAGE
            d.app_start(package)
            self.log("Facebook app opened")

            delay = max(0, int(getattr(self, "facebook_start_delay_seconds", 8)))
            wait_secs = random.uniform(delay, delay + 1.5) if delay > 0 else 0
            self.log(f"Waiting {wait_secs:.1f}s for Facebook UI to load")
            if self.interruptible_sleep(wait_secs):
                return False

            load_timeout = max(10, delay + 5)
            if d(packageName=package).wait(timeout=load_timeout):
                self.log("Facebook is running")
                return True
            self.log("Facebook app did not load in time")
            return False
        except Exception as exc:
            self.log(f"Failed to open Facebook: {exc}")
            return False

    def open_facebook_with_recovery(self, name, serial, max_retries=1):
        """Connect uiautomator2 and open Facebook, restarting LD on failure.

        On failure: stops Facebook, quits LD, waits, restarts LD, waits for
        device readiness, reconnects ADB (if `_ensure_adb_connection` is
        defined), reconnects uiautomator2, and retries `open_facebook`.

        Returns (success, d, serial). The serial may have changed after a
        restart; the old `d` object becomes stale, so callers should use the
        returned values.
        """
        attempt = 0
        while True:
            d = self.connect_u2(serial)
            if d is not None and self.open_facebook(d):
                return True, d, serial

            if attempt >= max_retries:
                return False, d, serial

            attempt += 1
            self.log(
                f"Recovering Facebook on {name} via LD restart "
                f"(attempt {attempt}/{max_retries})"
            )

            if d is not None:
                try:
                    d.app_stop(FACEBOOK_PACKAGE)
                except Exception:
                    pass

            try:
                if hasattr(self.emulator, "quit_ld"):
                    self.emulator.quit_ld(name)
            except Exception as exc:
                self.log(f"Failed to quit LD {name}: {exc}")

            if self.interruptible_sleep(5):
                return False, None, serial

            try:
                if not self.emulator.start_ld(name):
                    self.log(f"Failed to restart LD: {name}")
                    return False, None, serial
            except Exception as exc:
                self.log(f"Failed to start LD {name}: {exc}")
                return False, None, serial

            self.auto_arrange_ld_windows()

            boot_timeout = max(90, int(getattr(self.emulator, "boot_delay", 20)) * 6)
            if not self.ensure_device_ready(name, timeout=boot_timeout):
                self.log(f"Device not ready after restart: {name}")
                return False, None, serial

            serial = self.emulator.name_to_serial.get(name, serial)

            ensure_adb = getattr(self, "_ensure_adb_connection", None)
            if callable(ensure_adb):
                if not ensure_adb(serial):
                    self.log(f"Failed to reconnect ADB after restart for {name}")
                    return False, None, serial

    def auto_arrange_ld_windows(self):
        """Arrange LD windows when enabled in settings."""
        if not bool(getattr(self, "auto_arrange_ld", False)):
            return
        try:
            self.emulator.sort_window()
            self.log("Auto arranged LD windows")
        except Exception as exc:
            self.log(f"Failed to auto arrange LD windows: {exc}")
