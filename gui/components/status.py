import tkinter as tk
from dataclasses import dataclass


DEFAULT_PALETTE = {
    "surface": "#0E1118",
    "surface_alt": "#141820",
    "text": "#E2E8F0",
    "muted": "#64748B",
    "primary": "#00E5FF",
    "secondary": "#7C3AED",
    "success": "#10B981",
    "warning": "#F59E0B",
    "danger": "#EF4444",
    "border": "#1A2030",
    "border_alt": "#222B3A",
}


@dataclass(frozen=True)
class StatusSpec:
    key: str
    label: str
    code: str
    semantic: str
    tag: str
    color_role: str
    bg: str
    sort: int
    aliases: tuple[str, ...] = ()


STATUS_SPECS = {
    "running": StatusSpec("running", "Running", "RUN", "success", "running", "success", "#081C14", 10, ("run",)),
    "active": StatusSpec("active", "Active", "ON", "info", "active", "primary", "#0A1A20", 20, ("online", "ready")),
    "ready": StatusSpec("ready", "Ready", "READY", "success", "active", "success", "#0A1A14", 21),
    "queued": StatusSpec("queued", "Queued", "QUEUE", "warning", "queued", "warning", "#111827", 30, ("queue",)),
    "starting": StatusSpec("starting", "Starting", "START", "warning", "queued", "warning", "#111827", 31),
    "preparing": StatusSpec("preparing", "Preparing", "PREP", "warning", "queued", "warning", "#111827", 32),
    "waiting": StatusSpec("waiting", "Waiting", "WAIT", "warning", "queued", "warning", "#111827", 33),
    "paused": StatusSpec("paused", "Paused", "PAUSE", "warning", "paused", "secondary", "#160F22", 40, ("pause",)),
    "completed": StatusSpec("completed", "Completed", "DONE", "info", "completed", "primary", "#0A1420", 50, ("done", "complete")),
    "inactive": StatusSpec("inactive", "Inactive", "OFF", "secondary", "inactive", "muted", "#0E1118", 60, ("offline",)),
    "idle": StatusSpec("idle", "Idle", "IDLE", "secondary", "idle", "muted", "#0E1118", 61),
    "disabled": StatusSpec("disabled", "Disabled", "OFF", "secondary", "inactive", "muted", "#0E1118", 62),
    "scheduled": StatusSpec("scheduled", "Scheduled", "SCHED", "info", "active", "primary", "#0A1A20", 70),
    "enabled": StatusSpec("enabled", "Enabled", "ON", "success", "active", "success", "#0A1A14", 71),
    "attention": StatusSpec("attention", "Attention", "ATTN", "danger", "attention", "danger", "#1F1720", 80),
    "failed": StatusSpec("failed", "Failed", "FAIL", "danger", "attention", "danger", "#1F1720", 81, ("failure",)),
    "error": StatusSpec("error", "Error", "ERR", "danger", "attention", "danger", "#1F1720", 82, ("errors",)),
    "unknown": StatusSpec("unknown", "Unknown", "UNK", "secondary", "inactive", "muted", "#0E1118", 99),
}


def _build_aliases():
    aliases = {}
    for key, spec in STATUS_SPECS.items():
        aliases[key] = key
        aliases[spec.label.lower()] = key
        for alias in spec.aliases:
            aliases[str(alias).lower()] = key
    return aliases


STATUS_ALIASES = _build_aliases()


def normalize_status(status):
    raw = str(status or "unknown").strip()
    if not raw:
        return "unknown"
    key = raw.lower().replace("_", " ").replace("-", " ")
    key = " ".join(key.split())
    if key in STATUS_ALIASES:
        return STATUS_ALIASES[key]
    for token, mapped in (
        ("error", "error"),
        ("failed", "failed"),
        ("failure", "failed"),
        ("attention", "attention"),
        ("timeout", "attention"),
        ("running", "running"),
        ("queued", "queued"),
        ("waiting", "waiting"),
        ("starting", "starting"),
        ("preparing", "preparing"),
        ("ready", "ready"),
        ("active", "active"),
        ("completed", "completed"),
        ("idle", "idle"),
        ("inactive", "inactive"),
        ("disabled", "disabled"),
        ("enabled", "enabled"),
        ("scheduled", "scheduled"),
        ("paused", "paused"),
    ):
        if token in key:
            return mapped
    return "unknown"


def get_status_spec(status):
    return STATUS_SPECS.get(normalize_status(status), STATUS_SPECS["unknown"])


def status_label(status):
    return get_status_spec(status).label


def status_code(status):
    return get_status_spec(status).code


def status_table_text(status):
    spec = get_status_spec(status)
    return f"[{spec.code}] {spec.label}"


def status_tag(status):
    return get_status_spec(status).tag


def status_bootstyle(status):
    return get_status_spec(status).semantic


def status_sort_key(status):
    return get_status_spec(status).sort


def status_color(status, palette=None):
    palette = palette or DEFAULT_PALETTE
    spec = get_status_spec(status)
    return palette.get(spec.color_role, palette["muted"])


def status_background(status):
    return get_status_spec(status).bg


def status_filter_values():
    return ("All", "Running", "Active", "Inactive", "Paused", "Completed", "Failed")


class StatusPill(tk.Frame):
    """Reusable compact status pill for non-Treeview UI areas."""

    def __init__(
        self,
        parent,
        status="unknown",
        *,
        palette=None,
        text=None,
        font=None,
        padx=8,
        pady=3,
        **kwargs,
    ):
        self.palette = palette or DEFAULT_PALETTE
        self._font = font
        self._padx = padx
        self._pady = pady
        super().__init__(parent, highlightthickness=0, bd=0, **kwargs)

        self.inner = tk.Frame(self, highlightthickness=0, bd=0)
        self.inner.pack(fill="both", expand=True, padx=1, pady=1)
        self.label = tk.Label(
            self.inner,
            font=self._font,
            padx=self._padx,
            pady=self._pady,
            bd=0,
        )
        self.label.pack(fill="both", expand=True)
        self.set_status(status, text=text)

    def set_status(self, status, text=None):
        spec = get_status_spec(status)
        fg = status_color(status, self.palette)
        bg = spec.bg
        border = fg
        label_text = text if text is not None else spec.label
        self.configure(bg=border)
        self.inner.configure(bg=bg)
        self.label.configure(text=label_text, bg=bg, fg=fg)

    def config(self, cnf=None, **kwargs):
        text = kwargs.pop("text", None)
        fg = kwargs.pop("fg", None)
        if text is not None:
            self.label.configure(text=text)
        if fg is not None:
            self.label.configure(fg=fg)
            self.configure(bg=fg)
        if kwargs:
            return super().config(cnf, **kwargs)
        return None

    configure = config
