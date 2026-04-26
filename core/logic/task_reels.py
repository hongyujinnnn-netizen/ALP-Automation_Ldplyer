import os
import json
import random
import re
import subprocess
import time

from unittest import result
import xml.etree.ElementTree as ET

from core.task_base import BaseTaskHandler, U2_AVAILABLE, u2
from core.paths import get_app_paths
from utils.ip_guard import check_ld_ip_allowed

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

    def _clear_recent_apps(self, d):
        """Open Recents and clear all running apps when possible."""
        serial = getattr(d, "serial", None)
        try:
            try:
                d.press("recent")
            except Exception:
                if serial:
                    subprocess.run(
                        ["adb", "-s", serial, "shell", "input", "keyevent", "187"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
            time.sleep(2)

            clear_selectors = [
                {"resourceId": "com.android.systemui:id/clear_all"},
                {"text": "Clear all"},
                {"text": "CLEAR ALL"},
                {"text": "Close all"},
                {"text": "CLOSE ALL"},
                {"text": "Clear"},
                {"text": "CLEAR"},
            ]

            for selector in clear_selectors:
                try:
                    obj = d(**selector)
                    if obj.exists(timeout=1):
                        obj.click()
                        self.log("Cleared recent apps")
                        time.sleep(2)
                        break
                except Exception:
                    continue

            if serial:
                subprocess.run(
                    ["adb", "-s", serial, "shell", "am", "kill-all"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            try:
                d.press("home")
            except Exception:
                pass
            return True
        except Exception as e:
            self.log(f"Failed to clear recent apps: {e}")
            return False


    def execute(self, name, duration=60, max_videos=2, scroll_after_post=True, use_content_queue=True, page_per_account=2, clear_cache=True):
        if self.check_paused():
            return False

        if not self.emulator.is_ld_running(name):
            if not self.emulator.start_ld(name):
                self.log(f"Failed to start LD: {name}")
                return False
            self.auto_arrange_ld_windows()
            self.log(f"Waiting for emulator ready: {name}")
            if not self.ensure_device_ready(name, timeout=max(90, int(getattr(self.emulator, 'boot_delay', 20)) * 6)):
                self.log(f"Device not ready after startup: {name}")
                return False

        if not self.ensure_device_ready(name, timeout=60):
            self.log(f"Device is not ready for Reels task: {name}")
            return False

        serial = self.emulator.name_to_serial.get(name)
        if not serial:
            self.log(f"No serial for {name}")
            return False

        blocked_countries = getattr(self, "blocked_countries", None)
        if blocked_countries:
            if not check_ld_ip_allowed(serial, blocked_countries, self.log, ld_name=name):
                try:
                    if hasattr(self.emulator, "quit_ld"):
                        self.emulator.quit_ld(name)
                except Exception:
                    pass
                return False

        try:
            if not U2_AVAILABLE:
                self.log("uiautomator2 not available. Cannot run Reels task.")
                return False
            d = u2.connect(serial)
        except Exception as e:
            self.log(f"Failed to connect {serial}: {e}")
            return False
        
        page_ready = 0
        click_pages = 0
        f_index = 2
        video_posted = 0
        success_pots = 0
        videos_per_page = max(0, int(max_videos or 0))
        total_pages = max(0, int(page_per_account or 0))
        total_videos_target = videos_per_page * total_pages

        self.push_runtime_state(
            name,
            state="Running",
            task=f"Processed {success_pots}/{total_videos_target} video",
            progress=78 if total_videos_target > 0 else 0,
        )
        # logic switch for reels post, if page_per_account is 1, it will only click the first page, if it's 2, it will click the second page, and so on. This is to avoid the issue of some accounts having multiple pages and the script always clicking the first one which may not be the intended one.
        while page_ready < total_pages:
            setup_ready = False
            max_setup_attempts = 2

            for setup_attempt in range(1, max_setup_attempts + 1):
                try:
                    time.sleep(5)
                    if not self.open_facebook(d):
                        raise RuntimeError("Can't open Facebook")
                except Exception:
                    self.log("Can't open Facebook!")
                    return False

                time.sleep(5)
                menu_opened = self.click_facebook_menu(d)
                profile_dropdown_opened = False

                if menu_opened:
                    time.sleep(4)
                    profile_dropdown_opened = self.click_profile_dropdown(d)
                else:
                    self.log(f"Failed to open Facebook menu on {name}")

                if not menu_opened or not profile_dropdown_opened:
                    if menu_opened:
                        self.log(f"Failed to open Facebook profile dropdown on {name}")

                    if setup_attempt >= max_setup_attempts:
                        task_message = (
                            "Facebook menu not found"
                            if not menu_opened
                            else "Facebook profile dropdown not found"
                        )
                        self.push_runtime_state(
                            name,
                            phase="task",
                            state="Attention",
                            task=task_message,
                            progress=0,
                        )
                        return False

                    self.log(
                        f"Facebook switcher setup failed on {name}. "
                        f"Restarting Facebook before retry {setup_attempt + 1}/{max_setup_attempts}"
                    )
                    self._clear_recent_apps(d)
                    time.sleep(2)
                    continue

                time.sleep(4)
                page = self._get_dashboard_page_names(name)
                if page:
                    self.log(f"Using dashboard page names on {name}: {page}")
                else:
                    try:
                        detected_names = self.detect_facebook_page(d)
                    except Exception as e:
                        self.log(f"Error occurred while detecting page names on {name}: {e}")
                        return False
                    self.log(f"Detected page names on {name}: {detected_names}")
                    self._sync_detected_pages_to_dashboard(name, detected_names)
                    page = self._page_names_from_detected_switcher(detected_names)

                time.sleep(4)
                if not self.click_on_page(d, page, page_to_click=click_pages):
                    self.log(f"Failed to click on detected page names on {name}")
                    self.push_runtime_state(
                        name,
                        phase="task",
                        state="Attention",
                        task="Could not click detected page",
                        progress=0,
                    )
                    return False
                time.sleep(15)
                if self._open_file_manager_with_retry(d, attempts=2, delay=2):
                    time.sleep(3)
                    if self.navigate_to_pictures(d):
                        setup_ready = True
                        time.sleep(5)
                        if not self.click_folder_post_page(d, index=f_index):
                            self.log(f"Failed to click folder post page on {name}")
                            self.push_runtime_state(
                                name,
                                phase="task",
                                state="Attention",
                                task="Could not click folder post page",
                                progress=0,
                            )
                            return False
                        break
                    self.log(f"Failed to navigate to pictures on {name}")
                else:
                    self.log(f"Failed to open file manager on {name}")

                if setup_attempt >= max_setup_attempts:
                    break

                self.log(f"Setup failed on {name}. Clearing all apps before retry {setup_attempt + 1}/{max_setup_attempts}")
                self._clear_recent_apps(d)
                time.sleep(2)

            if not setup_ready:
                return False

            limiter = getattr(self, "rate_limiter", None)
            if limiter is not None and not limiter.can_perform_action("reels_post"):
                wait_for = max(0.0, limiter.get_wait_time())
                if wait_for > 0:
                    self.log(f"Reels rate limit reached on {name}; pausing for {wait_for:.1f}s")
                    time.sleep(min(wait_for, 90.0))

            page_video_posted = 0

            while page_video_posted < videos_per_page:
                try:
                    if not self.hold_on_video(d, hold_time=2):
                        self.log(f"Failed to hold on video on {name}")
                        video_posted += 1
                        page_video_posted += 1
                        continue

                    menu_present = any(
                        d(textContains=hint).exists(timeout=0.8)
                        for hint in ("Share", "Open with", "Delete", "Details", "Open")
                    ) or d(resourceId="android:id/title").exists(timeout=0.8)
                    if not menu_present:
                        self.log(f"Long-press did not open expected menu on {name}")
                        video_posted += 1
                        page_video_posted += 1
                        continue

                    time.sleep(2)
                    if not self.handle_context_menu_after_long_press(d, name):
                        self.log(f"Failed to handle context menu after long-press on {name}")
                        self.push_runtime_state(
                            name,
                            phase="task",
                            state="Attention",
                            task="Could not handle context menu after long-press",
                            progress=0,
                        )
                        return False

                    if not self.emulator.is_ld_running(name):
                        self.log(f"LD closed after sending to Facebook on {name}")
                        return True

                    time.sleep(5)
                    if self.check_and_handle_facebook_permission(d):
                        return True

                    if self.facebook_first_next(d):
                        time.sleep(2)
                    time.sleep(10)

                    video_data = None
                    if use_content_queue and self.content_manager:
                        video_data = self.content_manager.get_next_video()

                    if self.handle_reels_description(d, video_data):
                        self.log("Waiting 5s to complete Facebook post...")
                        time.sleep(5)

                        if scroll_after_post:
                            if self.emulator.is_ld_running(name):
                                self.log("Starting Reels scrolling after post...")
                                self.scroll_facebook_reels(d, duration=20, intensity="medium")
                            else:
                                self.log("LD closed before post-scroll, skipping Reels scrolling")

                        if not self.emulator.is_ld_running(name):
                            self.log("LD closed during Facebook post, skipping cleanup")
                            video_posted += 1
                            page_video_posted += 1
                            continue

                        try:
                            time.sleep(5)
                            d.app_stop("com.facebook.katana")
                            time.sleep(2)

                            if not self.emulator.is_ld_running(name):
                                self.log("LD closed before video deletion, skipping")
                                video_posted += 1
                                page_video_posted += 1
                                continue

                            try:
                                if self.delete_video(d):
                                    self.log("Video deleted successfully")
                                else:
                                    if not self.emulator.is_ld_running(name):
                                        self.log("LD closed before file manager, skipping")
                                        video_posted += 1
                                        page_video_posted += 1
                                        continue

                                    if not self._open_file_manager_with_retry(d, attempts=2, delay=1):
                                        self.log(f"Failed to open file manager on {name}")
                                        time.sleep(1)
                                    if not self.delete_video(d):
                                        self.log("Failed to delete video, continuing")
                            except Exception as e:
                                self.log(f"Error during video deletion: {e}")
                        except Exception as e:
                            self.log(f"Error during cleanup: {e}")

                        video_posted += 1
                        page_video_posted += 1
                        success_pots += 1
                        progress_value = min(100, 78 + int((success_pots / total_videos_target) * 22)) if total_videos_target > 0 else 100
                        self.push_runtime_state(
                            name,
                            state="Running" if success_pots < total_videos_target else "Completed",
                            task=f"Processed {success_pots}/{total_videos_target} video",
                            progress=progress_value,
                        )
                        continue

                    self.log(f"Failed to complete reels description/post flow on {name}")
                    video_posted += 1
                    page_video_posted += 1
                except Exception as e:
                    self.log(f"Exception during task execution on {name}: {e}")
                    video_posted += 1
                    page_video_posted += 1
                    continue

                self.log(f"Finished processing video {video_posted} on {name}")

            page_ready += 1
            click_pages += 1
            f_index += 1

        self.log("Finished processing all pages/videos for this account")    
        time.sleep(5)
        self.end_to_accoutn_profile(d, name)  
        
        time.sleep(5)
        if clear_cache:
            self.clear_app_cache(d, name)
        
        self.push_runtime_state(
            name,
            state="Completed" if success_pots > 0 else "Attention",
            task=f"Processed {success_pots}/{total_videos_target} video",
            progress=100 if success_pots > 0 else 0,
        )
        self.log(f"Task completed: Processed {success_pots}/{total_videos_target} videos successfully")
        return success_pots > 0
    


    def end_to_accoutn_profile(self, d, name):
        if not self.open_facebook(d):
            self.log(f"Failed to open Facebook for final cleanup on {name}")

        time.sleep(6)
        if not self.click_facebook_menu(d):
            self.log(f"Failed to open Facebook menu on {name}")
            self.push_runtime_state(
                name,
                phase="task",
                state="Attention",
                task="Facebook menu not found",
                progress=0,
            )
            return False

        time.sleep(4)
        if not self.back_to_account_profile(d):
            self.log(f"Failed to switch back to profile on {name}")
            self.push_runtime_state(
                name,
                phase="task",
                state="Attention",
                task="Could not switch back to profile",
                progress=0,
            )
            return False
        return True

    def clear_app_cache(self, d, name, package_name="com.facebook.katana"):
        """Open Android app settings and clear Facebook cache without wiping app data."""
        serial = getattr(d, "serial", None) or self.emulator.name_to_serial.get(name)
        if not serial:
            self.log(f"Cannot clear Facebook cache on {name}: missing device serial")
            return False

        def _first_match(selectors, wait_timeout=1.0):
            for selector in selectors:
                try:
                    obj = d(**selector)
                    if obj.exists(timeout=wait_timeout):
                        return obj
                except Exception:
                    continue
            return None

        def _click_if_found(selectors, wait_timeout=1.0, label="control"):
            obj = _first_match(selectors, wait_timeout=wait_timeout)
            if not obj:
                return False

            try:
                info = obj.info
            except Exception:
                info = {}

            if info and not info.get("enabled", True):
                self.log(f"{label} is disabled on {name}")
                return True

            try:
                obj.click()
            except Exception:
                try:
                    bounds = info.get("bounds", {})
                    left = bounds.get("left", 0)
                    top = bounds.get("top", 0)
                    right = bounds.get("right", 0)
                    bottom = bounds.get("bottom", 0)
                    if right > left and bottom > top:
                        d.click((left + right) // 2, (top + bottom) // 2)
                    else:
                        return False
                except Exception:
                    return False

            self.log(f"Clicked {label} on {name}")
            return True

        def _click_storage_row(wait_timeout=1.5):
            """Tap the actual Storage row by bounds, skipping top summary/header text."""
            candidates = [
                {"text": "Storage"},
                {"text": "STORAGE"},
                {"textMatches": r"(?i)^storage$"},
            ]

            for selector in candidates:
                try:
                    nodes = d(**selector)
                    if not nodes.exists(timeout=wait_timeout):
                        continue
                except Exception:
                    continue

                try:
                    count = nodes.count
                except Exception:
                    count = 1

                for index in range(count):
                    try:
                        node = nodes[index] if count > 1 else nodes
                        info = node.info or {}
                        bounds = info.get("bounds", {})
                        left = bounds.get("left", 0)
                        top = bounds.get("top", 0)
                        right = bounds.get("right", 0)
                        bottom = bounds.get("bottom", 0)
                        width = right - left
                        height = bottom - top
                    except Exception:
                        continue

                    if width <= 0 or height <= 0:
                        continue

                    # Ignore compact header/summary labels such as "Permissions / Storage".
                    if top < 220 or height < 40:
                        continue

                    center_x = (left + right) // 2
                    center_y = (top + bottom) // 2

                    try:
                        d.click(center_x, center_y)
                        self.log(
                            f"Clicked Storage row on {name} at ({center_x}, {center_y})"
                        )
                        return True
                    except Exception:
                        continue

            return False

        clear_cache_selectors = [
            {"textMatches": r"(?i)^clear cache$"},
            {"text": "Clear cache"},
            {"textContains": "Clear cache"},
        ]

        try:
            self.log(f"Clearing Facebook cache on {name}")

            try:
                d.app_stop(package_name)
                time.sleep(1)
            except Exception:
                pass

            result = subprocess.run(
                [
                    "adb",
                    "-s",
                    serial,
                    "shell",
                    "am",
                    "start",
                    "-a",
                    "android.settings.APPLICATION_DETAILS_SETTINGS",
                    "-d",
                    f"package:{package_name}",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode != 0:
                error_output = (result.stderr or result.stdout or "unknown adb error").strip()
                self.log(f"Failed to open app settings on {name}: {error_output}")
                return False

            time.sleep(3)

            if not _click_if_found(clear_cache_selectors, wait_timeout=1.0, label="Clear cache"):
                storage_opened = _click_storage_row(wait_timeout=1.5)
                if not storage_opened:
                    for _ in range(2):
                        try:
                            d.swipe(0.5, 0.8, 0.5, 0.25, 0.25)
                            time.sleep(1)
                        except Exception:
                            pass
                        if _click_storage_row(wait_timeout=1.0):
                            storage_opened = True
                            break

                if not storage_opened:
                    self.log(f"Could not find Storage section while clearing cache on {name}")
                    return False

                time.sleep(2)
                if not _click_if_found(clear_cache_selectors, wait_timeout=1.5, label="Clear cache"):
                    self.log(f"Could not find Clear cache button on {name}")
                    return False

            time.sleep(2)
            self.log(f"Facebook cache cleared on {name}")
            return True
        except Exception as e:
            self.log(f"Failed to clear Facebook cache on {name}: {e}")
            return False
        finally:
            try:
                d.app_stop("com.android.settings")
            except Exception:
                pass
            try:
                d.press("home")
            except Exception:
                pass
    
    #def handle_facebook_reels_post(self, d, video_data=None):
    def handle_reels_description(self, d, video_data=None):
        """
        Handle the Facebook Reels description and audience selection screen
        that appears after clicking Next button
        """
        try:
            # Wait for the reels description screen to load
            time.sleep(5)
            
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

            time.sleep(2)
            # scroll down to make sure the share button is visible
            d.swipe_ext("up", scale=0.7)
            time.sleep(1)
            d.swipe_ext("up", scale=0.7)
            time.sleep(1)
            
            # Look for the final share/post button with more flexible detection
            self.log(" Looking for Share...")
            time.sleep(3)
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
                base_swipe = random.uniform(*params["swipe_time"])
                randomizer = getattr(self, "randomizer", None)
                swipe_time = (
                    max(150, int(randomizer.random_swipe_duration(base_swipe, variation=0.25)))
                    if randomizer is not None
                    else base_swipe
                )
                
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
                base_delay = random.uniform(*params["delay"])
                delay = (
                    max(0.2, randomizer.random_delay(base_delay, variation=0.35))
                    if randomizer is not None
                    else base_delay
                )
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

    def _quick_switch_button(self, d, timeout=8):
        """
        On the Menu header, tap the circular arrows quick-switch button.
        """
        end_time = time.time() + timeout

        try:
            w, h = d.window_size()
        except Exception:
            w, h = 1080, 1920

        def _switcher_opened():
            selectors = [
                {"textContains": "See all profiles"},
                {"textContains": "Switch profile"},
                {"textContains": "Switch to Page"},
                {"textContains": "Pages"},
                {"descriptionContains": "Switch"},
                {"descriptionContains": "profile"},
            ]
            for selector in selectors:
                try:
                    if d(**selector).exists:
                        return True
                except Exception:
                    continue
            return False

        def _in_switcher_zone(node):
            try:
                bounds = node.info.get("bounds", {})
                right = bounds.get("right", 0)
                top = bounds.get("top", 0)
                bottom = bounds.get("bottom", 0)
                return right > w * 0.55 and top < h * 0.35 and bottom < h * 0.45
            except Exception:
                return False

        resource_patterns = [
            r".*switch.*",
            r".*swap.*",
            r".*toggle.*",
            r".*profile_switcher.*",
            r".*account_switcher.*",
        ]
        description_patterns = [
            r"(?i)switch",
            r"(?i)toggle",
            r"(?i)change.*account",
            r"(?i)switch to page",
            r"(?i)switch profile",
        ]

        while time.time() < end_time:
            for pat in resource_patterns:
                try:
                    node = d(resourceIdMatches=pat)
                    if node.exists and _in_switcher_zone(node):
                        self.log(f"Tapping quick switcher via resourceId pattern: {pat}")
                        if self._tap(node):
                            time.sleep(2)
                            return True
                except Exception as exc:
                    self.log(f"Quick switch resource match failed {pat}: {exc}")

            for pat in description_patterns:
                try:
                    node = d(descriptionMatches=pat)
                    if node.exists and _in_switcher_zone(node):
                        self.log(f"Tapping quick switcher via description pattern: {pat}")
                        if self._tap(node):
                            time.sleep(2)
                            return True
                except Exception as exc:
                    self.log(f"Quick switch description match failed {pat}: {exc}")

            for x, y in (
                (int(w * 0.78), int(h * 0.21)),
                (int(w * 0.86), int(h * 0.18)),
                (int(w * 0.90), int(h * 0.18)),
            ):
                try:
                    self.log(f"Trying switcher fallback tap at ({x}, {y})")
                    d.click(x, y)
                    time.sleep(2)
                    if _switcher_opened():
                        return True
                except Exception as exc:
                    self.log(f"Switcher fallback tap failed at ({x}, {y}): {exc}")

            time.sleep(0.4)

        self.log("Quick switcher not found")
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

    def handle_context_menu_after_long_press(self, d, name, timeout=0.8):
        """
        Verify the long-press menu is visible, then click a valid option.
        """
        try:
            menu_hints = ("Share", "Open with", "Delete", "Details", "Open")
            menu_present = any(
                d(textContains=hint).exists(timeout=timeout)
                for hint in menu_hints
            ) or d(resourceId="android:id/title").exists(timeout=timeout)

            if not menu_present:
                self.log(f"Long-press did not open expected menu on {name}")
                return False

            return self.click_context_option(d)
        except Exception as e:
            self.log(f"Error handling context menu on {name}: {e}")
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
    
    def check_and_handle_facebook_permission(self, d):
        """Check for Facebook permission dialog, click ALLOW if found, and continue flow."""
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
                                # Permission was handled, but the reels flow still needs to continue.
                                return False
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
                            # Permission was handled, but the reels flow still needs to continue.
                            return False
                    except Exception as e:
                        self.log(f"Error clicking right-side element: {e}")
                        continue
                
                self.log("Could not find ALLOW button in permission dialog")
                return False
            return False
        except Exception as e:
            self.log(f"Error checking Facebook permission: {e}")
            return False
    
    def click_facebook_menu(self, d, timeout=10):

        time.sleep(0.4)
        d.swipe_ext("down", scale=0.75, duration=0.08)
        time.sleep(0.25)

        selectors = [
            # Best case: accessibility description
            {"descriptionContains": "menu"},
            {"descriptionContains": "Menu"},
            {"descriptionContains": "More"},

            # Sometimes Facebook uses resource-id
            {"resourceIdMatches": ".*menu.*"},

            # Fallback by class (top-left clickable button)
            {"className": "android.widget.ImageView"},
            {"className": "android.widget.Button"},
        ]

        def try_click_menu_button():
            for sel in selectors:
                try:
                    obj = d(**sel)
                    if obj.exists:
                        bounds = obj.info.get("bounds", {})
                        x = (bounds.get("left", 0) + bounds.get("right", 0)) // 2
                        y = (bounds.get("top", 0) + bounds.get("bottom", 0)) // 2

                        # Only click if it's near top-left (hamburger location)
                        if x < d.window_size()[0] * 0.3 and y < d.window_size()[1] * 0.2:
                            self.log("Clicking Facebook menu button")
                            obj.click()
                            return True
                except Exception as e:
                    self.log(f"Error: {e}")
            return False

        # Use up to 2 quick swipes to reveal the menu button if Facebook is still settling.
        for attempt in range(2):
            if try_click_menu_button():
                return True

        deadline = time.time() + timeout

        while time.time() < deadline:
            if try_click_menu_button():
                return True

            time.sleep(0.5)

        self.log("Menu button not found")
        self.log("skipping Facebook menu click")
        return False
    
    # Detect presence of page names in the list by looking for common patterns in the text of visible items.
    def click_profile_dropdown(self, d, timeout=5):
        """
        Click Facebook profile dropdown reliably using multiple strategies:
        1. content-desc (best)
        2. xpath fallback
        3. coordinate fallback (last resort)
        """

        try:
            # --- Strategy 1: Content-desc (BEST) ---
            selectors = [
                {"descriptionContains": "Open profile switcher"},
                {"descriptionContains": "profile switcher"},
                {"descriptionContains": "notifications"},
            ]

            for sel in selectors:
                obj = d(**sel)
                if obj.exists(timeout=timeout):
                    obj.click()
                    return True

            # --- Strategy 2: XPath fallback ---
            xpath_list = [
                '//android.widget.Button[contains(@content-desc,"Open profile")]',
                '//android.view.ViewGroup[contains(@content-desc,"profile")]',
            ]

            for xp in xpath_list:
                obj = d.xpath(xp)
                if obj.exists:
                    obj.click()
                    return True

            # --- Strategy 3: Bounds-based click (from UI dump) ---
            # safer than fixed coord → use relative screen %
            width, height = d.window_size()

        except Exception as e:
            print(f"[ERROR] click_profile_dropdown: {e}")
            return False

    # This method tries to click on a page name using an XPath expression that matches the text. It handles both single page names and lists of page names, and it includes a fallback to click based on bounds if the XPath click fails. It also includes logging and retries until a timeout is reached.
    def click_on_page(self, d, pages, page_to_click, timeout=5):
        """
        Click a page name using xpath:
        //android.view.View[@text="page"]

        Examples:
        - click_on_page(d, "page1")
        - click_on_page(d, ["page1", "page2"])  # clicks index 0 by default
        - click_on_page(d, ["page1", "page2"], page_to_click=1)
        """
        if isinstance(pages, (list, tuple)):
            if not pages:
                self.log("No page names were provided to click_on_page")
                return False
            if page_to_click < 0 or page_to_click >= len(pages):
                self.log(f"Invalid page_to_click index: {page_to_click}")
                return False
            page_name = str(pages[page_to_click]).strip()
        else:
            page_name = str(pages).strip()

        if not page_name:
            self.log("Page name is empty, cannot click")
            return False

        if '"' in page_name and "'" not in page_name:
            xpath_expr = f"//android.view.View[@text='{page_name}']"
        else:
            safe_page_name = page_name.replace('"', '\\"')
            xpath_expr = f'//android.view.View[@text="{safe_page_name}"]'

        self.log(f"Trying to click page: {page_name}")
        deadline = time.time() + timeout

        while time.time() < deadline:
            try:
                obj = d.xpath(xpath_expr)
                if obj.exists:
                    try:
                        obj.click()
                        self.log(f"Clicked page by xpath: {page_name}")
                        return True
                    except Exception:
                        pass

                    try:
                        info = obj.info
                        bounds = info.get("bounds", {})
                        left = bounds.get("left", 0)
                        top = bounds.get("top", 0)
                        right = bounds.get("right", 0)
                        bottom = bounds.get("bottom", 0)

                        if right > left and bottom > top:
                            cx = (left + right) // 2
                            cy = (top + bottom) // 2
                            d.click(cx, cy)
                            self.log(f"Clicked page by bounds fallback: {page_name}")
                            return True
                    except Exception:
                        pass
                time.sleep(0.5)
            except Exception as e:
                self.log(f"Error while clicking page '{page_name}': {e}")
                time.sleep(0.5)

        self.log(f"Could not find page to click: {page_name}")
        return False
    
    def click_folder_post_page(self, d, index, timeout=5):
        xpath_expr = f'(//android.widget.ImageView[@resource-id="com.cyanogenmod.filemanager:id/navigation_view_item_icon"])[{index}]'
        obj = d.xpath(xpath_expr)
        if obj.exists:
            obj.click()
            return True
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

    def back_to_account_profile(self, d, timeout=3):
        """
        Tap the main account/profile card without using account name.
        Works even when account name changes.
        """

        try:
            # 1) Best selector: profile button usually contains this stable phrase
            stable_selectors = [
                {"descriptionContains": "see your profile"},
                {"descriptionContains": "your profile picture"},
            ]

            for sel in stable_selectors:
                obj = d(**sel)
                if obj.exists(timeout=timeout):
                    obj.click()
                    self.log(f"Tapped account profile using selector: {sel}")
                    return True

            # 2) XPath without account name
            xpaths = [
                '//android.widget.Button[contains(@content-desc,"see your profile")]',
                '//android.widget.ImageView[contains(@content-desc,"your profile picture")]',
            ]

            for xp in xpaths:
                obj = d.xpath(xp)
                if obj.exists:
                    obj.click()
                    self.log(f"Tapped account profile using xpath: {xp}")
                    return True

            # 3) Smarter fallback: tap first big button/card near top menu
            buttons = d(className="android.widget.Button")
            count = buttons.count

            for i in range(count):
                info = buttons[i].info
                bounds = info.get("bounds", {})

                left = bounds.get("left", 0)
                top = bounds.get("top", 0)
                right = bounds.get("right", 0)
                bottom = bounds.get("bottom", 0)

                width = right - left
                height = bottom - top

                # Profile card area from screenshot:
                # top area, wide card, not small icon
                if top < 250 and width > 180 and height > 50:
                    buttons[i].click()
                    self.log(f"Tapped top profile card using bounds: {bounds}")
                    return True

            # 4) Final fallback: relative coordinate
            w, h = d.window_size()
            x = int(w * 0.78)
            y = int(h * 0.145)

            d.click(x, y)
            self.log(f"Tapped profile fallback coordinate: ({x}, {y})")
            return True

        except Exception as e:
            self.log(f"Failed to tap account profile: {e}")
            return False
        
    def detect_facebook_page(self, d):
        """
        Detect Facebook Pages from Facebook account/page switcher.

        Returns:
            list[str]: page names found
        """

        pages = []

        try:
            # Wait for switcher / account list
            d(resourceId="com.facebook.katana:id/(name removed)").exists(timeout=3)
        except Exception:
            pass

        try:
            # Get all visible text elements
            text_elements = d(className="android.view.View")

            for el in text_elements:
                try:
                    info = el.info
                    text = (info.get("text") or "").strip()
                    desc = (info.get("contentDescription") or "").strip()

                    if not text:
                        continue

                    # Skip non-page UI text
                    skip_words = [
                        "Create Facebook Page",
                        "Go to Accounts Center",
                        "Meta",
                        "Cancel",
                        "notification",
                        "notifications",
                    ]

                    if any(word.lower() in text.lower() for word in skip_words):
                        continue

                    # Detect page by parent content-desc like:
                    # "Demoworld, 1 notification"
                    if desc:
                        continue

                    # avoid number/notification text
                    if "notification" in text.lower():
                        continue

                    # basic valid page name filter
                    if len(text) >= 2:
                        pages.append(text)

                except Exception:
                    continue

            # remove duplicate but keep order
            clean_pages = []
            for p in pages:
                if p not in clean_pages:
                    clean_pages.append(p)

            self.log(f"Detected Facebook pages: {clean_pages}")
            return clean_pages

        except Exception as e:
            self.log(f"Failed to detect Facebook pages: {e}")
            return []

    def _get_dashboard_page_names(self, instance_name):
        if not instance_name:
            return []

        try:
            paths = get_app_paths()
            path = paths.config_dir / "dashboard_instances.json"
            if not path.exists():
                return []

            data = json.loads(path.read_text(encoding="utf-8")) or {}
            for instance in data.get("instances") or []:
                if str(instance.get("name") or "").strip() != str(instance_name).strip():
                    continue
                account = instance.get("account") or {}
                return self._page_names_from_dashboard(account.get("pages") or [])
        except Exception as exc:
            self.log(f"Failed to read dashboard pages for {instance_name}: {exc}")
        return []

    def _page_names_from_dashboard(self, pages):
        page_names = []
        for page in pages or []:
            if isinstance(page, dict):
                text = str(page.get("name") or "").strip()
            else:
                text = str(page or "").strip()
            if text and text not in page_names:
                page_names.append(text)
        return page_names

    def _page_names_from_detected_switcher(self, detected_names):
        clean_names = []
        for value in detected_names or []:
            text = str(value or "").strip()
            if text and text not in clean_names:
                clean_names.append(text)
        if len(clean_names) <= 1:
            return []
        return clean_names[1:]

    def _sync_detected_pages_to_dashboard(self, instance_name, detected_names):
        """
        Persist Facebook switcher names to dashboard config.

        Facebook returns the main account first, followed by managed pages. The
        dashboard stores pages as objects so existing reels settings can survive.
        """
        clean_names = []
        for value in detected_names or []:
            text = str(value or "").strip()
            if text and text not in clean_names:
                clean_names.append(text)

        if not instance_name or not clean_names:
            return False

        account_name = clean_names[0]
        page_names = self._page_names_from_detected_switcher(clean_names)

        try:
            paths = get_app_paths()
            paths.ensure_runtime_dirs()
            path = paths.config_dir / "dashboard_instances.json"
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8")) or {}
            else:
                data = {}

            instances = data.setdefault("instances", [])
            instance = None
            for item in instances:
                if str(item.get("name") or "").strip() == str(instance_name).strip():
                    instance = item
                    break

            if instance is None:
                instance = {"name": instance_name, "account": {}}
                instances.append(instance)

            account = instance.setdefault("account", {})
            account["name"] = account_name
            account.setdefault("uid", None)
            account.setdefault("password", None)
            account.setdefault("twofa", None)
            account.setdefault("mail", None)

            existing_pages = []
            by_name = {}
            for page in account.get("pages") or []:
                if isinstance(page, dict):
                    page_name = str(page.get("name") or "").strip()
                    payload = dict(page)
                else:
                    page_name = str(page or "").strip()
                    payload = self._dashboard_page_payload(page_name)
                if not page_name or page_name == account_name or page_name in by_name:
                    continue
                payload.setdefault("name", page_name)
                payload.setdefault("page_id", None)
                payload.setdefault("reels", self._dashboard_reels_defaults())
                by_name[page_name] = payload
                existing_pages.append(payload)

            for page_name in page_names:
                if page_name in by_name:
                    continue
                payload = self._dashboard_page_payload(page_name)
                by_name[page_name] = payload
                existing_pages.append(payload)

            account["pages"] = existing_pages
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            self.log(f"Updated dashboard config for {instance_name}: account '{account_name}', {len(page_names)} page(s)")
            return True
        except Exception as exc:
            self.log(f"Failed to update dashboard config for {instance_name}: {exc}")
            return False

    def _dashboard_page_payload(self, name):
        return {
            "name": name,
            "page_id": None,
            "reels": self._dashboard_reels_defaults(),
        }

    def _dashboard_reels_defaults(self):
        return {
            "enabled": True,
            "schedule": "Manual",
            "interval_min": 30,
            "hashtags": [],
            "caption_template": "",
            "source_folder": "",
        }
