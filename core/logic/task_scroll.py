import os
import random
import re
import subprocess
import time

from core.task_base import BaseTaskHandler, U2_AVAILABLE, u2
from utils.ip_guard import check_ld_ip_allowed

class ScrollTaskHandler(BaseTaskHandler):
    """Handler for Facebook scrolling tasks"""
    def _restart_scroll_task(self, name, serial, remaining_duration, direction, intensity, restart_attempts):
        """Restart LD and resume the scroll task with the remaining duration."""
        try:
            if hasattr(self.emulator, "quit_ld"):
                self.log(f"Restarting LD for scroll task on {name}")
                self.emulator.quit_ld(name)
                time.sleep(5)
        except Exception as e:
            self.log(f"Failed to quit LD {name}: {e}")
            return False

        if not self.emulator.start_ld(name):
            self.log(f"Failed to restart LD: {name}")
            return False
        self.auto_arrange_ld_windows()

        self.log(f"Waiting for emulator ready after restart: {name}")
        if not self.ensure_device_ready(name, timeout=max(90, int(getattr(self.emulator, 'boot_delay', 20)) * 6)):
            self.log(f"Device not ready after restart: {name}")
            return False

        serial = self.emulator.name_to_serial.get(name, serial)

        if not self._ensure_adb_connection(serial):
            self.log(f"Failed to reconnect ADB after restart for {name}")
            return False

        return self.execute(
            name,
            duration=max(1, int(remaining_duration)),
            direction=direction,
            intensity=intensity,
            restart_attempts=restart_attempts + 1,
        )

    def execute(self, name, duration=900, direction="down", intensity="medium", restart_attempts=0):
        """
        Execute smooth scrolling on the specified device.
        
        Args:
            name (str): Device identifier
            duration (int): Total scrolling duration in seconds (default: 900)
            direction (str): Scroll direction - "down", "up", or "random" (default: "down")
            intensity (str): Scroll intensity - "light", "medium", or "heavy" (default: "medium")
        
        Returns:
            bool: True if successful, False otherwise
        """
        if self.check_paused():
            return False
            
        # Get device serial
        serial = self.emulator.name_to_serial.get(name, name)
        if not serial:
            self.log(f"No serial found for {name}")
            return False

        # Ensure we're connected to the device with retry logic
        if not self._ensure_adb_connection(serial):
            self.log(f"Failed to connect to device {serial}")
            return False
        
        # Start LD if not running
        if not self.emulator.is_ld_running(name):
            if not self.emulator.start_ld(name):
                self.log(f"âŒ Failed to start LD: {name}")
                return False
            self.auto_arrange_ld_windows()
            self.log(f"Waiting for emulator ready: {name}")
            if not self.ensure_device_ready(name, timeout=max(90, int(getattr(self.emulator, 'boot_delay', 20)) * 6)):
                self.log(f"Device not ready after startup: {name}")
                return False

        if not self.ensure_device_ready(name, timeout=60):
            self.log(f"Device is not ready for automation: {name}")
            return False

        # Per-LD IP / country guard: query public IP from inside the emulator
        # so that per-instance VPN / proxy settings are respected.
        blocked_countries = getattr(self, "blocked_countries", None)
        if blocked_countries:
            if not check_ld_ip_allowed(serial, blocked_countries, self.log, ld_name=name):
                # Optionally close the LD instance when blocked, to avoid
                # leaving a leaking session running.
                try:
                    if hasattr(self.emulator, "quit_ld"):
                        self.emulator.quit_ld(name)
                except Exception:
                    pass
                return False

        # Connect with uiautomator2 for profile switching
        try:
            if not U2_AVAILABLE:
                self.log("âŒ uiautomator2 not available. Cannot switch profile.")
                return False
            d = u2.connect(serial)
        except Exception as e:
            self.log(f"âŒ Failed to connect {serial}: {e}")
            return False

        self.log(f"Opening Facebook after IP check: {name}")
        if not self.open_facebook(d):
            self.log(f"Failed to open Facebook before scrolling: {name}")
            return False
        self.log(f"Running scroll task on LD: {name}")

        # Configure scroll parameters based on intensity.
        # Durations are in milliseconds for the ADB swipe command.
        intensity_params = {
            "light": {
                "duration_range": (550, 800),   # slightly slower, longer swipes
                "delay_range": (1.8, 3.0),
            },
            "medium": {
                "duration_range": (450, 700),
                "delay_range": (1.4, 2.4),
            },
            "heavy": {
                "duration_range": (380, 600),   # faster but still non-robotic
                "delay_range": (1.0, 2.0),
            },
        }

        params = intensity_params.get(intensity, intensity_params["medium"])
        
        # Let Facebook/feed settle before issuing swipe commands
        settle_delay = random.uniform(5, 10)
        self.log(f"Waiting {settle_delay:.1f}s before starting scrolls")
        time.sleep(settle_delay)

        start_time = time.time()
        successful_swipes = 0
        failed_swipes = 0
        consecutive_failures = 0
        consecutive_timeouts = 0
        max_timeout_restarts = 1
        
        try:
            while time.time() - start_time < duration:
                if self.check_paused():
                    self.log(f"Scrolling paused on {name} after {successful_swipes} successful swipes")
                    return False
                
                # Determine scroll direction.
                # Even when direction is "down", add a small probability of brief
                # reverse scrolls to mimic human corrections.
                if direction == "random":
                    current_direction = "down" if random.random() > 0.5 else "up"
                else:
                    current_direction = direction
                    if current_direction == "down" and random.random() < 0.12:
                        current_direction = "up"
                    elif current_direction == "up" and random.random() < 0.12:
                        current_direction = "down"
                
                # Generate swipe parameters based on direction and intensity.
                scroll_duration = random.uniform(*params["duration_range"])

                # Vary the scroll "distance" so some swipes are short nudges and
                # others are longer feed jumps.
                long_scroll_chance = 0.25
                if random.random() < long_scroll_chance:
                    vertical_span = (260, 720)
                else:
                    vertical_span = (320, 560)

                if current_direction == "down":
                    start_y = random.randint(760, 920)
                    end_y = start_y - random.randint(*vertical_span)
                else:  # up direction
                    start_y = random.randint(320, 520)
                    end_y = start_y + random.randint(*vertical_span)

                # Add slight horizontal variation and occasional micro-jitter for
                # more natural movement instead of a perfectly straight line.
                base_x = random.randint(270, 330)
                jitter = random.randint(-8, 8)
                x_pos = base_x + jitter
                
                # Respect optional rate limiter if present (EnhancedScrollTaskHandler and similar).
                limiter = getattr(self, "rate_limiter", None)
                if limiter is not None:
                    if not limiter.can_perform_action("scroll_swipe"):
                        wait_for = max(0.0, limiter.get_wait_time())
                        if wait_for > 0:
                            self.log(f"Rate limit reached for {name}; backing off for {wait_for:.1f}s")
                            # Sleep in the worker thread, does not block Tkinter UI.
                            time.sleep(min(wait_for, 60.0))

                # Execute the swipe command
                try:
                    result = subprocess.run([
                        "adb", "-s", serial,
                        "shell", "input", "swipe", 
                        str(x_pos), str(start_y), 
                        str(x_pos), str(end_y), 
                        str(int(scroll_duration))
                    ], capture_output=True, text=True, timeout=10)
                    
                    if result.returncode == 0:
                        successful_swipes += 1
                        consecutive_failures = 0
                        consecutive_timeouts = 0
                    else:
                        failed_swipes += 1
                        consecutive_failures += 1
                        consecutive_timeouts = 0
                        self.log(f"ADB command failed: {result.stderr}")
                        
                        # If too many consecutive failures, try to reconnect
                        if consecutive_failures >= 3:
                            self.log("Too many failures, attempting to reconnect...")
                            if not self._ensure_adb_connection(serial):
                                self.log("Reconnection failed, aborting")
                                return False
                            consecutive_failures = 0
                            
                except subprocess.TimeoutExpired:
                    failed_swipes += 1
                    consecutive_failures += 1
                    consecutive_timeouts += 1
                    self.log(f"ADB command timed out for {name}")

                    if consecutive_timeouts >= 5:
                        if restart_attempts >= max_timeout_restarts:
                            self.log(f"ADB command timed out for {name} 5 times after restart; aborting")
                            return False

                        remaining_duration = duration - (time.time() - start_time)
                        self.log(f"ADB command timed out for {name} 5 times. Restarting LD and resuming scroll task")
                        return self._restart_scroll_task(
                            name,
                            serial,
                            remaining_duration,
                            direction,
                            intensity,
                            restart_attempts,
                        )

                    if consecutive_failures >= 3:
                        self.log("Too many timeouts, attempting to reconnect...")
                        if not self._ensure_adb_connection(serial):
                            self.log("Reconnection failed, aborting")
                            return False
                        consecutive_failures = 0
                
                # Vary the delay between swipes for more human-like behavior.
                base_delay = random.uniform(*params["delay_range"])

                # If an ActivityRandomizer is attached (EnhancedScrollTaskHandler), use it for jitter.
                randomizer = getattr(self, "randomizer", None)
                if randomizer is not None:
                    delay = max(0.1, randomizer.random_delay(base_delay, variation=0.35))
                else:
                    delay = base_delay

                # Add occasional longer pauses to mimic "reading" or watching a reel.
                if successful_swipes > 0 and successful_swipes % 4 == 0 and random.random() < 0.7:
                    delay += random.uniform(1.2, 3.0)

                # Occasionally introduce a micro-pause as if hesitating.
                if random.random() < 0.15:
                    delay += random.uniform(0.15, 0.45)

                time.sleep(delay)
                
            self.log(f"Completed scrolling on {name}: {successful_swipes} successful, {failed_swipes} failed swipes")
            return True
            
        except Exception as e:
            self.log(f"Unexpected error scrolling on {name}: {str(e)}")
            return False

    def _ensure_adb_connection(self, serial, max_retries=3):
        """Ensure ADB connection to the device with retry logic"""
        for attempt in range(max_retries):
            try:
                # First check if device is already connected
                result = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=10)
                if serial in result.stdout and "device" in result.stdout:
                    self.log(f"ADB device {serial} is already connected")
                    return True
                
                # Try to connect
                self.log(f"Attempting to connect to {serial} (attempt {attempt + 1}/{max_retries})")
                result = subprocess.run(["adb", "connect", serial], capture_output=True, text=True, timeout=10)
                
                if "connected to" in result.stdout.lower() or "already connected" in result.stdout.lower():
                    self.log(f"Successfully connected to {serial}")
                    return True
                else:
                    self.log(f"Connection attempt failed: {result.stdout.strip()}")
                    
                time.sleep(2)  # Wait before retry
                
            except subprocess.TimeoutExpired:
                self.log(f"ADB connection timeout for {serial}")
            except Exception as e:
                self.log(f"Error connecting to {serial}: {str(e)}")
                
        return False

    def open_facebook(self, d, ready_delay_range=(5, 10)):
        try:
            package = "com.facebook.katana"  # Main Facebook package name
            activity = "com.facebook.katana.LoginActivity"

            # Try launching Facebook
            d.app_start(package)
            self.log("Facebook app opened")

            # Give the app time to finish initial loading so UI is stable
            wait_secs = random.uniform(*ready_delay_range)
            self.log(f"Waiting {wait_secs:.1f}s for Facebook to be ready")
            time.sleep(wait_secs)

            # Wait until main UI appears (logo or feed)
            if d(packageName=package).wait(timeout=10):
                self.log("Facebook is running")
                return True
            else:
                self.log("Facebook app did not load in time")
                return False

        except Exception as e:
            self.log(f"Failed to open Facebook: {e}")
            return False

    def _in_top_right(self, d, node, top_ratio=0.25, right_ratio=0.28):
        try:
            w, h = d.window_size()
            b = node.info.get("bounds", {})
            l, t, r, btm = b.get("left",0), b.get("top",0), b.get("right",0), b.get("bottom",0)
            return t < h*top_ratio and r > w*(1-right_ratio)
        except Exception:
            return False

    def _already_in_page(self, d):
        """
        Detect if we're currently in Facebook Page mode.
        """
        try:
            # Page-specific text patterns
            page_text_patterns = [
                r"(?i)professional\s+dashboard",
                r"(?i)ad\s+center",
                r"(?i)meta\s+business",
                r"(?i)promote",
                r"(?i)manage",
                r"(?i)insights",
                r"(?i)page\s+transparency",
                r"(?i)page\s+quality",
                r"(?i)creator\s+studio",
                r"(?i)business\s+suite",
                r"(?i)page\s+info",
                r"(?i)switch\s+to\s+personal"
            ]
            
            # Check both text and description matches with timeout
            for pattern in page_text_patterns:
                try:
                    if (d(textMatches=pattern).exists(timeout=1.0) or 
                        d(descriptionMatches=pattern).exists(timeout=1.0)):
                        return True
                except:
                    continue

            return False

        except Exception as e:
            self.log(f"Error detecting Page mode: {e}")
            return False

    def _open_menu_profile_switcher(self, d, wait=6):
        """
        From anywhere in FB, open the Menu tab with the profile switcher header.
        """
        # 1) Obvious switcher/avatar button (home screen)
        ids = [
            r".*profile_switcher.*", r".*account_switcher.*", r".*menu_tab_profile.*",
        ]
        descs = [
            r"(?i)(account|profile).*(switch|changer)",
            r"(?i)switch.*(account|profile)",
            r"(?i)Menu"
        ]
        for i in ids:
            node = d(resourceIdMatches=i)
            if node.exists and self._in_top_right(d, node):
                if self._tap(node):
                    return True
        for p in descs:
            node = d(descriptionMatches=p)
            if node.exists and self._in_top_right(d, node):
                if self._tap(node):
                    return True

        # 2) Fallback: tap in the top-right corner
        w, h = d.window_size()
        for _ in range(2):
            d.click(w*0.93, h*0.09)
            time.sleep(1)
            d.click(w*0.93, h*0.09)
            if d(textMatches=r"(?i)Menu").exists or d(descriptionMatches=r"(?i)Settings|Search").exists:
                return True
            time.sleep(0.4)

        # 3) Try bottom Menu tab
        possible_tabs = [
            r".*tab_bar_menu.*", r".*tab_menu.*", r".*menu_tab.*"
        ]
        for i in possible_tabs:
            node = d(resourceIdMatches=i)
            if node.exists and self._tap(node):
                return True

        return False

    def _quick_switch_button(self, d):
        """
        On the Menu header, tap the circular arrows quick-switch button.
        """
        candidates = [
            r".*switch.*", r".*swap.*", r".*toggle.*"
        ]
        # Try resource-id first
        for pat in candidates:
            node = d(resourceIdMatches=pat)
            if node.exists and self._in_top_right(d, node, top_ratio=0.33, right_ratio=0.45):
                if self._tap(node):
                    return True

        # Try description
        for pat in [r"(?i)switch", r"(?i)toggle", r"(?i)change.*account", r"(?i)switch to page"]:
            node = d(descriptionMatches=pat)
            if node.exists and self._in_top_right(d, node, top_ratio=0.33, right_ratio=0.45):
                if self._tap(node):
                    return True

        # Fallback: tap the header's right side
        w, h = d.window_size()
        d.click(w*0.784, h*0.206)
        return True

    def _tap(self, elem):
        try:
            if elem and elem.exists:
                elem.click()
                return True
        except Exception:
            pass
        return False

    def switch_to_profile(self, d, max_wait=8):
        """
        Switch from Page to personal Profile.
        """
        try:
            time.sleep(2)
            # Open Menu/profile-switcher area
            if not self._open_menu_profile_switcher(d, wait=max_wait):
                return False
            
            # Check if we're in Page mode
            if self._already_in_page(d):
                self.log("Switching to Profile from Page...")
                self._quick_switch_button(d)
                time.sleep(3)
                return True
            else:
                self.log("Already in Profile mode")
                time.sleep(3)
                return True

        except Exception as e:
            self.log(f"[switch_to_profile] Error: {e}")
            return False
           
    def click_home_button(self, d, max_wait=5, retries=2):
        """
        Click the Home button (house icon) in Facebook.

        Args:
            d (uiautomator2.Device): connected device instance
            max_wait (int): wait time in seconds to find the Home button
            retries (int): number of retry attempts if click fails

        Returns:
            bool: True if clicked successfully, False otherwise
        """
        def _on_home_feed(timeout_sec=2.5):
            """Best-effort confirmation that Facebook Home/feed is visible."""
            checks = [
                d(resourceIdMatches=r".*tab_bar_home.*selected.*"),
                d(descriptionMatches=r"(?i)^home$"),
                d(textMatches=r"(?i)what'?s on your mind"),
                d(textMatches=r"(?i)reels"),
                d(resourceIdMatches=r".*feed.*"),
            ]

            end_at = time.time() + timeout_sec
            while time.time() < end_at:
                try:
                    current = d.app_current()
                    if "facebook" not in current.get("package", "").lower():
                        time.sleep(0.2)
                        continue
                except Exception:
                    pass

                for sel in checks:
                    try:
                        if sel.exists(timeout=0.2):
                            return True
                    except Exception:
                        continue
                time.sleep(0.2)
            return False

        for attempt in range(1, retries + 1):
            try:
                # If already on Home, do not retry.
                if _on_home_feed(timeout_sec=1.2):
                    self.log(f"Home feed already visible (attempt {attempt})")
                    return True

                # Try detecting by description.
                if d(descriptionMatches=r"(?i)home").wait(timeout=max_wait):
                    d(descriptionMatches=r"(?i)home").click()
                    time.sleep(0.8)
                    if _on_home_feed(timeout_sec=2.0):
                        self.log(f"Clicked Home button by description (attempt {attempt})")
                        return True

                # Try by resource-id.
                if d(resourceIdMatches=r".*tab_bar_home.*").exists:
                    d(resourceIdMatches=r".*tab_bar_home.*").click()
                    time.sleep(0.8)
                    if _on_home_feed(timeout_sec=2.0):
                        self.log(f"Clicked Home button by resource-id (attempt {attempt})")
                        return True

                # Fallback: fixed position (approx top-left icon).
                w, h = d.window_size()
                d.click(w * 0.12, h * 0.08)
                self.log(f"Clicked fallback Home position (attempt {attempt})")

                # Confirm feed with broader signals (not only one localized text).
                time.sleep(1.0)
                if _on_home_feed(timeout_sec=2.0):
                    return True

            except Exception as e:
                self.log(f"Failed to click Home button on attempt {attempt}: {e}")

            if attempt < retries:
                self.log("Retrying Home button...")
                time.sleep(2)

        self.log("Could not confirm Home button after retries")
        return False

class EnhancedScrollTaskHandler(ScrollTaskHandler):
    """Enhanced scroll handler with error handling and randomization"""
    def __init__(self, emulator, log_func, pause_event, running_flag):
        super().__init__(emulator, log_func, pause_event, running_flag)
        from utils.error_handler import EnhancedErrorHandler
        from utils.rate_limiter import RateLimiter
        from utils.activity_randomizer import ActivityRandomizer
        self.error_handler = EnhancedErrorHandler(log_func)
        self.rate_limiter = RateLimiter()
        self.randomizer = ActivityRandomizer()
    
    def execute(self, name, duration=900, direction="down", intensity="medium"):
        """Enhanced execute with error handling"""
        self.error_handler.reset_counters(name)
        return super().execute(name, duration, direction, intensity)
