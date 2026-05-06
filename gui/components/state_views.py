import tkinter as tk

import ttkbootstrap as tb

DEFAULT_PALETTE = {
    "surface": "#0E1118",
    "surface_alt": "#141820",
    "text": "#E2E8F0",
    "muted": "#64748B",
    "primary": "#00E5FF",
    "success": "#10B981",
    "warning": "#F59E0B",
    "danger": "#EF4444",
    "border": "#1A2030",
}


class StateView(tb.Frame):
    """Reusable inline empty/loading/error view for dynamic panels."""

    KIND_STYLES = {
        "empty": ("Empty", "info", "primary"),
        "loading": ("Loading", "warning", "warning"),
        "error": ("Error", "danger", "danger"),
        "success": ("Ready", "success", "success"),
    }

    def __init__(
        self,
        parent,
        *,
        kind="empty",
        title="Nothing to show",
        message="There is no data available for this section.",
        actions=None,
        palette=None,
        display_font="Segoe UI Semibold",
        mono_font="Consolas",
        padding=(18, 18),
        **kwargs,
    ):
        self.palette = palette or DEFAULT_PALETTE
        self.display_font = display_font
        self.mono_font = mono_font
        super().__init__(parent, style="CardInner.TFrame", padding=padding, **kwargs)

        self.indicator = tk.Frame(self, height=3, bg=self.palette["primary"])
        self.indicator.pack(fill="x", pady=(0, 12))

        self.badge = tb.Label(self, text="", style="MetricLabel.TLabel")
        self.badge.pack(anchor="w")

        self.title_label = tk.Label(
            self,
            text=title,
            bg=self.palette["surface"],
            fg=self.palette["text"],
            font=(self.display_font, 13),
            anchor="w",
            justify="left",
        )
        self.title_label.pack(anchor="w", pady=(5, 4))

        self.message_label = tk.Label(
            self,
            text=message,
            bg=self.palette["surface"],
            fg=self.palette["muted"],
            font=(self.mono_font, 9),
            anchor="w",
            justify="left",
            wraplength=720,
        )
        self.message_label.pack(anchor="w")

        self.actions_frame = tb.Frame(self, style="CardInner.TFrame")
        self.actions_frame.pack(anchor="w", pady=(12, 0))
        self.set(kind=kind, title=title, message=message, actions=actions or [])

    def set(self, *, kind=None, title=None, message=None, actions=None):
        if kind is not None:
            self.kind = str(kind or "empty").lower()
        label, bootstyle, color_role = self.KIND_STYLES.get(self.kind, self.KIND_STYLES["empty"])
        self.indicator.configure(bg=self.palette.get(color_role, self.palette["primary"]))
        self.badge.configure(text=label.upper(), bootstyle=bootstyle)
        if title is not None:
            self.title_label.configure(text=title)
        if message is not None:
            self.message_label.configure(text=message)
        if actions is not None:
            self._set_actions(actions)

    def _set_actions(self, actions):
        for child in self.actions_frame.winfo_children():
            child.destroy()
        if not actions:
            self.actions_frame.pack_forget()
            return

        if not self.actions_frame.winfo_ismapped():
            self.actions_frame.pack(anchor="w", pady=(12, 0))

        for action in actions:
            if not action:
                continue
            if isinstance(action, dict):
                text = action.get("text", "Action")
                command = action.get("command")
                bootstyle = action.get("bootstyle", "outline-info")
            else:
                text, command = action[:2]
                bootstyle = action[2] if len(action) > 2 else "outline-info"
            tb.Button(
                self.actions_frame,
                text=text,
                command=command,
                bootstyle=bootstyle,
                width=max(10, min(18, len(str(text)) + 2)),
            ).pack(side="left", padx=(0, 8))


def show_state(parent, **kwargs):
    view = StateView(parent, **kwargs)
    view.pack(fill="x", pady=6)
    return view
