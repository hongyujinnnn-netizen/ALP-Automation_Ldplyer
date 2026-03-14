import tkinter as tk
from datetime import datetime
import psutil

from gui.gradient_progress import GradientProgressBar


class StatusBarMixin:
    def create_status_bar(self):
        """Compact status bar with uptime and live progress."""
        bar = tk.Frame(self.root, bg=self.palette["surface"], height=26)
        bar.pack(side="bottom", fill="x")
        bar.pack_propagate(False)
        tk.Frame(bar, bg=self.palette["border"], height=1).pack(side="top", fill="x")

        inner = tk.Frame(bar, bg=self.palette["surface"])
        inner.pack(fill="both", expand=True, padx=12)

        left = tk.Frame(inner, bg=self.palette["surface"])
        left.pack(side="left", fill="x", expand=True)
        right = tk.Frame(inner, bg=self.palette["surface"])
        right.pack(side="right")

        self.footer_selected_label = tk.Label(
            left,
            text="Selected: 0/0",
            bg=self.palette["surface"],
            fg=self.palette["muted"],
            font=(self.mono_font, 9),
        )
        self.footer_selected_label.pack(side="left", padx=(0, 14))

        self.status_sys_lbl = tk.Label(
            left,
            text="● System: Idle",
            bg=self.palette["surface"],
            fg=self.palette["muted"],
            font=(self.mono_font, 9),
        )
        self.status_sys_lbl.pack(side="left", padx=(0, 14))
        # alias for existing log helpers
        self.status_label = self.status_sys_lbl

        self.status_adb_lbl = tk.Label(
            left,
            text="ADB: — devices",
            bg=self.palette["surface"],
            fg=self.palette["muted"],
            font=(self.mono_font, 9),
        )
        self.status_adb_lbl.pack(side="left", padx=(0, 14))

        self.status_task_lbl = tk.Label(
            left,
            text="Tasks: 0 active",
            bg=self.palette["surface"],
            fg=self.palette["muted"],
            font=(self.mono_font, 9),
        )
        self.status_task_lbl.pack(side="left", padx=(0, 14))

        self.footer_cpu_label = tk.Label(
            left,
            text="CPU: 0%",
            bg=self.palette["surface"],
            fg=self.palette["muted"],
            font=(self.mono_font, 9),
        )
        self.footer_cpu_label.pack(side="left", padx=(0, 10))
        self.footer_mem_label = tk.Label(
            left,
            text="Mem: 0%",
            bg=self.palette["surface"],
            fg=self.palette["muted"],
            font=(self.mono_font, 9),
        )
        self.footer_mem_label.pack(side="left", padx=(0, 10))

        self.status_uptime = tk.Label(
            right,
            text="Uptime: 00:00:00",
            bg=self.palette["surface"],
            fg=self.palette["muted"],
            font=(self.mono_font, 9),
        )
        self.status_uptime.pack(side="right", padx=(10, 0))

        self.footer_progress_label = tk.Label(
            right,
            text="0%",
            bg=self.palette["surface"],
            fg=self.palette["muted"],
            font=(self.mono_font, 9),
            width=5,
        )
        self.footer_progress_label.pack(side="right", padx=(0, 6))
        self.footer_progress = GradientProgressBar(
            right,
            bg=self.palette["surface_alt"],
            color_start=self.palette["primary"],
            color_end=self.palette["secondary"],
            height=6,
        )
        self.footer_progress.pack(side="right", padx=(0, 8), pady=(7, 0))

        self._uptime_start = datetime.now()
        self._tick_uptime()

    def _tick_uptime(self):
        elapsed = datetime.now() - getattr(self, "_uptime_start", datetime.now())
        h, rem = divmod(int(elapsed.total_seconds()), 3600)
        m, s = divmod(rem, 60)
        if hasattr(self, "status_uptime"):
            self.status_uptime.config(text=f"Uptime: {h:02}:{m:02}:{s:02}")
        self.root.after(1000, self._tick_uptime)

    def start_system_metrics_refresh(self):
        """Periodic system metrics for the footer."""

        def _tick():
            try:
                cpu = psutil.cpu_percent(interval=None)
                mem = psutil.virtual_memory().percent
                if hasattr(self, "footer_cpu_label"):
                    self.footer_cpu_label.config(text=f"CPU: {cpu:.0f}%")
                if hasattr(self, "footer_mem_label"):
                    self.footer_mem_label.config(text=f"Mem: {mem:.0f}%")
                if hasattr(self, "sidebar_status_pill"):
                    adb_online = sum(1 for status in self._ld_status_cache.values() if status in ("Active", "Running"))
                    self.sidebar_status_pill.config(text=f"ADB Online | {adb_online} active | CPU {cpu:.0f}%")
                if hasattr(self, "status_adb_lbl"):
                    adb_online = sum(1 for status in self._ld_status_cache.values() if status in ("Active", "Running"))
                    self.status_adb_lbl.config(text=f"ADB: {adb_online} devices")
                if hasattr(self, "status_task_lbl"):
                    running = sum(1 for status in self._ld_status_cache.values() if status == "Running")
                    self.status_task_lbl.config(text=f"Tasks: {running} active")
                disk = psutil.disk_usage("/").percent
                temp = min(95.0, 38.0 + (cpu * 0.35))
                if hasattr(self, "sys_rows"):
                    row = self.sys_rows.get("cpu")
                    if row:
                        row["bar"].set(cpu)
                        row["value"].config(text=f"{cpu:.0f}%")
                    row = self.sys_rows.get("ram")
                    if row:
                        row["bar"].set(mem)
                        row["value"].config(text=f"{mem:.0f}%")
                    row = self.sys_rows.get("disk")
                    if row:
                        row["bar"].set(disk)
                        row["value"].config(text=f"{disk:.0f}%")
                    row = self.sys_rows.get("temp")
                    if row:
                        row["bar"].set(temp)
                        row["value"].config(text=f"{temp:.0f}C")
            except Exception:
                pass
            self.root.after(2500, _tick)

        self.root.after(1200, _tick)
