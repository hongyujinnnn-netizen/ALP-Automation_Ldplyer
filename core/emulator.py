import ctypes
import os
import shlex
import subprocess
import time


# ==================== LOCAL IMPORTS ====================
# Define our own LDPlayer class for compatibility
class LDPlayer:
    def __init__(self, ld_dir):
        self.ld_dir = ld_dir
        self.emulators = {}
        print(f"LDPlayer initialized with directory: {ld_dir}")

    def sort_window(self):
        print("LDPlayer: sort_window called")
        # Your implementation here


# New: import uiautomator2 (optional fallback if not installed)
try:
    import uiautomator2 as u2

    U2_AVAILABLE = True
except Exception as e:
    u2 = None
    U2_AVAILABLE = False
    print("uiautomator2 not available:", e)


class SimpleLDPlayer:
    def __init__(self, ld_path="C:\\LDPlayer\\LDPlayer9"):
        self.ld_path = ld_path
        self.console_path = os.path.join(ld_path, "dnconsole.exe")

    def list_emulators(self):
        try:
            result = subprocess.run([self.console_path, "list2"], capture_output=True, text=True, timeout=10)
            print("Console output:", result.stdout)
            return result.stdout
        except subprocess.TimeoutExpired:
            print("dnconsole list2 timed out after 10s")
            return None
        except Exception as e:
            error_str = str(e)
            if "740" in error_str or "elevation" in error_str.lower():
                print("LDPlayer console requires administrator privileges.")
            else:
                print(f"Error: {e}")
            return None


