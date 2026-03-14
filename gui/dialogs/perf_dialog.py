"""
gui/dialogs/perf_dialog.py
Performance Report dialog — KPI cards + animated gradient progress bars.
Author: Bunhong
"""

import tkinter as tk
import ttkbootstrap as tb
from gui.gradient_progress import GradientProgressBar


class PerformanceDialogMixin:

    def show_performance_report(self):
        if hasattr(self, "_perf_dialog") and self._perf_dialog.winfo_exists():
            self._perf_dialog.focus()
            return

        P = self.palette
        win = tk.Toplevel(self.root)
        win.title("Performance Report")
        win.resizable(False, False)
        win.geometry("540x460")
        win.transient(self.root)
        win.grab_set()
        win.configure(bg=P["surface"])
        self._perf_dialog = win

        # ── header ────────────────────────────────────────────────────── #
        hdr = tk.Frame(win, bg=P["surface_alt"],
                       highlightthickness=1,
                       highlightbackground=P["border_alt"])
        hdr.pack(fill="x")

        tk.Label(hdr, text="📈", bg="#050E0A",
                 fg="#10B981", font=(self.display_font, 14),
                 width=4, pady=14).pack(side="left")
        tk.Label(hdr, text="Performance Report", bg=P["surface_alt"],
                 fg=P["text"], font=(self.display_font, 14)).pack(side="left", padx=(4, 0))
        tk.Label(hdr, text="Live session metrics & task statistics",
                 bg=P["surface_alt"], fg=P["muted"],
                 font=(self.mono_font, 9)).pack(side="left", padx=(8, 0))

        # ── body ──────────────────────────────────────────────────────── #
        body = tk.Frame(win, bg=P["surface"], padx=18, pady=16)
        body.pack(fill="both", expand=True)

        # KPI cards row
        kpi_row = tk.Frame(body, bg=P["surface"])
        kpi_row.pack(fill="x", pady=(0, 14))

        self._perf_kpis = {}
        kpis = [
            ("tasks_done", "Tasks Done", "0",      P["primary"],   "00"),
            ("uptime",     "Uptime",     "00:00",   "#10B981",      "01"),
            ("errors",     "Errors",     "0",       "#F59E0B",      "02"),
        ]
        for i, (key, label, val, color, _) in enumerate(kpis):
            card = tk.Frame(kpi_row, bg=P["surface_alt"],
                            highlightthickness=1,
                            highlightbackground=P["border"])
            card.pack(side="left", fill="both", expand=True, padx=(0, 6 if i < 2 else 0))

            stripe = tk.Frame(card, bg=color, height=3)
            stripe.pack(fill="x", side="top")

            inner = tk.Frame(card, bg=P["surface_alt"], padx=14, pady=12)
            inner.pack(fill="both", expand=True)

            tk.Label(inner, text=label.upper(), bg=P["surface_alt"],
                     fg=P["muted"], font=(self.mono_font, 8),
                     anchor="w").pack(fill="x")

            val_lbl = tk.Label(inner, text=val, bg=P["surface_alt"],
                               fg=color, font=(self.display_font, 22),
                               anchor="w")
            val_lbl.pack(fill="x", pady=(4, 0))
            self._perf_kpis[key] = val_lbl

        # divider
        tk.Frame(body, bg=P["border"], height=1).pack(fill="x", pady=(0, 14))

        # section label
        tk.Label(body, text="RESOURCE UTILIZATION", bg=P["surface"],
                 fg=P["muted"], font=(self.display_font, 9)).pack(anchor="w", pady=(0, 10))

        # bar rows
        self._perf_bars = {}
        bars = [
            ("cpu",  "CPU Usage",  ("#0891B2", "#00E5FF"), "0%"),
            ("ram",  "RAM",        ("#6D28D9", "#A78BFA"), "0%"),
            ("disk", "Disk I/O",   ("#059669", "#10B981"), "0%"),
            ("temp", "Temp (est)", ("#D97706", "#F59E0B"), "0°C"),
        ]
        for key, label, (c1, c2), init in bars:
            row = tk.Frame(body, bg=P["surface"])
            row.pack(fill="x", pady=5)

            top = tk.Frame(row, bg=P["surface"])
            top.pack(fill="x")
            tk.Label(top, text=label, bg=P["surface"],
                     fg=P["muted"], font=(self.mono_font, 9),
                     anchor="w").pack(side="left")
            val_lbl = tk.Label(top, text=init, bg=P["surface"],
                               fg=c2, font=(self.mono_font, 9))
            val_lbl.pack(side="right")

            bar = GradientProgressBar(row, bg=P["surface_alt"],
                                      color_start=c1, color_end=c2, height=5)
            bar.pack(fill="x", pady=(3, 0))
            self._perf_bars[key] = {"bar": bar, "lbl": val_lbl}

        self._update_performance_report()

        # ── footer ────────────────────────────────────────────────────── #
        foot = tk.Frame(win, bg=P["surface_alt"],
                        highlightthickness=1, highlightbackground=P["border"])
        foot.pack(fill="x", side="bottom")
        fp = tk.Frame(foot, bg=P["surface_alt"], padx=16, pady=12)
        fp.pack(fill="x")

        def _btn(text, fg, side, cmd):
            f = tk.Frame(fp, bg=fg if side == "right" else P["border"],
                         padx=1, pady=1)
            f.pack(side=side, padx=4)
            tk.Button(f, text=text, bg=P["surface_alt"], fg=fg,
                      activebackground=P["surface"], activeforeground=fg,
                      relief="flat", font=(self.mono_font, 10),
                      padx=14, pady=5, cursor="hand2", command=cmd).pack()

        _btn("Close", P["muted"], "left", win.destroy)
        _btn("↺ Refresh", "#10B981", "right", self._update_performance_report)

    # ──────────────────────────────────────────────────────────────────── #

    def _update_performance_report(self):
        try:
            stats = self.performance_monitor.get_stats()
        except Exception:
            stats = {}

        import psutil as _ps
        cpu  = _ps.cpu_percent(interval=None)
        mem  = _ps.virtual_memory().percent
        disk = _ps.disk_usage("/").percent
        temp = min(95.0, 38.0 + cpu * 0.35)

        # KPI values
        if hasattr(self, "_perf_kpis"):
            done = stats.get("tasks_completed", stats.get("tasks_done", 0))
            errs = stats.get("errors", stats.get("error_count", 0))
            self._perf_kpis["tasks_done"].config(text=str(done))
            self._perf_kpis["errors"].config(text=str(errs))

            if hasattr(self, "_uptime_start"):
                from datetime import datetime
                el = datetime.now() - self._uptime_start
                h, rem = divmod(int(el.total_seconds()), 3600)
                m, _ = divmod(rem, 60)
                self._perf_kpis["uptime"].config(text=f"{h:02}:{m:02}")

        # Bars
        if hasattr(self, "_perf_bars"):
            updates = [
                ("cpu",  cpu,  f"{cpu:.0f}%"),
                ("ram",  mem,  f"{mem:.0f}%"),
                ("disk", disk, f"{disk:.0f}%"),
                ("temp", temp, f"{temp:.0f}°C"),
            ]
            for key, pct, label in updates:
                b = self._perf_bars.get(key)
                if b:
                    b["bar"].set(pct)
                    b["lbl"].config(text=label)
