"""
Content Management Page — Modern three-pane redesign.

Workflow:
    [Left]   List of LDPlayer instances as cards (avatar + name + counts).
    [Middle] When an instance is selected → list its shared-folder subfolders
             as folder-icon cards with file counts.
    [Right]  When a folder is selected → list its videos with size + actions.

Visual upgrades over the previous version:
    • Header strip with an app icon, page title, search box and refresh
    • Four metric tiles (Instances · Sub-folders · Total videos · Disk used)
    • Breadcrumb + primary action toolbar
    • Card rows with hover/selected accents instead of flat Treeview rows
    • Coloured initials avatar per instance
    • Folder-icon rows with pill count badges
    • Selection action-bar at the bottom of the videos pane
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, ttk
from tkinter import messagebox as MessageBox

import ttkbootstrap as tb

from gui.components.cards import DetailCard


# ── constants ────────────────────────────────────────────────────────
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".m4v", ".3gp"}

# Tinted avatar palette (BG, FG) pairs — picked from app's accent ramps
AVATAR_PALETTE = [
    ("#EEEDFE", "#3C3489"),  # purple
    ("#E1F5EE", "#085041"),  # teal
    ("#FAECE7", "#712B13"),  # coral
    ("#FBEAF0", "#72243E"),  # pink
    ("#E6F1FB", "#0C447C"),  # blue
    ("#EAF3DE", "#27500A"),  # green
    ("#FAEEDA", "#633806"),  # amber
    ("#F1EFE8", "#444441"),  # gray
]


# ── helpers ──────────────────────────────────────────────────────────
def _is_video(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in VIDEO_EXTS


def _human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def _count_videos(folder: str) -> int:
    if not folder or not os.path.isdir(folder):
        return 0
    n = 0
    try:
        for entry in os.scandir(folder):
            if entry.is_file() and _is_video(entry.name):
                n += 1
    except OSError:
        return 0
    return n


def _list_videos(folder: str):
    if not folder or not os.path.isdir(folder):
        return []
    out = []
    try:
        for entry in os.scandir(folder):
            if entry.is_file() and _is_video(entry.name):
                try:
                    st = entry.stat()
                    out.append((entry.name, st.st_size, st.st_mtime, entry.path))
                except OSError:
                    continue
    except OSError:
        return []
    out.sort(key=lambda x: x[0].lower())
    return out


def _folder_size(folder: str) -> int:
    if not folder or not os.path.isdir(folder):
        return 0
    total = 0
    try:
        for entry in os.scandir(folder):
            try:
                if entry.is_file():
                    total += entry.stat().st_size
            except OSError:
                continue
    except OSError:
        return 0
    return total


def _initials(name: str) -> str:
    if not name:
        return "?"
    parts = [p for p in name.replace("_", " ").replace("-", " ").split() if p]
    if not parts:
        return name[:2].upper()
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


def _avatar_colors(name: str) -> tuple[str, str]:
    if not name:
        return AVATAR_PALETTE[0]
    h = int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16)
    return AVATAR_PALETTE[h % len(AVATAR_PALETTE)]


def _folder_color_for(name: str) -> str:
    """Stable per-name colour using only the FG (dark) tone of the avatar palette."""
    if not name:
        return AVATAR_PALETTE[0][1]
    h = int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16)
    return AVATAR_PALETTE[h % len(AVATAR_PALETTE)][1]


def _relative_time(mtime: float) -> str:
    if not mtime:
        return ""
    try:
        delta = datetime.now() - datetime.fromtimestamp(mtime)
    except Exception:
        return ""
    secs = int(delta.total_seconds())
    if secs < 0:
        return "just now"
    if secs < 60:
        return "just now"
    if secs < 3600:
        m = secs // 60
        return f"{m} minute{'s' if m != 1 else ''} ago"
    days = delta.days
    if days <= 0:
        h = secs // 3600
        return f"{h} hour{'s' if h != 1 else ''} ago"
    if days == 1:
        return "Yesterday"
    if days < 7:
        return f"{days} days ago"
    if days < 30:
        w = days // 7
        return f"{w} week{'s' if w != 1 else ''} ago"
    if days < 365:
        mo = days // 30
        return f"{mo} month{'s' if mo != 1 else ''} ago"
    y = days // 365
    return f"{y} year{'s' if y != 1 else ''} ago"


def _load_used_set(folder: str) -> set:
    """Best-effort load of a `.used.json` sidecar in `folder`. Returns empty set if absent."""
    if not folder:
        return set()
    sidecar = os.path.join(folder, ".used.json")
    if not os.path.isfile(sidecar):
        return set()
    try:
        with open(sidecar, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return set()
    if isinstance(data, list):
        return {str(x) for x in data}
    if isinstance(data, dict):
        used = data.get("used")
        if isinstance(used, list):
            return {str(x) for x in used}
        return {str(k) for k in data.keys()}
    return set()


def _open_in_explorer(path: str) -> None:
    if not path:
        return
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


# ── widgets ──────────────────────────────────────────────────────────
class ScrollableCardList(tb.Frame):
    """A vertical scroll area that holds custom card rows.

    Scrolling rules:
      - Mouse wheel only scrolls the pane the cursor is currently over.
      - Each newly-added child (and *all* of its descendants) automatically
        receives the same wheel binding via ``register_child()`` so the user
        can scroll while hovering over any card, label, avatar, etc.
      - On Windows/macOS we use ``<MouseWheel>``; on Linux ``<Button-4>``
        and ``<Button-5>``. The handler treats both consistently.
    """

    # Track all live instances so we can dispatch wheel events to the
    # right pane based on cursor position (used as a fallback).
    _instances: list["ScrollableCardList"] = []

    def __init__(self, parent, palette, **kwargs):
        super().__init__(parent, **kwargs)
        self.palette = palette

        self.canvas = tk.Canvas(
            self,
            highlightthickness=0,
            bd=0,
            bg=palette.get("surface", "#FFFFFF"),
        )
        self.vsb = tb.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)

        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner = tb.Frame(self.canvas)
        self._inner_id = self.canvas.create_window(
            (0, 0), window=self.inner, anchor="nw"
        )

        # Track active pane via Enter/Leave on the canvas so wheel events
        # can be routed correctly without bind_all collisions.
        self._active = False
        self.canvas.bind("<Enter>", self._on_enter)
        self.canvas.bind("<Leave>", self._on_leave)
        self.inner.bind("<Enter>",  self._on_enter)
        self.inner.bind("<Leave>",  self._on_leave)

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # Direct wheel bindings on the canvas (no bind_all so panes
        # don't fight each other).
        self._bind_wheel(self.canvas)
        self._bind_wheel(self.inner)

        # Also catch keys when focused
        self.canvas.bind("<Up>",       lambda _e: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind("<Down>",     lambda _e: self.canvas.yview_scroll( 1, "units"))
        self.canvas.bind("<Prior>",    lambda _e: self.canvas.yview_scroll(-1, "pages"))
        self.canvas.bind("<Next>",     lambda _e: self.canvas.yview_scroll( 1, "pages"))
        self.canvas.bind("<Home>",     lambda _e: self.canvas.yview_moveto(0.0))
        self.canvas.bind("<End>",      lambda _e: self.canvas.yview_moveto(1.0))

        ScrollableCardList._instances.append(self)
        self.bind("<Destroy>", self._on_destroy)

    # ── public API ──────────────────────────────────────────────────
    def register_child(self, widget):
        """Recursively bind mouse-wheel events on a widget and all its
        descendants. Call this whenever you add a CardRow (or any complex
        child) so scrolling works no matter where the cursor sits.
        """
        self._bind_wheel(widget)
        for child in widget.winfo_children():
            self.register_child(child)

    def clear(self):
        for child in self.inner.winfo_children():
            child.destroy()
        # Reset scroll to top so the next population doesn't keep the
        # previous list's scroll offset.
        self.canvas.yview_moveto(0.0)

    # ── internals ───────────────────────────────────────────────────
    def _bind_wheel(self, widget):
        # Use add="+" so we don't clobber other bindings on the widget.
        widget.bind("<MouseWheel>",   self._on_mousewheel,         add="+")
        widget.bind("<Button-4>",     self._on_mousewheel_linux_up,   add="+")
        widget.bind("<Button-5>",     self._on_mousewheel_linux_down, add="+")
        # Shift-MouseWheel is sometimes the only one delivered on macOS
        widget.bind("<Shift-MouseWheel>", self._on_mousewheel,     add="+")
        # Enter/Leave on every child too, so the "active pane" stays
        # accurate as the cursor moves across cards.
        widget.bind("<Enter>", self._on_enter, add="+")

    def _on_enter(self, _event=None):
        self._active = True
        try:
            self.canvas.focus_set()
        except Exception:
            pass

    def _on_leave(self, _event=None):
        # Don't immediately deactivate — pointer may have moved onto a child
        # widget, which fires Leave on the parent. Re-check on next tick.
        self.after_idle(self._recheck_active)

    def _recheck_active(self):
        try:
            x, y = self.winfo_pointerxy()
            w = self.winfo_containing(x, y)
            self._active = self._is_descendant(w)
        except Exception:
            self._active = False

    def _is_descendant(self, w) -> bool:
        while w is not None:
            if w is self or w is self.canvas or w is self.inner:
                return True
            try:
                w = w.master
            except Exception:
                return False
        return False

    def _on_inner_configure(self, _event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self._inner_id, width=event.width)

    def _scroll_by(self, units: int):
        # Skip when content fits — avoids the canvas bouncing when there's
        # nothing to scroll.
        try:
            first, last = self.canvas.yview()
            if first <= 0.0 and last >= 1.0:
                return
        except Exception:
            pass
        self.canvas.yview_scroll(units, "units")

    def _on_mousewheel(self, event):
        # event.delta: Windows = ±120 per notch, macOS = small ints
        if not self._active:
            # Fallback: dispatch to whichever instance contains the pointer
            target = ScrollableCardList._find_active()
            if target is not None and target is not self:
                target._on_mousewheel(event)
            return "break" if self._active else None
        if event.delta == 0:
            return "break"
        # Negative delta → scroll down; positive → up. Normalize to "units".
        if sys.platform == "darwin":
            units = -1 if event.delta > 0 else 1
        else:
            units = int(-1 * (event.delta / 120)) or (-1 if event.delta > 0 else 1)
        self._scroll_by(units)
        return "break"

    def _on_mousewheel_linux_up(self, _event):
        if not self._active:
            target = ScrollableCardList._find_active()
            if target is not None and target is not self:
                return target._on_mousewheel_linux_up(_event)
            return None
        self._scroll_by(-1)
        return "break"

    def _on_mousewheel_linux_down(self, _event):
        if not self._active:
            target = ScrollableCardList._find_active()
            if target is not None and target is not self:
                return target._on_mousewheel_linux_down(_event)
            return None
        self._scroll_by(1)
        return "break"

    def _on_destroy(self, _event=None):
        try:
            ScrollableCardList._instances.remove(self)
        except ValueError:
            pass

    @classmethod
    def _find_active(cls):
        """Return the instance whose canvas currently contains the pointer."""
        for inst in cls._instances:
            try:
                if not inst.winfo_exists():
                    continue
                x, y = inst.winfo_pointerxy()
                w = inst.winfo_containing(x, y)
                if inst._is_descendant(w):
                    return inst
            except Exception:
                continue
        return None


class CardRow(tk.Frame):
    """One selectable row, drawn as a card with hover and selected states.

    on_click(row) is called when the row is clicked.
    """

    def __init__(
        self,
        parent,
        palette,
        *,
        leading=None,        # callable(parent) → widget for the left slot
        title="",
        subtitle="",
        trailing_text="",
        trailing_pill=None,  # (text, fg, bg) or None
        on_click=None,
        on_double_click=None,
        accent_color=None,
    ):
        bg = palette.get("surface", "#FFFFFF")
        super().__init__(
            parent, bg=bg, bd=0,
            highlightthickness=1,
            highlightbackground=bg,
            highlightcolor=bg,
        )

        self.palette = palette
        self.on_click = on_click
        self.on_double_click = on_double_click
        self._selected = False
        self._hover = False
        self._accent = accent_color or palette.get("primary", "#2563EB")

        self._normal_bg = bg
        self._hover_bg = palette.get("hover_bg", palette.get("surface_alt", "#F1F5F9"))
        self._selected_bg = palette.get(
            "selected_bg", palette.get("primary_bg", "#E6F1FB")
        )

        # Outer container with a vertical accent stripe on the left
        self.stripe = tk.Frame(self, width=4, bg=self._normal_bg, bd=0)
        self.stripe.pack(side="left", fill="y")

        # Inner padding box (this is what shows hover/selected colour)
        self.body = tk.Frame(self, bg=self._normal_bg, bd=0)
        self.body.pack(side="left", fill="both", expand=True, padx=0, pady=0)

        inner = tk.Frame(self.body, bg=self._normal_bg)
        inner.pack(fill="both", expand=True, padx=10, pady=5)

        # Leading slot
        if leading is not None:
            lead_widget = leading(inner)
            lead_widget.pack(side="left", padx=(0, 10))

        # Text column
        text_col = tk.Frame(inner, bg=self._normal_bg)
        text_col.pack(side="left", fill="both", expand=True)

        title_row = tk.Frame(text_col, bg=self._normal_bg)
        title_row.pack(fill="x")

        self._title_font_normal = ("Segoe UI", 10)
        self._title_font_selected = ("Segoe UI Semibold", 10)
        self.title_label = tk.Label(
            title_row,
            text=title,
            bg=self._normal_bg,
            fg=palette.get("text", "#111827"),
            font=self._title_font_normal,
            anchor="w",
        )
        self.title_label.pack(side="left", fill="x", expand=True)

        if trailing_text:
            self.trailing_label = tk.Label(
                title_row,
                text=trailing_text,
                bg=self._normal_bg,
                fg=palette.get("muted", "#64748B"),
                font=("Segoe UI", 9),
                anchor="e",
            )
            self.trailing_label.pack(side="right")
        else:
            self.trailing_label = None

        if trailing_pill is not None:
            pill_text, pill_fg, pill_bg = trailing_pill
            self.pill = tk.Label(
                title_row,
                text=pill_text,
                bg=pill_bg,
                fg=pill_fg,
                font=("Segoe UI Semibold", 9),
                padx=8,
                pady=1,
                bd=0,
                relief="flat",
            )
            self.pill.pack(side="right", padx=(0, 6))
        else:
            self.pill = None

        if subtitle:
            self.subtitle_label = tk.Label(
                text_col,
                text=subtitle,
                bg=self._normal_bg,
                fg=palette.get("muted", "#64748B"),
                font=("Segoe UI", 9),
                anchor="w",
            )
            self.subtitle_label.pack(fill="x", pady=(2, 0))
        else:
            self.subtitle_label = None

        # Wire mouse events on every child widget so the whole row is clickable
        for w in self._all_widgets():
            w.bind("<Enter>", self._on_enter, add="+")
            w.bind("<Leave>", self._on_leave, add="+")
            w.bind("<Button-1>", self._on_click_event, add="+")
            if on_double_click is not None:
                w.bind("<Double-Button-1>", self._on_double_click_event, add="+")

    # ── interactive states ──
    def _all_widgets(self):
        widgets = [self, self.body]
        def walk(w):
            widgets.append(w)
            for c in w.winfo_children():
                walk(c)
        walk(self.body)
        return widgets

    def _apply_bg(self, bg):
        self.body.configure(bg=bg)
        for w in self._all_widgets():
            if w is self.stripe or w is self.pill:
                continue
            try:
                w.configure(bg=bg)
            except tk.TclError:
                pass

    def _on_enter(self, _event=None):
        self._hover = True
        if not self._selected:
            self._apply_bg(self._hover_bg)

    def _on_leave(self, _event=None):
        self._hover = False
        if not self._selected:
            self._apply_bg(self._normal_bg)

    def _on_click_event(self, _event=None):
        if self.on_click is not None:
            self.on_click(self)

    def _on_double_click_event(self, _event=None):
        if self.on_double_click is not None:
            self.on_double_click(self)

    def set_selected(self, selected: bool):
        self._selected = selected
        if selected:
            self._apply_bg(self._selected_bg)
            self.stripe.configure(bg=self._accent)
            try:
                self.configure(highlightbackground=self._accent,
                               highlightcolor=self._accent)
            except tk.TclError:
                pass
            try:
                self.title_label.configure(font=self._title_font_selected)
            except tk.TclError:
                pass
        else:
            bg = self._hover_bg if self._hover else self._normal_bg
            self._apply_bg(bg)
            self.stripe.configure(bg=self._normal_bg)
            try:
                self.configure(highlightbackground=self._normal_bg,
                               highlightcolor=self._normal_bg)
            except tk.TclError:
                pass
            try:
                self.title_label.configure(font=self._title_font_normal)
            except tk.TclError:
                pass


def _make_avatar(parent, palette, name: str, size: int = 32):
    bg, fg = _avatar_colors(name)
    canvas = tk.Canvas(
        parent,
        width=size,
        height=size,
        highlightthickness=0,
        bd=0,
        bg=palette.get("surface", "#FFFFFF"),
    )
    # rounded square
    r = 6
    canvas.create_rectangle(
        0, r, size, size - r, fill=bg, outline=bg,
    )
    canvas.create_rectangle(
        r, 0, size - r, size, fill=bg, outline=bg,
    )
    for cx, cy in ((r, r), (size - r, r), (r, size - r), (size - r, size - r)):
        canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=bg, outline=bg)
    canvas.create_text(
        size // 2, size // 2 + 1,
        text=_initials(name),
        fill=fg,
        font=("Segoe UI Semibold", 9),
    )
    return canvas


def _make_folder_icon(parent, palette, color="#0C447C", size: int = 32):
    bg = palette.get("surface", "#FFFFFF")
    canvas = tk.Canvas(
        parent,
        width=size,
        height=size,
        highlightthickness=0,
        bd=0,
        bg=bg,
    )
    # Tab
    canvas.create_rectangle(4, 8, 14, 12, fill=color, outline=color)
    # Body
    canvas.create_rectangle(4, 11, size - 4, size - 6, fill=color, outline=color)
    # Highlight strip
    canvas.create_rectangle(4, 14, size - 4, 17, fill=bg, outline=bg)
    return canvas


def _make_video_icon(parent, palette, size: int = 32):
    bg = palette.get("surface", "#FFFFFF")
    canvas = tk.Canvas(
        parent,
        width=size, height=size,
        highlightthickness=0, bd=0, bg=bg,
    )
    canvas.create_rectangle(4, 8, size - 4, size - 8, fill="#1A1F2C", outline="#1A1F2C")
    # play triangle
    canvas.create_polygon(
        size / 2 - 4, size / 2 - 5,
        size / 2 - 4, size / 2 + 5,
        size / 2 + 5, size / 2,
        fill="#FFFFFF", outline="#FFFFFF",
    )
    return canvas


# ── Page mixin ───────────────────────────────────────────────────────
class ContentPageMixin:
    # ──────────────────────────────────────────────────── Tab entry ──
    def create_content_tab(self):
        content_tab = tb.Frame(self.notebook)
        self.notebook.add(content_tab, text="Content")
        self.create_content_management_section(content_tab)

    # ────────────────────────────────────────────────── Main layout ──
    def create_content_management_section(self, parent):
        # selection state
        self._content_selected_instance = None
        self._content_selected_folder = None
        self._content_instance_rows = {}   # name → CardRow
        self._content_folder_rows = {}     # abs_path → CardRow
        self._content_video_rows = {}      # abs_path → CardRow
        self._content_selected_videos = set()  # set of abs paths
        self._content_search_query = ""
        self._content_instances_raw = []
        self._content_instances_load_error = None
        self._content_folders_raw = []
        self._content_folders_shared_root = None
        self._content_folders_load_error = None
        self._content_videos_raw = []
        self._content_videos_folder = None
        self._content_used_set = set()

        p = self.palette
        surface = p.get("surface", "#FFFFFF")
        surface_alt = p.get("surface_alt", "#F1F5F9")
        border = p.get("border", "#E5E7EB")
        text_clr = p.get("text", "#111827")
        muted = p.get("muted", "#64748B")

        content_frame = self._create_card_section(
            parent,
            "Content Library",
            "Browse videos by LD instance → shared folder → file. "
            "Add, rename, move, or delete videos in-place.",
            expand=True,
        )

        # ── Header row: breadcrumb (left) · metric chips · search (right) ──
        header_row = tb.Frame(content_frame)
        header_row.pack(fill="x", padx=4, pady=(8, 6))

        # search box (packed first so it sits flush right)
        search_wrap = tk.Frame(
            header_row, bg=surface_alt, bd=0,
            highlightthickness=1,
            highlightbackground=border, highlightcolor=border,
        )
        search_wrap.pack(side="right", padx=(8, 0))
        tk.Label(
            search_wrap, text="🔍", bg=surface_alt, fg=muted,
            font=("Segoe UI", 9),
        ).pack(side="left", padx=(8, 4), pady=4)
        self._content_search_var = tk.StringVar(value="")
        self._content_search_entry = tk.Entry(
            search_wrap, textvariable=self._content_search_var, width=24,
            bd=0, relief="flat", bg=surface_alt, fg=text_clr,
            insertbackground=text_clr, font=("Segoe UI", 9),
        )
        self._content_search_entry.pack(side="left", pady=4)
        self._content_search_clear_btn = tk.Label(
            search_wrap, text="×", bg=surface_alt, fg=muted,
            font=("Segoe UI", 11), cursor="hand2",
        )
        self._content_search_clear_btn.pack(side="right", padx=(2, 8), pady=4)
        self._content_search_clear_btn.bind(
            "<Button-1>", lambda _e: self._content_clear_search()
        )
        self._content_search_entry.bind("<KeyRelease>", self._content_on_search)
        self._content_install_search_placeholder()

        # metric chips
        chips = tk.Frame(header_row, bg=surface)
        chips.pack(side="right")
        self._content_metric_labels = {}
        for key, label in (
            ("instances", "Instances"),
            ("folders", "Sub-folders"),
            ("videos", "Total videos"),
            ("disk", "Disk used"),
        ):
            chip = tk.Frame(chips, bg=surface_alt)
            chip.pack(side="left", padx=(0, 6))
            inner = tk.Frame(chip, bg=surface_alt)
            inner.pack(padx=10, pady=5)
            tk.Label(
                inner, text=label.upper(),
                bg=surface_alt, fg=muted,
                font=("Segoe UI", 8, "bold"), anchor="w",
            ).pack(anchor="w")
            value_label = tk.Label(
                inner, text="—",
                bg=surface_alt, fg=text_clr,
                font=("Segoe UI Semibold", 14), anchor="w",
            )
            value_label.pack(anchor="w")
            self._content_metric_labels[key] = value_label

        # breadcrumb (fills remaining space on the left)
        bc_box = tk.Frame(header_row, bg=surface)
        bc_box.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._content_breadcrumb_top = tk.Label(
            bc_box, text="Select an instance to begin",
            bg=surface, fg=muted, font=("Segoe UI", 10),
            anchor="center", justify="center",
        )
        self._content_breadcrumb_top.pack(fill="x")
        self._content_breadcrumb_path = tk.Label(
            bc_box, text="", bg=surface,
            fg=muted, font=("Segoe UI", 8), anchor="w",
        )
        # path label only shows once a folder is selected

        # ── Three-pane split ─────────────────────────────────────────
        split = ttk.Panedwindow(content_frame, orient=tk.HORIZONTAL)
        split.pack(fill="both", expand=True, padx=4, pady=(0, 8))

        inst_card   = DetailCard(split, "LD Instances",   palette=self.palette, padding=6)
        folder_card = DetailCard(split, "Shared folders", palette=self.palette, padding=6)
        videos_card = DetailCard(split, "Videos",         palette=self.palette, padding=6)
        split.add(inst_card,   weight=2)
        split.add(folder_card, weight=2)
        split.add(videos_card, weight=3)

        self._content_add_pane_actions(inst_card, [
            ("⟳ Refresh", self._content_refresh_all, "outline-secondary"),
        ])
        self._content_add_pane_actions(folder_card, [
            ("＋ New folder", self._content_new_subfolder, "outline-secondary"),
            ("🔗 Shared path", self._content_set_shared_folder, "outline-info"),
        ])
        self._content_add_pane_actions(videos_card, [
            ("⬆ Add videos", self._content_add_videos, "outline-primary"),
        ])

        # Pane 1: Instances
        self.instances_list = ScrollableCardList(inst_card.body, self.palette)
        self.instances_list.pack(fill="both", expand=True)
        self._instances_empty_label = tk.Label(
            inst_card.body, text="Loading instances…",
            bg=surface, fg=muted, font=("Segoe UI", 10),
        )

        # Pane 2: Folders
        self.folders_list = ScrollableCardList(folder_card.body, self.palette)
        self.folders_list.pack(fill="both", expand=True)
        self._folders_empty_label = tk.Label(
            folder_card.body, text="Select an instance",
            bg=surface, fg=muted, font=("Segoe UI", 10),
        )

        # Pane 3: Videos (list + action bar)
        videos_outer = tk.Frame(videos_card.body, bg=surface)
        videos_outer.pack(fill="both", expand=True)

        self.videos_list = ScrollableCardList(videos_outer, self.palette)
        self.videos_list.pack(fill="both", expand=True)

        self._videos_empty_frame = tk.Frame(videos_outer, bg=surface)
        self._videos_empty_label = tk.Label(
            self._videos_empty_frame, text="Select a folder",
            bg=surface, fg=muted, font=("Segoe UI", 10),
        )
        self._videos_empty_label.pack(pady=(20, 8))
        self._videos_upload_placeholder = self._content_make_upload_placeholder(
            self._videos_empty_frame, surface, muted,
            on_click=self._content_add_videos,
        )

        # Action bar (only shown when videos are selected)
        self._video_actionbar = tk.Frame(
            videos_outer, bg=p.get("text", "#111827"),
            bd=0, highlightthickness=0,
        )
        ab_inner = tk.Frame(self._video_actionbar, bg=p.get("text", "#111827"))
        ab_inner.pack(fill="x", padx=10, pady=6)
        self._video_action_count = tk.Label(
            ab_inner, text="0 selected",
            bg=p.get("text", "#111827"), fg="#FFFFFF",
            font=("Segoe UI", 9),
        )
        self._video_action_count.pack(side="left")
        for text, cmd, style in (
            ("✎ Rename",     self._content_rename_video,         "outline-light"),
            ("⇲ Open",       self._content_open_selected_video,  "outline-light"),
            ("🗑 Delete",    self._content_delete_selected,      "danger"),
        ):
            tb.Button(ab_inner, text=text, command=cmd, bootstyle=style).pack(
                side="right", padx=3
            )

        # initial load
        self._content_refresh_all()

    # ──────────────────────────────────────────── pane helpers ──
    def _content_add_pane_actions(self, card, actions):
        """Re-flow a DetailCard's title row to include small action buttons on the right."""
        title_text = card.title_label.cget("text")
        try:
            title_style = str(card.title_label.cget("style"))
        except tk.TclError:
            title_style = "SectionTitle.TLabel"
        card.title_label.pack_forget()
        header = tb.Frame(card.card, style="Card.TFrame")
        header.pack(fill="x", before=card.body)
        tb.Label(header, text=title_text, style=title_style).pack(side="left")
        btn_frame = tb.Frame(header, style="Card.TFrame")
        btn_frame.pack(side="right")
        for text, cmd, style in actions:
            tb.Button(btn_frame, text=text, command=cmd, bootstyle=style).pack(
                side="left", padx=(4, 0)
            )

    def _content_make_upload_placeholder(self, parent, surface, muted, on_click):
        """A clickable dashed-border placeholder shown in empty Videos pane."""
        wrapper = tk.Frame(parent, bg=surface)
        canvas = tk.Canvas(
            wrapper, height=72, bg=surface,
            highlightthickness=0, bd=0, cursor="hand2",
        )
        canvas.pack(fill="x", padx=24, pady=(0, 8))

        def redraw(_e=None):
            canvas.delete("all")
            w = max(canvas.winfo_width(), 80)
            h = 72
            canvas.create_rectangle(
                2, 2, w - 2, h - 2,
                outline=muted, dash=(6, 4), width=1,
            )
            canvas.create_text(
                w // 2, h // 2,
                text="⬆  Click here or use 'Add videos' to import",
                fill=muted, font=("Segoe UI", 10),
            )

        canvas.bind("<Configure>", redraw)
        canvas.bind("<Button-1>", lambda _e: on_click())
        wrapper._canvas = canvas
        return wrapper

    # ──────────────────────────────────────────── search ──
    def _content_install_search_placeholder(self):
        self._content_search_placeholder = "Search instances, folders, videos…"
        entry = self._content_search_entry
        self._content_search_text_color = self.palette.get("text", "#111827")
        self._content_search_muted_color = self.palette.get("muted", "#64748B")
        self._content_search_is_placeholder = False

        def show_placeholder():
            if not self._content_search_var.get():
                entry.configure(fg=self._content_search_muted_color)
                self._content_search_var.set(self._content_search_placeholder)
                self._content_search_is_placeholder = True

        def on_focus_in(_e):
            if getattr(self, "_content_search_is_placeholder", False):
                self._content_search_var.set("")
                entry.configure(fg=self._content_search_text_color)
                self._content_search_is_placeholder = False

        def on_focus_out(_e):
            if not self._content_search_var.get():
                show_placeholder()

        entry.bind("<FocusIn>", on_focus_in, add="+")
        entry.bind("<FocusOut>", on_focus_out, add="+")
        show_placeholder()

    def _content_on_search(self, _event=None):
        if getattr(self, "_content_search_is_placeholder", False):
            self._content_search_query = ""
        else:
            self._content_search_query = self._content_search_var.get().strip().lower()
        self._render_instances()
        self._render_folders()
        self._render_videos()

    def _content_clear_search(self):
        if getattr(self, "_content_search_is_placeholder", False):
            return
        self._content_search_var.set("")
        self._content_search_query = ""
        self._render_instances()
        self._render_folders()
        self._render_videos()
        self._content_search_entry.focus_set()

    # ───────────────────────────────────────────────── refresh ──
    def _content_refresh_all(self):
        self._populate_instances()
        if self._content_selected_instance:
            self._select_instance_by_name(
                self._content_selected_instance.get("name")
            )
        self._update_metrics()

    def _update_metrics(self):
        try:
            instances = list(self._db_instances() or [])
        except Exception:
            instances = []
        total_folders = 0
        total_videos = 0
        total_bytes = 0
        for inst in instances:
            shared = self._safe_get_shared(inst.get("name"))
            if not shared or not os.path.isdir(shared):
                continue
            # root videos
            rv = _count_videos(shared)
            if rv:
                total_folders += 1
                total_videos += rv
                total_bytes += _folder_size(shared)
            try:
                for entry in os.scandir(shared):
                    if entry.is_dir():
                        total_folders += 1
                        total_videos += _count_videos(entry.path)
                        total_bytes += _folder_size(entry.path)
            except OSError:
                continue
        self._content_metric_labels["instances"].config(text=str(len(instances)))
        self._content_metric_labels["folders"].config(text=str(total_folders))
        self._content_metric_labels["videos"].config(text=str(total_videos))
        self._content_metric_labels["disk"].config(text=_human_size(total_bytes))

    def _safe_get_shared(self, name):
        try:
            return self.emulator.get_shared_folder(name)
        except Exception:
            return None

    # ───────────────────────────────────────────── instances pane ──
    def _populate_instances(self):
        """Re-read instances from the DB into a cached list, then render."""
        self._content_instances_raw = []
        self._content_instances_load_error = None
        try:
            instances = list(self._db_instances() or [])
        except Exception as exc:
            self._content_instances_load_error = str(exc)
            self._render_instances()
            return
        for inst in instances:
            name = str(inst.get("name") or "").strip()
            if not name:
                continue
            shared = self._safe_get_shared(name)
            n_folders, n_videos = self._summarise_shared(shared)
            self._content_instances_raw.append({
                "name": name, "inst": inst, "shared": shared,
                "n_folders": n_folders, "n_videos": n_videos,
            })
        self._render_instances()

    def _render_instances(self):
        self.instances_list.clear()
        self._content_instance_rows = {}
        self._instances_empty_label.pack_forget()

        if self._content_instances_load_error:
            self._instances_empty_label.configure(
                text=f"Could not load instances: {self._content_instances_load_error}"
            )
            self._instances_empty_label.pack(pady=20)
            return
        if not self._content_instances_raw:
            self._instances_empty_label.configure(
                text="No instances configured.\nAdd them from Dashboard or Devices first."
            )
            self._instances_empty_label.pack(pady=20)
            return

        q = self._content_search_query
        visible = [e for e in self._content_instances_raw if (not q) or q in e["name"].lower()]
        if not visible:
            self._instances_empty_label.configure(text=f"No instances match '{q}'.")
            self._instances_empty_label.pack(pady=20)
            return

        selected_name = None
        if self._content_selected_instance:
            selected_name = self._content_selected_instance.get("name")

        for entry in visible:
            name = entry["name"]
            shared = entry["shared"]
            n_folders, n_videos = entry["n_folders"], entry["n_videos"]
            subtitle = (
                f"{n_folders} folder{'s' if n_folders != 1 else ''} · "
                f"{n_videos} video{'s' if n_videos != 1 else ''}"
            )
            if not shared:
                subtitle = "No shared folder set"
                trailing = ("no share", self.palette.get("warning", "#D97706"),
                            self.palette.get("warning_bg", "#FFF4DB"))
            else:
                trailing = (str(n_videos),
                            self.palette.get("text", "#111827"),
                            self.palette.get("surface_alt", "#F1F5F9"))

            def make_lead(_name=name):
                return lambda p: _make_avatar(p, self.palette, _name, size=32)

            row = CardRow(
                self.instances_list.inner,
                self.palette,
                leading=make_lead(),
                title=name,
                subtitle=subtitle,
                trailing_pill=trailing,
                on_click=lambda r, _inst=entry["inst"]: self._on_instance_clicked(_inst, r),
            )
            row.pack(fill="x", padx=4, pady=1)
            self.instances_list.register_child(row)
            self._content_instance_rows[name] = row
            if name == selected_name:
                row.set_selected(True)

    def _summarise_shared(self, shared_root):
        if not shared_root or not os.path.isdir(shared_root):
            return 0, 0
        folders = 0
        videos = 0
        rv = _count_videos(shared_root)
        if rv:
            folders += 1
            videos += rv
        try:
            for entry in os.scandir(shared_root):
                if entry.is_dir():
                    folders += 1
                    videos += _count_videos(entry.path)
        except OSError:
            pass
        return folders, videos

    def _on_instance_clicked(self, inst, row):
        # deselect others
        for r in self._content_instance_rows.values():
            r.set_selected(False)
        row.set_selected(True)
        self._content_selected_instance = inst
        self._content_selected_folder = None
        shared = self._safe_get_shared(inst.get("name"))
        self._populate_folders(shared)
        self._clear_videos_pane()
        self._update_breadcrumb()

    def _select_instance_by_name(self, name):
        row = self._content_instance_rows.get(name)
        if row is None:
            return
        inst = next(
            (e["inst"] for e in self._content_instances_raw if e["name"] == name),
            None,
        )
        if inst is None:
            return
        self._on_instance_clicked(inst, row)

    # ────────────────────────────────────────────── folders pane ──
    def _populate_folders(self, shared_root):
        """Scan the shared folder, cache results, then render."""
        self._content_folders_shared_root = shared_root
        self._content_folders_raw = []
        self._content_folders_load_error = None
        if not shared_root or not os.path.isdir(shared_root):
            self._render_folders()
            return
        rv = _count_videos(shared_root)
        if rv:
            self._content_folders_raw.append(
                ("(root)", shared_root, rv, _folder_size(shared_root))
            )
        try:
            for ent in sorted(os.scandir(shared_root), key=lambda e: e.name.lower()):
                if ent.is_dir():
                    self._content_folders_raw.append(
                        (ent.name, ent.path,
                         _count_videos(ent.path), _folder_size(ent.path))
                    )
        except OSError as exc:
            self._content_folders_load_error = str(exc)
        self._render_folders()

    def _render_folders(self):
        self.folders_list.clear()
        self._content_folder_rows = {}
        self._folders_empty_label.pack_forget()

        shared_root = self._content_folders_shared_root
        if shared_root is None:
            self._folders_empty_label.configure(text="Select an instance")
            self._folders_empty_label.pack(pady=20)
            return
        if not shared_root:
            self._folders_empty_label.configure(
                text="No shared folder set.\nClick “🔗 Shared path” to set one."
            )
            self._folders_empty_label.pack(pady=20)
            return
        if not os.path.isdir(shared_root):
            self._folders_empty_label.configure(
                text=f"Shared folder missing:\n{shared_root}"
            )
            self._folders_empty_label.pack(pady=20)
            return
        if self._content_folders_load_error:
            self._folders_empty_label.configure(
                text=f"Cannot read folder: {self._content_folders_load_error}"
            )
            self._folders_empty_label.pack(pady=20)
            return
        if not self._content_folders_raw:
            self._folders_empty_label.configure(
                text="Shared folder is empty.\nCreate a sub-folder or add videos."
            )
            self._folders_empty_label.pack(pady=20)
            return

        q = self._content_search_query
        visible = [e for e in self._content_folders_raw if (not q) or q in e[0].lower()]
        if not visible:
            self._folders_empty_label.configure(text=f"No folders match '{q}'.")
            self._folders_empty_label.pack(pady=20)
            return

        sel_path = self._content_selected_folder
        for folder_name, abs_path, count, size in visible:
            color = _folder_color_for(folder_name)
            subtitle = f"{count} video{'s' if count != 1 else ''}"
            if size:
                subtitle += f" · {_human_size(size)}"
            pill_fg = (self.palette.get("primary_fg", "#FFFFFF") if count
                       else self.palette.get("muted", "#64748B"))
            pill_bg = color if count else self.palette.get("surface_alt", "#F1F5F9")

            def make_lead(_color=color):
                return lambda p: _make_folder_icon(p, self.palette, color=_color, size=32)

            row = CardRow(
                self.folders_list.inner, self.palette,
                leading=make_lead(),
                title=folder_name, subtitle=subtitle,
                trailing_pill=(str(count), pill_fg, pill_bg),
                accent_color=color,
                on_click=lambda r, _p=abs_path: self._on_folder_clicked(_p, r),
                on_double_click=lambda r, _p=abs_path: _open_in_explorer(_p),
            )
            row.pack(fill="x", padx=4, pady=1)
            self.folders_list.register_child(row)
            self._content_folder_rows[abs_path] = row
            if abs_path == sel_path:
                row.set_selected(True)

    def _on_folder_clicked(self, folder_path, row):
        for r in self._content_folder_rows.values():
            r.set_selected(False)
        row.set_selected(True)
        self._content_selected_folder = folder_path
        self._populate_videos(folder_path)
        self._update_breadcrumb()

    def _clear_folders_pane(self):
        self._content_folders_shared_root = None
        self._content_folders_raw = []
        self._content_folders_load_error = None
        self._render_folders()

    # ─────────────────────────────────────────────── videos pane ──
    def _populate_videos(self, folder):
        self._content_videos_folder = folder
        self._content_videos_raw = _list_videos(folder) if folder else []
        self._content_used_set = _load_used_set(folder) if folder else set()
        self._content_selected_videos = set()
        self._render_videos()

    def _render_videos(self):
        self.videos_list.clear()
        self._content_video_rows = {}
        self._videos_empty_frame.pack_forget()
        self._video_actionbar.pack_forget()

        folder = self._content_videos_folder
        if not folder:
            self._videos_empty_label.configure(text="Select a folder")
            self._videos_upload_placeholder.pack_forget()
            self._videos_empty_frame.pack(fill="x", pady=20)
            self._update_action_bar()
            return

        raw = self._content_videos_raw
        q = self._content_search_query
        visible = [v for v in raw if (not q) or q in v[0].lower()]

        if not raw:
            self._videos_empty_label.configure(
                text="No videos in this folder.\nUse “Add videos” to import."
            )
            self._videos_upload_placeholder.pack(fill="x")
            self._videos_empty_frame.pack(fill="x", pady=(20, 0))
            self._update_action_bar()
            return
        if not visible:
            self._videos_empty_label.configure(text=f"No videos match '{q}'.")
            self._videos_upload_placeholder.pack_forget()
            self._videos_empty_frame.pack(fill="x", pady=20)
            self._update_action_bar()
            return

        used_pill_fg = self.palette.get("success_fg", "#FFFFFF")
        used_pill_bg = self.palette.get("success", "#10B981")
        for name, size, mtime, path in visible:
            def make_lead():
                return lambda p: _make_video_icon(p, self.palette, size=32)

            sub = _human_size(size)
            rel = _relative_time(mtime)
            if rel:
                sub = f"{sub} · {rel}"
            pill = (("USED", used_pill_fg, used_pill_bg)
                    if name in self._content_used_set else None)

            row = CardRow(
                self.videos_list.inner, self.palette,
                leading=make_lead(),
                title=name, subtitle=sub,
                trailing_pill=pill,
                on_click=lambda r, _p=path: self._on_video_clicked(_p, r),
                on_double_click=lambda r, _p=path: _open_in_explorer(_p),
            )
            row.pack(fill="x", padx=4, pady=1)
            self.videos_list.register_child(row)
            self._content_video_rows[path] = row
            if path in self._content_selected_videos:
                row.set_selected(True)

        self._update_action_bar()

    def _on_video_clicked(self, path, row):
        # toggle selection (multi-select)
        if path in self._content_selected_videos:
            self._content_selected_videos.discard(path)
            row.set_selected(False)
        else:
            self._content_selected_videos.add(path)
            row.set_selected(True)
        self._update_action_bar()

    def _update_action_bar(self):
        n = len(self._content_selected_videos)
        if n == 0:
            self._video_actionbar.pack_forget()
            return
        self._video_action_count.configure(
            text=f"{n} video{'s' if n != 1 else ''} selected"
        )
        self._video_actionbar.pack(side="bottom", fill="x", pady=(8, 0))

    def _clear_videos_pane(self):
        self._content_videos_folder = None
        self._content_videos_raw = []
        self._content_used_set = set()
        self._content_selected_videos = set()
        self._render_videos()

    # ──────────────────────────────────────────── breadcrumb ──
    def _update_breadcrumb(self):
        inst = self._content_selected_instance
        folder = self._content_selected_folder
        if not inst:
            self._content_breadcrumb_top.configure(
                text="Select an instance to begin",
                anchor="center", justify="center",
                fg=self.palette.get("muted", "#64748B"),
                font=("Segoe UI", 10),
            )
            self._content_breadcrumb_path.pack_forget()
            return

        inst_name = inst.get("name") or "?"
        parts_text = f"📱  {inst_name}"
        if folder:
            folder_name = os.path.basename(folder) or folder
            parts_text += f"   ›   📁  {folder_name}"
        self._content_breadcrumb_top.configure(
            text=parts_text, anchor="w", justify="left",
            fg=self.palette.get("text", "#111827"),
            font=("Segoe UI Semibold", 11),
        )
        if folder:
            self._content_breadcrumb_path.configure(
                text=folder, fg=self.palette.get("muted", "#64748B"),
            )
            self._content_breadcrumb_path.pack(fill="x", anchor="w")
        else:
            self._content_breadcrumb_path.pack_forget()

    # ────────────────────────────────────────── actions: shared ──
    def _content_set_shared_folder(self):
        inst = self._content_selected_instance
        if not inst:
            MessageBox.showinfo("Set Shared Folder", "Select an instance first.")
            return
        name = inst.get("name")
        folder = filedialog.askdirectory(title=f"Choose shared folder for '{name}'")
        if not folder:
            return
        try:
            ok = self.emulator.set_shared_folder(name, folder)
        except Exception as exc:
            MessageBox.showerror("Set Shared Folder", f"Failed: {exc}")
            return
        if not ok:
            MessageBox.showerror(
                "Set Shared Folder",
                "Config could not be written.\nStop the LD instance and retry.",
            )
            return
        self.log(f"Shared folder set for '{name}' → {folder}", "SUCCESS",
                 category="Content")
        MessageBox.showinfo(
            "Set Shared Folder",
            "Done. Restart the LD instance for the change to take effect.",
        )
        self._content_refresh_all()

    # ─────────────────────────────────────── actions: folders/videos ──
    def _require_shared_root(self):
        inst = self._content_selected_instance
        if not inst:
            MessageBox.showinfo("Content", "Select an instance first.")
            return None
        shared = self._safe_get_shared(inst.get("name"))
        if not shared or not os.path.isdir(shared):
            MessageBox.showwarning(
                "No shared folder",
                "This instance has no shared folder set, or it is missing.\n"
                "Use “🔗 Shared path” to configure it.",
            )
            return None
        return shared

    def _content_new_subfolder(self):
        shared = self._require_shared_root()
        if not shared:
            return
        from tkinter import simpledialog
        name = simpledialog.askstring("New sub-folder", "Folder name:",
                                       parent=self.root)
        if not name:
            return
        if any(ch in name for ch in r'\/:*?"<>|'):
            MessageBox.showerror("Invalid name",
                                 "Name contains invalid characters.")
            return
        target = os.path.join(shared, name.strip())
        if os.path.exists(target):
            MessageBox.showinfo("Exists", "A folder with that name already exists.")
            return
        try:
            os.makedirs(target, exist_ok=False)
        except OSError as exc:
            MessageBox.showerror("Create folder", f"Failed: {exc}")
            return
        self.log(f"Created folder: {target}", "SUCCESS", category="Content")
        self._content_refresh_all()

    def _content_add_videos(self):
        shared = self._require_shared_root()
        if not shared:
            return
        dest = self._content_selected_folder or shared
        if not os.path.isdir(dest):
            MessageBox.showerror("Add Videos", f"Destination missing:\n{dest}")
            return
        files = filedialog.askopenfilenames(
            title=f"Add videos to '{os.path.basename(dest) or dest}'",
            filetypes=[
                ("Video Files", "*.mp4 *.mov *.avi *.mkv *.webm *.flv *.m4v *.3gp"),
                ("All Files", "*.*"),
            ],
        )
        if not files:
            return
        copied, skipped, failed = 0, 0, []
        for src in files:
            if not _is_video(src):
                skipped += 1
                continue
            dst = os.path.join(dest, os.path.basename(src))
            if os.path.exists(dst):
                stem, ext = os.path.splitext(os.path.basename(src))
                i = 1
                while True:
                    candidate = os.path.join(dest, f"{stem} ({i}){ext}")
                    if not os.path.exists(candidate):
                        dst = candidate
                        break
                    i += 1
            try:
                shutil.copy2(src, dst)
                copied += 1
            except Exception as exc:
                failed.append(f"{os.path.basename(src)}: {exc}")
        self.log(
            f"Added {copied} video(s) to {dest}"
            + (f"; skipped {skipped}" if skipped else "")
            + (f"; {len(failed)} failed" if failed else ""),
            "SUCCESS" if copied else "WARNING",
            category="Content",
        )
        if failed:
            MessageBox.showwarning("Some files failed",
                                    "\n".join(failed[:10]))
        self._refresh_after_change(dest)

    def _content_rename_video(self):
        sel = list(self._content_selected_videos)
        if len(sel) != 1:
            MessageBox.showinfo("Rename", "Select exactly one video to rename.")
            return
        path = sel[0]
        old_name = os.path.basename(path)
        from tkinter import simpledialog
        new_name = simpledialog.askstring(
            "Rename", "New filename:", initialvalue=old_name, parent=self.root,
        )
        if not new_name or new_name == old_name:
            return
        if any(ch in new_name for ch in r'\/:*?"<>|'):
            MessageBox.showerror("Invalid", "Filename has invalid characters.")
            return
        new_path = os.path.join(os.path.dirname(path), new_name)
        if os.path.exists(new_path):
            MessageBox.showerror("Exists", "A file with that name already exists.")
            return
        try:
            os.rename(path, new_path)
        except OSError as exc:
            MessageBox.showerror("Rename", f"Failed: {exc}")
            return
        self.log(f"Renamed: {old_name} → {new_name}", "SUCCESS", category="Content")
        self._refresh_after_change(os.path.dirname(path))

    def _content_delete_selected(self):
        paths = list(self._content_selected_videos)
        if not paths:
            MessageBox.showinfo("Delete", "Select at least one video.")
            return
        if not MessageBox.askyesno(
            "Delete",
            f"Permanently delete {len(paths)} video(s)?\n\n"
            + "\n".join(os.path.basename(p) for p in paths[:10])
            + ("\n…" if len(paths) > 10 else ""),
        ):
            return
        deleted, failed = 0, []
        for p in paths:
            try:
                os.remove(p)
                deleted += 1
            except OSError as exc:
                failed.append(f"{os.path.basename(p)}: {exc}")
        self.log(
            f"Deleted {deleted} video(s)"
            + (f"; {len(failed)} failed" if failed else ""),
            "SUCCESS" if deleted else "ERROR",
            category="Content",
        )
        if failed:
            MessageBox.showwarning("Some deletes failed", "\n".join(failed[:10]))
        if self._content_selected_folder:
            self._refresh_after_change(self._content_selected_folder)

    def _content_open_selected_video(self):
        for p in self._content_selected_videos:
            _open_in_explorer(p)
            break

    def _refresh_after_change(self, folder_to_reselect=None):
        inst_name = (self._content_selected_instance or {}).get("name")
        self._populate_instances()
        self._update_metrics()
        if inst_name:
            row = self._content_instance_rows.get(inst_name)
            if row is not None:
                inst = next(
                    (i for i in self._db_instances() or [] if i.get("name") == inst_name),
                    None,
                )
                if inst is not None:
                    self._on_instance_clicked(inst, row)
        if folder_to_reselect and self._content_folder_rows:
            target = os.path.normpath(folder_to_reselect)
            for path, row in self._content_folder_rows.items():
                if os.path.normpath(path) == target:
                    self._on_folder_clicked(path, row)
                    break

    # ────────────────────────────────────── legacy compatibility ──
    def add_video(self):
        self._content_add_videos()

    def load_video_folder(self):
        self._content_add_videos()

    def clear_used_videos(self):
        MessageBox.showinfo(
            "Content",
            "The 'used videos' queue has been replaced by direct folder browsing.\n"
            "Delete videos directly from the Videos pane instead.",
        )

    def show_content_stats(self):
        self._update_metrics()

    def update_content_display(self):
        self._content_refresh_all()
