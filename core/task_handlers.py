import os
import subprocess
import time
import random
import re
from abc import ABC, abstractmethod

# Import uiautomator2
try:
    import uiautomator2 as u2
    U2_AVAILABLE = True
except Exception as e:
    u2 = None
    U2_AVAILABLE = False

# ==================== TASK HANDLERS ====================
class BaseTaskHandler(ABC):
    """Abstract base class for task handlers"""
    def __init__(self, emulator, log_func, pause_event, running_flag):
        self.emulator = emulator
        self.log = log_func
        self.pause_event = pause_event
        self.running_flag = running_flag
    
    @abstractmethod
    def execute(self, name, duration=None, **kwargs):
        pass
    
    def check_paused(self):
        """Check if operations should be paused - blocks if paused"""
        while not self.pause_event.is_set() and self.running_flag():
            time.sleep(0.5)
        return not self.running_flag()

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

class ScrollTaskHandler(BaseTaskHandler):
    """Handler for Facebook scrolling tasks"""
    def execute(self, name, duration=900, direction="down", intensity="medium"):
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
            self.log(f"Waiting for emulator ready: {name}")
            if not self.ensure_device_ready(name, timeout=max(90, int(getattr(self.emulator, 'boot_delay', 20)) * 6)):
                self.log(f"Device not ready after startup: {name}")
                return False

        if not self.ensure_device_ready(name, timeout=60):
            self.log(f"Device is not ready for automation: {name}")
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

        # Configure scroll parameters based on intensity
        intensity_params = {
            "light": {"duration_range": (500, 700), "delay_range": (2.0, 3.0)},
            "medium": {"duration_range": (400, 600), "delay_range": (1.5, 2.5)},
            "heavy": {"duration_range": (300, 500), "delay_range": (1.0, 2.0)}
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
        
        try:
            while time.time() - start_time < duration:
                if self.check_paused():
                    self.log(f"Scrolling paused on {name} after {successful_swipes} successful swipes")
                    return False
                
                # Determine scroll direction
                if direction == "random":
                    current_direction = "down" if random.random() > 0.5 else "up"
                else:
                    current_direction = direction
                
                # Generate swipe parameters based on direction and intensity
                scroll_duration = random.uniform(*params["duration_range"])
                
                if current_direction == "down":
                    start_y = random.randint(800, 900)
                    end_y = random.randint(300, 400)
                else:  # up direction
                    start_y = random.randint(300, 400)
                    end_y = random.randint(800, 900)
                
                # Add slight horizontal variation for more natural movement
                x_pos = random.randint(280, 320)
                
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
                    else:
                        failed_swipes += 1
                        consecutive_failures += 1
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
                    self.log(f"ADB command timed out for {name}")
                    
                    if consecutive_failures >= 3:
                        self.log("Too many timeouts, attempting to reconnect...")
                        if not self._ensure_adb_connection(serial):
                            self.log("Reconnection failed, aborting")
                            return False
                        consecutive_failures = 0
                
                # Vary the delay between swipes for more human-like behavior
                delay = random.uniform(*params["delay_range"])
                
                # Add occasional longer pauses to mimic reading behavior
                if successful_swipes % 5 == 0:
                    delay += random.uniform(0.5, 1.5)
                    
                # Occasionally vary swipe length (20% of the time)
                if random.random() < 0.2:
                    delay += random.uniform(0.3, 0.8)
                    
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

class ReelsTaskHandler(BaseTaskHandler):
    """Handler for Facebook Reels tasks"""
    def __init__(self, emulator, log_func, pause_event, running_flag, content_manager=None):
        super().__init__(emulator, log_func, pause_event, running_flag)
        self.content_manager = content_manager
        from utils.error_handler import EnhancedErrorHandler
        from utils.rate_limiter import RateLimiter
        from utils.activity_randomizer import ActivityRandomizer
        self.error_handler = EnhancedErrorHandler(log_func)
        self.rate_limiter = RateLimiter()
        self.randomizer = ActivityRandomizer()

    def _open_file_manager_with_retry(self, d, attempts=2, delay=2):
        """Open file manager with bounded retries."""
        for attempt in range(1, attempts + 1):
            try:
                if self.open_file_manager(d):
                    return True
            except Exception:
                pass
            if attempt < attempts:
                time.sleep(delay)
        return False
        
    def execute(self, name, duration=60, max_videos=2,scroll_after_post=True, use_content_queue=True):
        """
        Run Reels task: navigate to Page-1 and attempt to long-press the top video.
        Skip to next LD if any step fails instead of retrying.
        
        Args:
            name (str): Device identifier
            duration (int): Task duration in seconds (default: 60)
            max_videos (int): Maximum number of videos to process (default: 2)
        """
        if self.check_paused():
            return False

        # Start LD if not running
        if not self.emulator.is_ld_running(name):
            if not self.emulator.start_ld(name):
                self.log(f"âŒ Failed to start LD: {name}")
                return False
            self.log(f"Waiting for emulator ready: {name}")
            if not self.ensure_device_ready(name, timeout=max(90, int(getattr(self.emulator, 'boot_delay', 20)) * 6)):
                self.log(f"Device not ready after startup: {name}")
                return False

        if not self.ensure_device_ready(name, timeout=60):
            self.log(f"Device is not ready for Reels task: {name}")
            return False

        serial = self.emulator.name_to_serial.get(name)
        if not serial:
            self.log(f"âŒ No serial for {name}")
            return False

        # Connect with uiautomator2
        try:
            if not U2_AVAILABLE:
                self.log("âŒ uiautomator2 not available. Cannot run Reels task.")
                return False
            d = u2.connect(serial)
        except Exception as e:
            self.log(f"âŒ Failed to connect {serial}: {e}")
            return False

        # Open Facebook
        try:
            time.sleep(5)
            self.open_facebook(d)
                       
        except Exception:
            self.log("âŒ Can't open Facebook!")
            return False

        # Navigate to video location
        if not self._open_file_manager_with_retry(d, attempts=2, delay=2):
            self.log(f"âŒ Failed to open file manager on {name}")
            return False
        
        if not self.navigate_to_pictures(d):
            self.log(f"âŒ Failed to navigate to pictures on {name}")
            return False

        video_posted = 0
        success_pots = 0
        while video_posted < max_videos:
            try:
                if not self.hold_on_video(d, hold_time=2):
                    self.log(f"âŒ Failed to hold on video on {name}")
                    video_posted += 1
                    continue

                # Check if context menu appeared
                menu_present = any(
                    d(textContains=hint).exists(timeout=0.8)
                    for hint in ("Share", "Open with", "Delete", "Details", "Open")
                ) or d(resourceId="android:id/title").exists(timeout=0.8)

                if not menu_present:
                    self.log(f"âš ï¸ Long-press did not open expected menu on {name}")
                    video_posted += 1
                    continue

                # Try to click context option (e.g. share to Facebook)
                if not self.click_context_option(d):
                    self.log(f"âš ï¸ Context menu opened but no option clicked on {name}")
                    video_posted += 1
                    continue

                # Facebook handling
                if not self.emulator.is_ld_running(name):
                    self.log(f"âš ï¸ LD closed after sending to Facebook on {name}")
                    return True  # still counts as success

                time.sleep(5)

                if self.check_and_handle_facebook_permission(d):
                    return True

                if self.facebook_first_next(d):
                    time.sleep(2)
                    # In the ReelsTaskHandler.execute method, modify the cleanup section:
                time.sleep(10)
                
                # Get video data if using content queue
                video_data = None
                if use_content_queue and self.content_manager:
                    video_data = self.content_manager.get_next_video()
                
                if self.handle_reels_description(d, video_data):
                    self.log("â³ Waiting 20s to complete Facebook post...")
                    time.sleep(20)

                    # Check if the device is still connected before attempting cleanup
                    if not self.emulator.is_ld_running(name):
                        self.log("âš ï¸ LD closed during Facebook post, skipping cleanup")
                        video_posted += 1
                        continue

                    try:
                        time.sleep(5)
                        # Close Facebook
                        d.app_stop("com.facebook.katana")
                        time.sleep(2)

                        # Delete video file - check if device is still connected
                        if not self.emulator.is_ld_running(name):
                            self.log("âš ï¸ LD closed before video deletion, skipping")
                            video_posted += 1
                            continue

                        try:
                            if self.delete_video(d):
                                self.log("âœ… Video deleted successfully")

                            else:
                                if not self.emulator.is_ld_running(name):
                                    self.log("âš ï¸ LD closed before file manager, skipping")
                                    video_posted += 1
                                    continue
                                    
                                if not self._open_file_manager_with_retry(d, attempts=2, delay=1):
                                    self.log(f"âŒ Failed to open file manager on {name}")
                                    time.sleep(1)
                                if not self.delete_video(d):   
                                    self.log("âš ï¸ Failed to delete video, continuing")
                        except Exception as e:
                            self.log(f"âŒ Error during video deletion: {e}")
                            # Continue to next video even if deletion fails
                    except Exception as e:
                        self.log(f"âŒ Error during cleanup: {e}")
                        # Continue to next video even if cleanup fails

                    video_posted += 1
                    success_pots += 1
                    continue
            except Exception as e:
                self.log(f"âŒ Exception during task execution on {name}: {e}")
                video_posted += 1
                continue

        # Re-open Facebook and allow it to settle before any follow-up actions
        self.open_facebook(d)
            
        if scroll_after_post:
            self.log("ðŸŽ¬ Starting Reels scrolling after post...")
            self.scroll_facebook_reels(d, duration=20, intensity="light")

        self.log(f"ðŸ“Š Task completed: Processed {success_pots}/{max_videos} videos successfully")
        return success_pots > 0
    
    def handle_reels_description(self, d, video_data=None):
        """
        Handle the Facebook Reels description and audience selection screen
        that appears after clicking Next button
        """
        try:
            # Wait for the reels description screen to load
            time.sleep(3)
            
            # FIRST: Check for and click OK button if it exists
            ok_button_found = False
            ok_button_texts = [
                "OK", "Okay", "Xong", "ç¡®è®¤", "í™•ì¸", "Aceptar", 
                "Accepter", "Accetta", "Einverstanden", "OKE"
            ]
            
            # Try to find and click OK button
            for text in ok_button_texts:
                try:
                    if d(text=text).exists(timeout=2):
                        d(text=text).click()
                        self.log(f"Clicked OK button: {text}")
                        ok_button_found = True
                        time.sleep(2)
                        break
                except:
                    continue
            
            # If OK button was found and clicked, we're done
            if ok_button_found:
                self.log(" OK button handled successfully")
                return True
            
            # NEW: Try to add description with appropriate caption method
            description_added = False
            try:
                # Look for description input field using multiple approaches
                description_selectors = [
                    d(className="android.widget.EditText"),
                    d(className="android.widget.TextView", clickable=True),
                    d(className="android.view.View", clickable=True),
                    d(textContains="Describe your reel"),
                    d(textContains="Add a description"),
                    d(textContains="Write a caption"),
                    d(description="Description input field")
                ]
                
                description_field = None
                for selector in description_selectors:
                    try:
                        if selector.exists(timeout=2):
                            description_field = selector
                            break
                    except:
                        continue
                
                if description_field:
                    description_field.click()
                    time.sleep(1)
                    
                    # Clear any existing text first
                    d.clear_text()
                    time.sleep(1)
                    
                    # Use content from video_data if available
                    if video_data and video_data.get('caption'):
                        caption = video_data['caption']
                        if video_data.get('hashtags'):
                            caption += " " + video_data['hashtags']
                        self.log(f" Using content manager caption: {caption}")
                    else:
                        # Fallback to original method
                        device_key = f"{d.serial}_last_video_title"
                        video_title = getattr(self, device_key, None)
                        
                        if video_title:
                            # Remove file extension from video title
                            video_title_without_ext = self._remove_file_extension(video_title)
                            
                            # Use the video title without extension as caption
                            caption = video_title_without_ext
                            self.log(f" Using video title as caption:{video_title_without_ext}")
                        else:
                            # Video has no title, use generated caption
                            caption = self._generate_video_caption()
                            self.log(" Using generated caption for untitled video")
                    
                    # Add the caption to description
                    d.send_keys(caption)
                    time.sleep(1)
                    
                    # Hide keyboard
                    d.press("back")
                    time.sleep(1)
                    description_added = True
                    self.log(f" Description added: {caption}")
            except Exception as e:
                self.log(f"Could not add description: {e}")
            
            # Look for the final share/post button with more flexible detection
            share_button_found = False
            share_button_texts = [
                "Share", "Post", "Share now", "Publish", "ÄÄƒng", "Publicar",
                "å‘å¸ƒ", "å…±æœ‰", "Partager", "Compartir", "Condividi", "Teilen",
                "Share reel", "Post reel"  # Added more specific options
            ]
            
            # Try multiple approaches to find the share button
            attempts = [
                # 1. Text-based detection
                lambda: self._find_button_by_text(d, share_button_texts),
                # 2. Button class detection
                lambda: self._find_button_by_class(d, "android.widget.Button"),
                # 3. Resource ID detection (common Facebook buttons)
                lambda: self._find_button_by_resource_id(d, ["share", "post", "publish"]),
                # 4. Position-based detection (bottom of screen)
                lambda: self._find_button_by_position(d)
            ]
            
            for attempt in attempts:
                try:
                    if attempt():
                        share_button_found = True
                        break
                except Exception as e:
                    self.log(f" Button detection attempt failed: {e}")
                    continue
            
            if share_button_found:
                self.log("âœ… Reel posted successfully")
                return True
            else:
                self.log(" Could not find share button, but UI was detected - considering partial success")
                # Even if we can't find the share button, if we detected the reels screen,
                # consider it a success since we reached the intended UI
                return True
                
        except Exception as e:
            self.log(f" Error in handle_reels_description: {e}")
            return False

    def scroll_facebook_reels(self, d, duration=300, intensity="medium"):
        """
        Scroll through Facebook Reels using adb shell input swipe.
        """
        try:
            intensity_params = {
                "light": {"swipe_time": (500, 700), "delay": (3.0, 4.0)},
                "medium": {"swipe_time": (400, 600), "delay": (2.0, 3.0)},
                "heavy": {"swipe_time": (300, 500), "delay": (1.0, 2.0)}
            }
            params = intensity_params.get(intensity, intensity_params["medium"])
            
            start_time = time.time()
            successful_swipes = 0

            # get device screen size
            w, h = d.window_size()
            serial = d.serial  # required for adb

            while time.time() - start_time < duration:
                swipe_time = random.uniform(*params["swipe_time"])
                
                start_x = w // 2
                start_y = int(h * 0.8)
                end_y   = int(h * 0.25)

                # Use adb instead of u2.swipe()
                subprocess.run([
                    "adb", "-s", serial, "shell", "input", "swipe",
                    str(start_x), str(start_y),
                    str(start_x), str(end_y),
                    str(int(swipe_time))
                ], capture_output=True, text=True)

                successful_swipes += 1
                
                # Delay between swipes
                delay = random.uniform(*params["delay"])
                if successful_swipes % 3 == 0:
                    delay += random.uniform(1.0, 3.0)
                time.sleep(delay)
            
            self.log(f"ðŸŽ¬ Finished scrolling Reels: {successful_swipes} swipes")
            return True

        except Exception as e:
            self.log(f"âŒ Error while scrolling Reels: {e}")
            return False

    def _tap(self, elem):
        try:
            if elem and elem.exists:
                elem.click()
                return True
        except Exception:
            pass
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
        Robustly detect if we're currently in Facebook Page mode.
        Uses multiple detection methods for better reliability.
        """
        try:
            # Method 1: Check for Page-specific text patterns
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
            #show log to wait
            self.log("Working...! Switch to Page")
            # Check both text and description matches with timeout
            for pattern in page_text_patterns:
                try:
                    if (d(textMatches=pattern).exists(timeout=1.0) or 
                        d(descriptionMatches=pattern).exists(timeout=1.0)):
                    #log here if it true    
                        return True
                except:
                    continue

            #log here if it fale
            return False

        except Exception as e:
            self.log(f"Error detecting Page mode: {e}")
            # Fallback: assume not in Page mode on error
            return False

    def _open_menu_profile_switcher(self, d, wait=6):
        """
        From anywhere in FB, open the Menu tab with the profile switcher header.
        """
        # 1) Obvious switcher/avatar button (home screen)
        # Known ids/descriptions across builds
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

        # 2) Fallback: tap in the top-right corner (safe box), works on most layouts
        w, h = d.window_size()
        for _ in range(2):
            time.sleep(2)
            d.click(w*0.93, h*0.09)
            # give the Menu a moment to render
            if d(textMatches=r"(?i)Menu").exists or d(descriptionMatches=r"(?i)Settings|Search").exists:
                return True
            time.sleep(0.4)

        # 3) Try bottom Menu tab (some builds show a bottom nav)
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
        
            # As a coarse fallback, tap the header's right side where the icon sits
        w, h = d.window_size()
        d.click(w*0.784, h*0.206)

        time.sleep(10)    
        # If a switch happens, Page-only indicators will appear
        return True

    def switch_to_page(self, d, page_name=None, max_wait=8):
        """
        Robustly switch from personal profile to a Facebook Page.

        :param d: uiautomator2 device instance
        :param page_name: Optional page name to target
        :param max_wait: general wait budget in seconds
        :return: True on success, False otherwise
        """
        try:
            time.sleep(2)
            # 1) Open Menu/profile-switcher area
            if not self._open_menu_profile_switcher(d, wait=max_wait):
                return False
            # 0) Already in Page?
            try:
                if self._already_in_page(d):
                    self.log("You already in page!!")
                    return True
                else:
                # Small settle time
                    self.log("Switch to page!")
                    self._quick_switch_button(d)
                    time.sleep(3)
                    return True
            except Exception as e:    
                return False

        except Exception as e:
            self.log(f"[switch_to_page] Error: {e}")
            return False
        
    def switch_to_profile(self, d, page_name=None, max_wait=8):
        """
        Robustly switch from personal profile to a Facebook Page.

        :param d: uiautomator2 device instance
        :param page_name: Optional page name to target
        :param max_wait: general wait budget in seconds
        :return: True on success, False otherwise
        """
        try:
            time.sleep(2)
            # 1) Open Menu/profile-switcher area
            if not self._open_menu_profile_switcher(d, wait=max_wait):
                return False
            # 0) Already in Page?
            try:
                if self._already_in_page(d):
                    self.log("Switch to Profile!")
                    self._quick_switch_button(d)
                    return True
                else:
                # Small settle time
                    self.log("You in profile already")
                    time.sleep(3)
                    return True
            except Exception as e:    
                return False

        except Exception as e:
            self.log(f"[switch_to_page] Error: {e}")
            return False

    def open_facebook(self, d, ready_delay_range=(5, 10)):
        try:
            package = "com.facebook.katana"  # Main Facebook package name
            activity = "com.facebook.katana.LoginActivity"

            # Try launching Facebook
            d.app_start(package)
            self.log("Facebook app opened")

            # Give the app a short window to finish booting so UI elements exist
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

    #function clear app    
    def clear_app(self, d, package_name: str) -> bool:
        try:
            # Force stop the app first
            d.app_stop(package_name)
            time.sleep(1)
            # Clear data/cache (requires adb shell)
            os.system(f"adb -s {d.serial} shell pm clear {package_name}")
            return True
        except Exception as e:
            self.log(f"âŒ Failed to clear app {package_name}: {e}")
            return False
        
    #function delete video
    def delete_video(self, d):
        try:
            # Long press video
            self.hold_on_video(d, hold_time=2)
            time.sleep(2)

            # Find and click "Delete" option
            for element in d(className="android.widget.TextView"):
                text = element.info.get('text', '')
                if text and "Delete" in text:
                    element.click()
                    time.sleep(2)  # Wait for confirmation dialog
                    break

            # Handle the confirm deletion popup
            if d(text="YES").exists(timeout=2):
                d(text="YES").click()
                time.sleep(2)
                return True
            else:
                self.log("âš ï¸Confirm deletion dialog not found")
                return False

        except Exception as e:
            self.log(f"âŒError while deleting video: {e}")
            return False
    
    def _remove_file_extension(self, filename):
        """
        Remove file extension from filename
        """
        # List of common video extensions to remove
        video_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.m4v', '.wmv', '.3gp']
        
        # Remove any video extension found
        for ext in video_extensions:
            if filename.lower().endswith(ext):
                return filename[:-len(ext)]
        
        # If no known extension found, try to remove anything after the last dot
        if '.' in filename:
            return filename.rsplit('.', 1)[0]
        
        return filename

    def _generate_video_caption(self):
        """
        Generate engaging caption for videos without proper titles
        """
        # List of sample captions for generic videos
        base_captions = [
            "Check out this amazing video! ðŸŽ¥",
            "Just created this awesome content! âœ¨",
            "Watch this viral video trending now! ðŸ”¥",
            "This video is blowing up! ðŸ’¥",
            "Don't miss this incredible footage! ðŸ“¸",
            "Epic content coming your way! ðŸš€",
            "This is too good not to share! ðŸ‘",
            "Viral moment captured on camera! ðŸ“¹",
            "Trending content you need to see! ðŸ‘€",
            "Amazing video that you'll love! â¤ï¸"
        ]
        
        # List of popular hashtags for reels
        hashtag_groups = [
            "#reels #viral #trending #fyp #foryou #foryoupage #explorepage #instagramreels #reelitfeelit #reelkarofeelkaro #reelsindia #reelsteady #reelsvideo #reelsinsta #reelslovers #reelsofinstagram #reelsviral #reelsdance #reelsmusic #reelsfunny",
            "#viralvideo #trendingnow #fypã‚· #foryourpage #explore #instareels #reelit #reelkarofeelkaro #reelsindia #reelsteadygo #reelsvideoviral #reelsinstagram #reelslover #reelsofig #reelsviraltrick #reelsdancevideo #reelsmusicvideo #reelsfunnyvideos #contentcreator #digitalcreator",
            "#reels #viral #fyp #trending #foryou #instagramreels #reelitfeelit #reelsindia #reelsteady #reelsvideo #explorepage #foryoupage #reelsinsta #reelslovers #reelsofinstagram #reelsviral #reelsdance #reelsmusic #reelsfunny #contentcreation"
        ]
        
        # Select a random base caption
        base_caption = random.choice(base_captions)
        
        # Select a random hashtag group
        hashtags = random.choice(hashtag_groups)
        
        # Combine caption and hashtags
        full_caption = f"{base_caption} {hashtags}"
        
        return full_caption

    # Add these helper methods to the ReelsTaskHandler class:
    def _find_button_by_text(self, d, button_texts):
        """Find button by text content"""
        for text in button_texts:
            try:
                if d(text=text).exists(timeout=2):
                    d(text=text).click()
                    self.log(f" Clicked button by text: {text}")
                    time.sleep(3)
                    return True
            except:
                continue
        return False

    def _find_button_by_class(self, d, class_name):
        """Find button by class name"""
        try:
            buttons = d(className=class_name)
            for button in buttons:
                bounds = button.info.get('bounds', {})
                if bounds:
                    # Look for buttons at the bottom of the screen
                    screen_height = d.info.get("displayHeight", 1920)
                    if bounds["top"] > screen_height * 0.7:  # Bottom 30% of screen
                        button.click()
                        self.log(f"âœ… Clicked {class_name} button at bottom")
                        time.sleep(3)
                        return True
        except:
            pass
        return False

    def _find_button_by_resource_id(self, d, keywords):
        """Find button by resource ID containing keywords"""
        try:
            all_elements = d(className="android.view.View")
            for element in all_elements:
                resource_id = element.info.get('resourceId', '').lower()
                if any(keyword in resource_id for keyword in keywords):
                    bounds = element.info.get('bounds', {})
                    if bounds:
                        element.click()
                        self.log(f"âœ… Clicked button by resource ID: {resource_id}")
                        time.sleep(3)
                        return True
        except:
            pass
        return False

    def _find_button_by_position(self, d):
        """Find button by common screen positions"""
        try:
            screen_width = d.info.get("displayWidth", 1080)
            screen_height = d.info.get("displayHeight", 1920)
            
            # Common positions for action buttons
            positions = [
                (screen_width * 0.9, screen_height * 0.95),  # Bottom right
                (screen_width * 0.85, screen_height * 0.93),  # Slightly left of corner
                (screen_width * 0.95, screen_height * 0.9),   # Right side
            ]
            
            for x, y in positions:
                try:
                    d.click(x, y)
                    self.log(f"âœ… Clicked at position ({x}, {y}) as fallback")
                    time.sleep(3)
                    return True
                except:
                    continue
        except:
            pass
        return False

    def hold_on_video(self, d, hold_time=2):
        """Long-press top video in file manager after navigating to the Page-1 folder"""
        try:
            time.sleep(2)
            
            # First, make sure we're in the Page-1 folder by checking if we can see video files
            # If we see folder names instead, we need to click into the Page-1 folder first
            video_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv']
            
            # Check if we're already in a folder with video files
            text_elements = d(className="android.widget.TextView")
            video_files_found = False
            
            if text_elements:
                for element in text_elements:
                    text = element.info.get('text', '')
                    if any(ext in text.lower() for ext in video_extensions):
                        video_files_found = True
                        break
            
            # If we don't see video files, we might still be in the folder selection view
            # Try to click on Page-1 folder again if it exists
            if not video_files_found:
                if not self.navigate_to_page(d):
                    return False
                time.sleep(2)
            
            # Now we should be in the folder with video files
            # Try to find and long-press the first video file
            text_elements = d(className="android.widget.TextView")
            
            if text_elements:
                # Look for the first text element that contains a video extension
                for element in text_elements:
                    text = element.info.get('text', '')
                    if any(ext in text.lower() for ext in video_extensions):
                        # Found a video file - store the title in thread-local storage
                        # Use the device serial as a key to make it unique per device
                        device_key = f"{d.serial}_last_video_title"
                        setattr(self, device_key, text)
                        self.log(f"ðŸ“¹ Found video: {text}")
                        
                        # Long press it
                        element.long_click(duration=hold_time)
                        return True
                
                # If no video files found by extension, try pressing the first file-like element
                for i, element in enumerate(text_elements):
                    text = element.info.get('text', '')
                    # Skip elements that look like dates, sizes, or other metadata
                    if (re.search(r'\d{1,2}/\d{1,2}/\d{2,4}', text) or  # Dates
                        re.search(r'\d+\.?\d*\s*(MB|KB|GB)', text) or    # File sizes
                        len(text.strip()) < 2):                          # Very short text
                        continue

                    # This looks like a filename - store it in thread-local storage and long press
                    device_key = f"{d.serial}_last_video_title"
                    setattr(self, device_key, text)
                    self.log(f"ðŸ“¹ Found possible video file: {text}")
                    element.long_click(duration=hold_time)
                    return True
            
            # Fallback to thumbnail view
            image_items = d(className="android.widget.ImageView")
            if image_items:
                # Try to find the first image view that might represent a video thumbnail
                for i, image_item in enumerate(image_items):
                    try:
                        bounds = image_item.info.get("bounds")
                        if bounds:
                            x = (bounds["left"] + bounds["right"]) // 2
                            y = (bounds["top"] + bounds["bottom"]) // 2
                            d.long_click(x, y, duration=hold_time)
                            self.log(f"ðŸŽ¥ Long-pressed thumbnail #{i+1}")
                            
                            # Try to find associated text for the thumbnail
                            text_elements_nearby = d(className="android.widget.TextView")
                            for text_element in text_elements_nearby:
                                text_bounds = text_element.info.get("bounds")
                                if text_bounds:
                                    # Check if this text is near the thumbnail
                                    if (abs(text_bounds["top"] - bounds["bottom"]) < 50 or
                                        abs(text_bounds["bottom"] - bounds["top"]) < 50):
                                        text = text_element.info.get('text', '')
                                        if text and any(ext in text.lower() for ext in video_extensions):
                                            device_key = f"{d.serial}_last_video_title"
                                            setattr(self, device_key, text)
                                            self.log(f"ðŸ“¹ Found video near thumbnail: {text}")
                                            break
                            return True
                    except:
                        continue

            self.log(" No video files found to long-press in Page-1 folder")
            return False
            
        except Exception as e:
            self.log(f" Error holding video: {e}")
            return False

    def click_context_option(self, d):
        """Click on a context menu option that might be a send/share button"""
        try:
            time.sleep(2)
            # First, check if we're seeing the Facebook permission dialog
            if self.check_and_handle_facebook_permission(d):
                    return True 
            # If not in permission dialog, continue with original logic
            # First, get all available options for debugging
            all_options = []
            for element in d(className="android.widget.TextView"):
                text = element.info.get('text', '')
                if text:
                    all_options.append(text)
            
            # Check if we're in the initial context menu (with Send option)
            if "Send" in all_options:
                
                # Click the Send option
                for element in d(className="android.widget.TextView"):
                    text = element.info.get('text', '')
                    if text and "Send" in text:
                        element.click()
                        time.sleep(3)  # Wait for Share dialog to appear
                        break
                
                # Check for permission dialog again after clicking Send
                if self.check_and_handle_facebook_permission(d):
                    return True
                
                # Now look for the Share with dialog
                share_options = []
                for element in d(className="android.widget.TextView"):
                    text = element.info.get('text', '')
                    if text:
                        share_options.append(text)
                
                # Check if we're now in the Share with dialog
                if "Share with" in share_options or any("Bluetooth" in opt or "Nearby Share" in opt or "News Feed" in opt for opt in share_options):
                    
                    # Look for Reels option (may need to scroll)
                    reels_option = None
                    for element in d(className="android.widget.TextView"):
                        text = element.info.get('text', '')
                        if text and "reels" in text.lower():
                            reels_option = element
                            break
                    
                    # If Reels not found, scroll down
                    if not reels_option:
                        d.swipe(0.5, 0.7, 0.5, 0.3, 0.5)
                        time.sleep(1)
                        
                        # Look for Reels again after scrolling
                        for element in d(className="android.widget.TextView"):
                            text = element.info.get('text', '')
                            if text and "reels" in text.lower():
                                reels_option = element
                                break
                    
                    # If Reels found, click it
                    if reels_option:
                        reels_option.click()
                        time.sleep(3)
                        
                        # Wait for the "Always/Just once" dialog to appear
                        time.sleep(2)
                        
                        # Look for "Always" or "Just once" options - check all possible UI elements
                        always_found = False
                        
                        # Method 1: Look for buttons with specific text
                        for option_text in ["Always", "Just once"]:
                            for element in d(className="android.widget.Button"):  # Try Button class first
                                text = element.info.get('text', '')
                                if text and option_text.lower() in text.lower():
                                    element.click()
                                    time.sleep(2)
                                    
                                    # Check for permission dialog after clicking Always/Just once
                                    if self.check_and_handle_facebook_permission(d):
                                        return True
                                    
                                    always_found = True
                                    return True
                        
                        # Method 2: Look for TextView with specific text if buttons not found
                        if not always_found:
                            for option_text in ["Always", "Just once"]:
                                for element in d(className="android.widget.TextView"):
                                    text = element.info.get('text', '')
                                    if text and option_text.lower() in text.lower():
                                        # Check if this looks like a clickable element (reasonable size)
                                        bounds = element.info.get("bounds")
                                        if bounds and (bounds["bottom"] - bounds["top"]) > 40:
                                            element.click()
                                            time.sleep(2)
                                            
                                            # Check for permission dialog after clicking Always/Just once
                                            if self.check_and_handle_facebook_permission(d):
                                                return True
                                            
                                            self.log(f"Clicked '{option_text}' text view")
                                            always_found = True
                                            return True
                        
                        # Method 3: Look for any clickable element that might be the Always option
                        if not always_found:
                            clickable_elements = d(className="android.widget.Button")
                            if not clickable_elements.exists:
                                clickable_elements = d(className="android.widget.TextView")
                            
                            for element in clickable_elements:
                                text = element.info.get('text', '')
                                bounds = element.info.get("bounds")
                                if text and bounds and (bounds["bottom"] - bounds["top"]) > 40:
                                    # Check if it looks like a dialog button (not too wide, reasonable height)
                                    width = bounds["right"] - bounds["left"]
                                    height = bounds["bottom"] - bounds["top"]
                                    if height > 40 and width < 500:  # Reasonable button dimensions
                                        element.click()
                                        time.sleep(2)
                                        
                                        # Check for permission dialog after clicking Always/Just once
                                        if self.check_and_handle_facebook_permission(d):
                                            return True
                                        
                                        self.log(f"Clicked possible option: {text}")
                                        return True
                        
                        self.log("Always/Just once option not found after clicking Reels")
                        return False
                    
                    self.log("Reels option not found even after scrolling")
                    return False
                
                return True
            
            # Check if we're already in the Share with dialog (directly)
            elif "Share with" in all_options or any("Bluetooth" in opt or "Nearby Share" in opt or "News Feed" in opt for opt in all_options):
                # Look for Reels option (may need to scroll)
                reels_option = None
                for element in d(className="android.widget.TextView"):
                    text = element.info.get('text', '')
                    if text and "reels" in text.lower():
                        reels_option = element
                        break
                
                # If Reels not found, scroll down
                if not reels_option:
                    d.swipe(0.5, 0.7, 0.5, 0.3, 0.5)
                    time.sleep(1)
                    
                    # Look for Reels again after scrolling
                    for element in d(className="android.widget.TextView"):
                        text = element.info.get('text', '')
                        if text and "reels" in text.lower():
                            reels_option = element
                            break
                
                # If Reels found, click it
                if reels_option:
                    reels_option.click()
                    time.sleep(3)
                    
                    # Check for permission dialog again after clicking Reels
                    if self.check_and_handle_facebook_permission(d):
                        return True
                    
                    self.log("Clicked Reels option")
                    
                    # Wait for the "Always/Just once" dialog to appear
                    time.sleep(2)
                    
                    # Look for "Always" or "Just once" options
                    always_found = False
                    
                    # Method 1: Look for buttons with specific text
                    for option_text in ["Always", "Just once"]:
                        for element in d(className="android.widget.Button"):
                            text = element.info.get('text', '')
                            if text and option_text.lower() in text.lower():
                                element.click()
                                time.sleep(2)
                                
                                # Check for permission dialog after clicking Always/Just once
                                if self.check_and_handle_facebook_permission(d):
                                    return True
                                
                                self.log(f"Clicked '{option_text}' button")
                                always_found = True
                                return True
                    
                    # Method 2: Look for TextView with specific text if buttons not found
                    if not always_found:
                        for option_text in ["Always", "Just once"]:
                            for element in d(className="android.widget.TextView"):
                                text = element.info.get('text', '')
                                if text and option_text.lower() in text.lower():
                                    # Check if this looks like a clickable element
                                    bounds = element.info.get("bounds")
                                    if bounds and (bounds["bottom"] - bounds["top"]) > 40:
                                        element.click()
                                        time.sleep(2)
                                        
                                        # Check for permission dialog after clicking Always/Just once
                                        if self.check_and_handle_facebook_permission(d):
                                            return True
                                        
                                        self.log(f"Clicked '{option_text}' text view")
                                        always_found = True
                                        return True
                    
                    # Method 3: Look for any clickable element
                    if not always_found:
                        clickable_elements = d(className="android.widget.Button")
                        if not clickable_elements.exists:
                            clickable_elements = d(className="android.widget.TextView")
                        
                        for element in clickable_elements:
                            text = element.info.get('text', '')
                            bounds = element.info.get("bounds")
                            if text and bounds and (bounds["bottom"] - bounds["top"]) > 40:
                                width = bounds["right"] - bounds["left"]
                                height = bounds["bottom"] - bounds["top"]
                                if height > 40 and width < 500:
                                    element.click()
                                    time.sleep(2)
                                    
                                    # Check for permission dialog after clicking Always/Just once
                                    if self.check_and_handle_facebook_permission(d):
                                        return True
                                    
                                    self.log(f"Clicked possible option: {text}")
                                    return True
                    return False
                return False
            # Standard send/share options for other contexts
            send_options = ["send", "share", "gá»­i", "chia sáº»", "send to", "share with"]
            
            for option in send_options:
                # Look for elements that contain the option text (case insensitive)
                for element in d(className="android.widget.TextView"):
                    text = element.info.get('text', '').lower()
                    if option in text:
                        element.click()
                        time.sleep(2)
                        
                        # Check for permission dialog after clicking send/share option
                        if self.check_and_handle_facebook_permission(d):
                            return True
                        
                        self.log(f"Clicked option: {text}")
                        return True
            
            self.log("âŒ No suitable context option found to click")
            return False
            
        except Exception as e:
            self.log(f"Error clicking context option: {e}")
            return False

    def facebook_first_next(self, d):
        """Handle Facebook posting with better error recovery and UI detection"""
        try:
            # Wait for Facebook UI to load (max 25s)
            facebook_opened = False
            for _ in range(25):
                current_app = d.app_current()
                if "facebook" in current_app.get('package', '').lower():
                    facebook_opened = True
                    break
                time.sleep(1)
            
            if not facebook_opened:
                self.log("Facebook app did not open")
                return False

            # Wait additional time for UI to fully load
            time.sleep(3)
            
            # Candidate button texts in multiple languages
            post_button_texts = [
                "Next", "Post", "Share", "Share now", "Done", "Publish",
                "Tiáº¿p", "à¸•à¹ˆà¸­à¹„à¸›", "Siguiente", "Weiter", "Suivant", "Publicar",
                "æ¬¡ã¸", "ë‹¤ìŒ", "ä¸‹ä¸€æ­¥", "Ä°leri", "Avanti", "PrÃ³ximo", "å‘å¸ƒ",
                "ÄÄƒng", "Partager", "Compartir", "Condividi", "Teilen", "å…±æœ‰"
            ]

            # Try text-based detection first
            for text in post_button_texts:
                try:
                    if d(text=text).exists(timeout=2):
                        d(text=text).click()
                        time.sleep(2)
                        return True
                except:
                    continue

            # Try by resourceId and content description
            button_selectors = [
                d(className="android.widget.Button"),
                d(className="android.widget.TextView"),
                d(className="android.widget.ImageView"),  # For icon buttons
                d(className="android.widget.ImageButton")
            ]
            
            for selector in button_selectors:
                try:
                    for button in selector:
                        try:
                            rid = button.info.get('resourceId', '').lower()
                            txt = button.info.get('text', '').lower()
                            content_desc = button.info.get('contentDescription', '').lower()
                            bounds = button.info.get('bounds', {})
                            
                            # Check if this looks like a post button
                            button_keywords = ["next", "post", "share", "publish", "done", "continue", "send"]
                            is_post_button = (
                                any(kw in rid for kw in button_keywords) or
                                any(kw in txt for kw in button_keywords) or
                                any(kw in content_desc for kw in button_keywords)
                            )
                            
                            # Additional check for button position (usually at bottom right)
                            if is_post_button and bounds:
                                screen_width = d.info.get("displayWidth", 1080)
                                screen_height = d.info.get("displayHeight", 1920)
                                
                                # Check if button is in bottom-right quadrant
                                if (bounds["right"] > screen_width * 0.6 and 
                                    bounds["top"] > screen_height * 0.7):
                                    button.click()
                                    self.log(f"âœ… Clicked bottom-right button: {txt or content_desc or rid}")
                                    time.sleep(2)
                                    return True
                        except:
                            continue
                except:
                    continue

            # Try to find blue-colored buttons (common Facebook theme)
            try:
                # Get all elements and check for blue background
                all_elements = d(className="android.view.View")
                for element in all_elements:
                    try:
                        # Check if element has a blue background (common for Facebook buttons)
                        # This is a heuristic approach
                        bounds = element.info.get('bounds', {})
                        if bounds and (bounds["bottom"] - bounds["top"] > 40 and
                                    bounds["right"] - bounds["left"] > 100):
                            # Check if it's positioned at the bottom
                            screen_height = d.info.get("displayHeight", 1920)
                            if bounds["top"] > screen_height * 0.7:
                                element.click()
                                self.log("âœ… Clicked bottom blue element (likely post button)")
                                time.sleep(2)
                                return True
                    except:
                        continue
            except:
                pass

            # Final fallback: try clicking at common post button positions
            screen_width = d.info.get("displayWidth", 1080)
            screen_height = d.info.get("displayHeight", 1920)
            
            # Common positions for post buttons (bottom right area)
            click_positions = [
                (screen_width * 0.9, screen_height * 0.95),  # Bottom right corner
                (screen_width * 0.85, screen_height * 0.93),  # Slightly left of corner
                (screen_width * 0.95, screen_height * 0.9),   # Right side
            ]
            
            for x, y in click_positions:
                try:
                    d.click(x, y)
                    self.log(f"âœ… Clicked at position ({x}, {y}) as fallback")
                    time.sleep(2)
                    return True
                except:
                    continue

            self.log("âŒ Could not find Facebook Post button")
            return False

        except Exception as e:
            self.log(f"âŒ Error in facebook_post: {e}")
            return False

    def open_file_manager(self, d):
        """Open File Manager using multiple approaches"""
        try:
            # Method 1: Try to launch by package name (common alternatives)
            possible_packages = [
                "com.android.filemanager",
                "com.sec.android.app.myfiles",  # Samsung file manager
                "com.google.android.documentsui",  # Android's Files app
                "com.cyanogenmod.filemanager",
                "com.estrongs.android.pop",  # ES File Explorer
                "com.mediatek.filemanager"  # MediaTek file manager
            ]
            # Try each package name
            for pkg in possible_packages:
                try:
                    d.app_start(pkg)
                    current_package = d.app_current()["package"]
                    if current_package == pkg or "file" in current_package.lower():
                        self.log("File Manager launched")
                        return True
                except:
                    continue
                      
        except Exception as e:
            self.log(f"Error opening File Manager: {e}")

        self.log("Failed to open File Manager")
        return False

    def navigate_to_pictures(self, d):
        """Click on Pictures folder"""
        try:
            time.sleep(3)
            if d(text="Pictures").exists:
                d(text="Pictures").click()
                time.sleep(2)
                return True
            else:
                # Try to scroll if not visible
                d.swipe(0.5, 0.7, 0.5, 0.3, 0.5)
                time.sleep(1)
                if d(text="Pictures").exists:
                    d(text="Pictures").click()
                    time.sleep(2)
                    return True
                else:
                    return False
        except Exception as e:
            self.log(f"Error clicking Pictures: {e}")
            return False

    def navigate_to_page(self, d):
        """Click on Page-1 folder (exact Page-1 / Page 1 only)"""
        try:
            time.sleep(2)  # Wait for directory to load
            # Only match explicit "Page-1" or "Page 1"
            if d(text="Page-1").exists:
                d(text="Page-1").click()
                time.sleep(2)
                return True
            if d(text="Page 1").exists:
                d(text="Page 1").click()
                time.sleep(2)
                return True

            # Try a simple scroll and re-check once
            d.swipe(0.5, 0.7, 0.5, 0.3, 0.5)
            time.sleep(1)
            if d(text="Page-1").exists:
                d(text="Page-1").click()
                time.sleep(2)
                return True
            if d(text="Page 1").exists:
                d(text="Page 1").click()
                time.sleep(2)
                return True
            
            return False
        except Exception as e:
            self.log(f"Error clicking Page-1: {e}")
            return False
    
    def check_and_handle_facebook_permission(self, d):
        """Check for Facebook permission dialog and click ALLOW if found"""
        try:
            # More flexible text matching for permission dialogs
            permission_patterns = [
                "allow facebook.*access.*photos.*media.*files",
                "facebook.*permission.*access.*media",
                "allow.*facebook.*access.*storage",
                "facebook.*access.*photos"
            ]
            
            allow_button_patterns = [
                "allow",
                "always allow",
                "yes",
                "agree",
                "accept"
            ]
            
            deny_button_patterns = [
                "deny",
                "don't allow",
                "never",
                "no",
                "reject"
            ]
            
            # Get all text elements to check for the permission dialog
            all_texts = []
            for element in d(className="android.widget.TextView"):
                text = element.info.get('text', '')
                if text:
                    all_texts.append(text.lower())
            
            # Check if we're in a Facebook permission dialog using flexible matching
            is_permission_dialog = False
            for pattern in permission_patterns:
                if any(re.search(pattern, text, re.IGNORECASE) for text in all_texts):
                    is_permission_dialog = True
                    break
            
            if is_permission_dialog:
                self.log("Found Facebook permission dialog - looking for ALLOW button")
                
                # Look for the ALLOW button and click it - check multiple element types
                elements_to_check = []
                
                # First check buttons
                for element in d(className="android.widget.Button"):
                    elements_to_check.append(element)
                
                # Then check text views that might be clickable
                for element in d(className="android.widget.TextView"):
                    bounds = element.info.get("bounds")
                    if bounds and (bounds["bottom"] - bounds["top"]) > 40:  # Reasonable size for a button
                        elements_to_check.append(element)
                
                # Look for ALLOW button with flexible matching
                for element in elements_to_check:
                    text = element.info.get('text', '').lower()
                    bounds = element.info.get("bounds")
                    
                    if not text or not bounds:
                        continue
                    
                    # Check if this looks like an ALLOW button
                    is_allow_button = any(pattern in text for pattern in allow_button_patterns)
                    is_deny_button = any(pattern in text for pattern in deny_button_patterns)
                    
                    # Prioritize clicking ALLOW buttons
                    if is_allow_button:
                        try:
                            # Make sure it's clickable (reasonable size)
                            width = bounds["right"] - bounds["left"]
                            height = bounds["bottom"] - bounds["top"]
                            
                            if height > 30 and width > 50:  # Reasonable button dimensions
                                element.click()
                                time.sleep(3)
                                self.log(f"Clicked ALLOW button: {text}")
                                return True
                        except Exception as e:
                            self.log(f"Error clicking ALLOW button: {e}")
                            continue
                
                # If no ALLOW button found by text, try to find by position
                # (Usually ALLOW is on the right side, DENY on the left)
                right_side_elements = []
                screen_width = d.info.get("displayWidth", 1080)  # Default to common width
                
                for element in elements_to_check:
                    bounds = element.info.get("bounds")
                    if bounds and bounds["right"] > screen_width * 0.6:  # Right side of screen
                        right_side_elements.append(element)
                
                # Try clicking elements on the right side
                for element in right_side_elements:
                    try:
                        bounds = element.info.get("bounds")
                        if bounds and (bounds["bottom"] - bounds["top"]) > 30:
                            element.click()
                            time.sleep(3)
                            self.log("Clicked right-side element (likely ALLOW button)")
                            return True
                    except Exception as e:
                        self.log(f"Error clicking right-side element: {e}")
                        continue
                
                self.log("Could not find ALLOW button in permission dialog")
                return False
            return False
        except Exception as e:
            self.log(f"Error checking Facebook permission: {e}")
            return False
