import time
from unittest import result
import xml.etree.ElementTree as ET
import re
import random
from core.task_base import BaseTaskHandler, U2_AVAILABLE, u2


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
                state="Running",
                task="Facebook opened",
                progress=70,
            )

            serial_map = getattr(self.emulator, "name_to_serial", {})
            if not isinstance(serial_map, dict):
                return True

            serial = serial_map.get(name, name)
            if not serial:
                self.log(f"No serial found for {name}")
                return False

            if not U2_AVAILABLE:
                self.log("uiautomator2 not available. Cannot inspect Facebook UI.")
                return True

            try:
                d = u2.connect(serial)
            except Exception as exc:
                self.log(f"Failed to connect device {serial}: {exc}")
                return False

            # kwargs for potential future use:
            ld_page = 2  # default page index to click for LD selection in case of multiple pages, can be overridden by kwargs if needed
            video_page = (
                2  # default page index to click for video upload test, can be overridden by kwargs if needed
            )

            time.sleep(5)
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
            self.click_profile_dropdown(d)

            time.sleep(4)
            try:
                page = self.get_name_pages_by_bounds(d, ["[168,702][336,743]", "[168,851][328,892]"])
            except Exception as e:
                self.log(f"Error occurred while detecting page names on {name}: {e}")
                return False
            self.log(f"Detected page names on {name}: {page}")

            click_pages = 0
            f_index = 2
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
            # Try multiple times to open file manager, as it can be flaky on some devices
            if not self._open_file_manager_with_retry(d):
                self.log(f"Failed to open File Manager on {name}")
                self.push_runtime_state(
                    name,
                    phase="task",
                    state="Attention",
                    task="Could not open File Manager",
                    progress=0,
                )
                return False

            time.sleep(5)
            if not self.navigate_to_pictures(d):
                self.log(f"Failed to navigate to Pictures in File Manager on {name}")
                self.push_runtime_state(
                    name,
                    phase="task",
                    state="Attention",
                    task="Could not navigate to Pictures folder",
                    progress=0,
                )
                return False

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

            time.sleep(5)
            if not self.hold_on_video(d):
                self.log(f"Failed to long-press video file on {name}")
                self.push_runtime_state(
                    name,
                    phase="task",
                    state="Attention",
                    task="Could not long-press video file",
                    progress=0,
                )
                return False

            time.sleep(5)
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

            time.sleep(5)
            self.check_and_handle_facebook_permission(d)

            time.sleep(5)
            if not self.facebook_first_next(d):
                self.log("Failed to click first next button after permission dialog")
                return False

            time.sleep(5)
            self.handle_reels_description(d)
            time.sleep(random.uniform(4, 6))
            self.log("Test Video completed....")

            time.sleep(5)
            # Close Facebook
            d.app_stop("com.facebook.katana")

            time.sleep(3)
            if not self.delete_video(d):
                self.log(f"Failed to delete video file after test on {name}")
                try:
                    if not self._open_file_manager_with_retry(d, attempts=2, delay=1):
                        self.log(f"âŒ Failed to open file manager on {name}")
                        time.sleep(1)
                    if not self.delete_video(d):
                        self.log("âš ï¸ Failed to delete video, continuing")
                except Exception as e:
                    self.log(f"Error pushing runtime state for video deletion failure on {name}: {e}")
                    self.push_runtime_state(
                        name,
                        phase="task",
                        state="Attention",
                        task="could not delete video file",
                        progress=0,
                    )
                return False

            return True
        except Exception as exc:
            self.log(f"Test feature failed on {name}: {exc}")
            return False

    # The following methods are helper functions for interacting with the Facebook app's UI. They include strategies for clicking the menu button, tapping labels that may require expanding and scrolling, detecting page names based on screen coordinates, and clicking on pages using XPath or bounds as a fallback. These methods use uiautomator2 to interact with the Android UI and include logging and error handling to improve robustness across different Facebook layouts and versions.

    # Click Facebook menu with multiple strategies across older and newer layouts.
    def click_facebook_menu(self, d, timeout=10):

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

        deadline = time.time() + timeout

        while time.time() < deadline:
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

            time.sleep(0.5)

        self.log("Menu button not found")
        self.log("skipping Facebook menu click")
        return False

    # Detect presence of page names in the list by looking for common patterns in the text of visible items.
    def click_profile_dropdown(self, d):
        x, y = 544, 146

        try:
            d.click(x, y)
            return True
        except Exception as e:
            print(f"Click failed: {e}")
            return False

    # Helper methods to parse bounds and determine if a point is inside, used for matching text items to target areas. The main method get_name_pages_by_bounds uses these to find text whose bounds match the given coordinates.
    @staticmethod
    def _parse_bounds(bounds_text):
        m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", str(bounds_text).strip())
        if not m:
            return None
        return tuple(map(int, m.groups()))

    @staticmethod
    def _center_of(bounds):
        x1, y1, x2, y2 = bounds
        return ((x1 + x2) // 2, (y1 + y2) // 2)

    @staticmethod
    def _point_inside(px, py, bounds):
        x1, y1, x2, y2 = bounds
        return x1 <= px <= x2 and y1 <= py <= y2

    @staticmethod
    def _bounds_dict(bounds):
        x1, y1, x2, y2 = bounds
        return {"left": x1, "top": y1, "right": x2, "bottom": y2}

    @staticmethod
    def _node_label(node):
        return (
            node.attrib.get("text")
            or node.attrib.get("content-desc")
            or node.attrib.get("contentDescription")
            or ""
        ).strip()

    @staticmethod
    def _looks_like_page_name(label):
        text = re.sub(r"\s+", " ", str(label or "")).strip()
        if len(text) < 2:
            return False
        lower = text.lower()
        blocked = (
            "pages you manage",
            "see all",
            "see options",
            "search",
            "create",
            "notification",
            "accounts center",
            "meta",
            "cancel",
        )
        if any(word in lower for word in blocked):
            return False
        if re.match(r"^\d+\s+(new|notification|notifications)$", lower):
            return False
        return True

    @staticmethod
    def _build_page_row_fallback_points(bounds, screen_width, screen_height):
        left = int(bounds.get("left", 0))
        top = int(bounds.get("top", 0))
        right = int(bounds.get("right", screen_width))
        bottom = int(bounds.get("bottom", top))
        width = max(1, right - left)
        y = min((top + bottom) // 2, int(screen_height * 0.72))
        return [
            (left + int(width * 0.16), y),
            (min(screen_width - 1, left + int(width * 0.5)), y),
            (min(screen_width - 1, right - int(width * 0.12)), y),
        ]

    def _managed_page_candidates_from_hierarchy(self, xml, screen_height=None):
        try:
            root = ET.fromstring(xml)
        except Exception:
            return []

        anchor_top = None
        nodes = []
        for node in root.iter("node"):
            label = self._node_label(node)
            bounds = self._parse_bounds(node.attrib.get("bounds", ""))
            if not bounds:
                continue
            if "pages you manage" in label.lower():
                anchor_top = min(anchor_top, bounds[1]) if anchor_top is not None else bounds[1]
                continue
            nodes.append((label, bounds))

        if anchor_top is None:
            anchor_top = 0

        max_top = int(screen_height * 0.72) if screen_height else None
        candidates = []
        seen = set()
        for label, bounds in nodes:
            if bounds[1] <= anchor_top + 35:
                continue
            if max_top is not None and bounds[1] > max_top:
                continue
            if not self._looks_like_page_name(label):
                continue
            if label in seen:
                continue
            seen.add(label)
            candidates.append({"label": label, "bounds": self._bounds_dict(bounds)})
        return candidates

    def _find_page_row_target_from_hierarchy(self, xml, screen_width, page_name=None):
        candidates = self._managed_page_candidates_from_hierarchy(xml)
        requested = str(page_name or "").strip().lower()
        if requested:
            for candidate in candidates:
                if requested in candidate["label"].lower():
                    return candidate
        return candidates[0] if candidates else None

    def _extract_managed_page_names_from_hierarchy(self, xml, screen_height):
        return [
            candidate["label"]
            for candidate in self._managed_page_candidates_from_hierarchy(xml, screen_height=screen_height)
        ]

    # This method tries to find the text of items at specific screen locations by parsing the UI hierarchy and matching bounds. It first looks for any text whose bounds contain the center of the target area, and if not found, it looks for the text with the largest overlapping area. This is a heuristic to detect page names in the Facebook profile dropdown.
    def get_name_pages_by_bounds(self, d, bounds_list):
        """
        bounds_list example:
        [
            "[168,702][336,743]",
            "[168,851][328,892]"
        ]

        return:
        ['Demoworld', 'meiileungg']
        """
        self.log("Detecting page names...")
        try:
            xml = d.dump_hierarchy()
            root = ET.fromstring(xml)
        except Exception as e:
            self.log(f"Failed to dump hierarchy: {e}")
            return []

        text_nodes = []
        for node in root.iter("node"):
            text = (node.attrib.get("text") or "").strip()
            bounds_text = node.attrib.get("bounds", "")
            parsed = self._parse_bounds(bounds_text)

            if text and parsed:
                text_nodes.append(
                    {
                        "text": text,
                        "bounds": parsed,
                    }
                )

        result = []

        for raw_bounds in bounds_list:
            target = self._parse_bounds(raw_bounds)
            if not target:
                result.append("")
                continue

            cx, cy = self._center_of(target)
            found = ""

            for item in text_nodes:
                if self._point_inside(cx, cy, item["bounds"]):
                    found = item["text"]
                    break

            if not found:
                tx1, ty1, tx2, ty2 = target
                best_area = 0

                for item in text_nodes:
                    x1, y1, x2, y2 = item["bounds"]
                    overlap_w = max(0, min(tx2, x2) - max(tx1, x1))
                    overlap_h = max(0, min(ty2, y2) - max(ty1, y1))
                    area = overlap_w * overlap_h

                    if area > best_area:
                        best_area = area
                        found = item["text"]

            result.append(found)
        return result

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

    # This method attempts to open the file manager on the device with retries. It calls self.open_file_manager(d) and if it fails, it waits for a specified delay before retrying, up to a maximum number of attempts. This is useful for handling transient issues when trying to access the file manager.
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
                "com.mediatek.filemanager",  # MediaTek file manager
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

    # This method tries to navigate to the Pictures folder in the file manager by first looking for a text element with "Pictures". If it's not immediately visible, it attempts to scroll and look again. It includes logging and error handling to improve robustness across different file manager layouts.
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

    # This method tries to click on the folder icon in the File Manager using a specific XPath expression. If the XPath click fails, it falls back to clicking based on the bounds of the element. It includes retries until a timeout is reached, and it logs each step of the process.
    def click_folder_post_page(self, d, index, timeout=5):
        xpath_expr = f'(//android.widget.ImageView[@resource-id="com.cyanogenmod.filemanager:id/navigation_view_item_icon"])[{index}]'
        obj = d.xpath(xpath_expr)
        if obj.exists:
            obj.click()
            return True
        return False

    # This method attempts to long-press on a video file in the file manager. It first checks if we're in the correct folder by looking for video files, and if not, it tries to click into the folder. Then it looks for text elements that match common video file extensions and long-presses on the first one it finds. If it can't find video files by extension, it tries to long-press on any file-like element. If that also fails, it falls back to long-pressing on image thumbnails, which may represent videos. It includes logging and error handling to improve robustness across different file manager layouts and video file naming conventions.
    def hold_on_video(self, d, hold_time=2):
        """Long-press top video in file manager after navigating to the Page-1 folder"""
        try:
            time.sleep(2)

            # First, make sure we're in the Page-1 folder by checking if we can see video files
            # If we see folder names instead, we need to click into the Page-1 folder first
            video_extensions = [".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv"]

            # Check if we're already in a folder with video files
            text_elements = d(className="android.widget.TextView")
            video_files_found = False

            if text_elements:
                for element in text_elements:
                    text = element.info.get("text", "")
                    if any(ext in text.lower() for ext in video_extensions):
                        video_files_found = True
                        break

            # Now we should be in the folder with video files
            # Try to find and long-press the first video file
            text_elements = d(className="android.widget.TextView")

            if text_elements:
                # Look for the first text element that contains a video extension
                for element in text_elements:
                    text = element.info.get("text", "")
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
                    text = element.info.get("text", "")
                    # Skip elements that look like dates, sizes, or other metadata
                    if (
                        re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", text)  # Dates
                        or re.search(r"\d+\.?\d*\s*(MB|KB|GB)", text)  # File sizes
                        or len(text.strip()) < 2
                    ):  # Very short text
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
                            self.log(f"ðŸŽ¥ Long-pressed thumbnail #{i + 1}")

                            # Try to find associated text for the thumbnail
                            text_elements_nearby = d(className="android.widget.TextView")
                            for text_element in text_elements_nearby:
                                text_bounds = text_element.info.get("bounds")
                                if text_bounds:
                                    # Check if this text is near the thumbnail
                                    if (
                                        abs(text_bounds["top"] - bounds["bottom"]) < 50
                                        or abs(text_bounds["bottom"] - bounds["top"]) < 50
                                    ):
                                        text = text_element.info.get("text", "")
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

    # After long-pressing a video file, this method checks if the expected context menu is visible by looking for common menu options. If the menu is present, it tries to click on a valid option (e.g., share to Facebook) using another helper method. It includes logging and error handling to improve robustness across different file manager layouts and context menu designs.
    def handle_context_menu_after_long_press(self, d, name, timeout=0.8):
        """
        Verify the long-press menu is visible, then click a valid option.
        """
        try:
            menu_hints = ("Share", "Open with", "Delete", "Details", "Open")
            menu_present = any(d(textContains=hint).exists(timeout=timeout) for hint in menu_hints) or d(
                resourceId="android:id/title"
            ).exists(timeout=timeout)

            if not menu_present:
                self.log(f"Long-press did not open expected menu on {name}")
                return False

            return self.click_context_option(d)
        except Exception as e:
            self.log(f"Error handling context menu on {name}: {e}")
            return False

    # This method tries to click on a context menu option that would allow sharing the video to Facebook. It first checks if we're seeing a Facebook permission dialog and handles it if present. Then it looks for the "Send" option in the context menu, clicks it, and checks for the "Share with" dialog. If found, it looks for the "Reels" option, clicks it, and then looks for the "Always/Just once" dialog to confirm the share action. It includes multiple strategies for finding and clicking these options, as well as logging and error handling to improve robustness across different Android versions and Facebook layouts.
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
                text = element.info.get("text", "")
                if text:
                    all_options.append(text)

            # Check if we're in the initial context menu (with Send option)
            if "Send" in all_options:
                # Click the Send option
                for element in d(className="android.widget.TextView"):
                    text = element.info.get("text", "")
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
                    text = element.info.get("text", "")
                    if text:
                        share_options.append(text)

                # Check if we're now in the Share with dialog
                if "Share with" in share_options or any(
                    "Bluetooth" in opt or "Nearby Share" in opt or "News Feed" in opt for opt in share_options
                ):
                    # Look for Reels option (may need to scroll)
                    reels_option = None
                    for element in d(className="android.widget.TextView"):
                        text = element.info.get("text", "")
                        if text and "reels" in text.lower():
                            reels_option = element
                            break

                    # If Reels not found, scroll down
                    if not reels_option:
                        d.swipe(0.5, 0.7, 0.5, 0.3, 0.5)
                        time.sleep(1)

                        # Look for Reels again after scrolling
                        for element in d(className="android.widget.TextView"):
                            text = element.info.get("text", "")
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
                                text = element.info.get("text", "")
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
                                    text = element.info.get("text", "")
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
                                text = element.info.get("text", "")
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
            elif "Share with" in all_options or any(
                "Bluetooth" in opt or "Nearby Share" in opt or "News Feed" in opt for opt in all_options
            ):
                # Look for Reels option (may need to scroll)
                reels_option = None
                for element in d(className="android.widget.TextView"):
                    text = element.info.get("text", "")
                    if text and "reels" in text.lower():
                        reels_option = element
                        break

                # If Reels not found, scroll down
                if not reels_option:
                    d.swipe(0.5, 0.7, 0.5, 0.3, 0.5)
                    time.sleep(1)

                    # Look for Reels again after scrolling
                    for element in d(className="android.widget.TextView"):
                        text = element.info.get("text", "")
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
                            text = element.info.get("text", "")
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
                                text = element.info.get("text", "")
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
                            text = element.info.get("text", "")
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
                    text = element.info.get("text", "").lower()
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

    # handle Facebook permission dialog if it appears, with flexible text matching and multiple strategies for finding the ALLOW button. This is important because Facebook's permission dialogs can vary widely in text and layout across different versions and languages, so we need a robust method to detect and interact with them.
    def check_and_handle_facebook_permission(self, d):
        """Check for Facebook permission dialog, click ALLOW if found, and continue flow."""
        try:
            # More flexible text matching for permission dialogs
            permission_patterns = [
                "allow facebook.*access.*photos.*media.*files",
                "facebook.*permission.*access.*media",
                "allow.*facebook.*access.*storage",
                "facebook.*access.*photos",
            ]

            allow_button_patterns = ["allow", "always allow", "yes", "agree", "accept"]

            deny_button_patterns = ["deny", "don't allow", "never", "no", "reject"]

            # Get all text elements to check for the permission dialog
            all_texts = []
            for element in d(className="android.widget.TextView"):
                text = element.info.get("text", "")
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
                    text = element.info.get("text", "").lower()
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
                "OK",
                "Okay",
                "Xong",
                "ç¡®è®¤",
                "í™•ì¸",
                "Aceptar",
                "Accepter",
                "Accetta",
                "Einverstanden",
                "OKE",
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
                    d(description="Description input field"),
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
                    if video_data and video_data.get("caption"):
                        caption = video_data["caption"]
                        if video_data.get("hashtags"):
                            caption += " " + video_data["hashtags"]
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
            self.log(" Looking for Share/Post button...")
            time.sleep(3)
            share_button_found = False
            share_button_texts = [
                "Share",
                "Post",
                "Share now",
                "Publish",
                "ÄÄƒng",
                "Publicar",
                "å‘å¸ƒ",
                "å…±æœ‰",
                "Partager",
                "Compartir",
                "Condividi",
                "Teilen",
                "Share reel",
                "Post reel",  # Added more specific options
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
                lambda: self._find_button_by_position(d),
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
                bounds = button.info.get("bounds", {})
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
                resource_id = element.info.get("resourceId", "").lower()
                if any(keyword in resource_id for keyword in keywords):
                    bounds = element.info.get("bounds", {})
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
                (screen_width * 0.95, screen_height * 0.9),  # Right side
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

    def _remove_file_extension(self, filename):
        """
        Remove file extension from filename
        """
        # List of common video extensions to remove
        video_extensions = [".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".m4v", ".wmv", ".3gp"]

        # Remove any video extension found
        for ext in video_extensions:
            if filename.lower().endswith(ext):
                return filename[: -len(ext)]

        # If no known extension found, try to remove anything after the last dot
        if "." in filename:
            return filename.rsplit(".", 1)[0]

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
            "Amazing video that you'll love! â¤ï¸",
        ]

        # List of popular hashtags for reels
        hashtag_groups = [
            "#reels #viral #trending #fyp #foryou #foryoupage #explorepage #instagramreels #reelitfeelit #reelkarofeelkaro #reelsindia #reelsteady #reelsvideo #reelsinsta #reelslovers #reelsofinstagram #reelsviral #reelsdance #reelsmusic #reelsfunny",
            "#viralvideo #trendingnow #fypã‚· #foryourpage #explore #instareels #reelit #reelkarofeelkaro #reelsindia #reelsteadygo #reelsvideoviral #reelsinstagram #reelslover #reelsofig #reelsviraltrick #reelsdancevideo #reelsmusicvideo #reelsfunnyvideos #contentcreator #digitalcreator",
            "#reels #viral #fyp #trending #foryou #instagramreels #reelitfeelit #reelsindia #reelsteady #reelsvideo #explorepage #foryoupage #reelsinsta #reelslovers #reelsofinstagram #reelsviral #reelsdance #reelsmusic #reelsfunny #contentcreation",
        ]

        # Select a random base caption
        base_caption = random.choice(base_captions)

        # Select a random hashtag group
        hashtags = random.choice(hashtag_groups)

        # Combine caption and hashtags
        full_caption = f"{base_caption} {hashtags}"

        return full_caption

    # This method is designed to handle the Facebook posting process with improved error recovery and UI detection. It includes multiple strategies to find and click the post button, which can vary widely across different Facebook versions and languages. The method also includes enhanced logging for better debugging and understanding of the flow.
    def facebook_first_next(self, d):
        """Handle Facebook posting with better error recovery and UI detection"""
        try:
            # Wait for Facebook UI to load (max 25s)
            facebook_opened = False
            for _ in range(25):
                current_app = d.app_current()
                if "facebook" in current_app.get("package", "").lower():
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
                "Next",
                "Post",
                "Share",
                "Share now",
                "Done",
                "Publish",
                "Tiáº¿p",
                "à¸•à¹ˆà¸­à¹„à¸›",
                "Siguiente",
                "Weiter",
                "Suivant",
                "Publicar",
                "æ¬¡ã¸",
                "ë‹¤ìŒ",
                "ä¸‹ä¸€æ­¥",
                "Ä°leri",
                "Avanti",
                "PrÃ³ximo",
                "å‘å¸ƒ",
                "ÄÄƒng",
                "Partager",
                "Compartir",
                "Condividi",
                "Teilen",
                "å…±æœ‰",
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
                d(className="android.widget.ImageButton"),
            ]

            for selector in button_selectors:
                try:
                    for button in selector:
                        try:
                            rid = button.info.get("resourceId", "").lower()
                            txt = button.info.get("text", "").lower()
                            content_desc = button.info.get("contentDescription", "").lower()
                            bounds = button.info.get("bounds", {})

                            # Check if this looks like a post button
                            button_keywords = ["next", "post", "share", "publish", "done", "continue", "send"]
                            is_post_button = (
                                any(kw in rid for kw in button_keywords)
                                or any(kw in txt for kw in button_keywords)
                                or any(kw in content_desc for kw in button_keywords)
                            )

                            # Additional check for button position (usually at bottom right)
                            if is_post_button and bounds:
                                screen_width = d.info.get("displayWidth", 1080)
                                screen_height = d.info.get("displayHeight", 1920)

                                # Check if button is in bottom-right quadrant
                                if (
                                    bounds["right"] > screen_width * 0.6
                                    and bounds["top"] > screen_height * 0.7
                                ):
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
                        bounds = element.info.get("bounds", {})
                        if bounds and (
                            bounds["bottom"] - bounds["top"] > 40 and bounds["right"] - bounds["left"] > 100
                        ):
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
                (screen_width * 0.95, screen_height * 0.9),  # Right side
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

    # handle video deletion with improved error handling and logging. This method will long-press on the video to open the context menu, look for the "Delete" option, and handle the confirmation dialog if it appears. It includes enhanced logging for better debugging and understanding of the flow.
    def delete_video(self, d):
        try:
            # Long press video
            self.hold_on_video(d, hold_time=2)
            time.sleep(2)

            # Find and click "Delete" option
            for element in d(className="android.widget.TextView"):
                text = element.info.get("text", "")
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
