import threading
import time
from datetime import datetime

from services.emulator_service import EmulatorService
from utils.ip_guard import get_ld_public_ip_info


class MainWindow:
    def __init__(self, selected_ld_names, running_flag, ld_thread, log_func=print,
                 start_same_time=False, auto_arrange_ld=False, task_type="scroll", task_template="custom", task_handler=None, progress_callback=None,
                 boot_delay=20, task_duration=900, max_videos=2, page_per_account=2, accounts_per_ld=1, scroll_after_post=True, clear_cache=True, verify_account=True, emulator=None, state_callback=None,
                 accounts_pool=None, verify_2fa=True):

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
        emulator_count = len(self.em.name_to_serial)
        log_func(f"Available emulators: [{emulator_count} - Emulator ]")
        
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
        self.page_per_account = page_per_account
        self.accounts_per_ld = max(1, int(accounts_per_ld))
        self.scroll_after_post = scroll_after_post
        self.clear_cache = clear_cache
        self.verify_account = verify_account
        self._ip_lookup_inflight = set()
        self._closed_ld_names = set()
        self._close_lock = threading.Lock()
        self.reels_task_join_poll_seconds = 1.0
        self.verify_2fa = bool(verify_2fa)
        self._accounts_pool = list(accounts_pool or [])
        self._accounts_pool_lock = threading.Lock()

    def _take_login_account(self):
        with self._accounts_pool_lock:
            if not self._accounts_pool:
                return None
            return self._accounts_pool.pop(0)

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

    def _close_ld_if_needed(self, name):
        with self._close_lock:
            if name in self._closed_ld_names:
                self._push_state(
                    name,
                    phase="close",
                    state="Idle",
                    task="Waiting for next run",
                    progress=0,
                    finished_at=datetime.now().isoformat(),
                )
                return False

        self.log(f"Closing LD: {name}")
        self._push_state(name, phase="close", state="Closing", task="Shutdown sequence", progress=100)
        time.sleep(15)  # Fixed close delay
        closed = False
        try:
            closed = bool(self.em.quit_ld(name))
        except Exception as exc:
            self.log(f"Failed to close LD {name}: {exc}")
            closed = False

        if not closed:
            self._push_state(name, phase="close", state="Attention", task="Shutdown failed", progress=0)
            return False

        with self._close_lock:
            self._closed_ld_names.add(name)
        self._push_state(
            name,
            phase="close",
            state="Idle",
            task="Waiting for next run",
            progress=0,
            finished_at=datetime.now().isoformat(),
        )
        return True

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
            if self.task_type in {"scroll", "reg_account"}:
                if not self.em.wait_for_ld_ready(name, timeout=60, poll_interval=2):
                    self.log(f"Skip Facebook; LD not ready: {name}")
                    self._push_state(name, phase="facebook", state="Attention", task="Facebook skipped", progress=0)
                    return
                self.log(f"Opening Facebook on LD: {name}")
                self._push_state(name, phase="facebook", state="Preparing", task="Opening Facebook", progress=48)
                self.em.open_facebook(name)
                self._push_state(name, phase="facebook", state="Ready", task="Facebook opened", progress=60)
        elif stage == "task":
            if self.task_type not in {"scroll", "reg_account"}:
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
                clear_cache=self.clear_cache,
                verify_account=self.verify_account,
            )
            if self.task_handler is not None:
                if self.task_type == "reels":
                    success = self.task_handler.execute(
                        name,
                        self.task_duration,
                        max_videos=self.max_videos,
                        page_per_account=self.page_per_account,
                        scroll_after_post=self.scroll_after_post,
                        clear_cache=self.clear_cache,
                    )
                elif self.task_type == "login":
                    account = self._take_login_account()
                    if account is None:
                        self.log(f"No login account available for LD: {name}")
                        success = False
                    else:
                        identifier = (
                            account.get("identifier")
                            or account.get("uid")
                            or account.get("email")
                            or account.get("username")
                            or ""
                        )
                        identifier_label = account.get("identifier_label") or (
                            "uid" if account.get("uid") else ("email" if account.get("email") else "username")
                        )
                        twofa_secret = str(account.get("twofa") or account.get("twofa_secret") or "").strip()
                        payload = {
                            "identifier": identifier,
                            "identifier_label": identifier_label,
                            "account_name": str(account.get("name") or "").strip(),
                            "email": str(account.get("email") or "").strip(),
                            "password": str(account.get("password") or "").strip(),
                            "twofa": twofa_secret,
                            "twofa_secret": twofa_secret,
                            "twofa_email": str(account.get("twofa_email") or account.get("email") or "").strip(),
                            "verify_2fa": bool(self.verify_2fa) or bool(twofa_secret),
                            "clear_before_login": True,
                        }
                        self.log(f"Logging in '{identifier}' on LD: {name}")
                        self._push_state(
                            name,
                            phase="task",
                            state="Running",
                            task=f"Login {identifier}",
                            progress=80,
                        )
                        success = bool(self.task_handler.execute(name, self.task_duration, **payload))
                elif self.task_type == "reg_account":
                    requested_accounts = max(1, int(self.accounts_per_ld))
                    completed_accounts = 0
                    success = True

                    for attempt in range(requested_accounts):
                        if not self.running_flag() or self.check_paused():
                            success = False
                            break
                        self.log(f"Registering account {attempt + 1}/{requested_accounts} on LD: {name}")
                        self._push_state(
                            name,
                            phase="task",
                            state="Running",
                            task=f"Registering {attempt + 1}/{requested_accounts}",
                            progress=min(95, 72 + int(((attempt + 1) / requested_accounts) * 20)),
                        )
                        if not self.task_handler.execute(
                            name,
                            self.task_duration,
                            verify=self.verify_account,
                        ):
                            success = False
                            break
                        completed_accounts += 1

                    self.log(
                        f"Registration completed {completed_accounts}/{requested_accounts} account(s) on LD: {name}"
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

                if (
                    self.task_type == "reg_account"
                    and success
                    and completed_accounts == requested_accounts
                ):
                    # Registration batches should release the emulator immediately
                    # after the final account succeeds so we do not depend on the
                    # later close stage to shut the LD instance down.
                    self._close_ld_if_needed(name)

                if self.task_type == "login":
                    # Login is one-shot per LD: close immediately so the next batch
                    # can start fresh emulators with the next accounts.
                    self._close_ld_if_needed(name)
            
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
            self._close_ld_if_needed(name)

    def _wait_for_stage_threads(self, threads, stage):
        if stage == "task" and self.task_type == "reels":
            while any(t.is_alive() for t in threads):
                if not self.running_flag():
                    break
                for t in threads:
                    if t.is_alive():
                        t.join(timeout=self.reels_task_join_poll_seconds)
            return

        for t in threads:
            t.join(timeout=600 if stage == "task" else None)

    def main(self):
        total = len(self.thread_ld)
        self.log(f"Total LDs to process: {total}")

        try:
            for batch_start in range(0, total, self.ld_thread):
                if not self.running_flag():
                    break

                batch = self.thread_ld[batch_start:batch_start + self.ld_thread]
                self.log(f"Processing batch: {batch}")

                # Scroll tasks open Facebook inside the task handler after the
                # IP guard passes, so skip the legacy pre-open stage here.
                stages = ["start", "task"]
                if self.task_type != "test_feature":
                    stages.append("close")

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
                        
                        # Wait for all stage threads to fully finish before advancing.
                        self._wait_for_stage_threads(threads, stage)

                        if any(t.is_alive() for t in threads):
                            self.log(f"Stage {stage.capitalize()} is still running; not advancing to the next stage.")
                            break

                        if stage == "start":
                            self._auto_arrange_windows()
                            
        finally:
            # Only tear down ADB if this instance owns the emulator lifecycle
            if getattr(self, "_owns_emulator", False):
                self.em.cleanup_adb()
