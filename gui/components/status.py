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
    "primary_bg": "#0A1A20",
    "secondary_bg": "#160F22",
    "success_bg": "#081C14",
    "warning_bg": "#111827",
    "danger_bg": "#1F1720",
    "muted_bg": "#0E1118",
    "tree_odd": "#0C1016",
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
    "running": StatusSpec(
        "running", "Running", "RUN", "success", "running", "success", "#081C14", 10, ("run",)
    ),
    "live": StatusSpec(
        "live", "Live", "LIVE", "success", "active", "success", "#081C14", 19, ("online account",)
    ),
    "active": StatusSpec(
        "active", "Active", "ON", "info", "active", "primary", "#0A1A20", 20, ("online", "ready")
    ),
    "ready": StatusSpec("ready", "Ready", "READY", "success", "active", "success", "#0A1A14", 21),
    "queued": StatusSpec(
        "queued", "Queued", "QUEUE", "warning", "queued", "warning", "#111827", 30, ("queue",)
    ),
    "starting": StatusSpec("starting", "Starting", "START", "warning", "queued", "warning", "#111827", 31),
    "preparing": StatusSpec("preparing", "Preparing", "PREP", "warning", "queued", "warning", "#111827", 32),
    "waiting": StatusSpec("waiting", "Waiting", "WAIT", "warning", "queued", "warning", "#111827", 33),
    "paused": StatusSpec(
        "paused", "Paused", "PAUSE", "warning", "paused", "secondary", "#160F22", 40, ("pause",)
    ),
    "completed": StatusSpec(
        "completed", "Completed", "DONE", "info", "completed", "primary", "#0A1420", 50, ("done", "complete")
    ),
    "inactive": StatusSpec(
        "inactive", "Inactive", "OFF", "secondary", "inactive", "muted", "#0E1118", 60, ("offline",)
    ),
    "idle": StatusSpec("idle", "Idle", "IDLE", "secondary", "idle", "muted", "#0E1118", 61),
    "disabled": StatusSpec("disabled", "Disabled", "OFF", "secondary", "inactive", "muted", "#0E1118", 62),
    "neutral": StatusSpec(
        "neutral", "Neutral", "INFO", "secondary", "inactive", "muted", "#0E1118", 63, ("secondary",)
    ),
    "scheduled": StatusSpec("scheduled", "Scheduled", "SCHED", "info", "active", "primary", "#0A1A20", 70),
    "enabled": StatusSpec("enabled", "Enabled", "ON", "success", "active", "success", "#0A1A14", 71),
    "success": StatusSpec("success", "Success", "OK", "success", "active", "success", "#0A1A14", 72),
    "info": StatusSpec("info", "Info", "INFO", "info", "active", "primary", "#0A1A20", 73),
    "warning": StatusSpec("warning", "Warning", "WARN", "warning", "queued", "warning", "#111827", 74),
    "attention": StatusSpec("attention", "Attention", "ATTN", "danger", "attention", "danger", "#1F1720", 80),
    "critical": StatusSpec(
        "critical", "Critical", "CRIT", "danger", "attention", "danger", "#1F1720", 80, ("incident",)
    ),
    "failed": StatusSpec(
        "failed", "Failed", "FAIL", "danger", "attention", "danger", "#1F1720", 81, ("failure",)
    ),
    "error": StatusSpec("error", "Error", "ERR", "danger", "attention", "danger", "#1F1720", 82, ("errors",)),
    "dead": StatusSpec("dead", "Dead", "DEAD", "danger", "dead", "danger", "#1F1720", 83),
    "novery": StatusSpec(
        "novery",
        "No Verify",
        "NOVER",
        "warning",
        "novery",
        "warning",
        "#111827",
        84,
        ("no verify", "not verified"),
    ),
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
        ("live", "live"),
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
        ("secondary", "neutral"),
        ("neutral", "neutral"),
        ("enabled", "enabled"),
        ("scheduled", "scheduled"),
        ("paused", "paused"),
        ("success", "success"),
        ("warning", "warning"),
        ("critical", "critical"),
        ("info", "info"),
        ("dead", "dead"),
        ("novery", "novery"),
        ("no verify", "novery"),
        ("unknown", "unknown"),
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


def status_count_text(status, count):
    return f"{count} {status_label(status)}"


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


def status_background(status, palette=None):
    palette = palette or DEFAULT_PALETTE
    spec = get_status_spec(status)
    if spec.color_role == "primary":
        return palette.get("primary_bg", spec.bg)
    if spec.color_role == "secondary":
        return palette.get("secondary_bg", spec.bg)
    return palette.get(f"{spec.color_role}_bg", spec.bg)


def status_filter_values():
    return ("All", "Running", "Active", "Inactive", "Paused", "Completed", "Failed")


def configure_status_tree_tags(tree, palette=None, *, include_zebra=False):
    """Apply shared status colors to a Treeview-compatible tag set."""
    palette = palette or DEFAULT_PALETTE
    configured = set()
    for spec in STATUS_SPECS.values():
        tag = spec.tag
        if tag in configured:
            continue
        configured.add(tag)
        background = "" if tag in {"inactive", "idle"} else status_background(spec.key, palette)
        foreground = status_color(spec.key, palette)
        tree.tag_configure(tag, background=background, foreground=foreground)

    if include_zebra:
        tree.tag_configure("odd_row", background=palette.get("tree_odd", "#0C1016"))
        tree.tag_configure("even_row", background=palette["surface"])


def event_level_status(level):
    return {
        "SUCCESS": "success",
        "WARNING": "warning",
        "ERROR": "error",
        "INFO": "info",
        "DEBUG": "unknown",
    }.get(str(level or "").upper(), "unknown")


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
        self._status = status
        self._text = text
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
        self._status = status
        self._text = text
        spec = get_status_spec(status)
        fg = status_color(status, self.palette)
        bg = status_background(status, self.palette)
        border = fg
        label_text = text if text is not None else spec.label
        self.configure(bg=border)
        self.inner.configure(bg=bg)
        self.label.configure(text=label_text, bg=bg, fg=fg)

    def update_palette(self, palette):
        self.palette = palette or DEFAULT_PALETTE
        self.set_status(self._status, text=self._text)

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


StatusBadge = StatusPill
