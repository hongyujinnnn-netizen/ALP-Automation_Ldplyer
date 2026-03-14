import tkinter as tk
import ttkbootstrap as tb
from datetime import datetime


class TopBarMixin:
    def _make_chip(self, parent, text, bg, fg, border_color):
        frame = tk.Frame(parent, bg=border_color, padx=1, pady=1, highlightthickness=0)
        inner = tk.Frame(frame, bg=bg, padx=8, pady=3)
        inner.pack()
        lbl = tk.Label(inner, text=text, bg=bg, fg=fg, font=(self.display_font, 9))
        lbl.pack()
        frame.pack(side="left", padx=4)
        return lbl

    def create_top_bar(self, parent):
        """Top-level application header with global actions."""
        top_shadow = tb.Frame(parent, style="Shadow.TFrame", padding=(0, 0, 0, 1))
        top_shadow.pack(fill="x", side="top")
        top_bar = tb.Frame(top_shadow, style="Topbar.TFrame", padding=(16, 12))
        top_bar.pack(fill="x", padx=(0, 1))

        title_wrap = tb.Frame(top_bar, style="Topbar.TFrame")
        title_wrap.pack(side="left")

        tb.Label(
            title_wrap,
            text="Dashboard",
            style="TopTitle.TLabel"
        ).pack(anchor="w")
        self.top_status_label = tb.Label(
            title_wrap,
            text=f"System idle | {datetime.now().strftime('%d %b %Y %H:%M')}",
            style="TopSub.TLabel"
        )
        self.top_status_label.pack(anchor="w")

        center_meta = tb.Frame(top_bar, style="Topbar.TFrame")
        center_meta.pack(side="left", padx=(18, 0))
        self.top_selected_chip = self._make_chip(
            center_meta,
            "Selected: 0",
            bg="#071820",
            fg=self.palette["primary"],
            border_color="#00485A",
        )
        self.top_mode_chip = self._make_chip(
            center_meta,
            "Mode: Idle",
            bg="#0A1A10",
            fg=self.palette["success"],
            border_color="#1A5030",
        )
        self.top_task_chip = self._make_chip(
            center_meta,
            "Task: Scroll",
            bg="#10082A",
            fg=self.palette["secondary"],
            border_color="#3A1878",
        )

        tabs = tb.Frame(top_bar, style="Topbar.TFrame")
        tabs.pack(side="left", padx=(16, 0))
        self._top_tab_buttons = {}
        tab_defs = [
            ("Overview", 0, None),
            ("Devices", 0, self._focus_devices),
            ("Tasks", 1, None),
            ("Logs", 4, None),
        ]
        for label, idx, action in tab_defs:
            btn = tb.Button(
                tabs,
                text=label,
                bootstyle="secondary-link",
                command=(action if action is not None else (lambda i=idx: self.notebook.select(i) if hasattr(self, "notebook") else None)),
                width=9,
            )
            btn.pack(side="left", padx=2)
            self._top_tab_buttons[label] = btn

        actions = tb.Frame(top_bar, style="Topbar.TFrame")
        actions.pack(side="right")
        tb.Button(actions, text="⟳ Refresh", bootstyle="outline-info", command=self.refresh_all, width=10).pack(side="left", padx=4)
        tb.Button(actions, text="Stop All", bootstyle="danger", command=self.stop_automation, width=10).pack(side="left", padx=4)
        tb.Button(actions, text="▶ Start Automation", bootstyle="info", command=self.start_automation, width=16).pack(side="left", padx=4)
        self._update_header_chips()

    def _update_header_chips(self, mode_text=None):
        selected = 0
        if hasattr(self, "_ld_checked_names"):
            selected = len(self._ld_checked_names)
        if hasattr(self, "top_selected_chip"):
            self.top_selected_chip.config(text=f"Selected: {selected}")

        if hasattr(self, "top_mode_chip") and mode_text is not None:
            self.top_mode_chip.config(text=f"Mode: {mode_text}")

        task_label = {
            "scroll": "Scroll",
            "reels": "Reels",
            "autoscroll": "Auto Scroll",
            "likes": "Likes",
            "friends": "Add Friends",
        }.get(self.task_type_var.get(), self.task_type_var.get().title())
        if hasattr(self, "top_task_chip"):
            self.top_task_chip.config(text=f"Task: {task_label}")