# ==================== EMULATOR CONTROL ====================
class ControlEmulator:
    def __init__(self, ld_dir=r"C:\LDPlayer\LDPlayer9", fb_package="com.facebook.katana"):
        # Use raw string for Windows paths
        self.ld_dir = ld_dir

        # Create proper emulator mapping without external module
        self.em = {}
        self.name_to_serial = {}
        self.boot_delay = 20
        self.task_duration = 900
        self.fb = fb_package

        # Try to detect actual LDPlayer emulators
        self._detect_emulators()
        self._verify_adb()

    def _detect_emulators(self):
        """Try to detect actual LDPlayer instances"""
        try:
            # Try using dnconsole.exe to list emulators
            dnconsole_path = os.path.join(self.ld_dir, "dnconsole.exe")
            if os.path.exists(dnconsole_path):
                result = subprocess.run(
                    [dnconsole_path, "list2"], capture_output=True, text=True, encoding="utf-8", timeout=10
                )

                if result.returncode == 0:
                    # Parse the output
                    lines = result.stdout.strip().split("\n")
                    print(f"Console output lines: {len(lines)}")

                    for line in lines:
                        if line.strip():
                            parts = line.split(",")
                            print(f"Parsing line: {line}, parts: {parts}")

                            if len(parts) >= 2:
                                # The format appears to be: index,name,...
                                emu_index = parts[0].strip()
                                emu_name = parts[1].strip()

                                try:
                                    index_num = int(emu_index)
                                    port = 5554 + (index_num * 2)
                                    serial = f"emulator-{port}"
                                except:
                                    serial = f"emulator-5554"

                                # Create emulator object
                                emu_obj = type(
                                    "obj", (object,), {"name": emu_name, "index": emu_index, "serial": serial}
                                )()

                                self.em[emu_name] = emu_obj
                                self.name_to_serial[emu_name] = serial
                                print(f"Found emulator: '{emu_name}' -> {serial}")

                    if self.em:
                        print(f"Total emulators found: {len(self.em)}")
                        return
                    else:
                        print("No emulators parsed from output")

        except Exception as e:
            error_str = str(e)
            if "740" in error_str or "elevation" in error_str.lower():
                print("LDPlayer console requires administrator privileges. Using test emulators instead.")
            else:
                print(f"Error detecting emulators via dnconsole: {e}")

        # Fallback: create test emulators if none found
        if not self.em:
            self._create_test_emulators()

    def _create_test_emulators(self):
        """Create test emulators for development"""
        # Based on your console output
        test_emulators = ["US - clone", "US - 01", "US - 02", "US - 03", "US - 04", "US - 05"]
        for i, name in enumerate(test_emulators):
            port = 5555 + (i * 2)
            serial = f"127.0.0.1:{port}"

            emu_obj = type("obj", (object,), {"name": name, "index": i, "serial": serial})()

            self.em[name] = emu_obj
            self.name_to_serial[name] = serial

    def _build_serial_mapping(self):
        """Build or refresh the serial mapping for emulators"""
        if not self.em:
            self._detect_emulators()

    def _verify_adb(self):
        """Verify ADB is available and working"""
        # First, check if ADB is in LDPlayer directory
        ld_adb_path = os.path.join(self.ld_dir, "adb.exe")

        if os.path.exists(ld_adb_path):
            # Add LDPlayer directory to PATH temporarily
            os.environ["PATH"] = self.ld_dir + os.pathsep + os.environ["PATH"]
            print(f"Added LDPlayer ADB to PATH: {self.ld_dir}")

        try:
            # Test ADB
            result = subprocess.run(["adb", "version"], capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                print(f"ADB is working: {result.stdout.splitlines()[0]}")
                return True
            else:
                print("ADB command failed")
                return False

        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            print(f"ADB verification failed: {e}")

            # Try to start ADB server
            try:
                if os.path.exists(ld_adb_path):
                    subprocess.run([ld_adb_path, "start-server"], timeout=10)
                    print("Started ADB server")
                    return True
            except Exception as e2:
                print(f"Failed to start ADB server: {e2}")

            return False

    def sort_window(self):
        """Arrange visible LDPlayer windows without changing their current size."""
        if os.name != "nt":
            print("Window arrangement is only supported on Windows")
            return False

        user32 = ctypes.windll.user32
        current_pid = os.getpid()

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        work_area = RECT()
        SPI_GETWORKAREA = 0x0030
        if not user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(work_area), 0):
            work_area.left = 0
            work_area.top = 0
            work_area.right = user32.GetSystemMetrics(0)
            work_area.bottom = user32.GetSystemMetrics(1)

        known_names = sorted(self.name_to_serial.keys(), key=len, reverse=True)
        matched = []
        seen = set()

        def _window_text(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return ""
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            return buffer.value.strip()

        def _class_name(hwnd):
            buffer = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, buffer, 256)
            return buffer.value.strip()

        def _window_rect(hwnd):
            rect = RECT()
            if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return rect
            return None

        def _window_pid(hwnd):
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            return int(pid.value)

        def _is_ld_window(title, class_name):
            title_l = title.lower()
            class_l = class_name.lower()
            if any(name.lower() in title_l for name in known_names):
                return True
            if "ldplayer" in title_l or "dnplayer" in title_l:
                return True
            if "ldplayer" in class_l or "dnplayer" in class_l:
                return True
            return False

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def enum_proc(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                return True

            # Skip this manager app and any dialogs it owns. We only want
            # actual LDPlayer emulator windows to move.
            if _window_pid(hwnd) == current_pid:
                return True

            title = _window_text(hwnd)
            if not title:
                return True

            class_name = _class_name(hwnd)
            if not _is_ld_window(title, class_name):
                return True

            if hwnd not in seen:
                matched.append((hwnd, title))
                seen.add(hwnd)
            return True

        user32.EnumWindows(enum_proc, 0)

        if not matched:
            print("No visible LDPlayer windows found to arrange")
            return False

        matched.sort(key=lambda item: item[1].lower())
        count = len(matched)
        margin_x = 12
        margin_y = 12
        gap_x = 10
        gap_y = 10
        usable_width = max(200, work_area.right - work_area.left - (margin_x * 2))
        usable_height = max(200, work_area.bottom - work_area.top - (margin_y * 2))

        SWP_NOZORDER = 0x0004
        SWP_NOACTIVATE = 0x0010
        SW_RESTORE = 9

        placements = []
        x = work_area.left + margin_x
        y = work_area.top + margin_y
        row_height = 0

        for hwnd, title in matched:
            rect = _window_rect(hwnd)
            if rect:
                width = max(1, rect.right - rect.left)
                height = max(1, rect.bottom - rect.top)
            else:
                width = min(420, usable_width)
                height = min(760, usable_height)

            if x > work_area.left + margin_x and x + width > work_area.left + margin_x + usable_width:
                x = work_area.left + margin_x
                y += row_height + gap_y
                row_height = 0

            if y > work_area.top + margin_y and y + height > work_area.top + margin_y + usable_height:
                y = work_area.top + margin_y

            placements.append((hwnd, title, x, y, width, height))
            x += width + gap_x
            row_height = max(row_height, height)

        for hwnd, title, x, y, width, height in placements:
            try:
                user32.ShowWindow(hwnd, SW_RESTORE)
                user32.SetWindowPos(hwnd, 0, x, y, width, height, SWP_NOZORDER | SWP_NOACTIVATE)
            except Exception as exc:
                print(f"Failed to move window '{title}': {exc}")

        print(f"Arranged {count} LDPlayer window(s)")
        return True

    def list_emulators(self):
        """List all detected emulators"""
        print(f"Total emulators: {len(self.em)}")
        for name, emu in self.em.items():
            serial = self.name_to_serial.get(name, "N/A")
            status = "Active" if self.is_ld_running(name) else "Inactive"
            print(f"  '{name}': {serial} ({status})")

    def is_ld_running(self, name):
        """Check if LDPlayer is running"""
        serial = self.name_to_serial.get(name)
        if not serial:
            print(f"No serial found for '{name}'")
            return False

        try:
            result = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=5)

            # Check if serial is in the output and marked as device
            for line in result.stdout.split("\n"):
                if serial in line and "device" in line:
                    return True

            # Also try without the "127.0.0.1:" prefix
            if ":" in serial:
                port = serial.split(":")[1]
                for line in result.stdout.split("\n"):
                    if port in line and "device" in line:
                        return True

        except Exception as e:
            print(f"Error checking if LD is running: {e}")

        return False

    def start_ld(self, name, delay_between_starts=10):
        """Start an LDPlayer instance"""
        try:
            dnconsole_path = os.path.join(self.ld_dir, "dnconsole.exe")

            if os.path.exists(dnconsole_path):
                # Use dnconsole to launch
                print(f"Starting LD: '{name}'")
                result = subprocess.run(
                    [dnconsole_path, "launch", "--name", name],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=30,
                )

                if result.returncode == 0:
                    print(f"LD '{name}' started successfully")
                    time.sleep(delay_between_starts)

                    # Try to connect via ADB
                    serial = self.name_to_serial.get(name)
                    if serial:
                        self._connect_adb(serial)

                    return True
                else:
                    print(f"Failed to start LD '{name}': {result.stderr}")
                    return False
            else:
                print(f"dnconsole.exe not found at {dnconsole_path}")
                # Simulate start for testing
                print(f"LD '{name}' started (simulated)")
                time.sleep(5)
                return True

        except Exception as e:
            print(f"Error starting LD '{name}': {e}")
            return False

    def _connect_adb(self, serial):
        """Connect to device via ADB"""
        try:
            result = subprocess.run(["adb", "connect", serial], capture_output=True, text=True, timeout=10)
            print(f"ADB connect result: {result.stdout}")
            return "connected" in result.stdout.lower()
        except Exception as e:
            print(f"Error connecting ADB: {e}")
            return False

    def _is_serial_online(self, serial):
        """Check whether a serial appears as an online adb device."""
        try:
            result = subprocess.run(
                ["adb", "devices"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception:
            return False

        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("List of devices"):
                continue
            if serial in line and "\tdevice" in line:
                return True
        return False

    def wait_for_ld_ready(self, name, timeout=120, poll_interval=2):
        """
        Wait until LD is adb-online and Android reports boot completed.
        Returns True when ready, False on timeout/failure.
        """
        serial = self.name_to_serial.get(name)
        if not serial:
            print(f"No serial found for '{name}'")
            return False

        deadline = time.time() + timeout
        while time.time() < deadline:
            self._connect_adb(serial)

            if not self._is_serial_online(serial):
                time.sleep(poll_interval)
                continue

            try:
                boot = subprocess.run(
                    ["adb", "-s", serial, "shell", "getprop", "sys.boot_completed"],
                    capture_output=True,
                    text=True,
                    timeout=8,
                )
                if boot.returncode == 0 and boot.stdout.strip() == "1":
                    return True
            except Exception:
                pass

            time.sleep(poll_interval)

        print(f"Timeout waiting for LD '{name}' to be ready")
        return False

    def quit_ld(self, name):
        """Quit an LDPlayer instance.

        Returns True only when dnconsole reports success (or when the binary
        is absent and we're running in simulated mode). A non-zero exit from
        dnconsole — typically "instance not found" after a rename — is a
        real failure and must surface, otherwise callers will mark the LD as
        idle while the process is still running.
        """
        try:
            dnconsole_path = os.path.join(self.ld_dir, "dnconsole.exe")

            if not os.path.exists(dnconsole_path):
                print(f"LD '{name}' quit (simulated)")
                return True

            result = subprocess.run(
                [dnconsole_path, "quit", "--name", name],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=10,
            )

            if result.returncode == 0:
                print(f"LD '{name}' quit successfully")
                return True

            print(f"Failed to quit LD '{name}': {(result.stderr or result.stdout or '').strip()}")
            return False
        except Exception as e:
            print(f"Error quitting LD '{name}': {e}")
            return False

    def rename_ld(self, old_name, new_name):
        """Rename an LDPlayer instance via dnconsole.

        Returns True on success. Updates ``name_to_serial`` so existing
        serial lookups continue to work after the rename.
        """
        if not new_name or old_name == new_name:
            return False
        try:
            dnconsole_path = os.path.join(self.ld_dir, "dnconsole.exe")
            if not os.path.exists(dnconsole_path):
                print(f"dnconsole.exe not found; cannot rename LD '{old_name}'")
                return False

            result = subprocess.run(
                [dnconsole_path, "rename", "--name", old_name, "--title", new_name],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=10,
            )
            if result.returncode != 0:
                print(f"Failed to rename LD '{old_name}' -> '{new_name}': {result.stderr}")
                return False

            # Migrate the serial mapping so callers can keep using the new name.
            serial = self.name_to_serial.pop(old_name, None)
            if serial is not None:
                self.name_to_serial[new_name] = serial
            print(f"LD '{old_name}' renamed to '{new_name}'")
            return True
        except Exception as e:
            print(f"Error renaming LD '{old_name}' -> '{new_name}': {e}")
            return False

    def diagnose_ld(self, name):
        """Return any VBox-log wedging signals for this LD (read-only)."""
        from core.ld_recovery import diagnose

        return diagnose(self, name)

    def recover_ld(self, name, *, attempts=2, log=None, boot_timeout=120):
        """Best-effort recovery for a wedged LDPlayer instance.

        Quits the LD, force-kills orphan VBox/dnplayer processes that match
        its leidian index, then relaunches and waits for ADB-ready. Returns
        a ``RecoveryResult`` (truthy on success).
        """
        from core.ld_recovery import recover_instance

        return recover_instance(self, name, attempts=attempts, log=log, boot_timeout=boot_timeout)

    def _instance_index(self, name):
        """Return the LDPlayer index for a given instance name, or None."""
        emu = self.em.get(name) if hasattr(self, "em") else None
        index = getattr(emu, "index", None)
        if index is None:
            return None
        try:
            return int(index)
        except (TypeError, ValueError):
            return None

    def _instance_config_path(self, name):
        """Resolve <ld_dir>/vms/config/leidian{index}.config for this LD."""
        index = self._instance_index(name)
        if index is None:
            return None
        return os.path.join(self.ld_dir, "vms", "config", f"leidian{index}.config")

    def set_shared_folder(self, name, folder_path):
        """Set the LDPlayer instance's shared host folder.

        LDPlayer 9 stores share paths in the per-instance config file
        ``vms/config/leidian{index}.config`` under three concrete keys:
        ``statusSettings.sharedMisc`` (generic "Other"),
        ``statusSettings.sharedPictures``, and
        ``statusSettings.sharedApplications`` (APK drop). There is no
        enable flag on LD9 — setting the path is sufficient. We point all
        three at the chosen folder.

        Side effects:
            * Creates ``folder_path`` on disk if missing.
            * Writes a ``.bak`` snapshot of the config before mutating it.
            * Stores the path with forward slashes (``D:/Foo``) — LDPlayer's
              config parser accepts it more reliably than escaped backslashes.

        Returns True only when the JSON config was successfully rewritten.
        Caller should stop the LD before calling — LDPlayer rewrites the
        config on graceful shutdown, clobbering edits made while running.
        """
        import json
        import shutil

        if not name or not folder_path:
            return False

        # LD config files render Windows paths most reliably with forward
        # slashes; keep a native variant for the host-side mkdir / ldconsole.
        folder_native = os.path.normpath(folder_path)
        folder_for_config = folder_native.replace("\\", "/")

        # 1) Make sure the host folder exists — LD silently refuses to mount
        # a missing path on next boot.
        try:
            os.makedirs(folder_native, exist_ok=True)
        except Exception as exc:
            print(f"Could not create shared folder '{folder_native}': {exc}")
            return False

        # 2) Warn (don't refuse) if the LD is still running. LDPlayer rewrites
        # the per-instance config from memory at shutdown, so anything we
        # write now will be overwritten unless the caller stops it.
        try:
            if self.is_ld_running(name):
                print(
                    f"WARNING: LD '{name}' is running — its config will be "
                    "overwritten on shutdown. Stop the instance before "
                    "applying the shared folder."
                )
        except Exception:
            pass

        # 3) Authoritative path: edit the per-instance config JSON.
        config_path = self._instance_config_path(name)
        if not config_path:
            print(f"Cannot resolve LD index for '{name}'; aborting shared folder change")
            return False
        if not os.path.exists(config_path):
            print(f"Per-instance config not found: {config_path}")
            return False

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as exc:
            print(f"Failed to read {config_path}: {exc}")
            return False
        if not isinstance(cfg, dict):
            print(f"Unexpected config shape in {config_path}; expected a JSON object")
            return False

        # Backup before mutating — keeps a one-step rollback handy.
        try:
            shutil.copy2(config_path, config_path + ".bak")
        except Exception as exc:
            print(f"Backup failed for {config_path}: {exc}")

        # LDPlayer 9 exposes three concrete share targets — no enable flag.
        # Point all three at the chosen folder so it surfaces in Android
        # under "Other", "Picture", and as the APK install drop.
        shared_keys = (
            "statusSettings.sharedMisc",
            "statusSettings.sharedPictures",
            "statusSettings.sharedApplications",
        )
        for key in shared_keys:
            cfg[key] = folder_for_config

        try:
            tmp_path = config_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=4)
            os.replace(tmp_path, config_path)
        except Exception as exc:
            print(f"Failed to write {config_path}: {exc}")
            return False

        print(
            f"Shared folder for LD '{name}' written to {config_path} "
            f"(keys: {', '.join(shared_keys)}) → '{folder_for_config}'"
        )

        return True

    def get_shared_folder(self, name):
        """Return the host path stored in ``statusSettings.sharedMisc`` for
        this LD instance, or ``None`` if it cannot be resolved.

        Never raises — any failure (unknown instance, missing config, parse
        error, empty value) yields ``None`` so callers can treat "no shared
        folder configured" uniformly.
        """
        import json

        if not name:
            return None
        try:
            config_path = self._instance_config_path(name)
            if not config_path or not os.path.exists(config_path):
                return None
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if not isinstance(cfg, dict):
                return None
            value = cfg.get("statusSettings.sharedMisc")
            if not value or not isinstance(value, str):
                return None
            return os.path.normpath(value)
        except Exception:
            return None

    def remove_ld(self, name):
        """Delete an LDPlayer instance via dnconsole.

        Returns True on success. Cleans up ``name_to_serial`` so stale serial
        lookups don't linger after deletion.
        """
        if not name:
            return False
        try:
            dnconsole_path = os.path.join(self.ld_dir, "dnconsole.exe")
            if not os.path.exists(dnconsole_path):
                print(f"dnconsole.exe not found; cannot remove LD '{name}'")
                return False

            result = subprocess.run(
                [dnconsole_path, "remove", "--name", name],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=15,
            )
            if result.returncode != 0:
                print(f"Failed to remove LD '{name}': {result.stderr}")
                return False

            self.name_to_serial.pop(name, None)
            print(f"LD '{name}' removed")
            return True
        except Exception as e:
            print(f"Error removing LD '{name}': {e}")
            return False

    def open_facebook(self, name):
        """Open Facebook on the specified LDPlayer"""
        serial = self.name_to_serial.get(name)
        if not serial:
            print(f"No serial found for '{name}'")
            return False

        # Ensure ADB is connected
        self._connect_adb(serial)
        if not self.wait_for_ld_ready(name, timeout=90, poll_interval=2):
            print(f"LD '{name}' is not ready yet; skip opening Facebook")
            return False

        try:
            # First, try to start Facebook via package name
            result = subprocess.run(
                [
                    "adb",
                    "-s",
                    serial,
                    "shell",
                    "am",
                    "start",
                    "-n",
                    "com.facebook.katana/com.facebook.katana.LoginActivity",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )

            if result.returncode == 0:
                print(f"Facebook app launched on LD '{name}'")
                return True
            else:
                print(f"Failed to launch Facebook via activity: {result.stderr}")

                # Fallback: use monkey command
                result = subprocess.run(
                    [
                        "adb",
                        "-s",
                        serial,
                        "shell",
                        "monkey",
                        "-p",
                        "com.facebook.katana",
                        "-c",
                        "android.intent.category.LAUNCHER",
                        "1",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )

                if result.returncode == 0:
                    print(f"Facebook app launched on LD '{name}' (fallback)")
                    return True
                else:
                    print(f"Failed to launch Facebook on LD '{name}': {result.stderr}")
                    return False

        except subprocess.TimeoutExpired:
            print(f"Timeout launching Facebook on LD '{name}'")
            return False
        except Exception as e:
            print(f"Error launching Facebook on LD '{name}': {e}")
            return False

    def cleanup_adb(self):
        """Clean up ADB connections when done"""
        try:
            subprocess.run(["adb", "kill-server"], timeout=10)
            print("ADB server killed")
        except Exception as e:
            print(f"Error killing ADB server: {e}")

    def run_adb_command(self, command, timeout=15):
        """Run an adb command for the tools console and return combined output."""
        if not isinstance(command, str) or not command.strip():
            raise ValueError("ADB command cannot be empty")

        cmd = shlex.split(command.strip(), posix=False)
        if not cmd:
            raise ValueError("ADB command cannot be empty")

        if cmd[0].lower() != "adb":
            cmd.insert(0, "adb")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()

        parts = []
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

    def set_boot_delay(self, delay):
        """Set boot delay for emulator startup"""
        self.boot_delay = delay

    def set_task_duration(self, duration):
        """Set task duration in minutes"""
        self.task_duration = duration * 60  # Convert to seconds
