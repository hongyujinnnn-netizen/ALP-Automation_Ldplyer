import threading
import time
from datetime import datetime

from services.emulator_service import EmulatorService
from utils.ip_guard import get_ld_public_ip_info


class MainWindow:
    def __init__(self, selected_ld_names, running_flag, ld_thread, log_func=print,
                 start_same_time=False, auto_arrange_ld=False, task_type="scroll", task_template="custom", task_handler=None, progress_callback=None,
                 boot_delay=20, task_duration=900, max_videos=2, scroll_after_post=True, emulator=None, state_callback=None):

        # Import here to avoid circular imports when we need a fresh controller
        if emulator is None:
            self.em = EmulatorService()
            self._owns_emulator = True
        else:
            self.em = emulator
            self._owns_emulator = False
        # Set the boot delay and task duration from parameters
        self.em.boot_delay = boot_delay
        self.em.task_duration = task_duration
        
        # Debug: print what we're trying to process
        log_func(f"Selected LD names: {selected_ld_names}")
        log_func(f"Available emulators: {list(self.em.name_to_serial.keys())}")
        
        # Filter only the names that exist in our emulator mapping
        self.thread_ld = []
        for name in selected_ld_names:
            if name in self.em.name_to_serial:
                self.thread_ld.append(name)
            else:
                # Try to find by partial match (e.g., "US - 01" vs "1,US - 01")
                for emu_name in self.em.name_to_serial.keys():
                    if name in emu_name or emu_name in name:
                        self.thread_ld.append(emu_name)
                        log_func(f"Matched {name} to {emu_name}")
                        break
        
        log_func(f"Processing LDs: {self.thread_ld}")
        
        self.log = log_func
        self.running_flag = running_flag
        self.ld_thread = ld_thread
        self.task_duration = task_duration
        self.start_same_time = start_same_time
        self.auto_arrange_ld = auto_arrange_ld
        self.pause_event = threading.Event()
        self.pause_event.set()  # Start unpaused
        self.task_type = task_type
        self.task_template = task_template
        self.task_handler = task_handler
        self.progress_callback = progress_callback
        self.state_callback = state_callback
        self.completed_count = 0
        self.boot_delay = boot_delay
        self.max_videos = max_videos
        self.scroll_after_post = scroll_after_post
        self._ip_lookup_inflight = set()

    def _auto_arrange_windows(self):
        if not self.auto_arrange_ld:
            return
        try:
            self.em.sort_window()
            self.log("Auto arranged LD windows")
        except Exception as e:
            self.log(f"Failed to auto arrange LD windows: {e}")

    def check_paused(self):
        """Check if operations should be paused - blocks if paused"""
        while not self.pause_event.is_set() and self.running_flag():
            time.sleep(0.5)
        return not self.running_flag()

    def _push_state(self, name, **payload):
        if callable(self.state_callback):
            try:
                self.state_callback(name, payload)
            except Exception:
                pass

    def _start_ip_lookup(self, name, force=False):
        if name in self._ip_lookup_inflight:
            return
        serial = self.em.name_to_serial.get(name)
        if not serial:
            self._push_state(name, public_ip="Unavailable", public_ip_country="")
            return

        self._ip_lookup_inflight.add(name)
        if force:
            self._push_state(name, public_ip="Refreshing...", public_ip_country="")
        else:
            self._push_state(name, public_ip="Loading...", public_ip_country="")

        def worker():
            info = None
            try:
                info = get_ld_public_ip_info(serial, timeout=10.0)
            except Exception:
                info = None

            if info:
                ip = str(info.get("ip") or "Unknown")
                country = str(info.get("country") or "")
                self._push_state(name, public_ip=ip, public_ip_country=country)
            else:
                self._push_state(name, public_ip="Unavailable", public_ip_country="")
            self._ip_lookup_inflight.discard(name)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def ld_task_stage(self, name, stage):
        if not self.running_flag():
            return
        
        if self.check_paused():
            return
        
        if stage == "start":
            self._push_state(name, phase="start", state="Starting", task="Boot sequence", progress=10)
            self.log(f"Starting LD: {name}")
            self.em.start_ld(name, delay_between_starts=self.boot_delay)
            self.log(f"Waiting for LD ready: {name}")
            self._push_state(name, phase="start", state="Waiting", task="Waiting for Android ready", progress=24)
            if not self.em.wait_for_ld_ready(name, timeout=max(90, self.boot_delay * 6), poll_interval=2):
                self.log(f"LD not ready in time: {name}")
                self._push_state(name, phase="start", state="Attention", task="Boot timeout", progress=0)
            else:
                self._push_state(name, phase="ready", state="Active", task="Device online", progress=36)
                self._start_ip_lookup(name)
        elif stage == "facebook":
            if self.task_type == "scroll":
                if not self.em.wait_for_ld_ready(name, timeout=60, poll_interval=2):
                    self.log(f"Skip Facebook; LD not ready: {name}")
                    self._push_state(name, phase="facebook", state="Attention", task="Facebook skipped", progress=0)
                    return
                self.log(f"Opening Facebook on LD: {name}")
                self._push_state(name, phase="facebook", state="Preparing", task="Opening Facebook", progress=48)
                self.em.open_facebook(name)
                self._push_state(name, phase="facebook", state="Ready", task="Facebook opened", progress=60)
        elif stage == "task":
            self.log(f"Running {self.task_type} task on LD: {name}")
            self._start_ip_lookup(name, force=(self.task_type == "reels"))
            self._push_state(
                name,
                phase="task",
                state="Running",
                task=f"{self.task_type.title()} task",
                progress=78 if self.task_type == "reels" else 72,
                started_task_at=datetime.now().isoformat(),
                task_template=self.task_template,
                scroll_after_post=self.scroll_after_post,
            )
            if self.task_handler is not None:
                if self.task_type == "reels":
                    success = self.task_handler.execute(
                        name,
                        self.task_duration,
                        max_videos=self.max_videos,
                        scroll_after_post=self.scroll_after_post,
                    )
                else:
                    success = self.task_handler.execute(name, self.task_duration)
                self._push_state(
                    name,
                    phase="task",
                    state="Completed" if success else "Attention",
                    task=f"{self.task_type.title()} task",
                    progress=100 if success else 0,
                )
            
            # Update progress if callback provided
            if self.progress_callback:
                self.completed_count += 1
                progress = (self.completed_count / len(self.thread_ld)) * 100
                self.progress_callback(progress)
        elif stage == "close":
            # For reels task, make sure the task is actually complete before closing
            if self.task_type == "reels":
                # Wait a bit longer to ensure all cleanup is done
                time.sleep(5)
            self.log(f"Closing LD: {name}")
            self._push_state(name, phase="close", state="Closing", task="Shutdown sequence", progress=100)
            time.sleep(15)  # Fixed close delay
            self.em.quit_ld(name)
            self._push_state(name, phase="close", state="Idle", task="Waiting for next run", progress=0, finished_at=datetime.now().isoformat())

    def main(self):
        total = len(self.thread_ld)
        self.log(f"Total LDs to process: {total}")

        try:
            for batch_start in range(0, total, self.ld_thread):
                if not self.running_flag():
                    break

                batch = self.thread_ld[batch_start:batch_start + self.ld_thread]
                self.log(f"Processing batch: {batch}")

                # Define stages based on task type
                if self.task_type == "scroll":
                    stages = ["start", "facebook", "task", "close"]
                else:  # reels
                    stages = ["start", "task", "close"]

                for stage in stages:
                    if not self.running_flag():
                        break

                    self.log(f"Stage: {stage.capitalize()}")
                    
                    if stage == "start" and not self.start_same_time:
                        for name in batch:
                            if not self.running_flag():
                                break
                            self.ld_task_stage(name, stage)
                            time.sleep(10)  # Fixed start delay
                        self._auto_arrange_windows()
                    else:
                        threads = []
                        for name in batch:
                            if not self.running_flag():
                                break
                            t = threading.Thread(target=self.ld_task_stage, args=(name, stage))
                            t.daemon = True
                            t.start()
                            threads.append(t)
                        
                        # Wait for all threads to complete before moving to next stage
                        # Especially important for the task stage to finish before close
                        for t in threads:
                            t.join(timeout=600)  # Increased timeout to 10 minutes for reels tasks

                        if stage == "start":
                            self._auto_arrange_windows()
                            
                        # For reels task, add extra delay after task stage before closing
                        if stage == "task" and self.task_type == "reels":
                            self.log("Waiting for reels tasks to fully complete...")
                            time.sleep(30)  # Additional buffer time
                            
        finally:
            # Only tear down ADB if this instance owns the emulator lifecycle
            if getattr(self, "_owns_emulator", False):
                self.em.cleanup_adb()
