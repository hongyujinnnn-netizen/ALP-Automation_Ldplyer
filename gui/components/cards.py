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


class SectionCard(tb.Frame):
    """Standard page section card with shadow, title, subtitle, and body frame."""

    def __init__(
        self,
        parent,
        title,
        subtitle=None,
        *,
        palette=None,
        padding=14,
        body_padding=0,
        title_style="SectionTitle.TLabel",
        subtitle_style="Subtitle.TLabel",
        **kwargs,
    ):
        self.palette = palette or DEFAULT_PALETTE
        super().__init__(parent, style="Shadow.TFrame", padding=(0, 0, 0, 1), **kwargs)

        self.card = tb.Frame(self, style="Card.TFrame", padding=padding)
        self.card.pack(fill="both", expand=True, padx=(0, 1))

        self.title_label = tb.Label(self.card, text=title, style=title_style)
        self.title_label.pack(anchor="w")

        self.subtitle_label = None
        if subtitle:
            self.subtitle_label = tb.Label(self.card, text=subtitle, style=subtitle_style)
            self.subtitle_label.pack(anchor="w", pady=(2, 12))
        else:
            tb.Frame(self.card, height=8, style="CardInner.TFrame").pack(fill="x")

        self.body = tb.Frame(self.card, style="CardInner.TFrame", padding=body_padding)
        self.body.pack(fill="both", expand=True)


class MetricCard(tb.Frame):
    """Compact metric/KPI card with an accent stripe, value, and helper text."""

    def __init__(
        self,
        parent,
        title,
        value="0",
        subtitle=None,
        *,
        accent=None,
        palette=None,
        padding=(12, 10),
        **kwargs,
    ):
        self.palette = palette or DEFAULT_PALETTE
        self.accent = accent or self.palette["primary"]
        super().__init__(parent, style="Shadow.TFrame", padding=(0, 0, 0, 1), **kwargs)

        self.card = tb.Frame(self, style="Card.TFrame", padding=1)
        self.card.pack(fill="both", expand=True)
        self.stripe = tk.Frame(self.card, bg=self.accent, height=3)
        self.stripe.pack(fill="x")

        self.body = tb.Frame(self.card, style="CardInner.TFrame", padding=padding)
        self.body.pack(fill="both", expand=True)
        self.title_label = tb.Label(self.body, text=title.upper(), style="MetricLabel.TLabel")
        self.title_label.pack(anchor="w")
        self.value_label = tb.Label(
            self.body,
            text=str(value),
            style="MetricValue.TLabel",
            foreground=self.accent,
        )
        self.value_label.pack(anchor="w", pady=(5, 1))
        self.subtitle_label = tb.Label(self.body, text=subtitle or "-", style="MetricSub.TLabel")
        self.subtitle_label.pack(anchor="w")

    def set(self, value, subtitle=None, accent=None):
        if accent:
            self.accent = accent
            self.stripe.configure(bg=accent)
            self.value_label.configure(foreground=accent)
        self.value_label.configure(text=str(value))
        if subtitle is not None:
            self.subtitle_label.configure(text=subtitle)


class AlertCard(tb.Frame):
    """Semantic incident/alert card for dashboard and page-level messages."""

    SEVERITY_COLORS = {
        "critical": "danger",
        "warning": "warning",
        "info": "info",
        "success": "success",
        "neutral": "secondary",
    }

    def __init__(
        self,
        parent,
        severity,
        title,
        message,
        *,
        palette=None,
        action_widget=None,
        wraplength=900,
        **kwargs,
    ):
        self.palette = palette or DEFAULT_PALETTE
        self.severity = str(severity or "info").lower()
        self.accent = self._severity_color(self.severity)
        super().__init__(parent, style="Card.TFrame", padding=1, **kwargs)

        tk.Frame(self, bg=self.accent, width=4).pack(side="left", fill="y")
        self.body = tb.Frame(self, style="CardInner.TFrame", padding=(10, 7))
        self.body.pack(side="left", fill="both", expand=True)

        top = tb.Frame(self.body, style="CardInner.TFrame")
        top.pack(fill="x")
        tb.Label(
            top,
            text=self.severity.upper(),
            bootstyle=self.SEVERITY_COLORS.get(self.severity, "secondary"),
            style="Chip.TLabel",
            padding=(8, 2),
        ).pack(side="left")
        self.title_label = tb.Label(
            top,
            text=title,
            style="CardItemTitle.TLabel",
        )
        self.title_label.pack(side="left", padx=(8, 0))
        if action_widget is not None:
            action_widget.pack(in_=top, side="right")

        self.message_label = tb.Label(
            self.body,
            text=message,
            style="MetricSub.TLabel",
            wraplength=wraplength,
        )
        self.message_label.pack(anchor="w", pady=(3, 0))

    def _severity_color(self, severity):
        return {
            "critical": self.palette["danger"],
            "warning": self.palette["warning"],
            "info": self.palette["primary"],
            "success": self.palette["success"],
            "neutral": self.palette["muted"],
        }.get(severity, self.palette["primary"])


class DetailCard(SectionCard):
    """Section card with convenience helpers for structured key/value details."""

    def __init__(self, parent, title, subtitle=None, *, palette=None, **kwargs):
        super().__init__(parent, title, subtitle, palette=palette, **kwargs)
        self.rows = {}

    def add_row(self, key, label, value="-"):
        row = tb.Frame(self.body, style="CardInner.TFrame")
        row.pack(fill="x", pady=4)
        tb.Label(row, text=str(label).upper(), style="MetricLabel.TLabel").pack(side="left")
        value_label = tb.Label(row, text=str(value), style="MetricSub.TLabel", anchor="e")
        value_label.pack(side="right")
        self.rows[key] = value_label
        return value_label

    def set_row(self, key, value):
        if key in self.rows:
            self.rows[key].configure(text=str(value))


class FeedCard(tb.Frame):
    """Compact feed/list item card with accent rail and optional status chip."""

    def __init__(
        self,
        parent,
        title,
        message,
        *,
        accent=None,
        chip_text=None,
        chip_style="secondary",
        palette=None,
        wraplength=620,
        padding=(10, 8),
        **kwargs,
    ):
        self.palette = palette or DEFAULT_PALETTE
        self.accent = accent or self.palette["primary"]
        super().__init__(parent, style="Card.TFrame", padding=1, **kwargs)

        tk.Frame(self, bg=self.accent, width=3).pack(side="left", fill="y")
        self.body = tb.Frame(self, style="CardInner.TFrame", padding=padding)
        self.body.pack(side="left", fill="both", expand=True)

        self.header = tb.Frame(self.body, style="CardInner.TFrame")
        self.header.pack(fill="x")
        self.title_label = tb.Label(
            self.header,
            text=title,
            style="CardItemTitle.TLabel",
        )
        self.title_label.pack(side="left")
        self.chip_label = None
        if chip_text:
            self.chip_label = tb.Label(
                self.header,
                text=chip_text,
                bootstyle=chip_style,
                style="Chip.TLabel",
                padding=(8, 2),
            )
            self.chip_label.pack(side="right")

        self.message_label = tb.Label(
            self.body,
            text=message,
            style="MetricSub.TLabel",
            wraplength=wraplength,
        )
        self.message_label.pack(anchor="w", pady=(4, 0))
