import time

from core.paths import get_app_paths  # noqa: F401  # re-exported for test patching
from core.task_base import U2_AVAILABLE, BaseTaskHandler, u2  # noqa: F401
from core.tasks.handler.handler_reels import ReelsHandlerMixin
from utils.ip_guard import check_ld_ip_allowed


class ReelsTaskHandler(ReelsHandlerMixin, BaseTaskHandler):
    """Handler for Facebook Reels tasks"""

    def __init__(self, emulator, log_func, pause_event, running_flag, content_manager=None):
        super().__init__(emulator, log_func, pause_event, running_flag)
        self.content_manager = content_manager
        from utils.activity_randomizer import ActivityRandomizer
        from utils.error_handler import EnhancedErrorHandler
        from utils.rate_limiter import RateLimiter

        self.error_handler = EnhancedErrorHandler(log_func)
        self.rate_limiter = RateLimiter()
        self.randomizer = ActivityRandomizer()

    def execute(
        self,
        name,
        duration=60,
        max_videos=2,
        scroll_after_post=True,
        use_content_queue=True,
        page_per_account=2,
        clear_cache=True,
    ):
        if self.check_paused():
            return False

        if not self.emulator.is_ld_running(name):
            if not self.emulator.start_ld(name):
                self.log(f"Failed to start LD: {name}")
                return False
            self.auto_arrange_ld_windows()
            self.log(f"Waiting for emulator ready: {name}")
            if not self.ensure_device_ready(
                name, timeout=max(90, int(getattr(self.emulator, "boot_delay", 20)) * 6)
            ):
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

        success, d, serial = self.open_facebook_with_recovery(name, serial, max_retries=1)
        if not success:
            self.log(f"Failed to open Facebook on {name}")
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
                if self.interruptible_sleep(15):
                    return False
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

                self.log(
                    f"Setup failed on {name}. Clearing all apps before retry {setup_attempt + 1}/{max_setup_attempts}"
                )
                self._clear_recent_apps(d)
                time.sleep(2)

            if not setup_ready:
                return False

            limiter = getattr(self, "rate_limiter", None)
            if limiter is not None and not limiter.can_perform_action("reels_post"):
                wait_for = max(0.0, limiter.get_wait_time())
                if wait_for > 0:
                    self.log(f"Reels rate limit reached on {name}; pausing for {wait_for:.1f}s")
                    if self.interruptible_sleep(min(wait_for, 90.0)):
                        return False

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
                    if self.interruptible_sleep(10):
                        return False

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
                        progress_value = (
                            min(100, 78 + int((success_pots / total_videos_target) * 22))
                            if total_videos_target > 0
                            else 100
                        )
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
        if self.interruptible_sleep(5):
            return False
        self.end_to_accoutn_profile(d, name)

        if self.interruptible_sleep(6):
            return False
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

        if self.interruptible_sleep(6):
            return False
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

        if self.interruptible_sleep(4):
            return False
        if not self.back_to_account_profile(d, name):
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
