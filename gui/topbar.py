import tkinter as tk
import ttkbootstrap as tb
from datetime import datetime

from gui.components.status import StatusPill


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
            text="Analytics",
            style="TopTitle.TLabel"
        ).pack(anchor="w")
        self.top_status_label = tb.Label(
            title_wrap,
            text=f"System: Idle | {datetime.now().strftime('%d %b %Y %H:%M')}",
            style="TopSub.TLabel"
        )
        self.top_status_label.pack(anchor="w")

        center_meta = tb.Frame(top_bar, style="Topbar.TFrame")
        center_meta.pack(side="left", padx=(18, 0))
        self.top_selected_chip = self._make_chip(
            center_meta,
            "Selected: 0",
            bg=self.palette.get("primary_bg", self.palette["surface_alt"]),
            fg=self.palette["primary"],
            border_color=self.palette.get("primary_border", self.palette["primary"]),
        )
        self.top_mode_pill = StatusPill(
            center_meta,
            "Idle",
            palette=self.palette,
            text="Mode: Idle",
            font=(self.display_font, 9),
        )
        self.top_mode_pill.pack(side="left", padx=4)
        self.top_task_chip = self._make_chip(
            center_meta,
            "Task: Scroll",
            bg=self.palette.get("secondary_bg", self.palette["surface_alt"]),
            fg=self.palette["secondary"],
            border_color=self.palette.get("secondary_border", self.palette["secondary"]),
        )

        self._top_tab_buttons = {}

        actions = tb.Frame(top_bar, style="Topbar.TFrame")
        actions.pack(side="right")
        tb.Button(actions, text="⟳ Refresh", bootstyle="outline-info", command=self.refresh_all, width=10).pack(side="left", padx=4)
        self.top_stop_button = tb.Button(
            actions,
            text="Stop All",
            bootstyle="danger",
            command=self.stop_automation,
            width=10,
        )
        self.top_stop_button.pack(side="left", padx=4)

        # Single action button that morphs between Start / Pause / Resume.
        self._top_action_mode = "start"
        self.top_action_button = tb.Button(
            actions,
            text="▶ Start Automation",
            bootstyle="info",
            command=self._on_top_action_clicked,
            width=18,
        )
        self.top_action_button.pack(side="left", padx=4)
        self.set_top_action_state("idle")
        self._update_header_chips()

    def _on_top_action_clicked(self):
        """Dispatch the morphing top-bar action button based on current mode."""
        mode = getattr(self, "_top_action_mode", "start")
        if mode == "pause" or mode == "resume":
            self.toggle_pause()
        else:
            self.start_automation()

    def set_top_action_state(self, state):
        """Update the morphing action button to reflect the automation state.

        Accepts: 'idle' / 'running' / 'paused' (case-insensitive). Anything
        else falls back to the idle 'Start Automation' look.
        """
        button = getattr(self, "top_action_button", None)
        if button is None:
            return

        key = str(state).lower() if state is not None else "idle"
        # Normalise common aliases coming from AutomationState / status words.
        alias = {
            "automationstate.running": "running",
            "automationstate.paused": "paused",
            "automationstate.idle": "idle",
            "stopped": "idle",
            "ready": "idle",
        }
        key = alias.get(key, key)

        if key == "running":
            self._top_action_mode = "pause"
            button.configure(text="⏸ Pause Automation", bootstyle="warning")
        elif key == "paused":
            self._top_action_mode = "resume"
            button.configure(text="▶ Resume Automation", bootstyle="success")
        else:
            self._top_action_mode = "start"
            button.configure(text="▶ Start Automation", bootstyle="info")

        # Stop is meaningful only while something is running or paused.
        stop_btn = getattr(self, "top_stop_button", None)
        if stop_btn is not None:
            stop_btn.configure(state="normal" if key in ("running", "paused") else "disabled")

    def _update_header_chips(self, mode_text=None):
        selected = 0
        if hasattr(self, "_ld_checked_names"):
            selected = len(self._ld_checked_names)
        if hasattr(self, "top_selected_chip"):
            self.top_selected_chip.config(text=f"Selected: {selected}")

        if hasattr(self, "top_mode_pill") and mode_text is not None:
            self.top_mode_pill.set_status(mode_text, text=f"Mode: {mode_text}")

        task_label = {
            "scroll": "Scroll",
            "reg_account": "Register",
            "reels": "Reels",
            "test_feature": "Test Feature",
            "autoscroll": "Auto Scroll",
            "likes": "Likes",
            "friends": "Add Friends",
        }.get(self.task_type_var.get(), self.task_type_var.get().title())
        if hasattr(self, "top_task_chip"):
            self.top_task_chip.config(text=f"Task: {task_label}")
