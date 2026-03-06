import threading
import time
from datetime import datetime

class MainWindow:
    def __init__(self, selected_ld_names, running_flag, ld_thread, log_func=print,
                 start_same_time=False, task_type="scroll", task_handler=None, progress_callback=None,
                 boot_delay=20, task_duration=900, max_videos=2, emulator=None):

        # Import here to avoid circular imports when we need a fresh controller
        if emulator is None:
            from core.emulator import ControlEmulator
            self.em = ControlEmulator()
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
        self.pause_event = threading.Event()
        self.pause_event.set()  # Start unpaused
        self.task_type = task_type
        self.task_handler = task_handler
        self.progress_callback = progress_callback
        self.completed_count = 0
        self.boot_delay = boot_delay
        self.max_videos = max_videos

    def check_paused(self):
        """Check if operations should be paused - blocks if paused"""
        while not self.pause_event.is_set() and self.running_flag():
            time.sleep(0.5)
        return not self.running_flag()

    def ld_task_stage(self, name, stage):
        if not self.running_flag():
            return
        
        if self.check_paused():
            return
        
        if stage == "start":
            self.log(f"Starting LD: {name}")
            self.em.start_ld(name, delay_between_starts=self.boot_delay)
            self.log(f"Waiting for LD ready: {name}")
            if not self.em.wait_for_ld_ready(name, timeout=max(90, self.boot_delay * 6), poll_interval=2):
                self.log(f"LD not ready in time: {name}")
        elif stage == "facebook":
            if self.task_type == "scroll":
                if not self.em.wait_for_ld_ready(name, timeout=60, poll_interval=2):
                    self.log(f"Skip Facebook; LD not ready: {name}")
                    return
                self.log(f"Opening Facebook on LD: {name}")
                self.em.open_facebook(name)
        elif stage == "task":
            self.log(f"Running {self.task_type} task on LD: {name}")
            if self.task_handler is not None:
                if self.task_type == "reels":
                    success = self.task_handler.execute(name, self.task_duration, max_videos=self.max_videos)
                else:
                    success = self.task_handler.execute(name, self.task_duration)
            
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
            time.sleep(15)  # Fixed close delay
            self.em.quit_ld(name)

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
                            
                        # For reels task, add extra delay after task stage before closing
                        if stage == "task" and self.task_type == "reels":
                            self.log("Waiting for reels tasks to fully complete...")
                            time.sleep(30)  # Additional buffer time
                            
        finally:
            # Only tear down ADB if this instance owns the emulator lifecycle
            if getattr(self, "_owns_emulator", False):
                self.em.cleanup_adb()
