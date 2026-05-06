"""Futuristic startup splash screen for Ryu Automation.

Usage (typical):
    from gui.splash_screen import SplashScreen

    splash = SplashScreen()
    splash.show()
    splash.update_progress(20, "Checking devices...")
    # ... do startup work ...
    splash.update_progress(100, "Ready")
    splash.close()

The splash uses its own hidden Tk root so it can run before the main app
window is created. After close(), the caller is expected to create the
main Tk() instance.
"""

from __future__ import annotations

import math
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Project root = parent of the gui/ directory containing this file.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_LOGO = _PROJECT_ROOT / "assets" / "splash_screen_ryu.png"


# Palette (matches the requested design tokens)
COLORS = {
    "bg_outer": "#020617",
    "bg_inner": "#0F172A",
    "border": "#2A3550",  # approximation of rgba(255,255,255,0.12) on dark
    "text_primary": "#F8FAFC",
    "text_muted": "#94A3B8",
    "accent": "#38BDF8",
    "deep_glow": "#2563EB",
    "track": "#1E293B",
}

DEFAULT_STATUS_STEPS = (
    "Checking devices...",
    "Loading modules...",
    "Preparing dashboard...",
    "Starting automation engine...",
)


@dataclass
class SplashConfig:
    width: int = 720
    height: int = 420
    corner_radius: int = 22
    version: str = "v1.0.0"
    title: str = "RYU AUTOMATION"
    initial_progress: int = 68
    initial_status: str = "Starting automation engine..."
    rotate_status: bool = True
    rotate_interval_ms: int = 1400
    logo_path: str = "assets/splash_screen_ryu.png"
    logo_size: int = 155
    # If the logo image already contains the app name, set this False to
    # skip drawing the separate "RYU AUTOMATION" title text.
    show_title: bool = False


class SplashScreen:
    """A borderless, centered splash window drawn on a single Canvas."""

    def __init__(self, config: Optional[SplashConfig] = None, master: Optional[tk.Misc] = None) -> None:
        self.cfg = config or SplashConfig()

        # Reuse the caller's Tk root when provided so ttk/ttkbootstrap styles
        # (registered on the main root) remain valid for the rest of the app.
        if master is None:
            self._root = tk.Tk()
            self._root.withdraw()
            self._owns_root = True
        else:
            self._root = master
            self._owns_root = False
        self._root.title("Ryu Automation")

        self._win = tk.Toplevel(self._root)
        self._win.overrideredirect(True)
        self._win.configure(bg=COLORS["bg_outer"])
        self._win.attributes("-topmost", True)
        try:
            # Make the outer black truly transparent so the rounded corners
            # don't show square edges on Windows.
            self._win.attributes("-transparentcolor", "#000001")
            self._transparent_color = "#000001"
        except tk.TclError:
            self._transparent_color = COLORS["bg_outer"]

        self._center_window()

        self.canvas = tk.Canvas(
            self._win,
            width=self.cfg.width,
            height=self.cfg.height,
            bg=self._transparent_color,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack(fill="both", expand=True)

        self._progress_value = float(self.cfg.initial_progress)
        self._target_progress = float(self.cfg.initial_progress)
        self._status_text = self.cfg.initial_status
        self._status_index = 0
        self._dot_phase = 0
        self._pulse_phase = 0.0
        self._closed = False

        self._draw_static()
        self._draw_dynamic()

        if self.cfg.rotate_status:
            self._schedule_status_rotation()
        self._schedule_animation_tick()

    # ----- public API ------------------------------------------------------

    def show(self) -> None:
        self._win.deiconify()
        self._win.update()

    def update_progress(self, value: float, status: Optional[str] = None) -> None:
        """Set target progress (0-100). Smoothly animates toward it."""
        self._target_progress = max(0.0, min(100.0, float(value)))
        if status is not None:
            self.set_status(status)

    def set_status(self, text: str) -> None:
        self._status_text = text
        self.cfg.rotate_status = False  # explicit text overrides rotation

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._win.destroy()
        except Exception:
            pass
        if self._owns_root:
            try:
                self._root.destroy()
            except Exception:
                pass

    # ----- layout helpers --------------------------------------------------

    def _center_window(self) -> None:
        self._win.update_idletasks()
        sw = self._win.winfo_screenwidth()
        sh = self._win.winfo_screenheight()
        x = (sw - self.cfg.width) // 2
        y = (sh - self.cfg.height) // 2
        self._win.geometry(f"{self.cfg.width}x{self.cfg.height}+{x}+{y}")

    # ----- drawing ---------------------------------------------------------

    def _draw_static(self) -> None:
        w, h = self.cfg.width, self.cfg.height
        r = self.cfg.corner_radius

        # Fill outer area with the transparent color so corners cut out.
        self.canvas.create_rectangle(0, 0, w, h, fill=self._transparent_color, outline="")

        # Vertical gradient (bg_outer -> bg_inner -> bg_outer) inside rounded card.
        self._draw_rounded_gradient(2, 2, w - 2, h - 2, r, COLORS["bg_outer"], COLORS["bg_inner"])

        # Soft border
        self._draw_rounded_outline(2, 2, w - 2, h - 2, r, COLORS["border"])

        # Radial blue glow behind logo
        cx, cy = w // 2, int(h * 0.36)
        self._draw_radial_glow(cx, cy, radius=170, inner=COLORS["deep_glow"], outer=COLORS["bg_inner"])

        # Logo (image asset, falls back to canvas drawing)
        self._draw_logo_image(cx, cy)

        # Title — only render when not already baked into the logo image
        if self.cfg.show_title:
            self.canvas.create_text(
                w // 2,
                int(h * 0.58),
                text=self.cfg.title,
                fill=COLORS["text_primary"],
                font=("Segoe UI", 22, "bold"),
            )
            self.canvas.create_rectangle(
                w // 2 - 28,
                int(h * 0.58) + 22,
                w // 2 + 28,
                int(h * 0.58) + 23,
                fill=COLORS["accent"],
                outline="",
            )

        # Version (bottom center)
        self.canvas.create_text(
            w // 2,
            h - 26,
            text=self.cfg.version,
            fill=COLORS["text_muted"],
            font=("Segoe UI", 9),
        )

    def _draw_dynamic(self) -> None:
        """(Re)draw items that change: status text, progress bar, dots, pulse."""
        self.canvas.delete("dynamic")

        w, h = self.cfg.width, self.cfg.height

        # Status text
        self.canvas.create_text(
            w // 2,
            int(h * 0.68),
            text=self._status_text,
            fill=COLORS["text_muted"],
            font=("Segoe UI", 11),
            tags="dynamic",
        )

        # Progress bar geometry (~55% width)
        bar_w = int(w * 0.55)
        bar_h = 6
        bar_x = (w - bar_w) // 2
        bar_y = int(h * 0.78)

        # Track
        self._draw_rounded_rect(
            bar_x,
            bar_y,
            bar_x + bar_w,
            bar_y + bar_h,
            bar_h // 2,
            fill=COLORS["track"],
            tag="dynamic",
        )

        # Fill
        pct = self._progress_value / 100.0
        fill_w = max(int(bar_w * pct), bar_h)
        # Glow underlay (slightly taller, semi-transparent feel via color blend)
        self._draw_rounded_rect(
            bar_x - 2,
            bar_y - 3,
            bar_x + fill_w + 2,
            bar_y + bar_h + 3,
            (bar_h // 2) + 3,
            fill=COLORS["deep_glow"],
            tag="dynamic",
        )
        self._draw_rounded_rect(
            bar_x,
            bar_y,
            bar_x + fill_w,
            bar_y + bar_h,
            bar_h // 2,
            fill=COLORS["accent"],
            tag="dynamic",
        )

        # Percent text on the right
        self.canvas.create_text(
            bar_x + bar_w + 28,
            bar_y + bar_h // 2,
            text=f"{int(round(self._progress_value))}%",
            fill=COLORS["text_primary"],
            font=("Segoe UI", 10, "bold"),
            anchor="w",
            tags="dynamic",
        )

        # Animated dots under the bar
        dot_y = bar_y + 28
        dot_cx = w // 2
        for i in range(3):
            active = i == self._dot_phase % 3
            color = COLORS["accent"] if active else COLORS["track"]
            x = dot_cx - 14 + i * 14
            self.canvas.create_oval(
                x - 3,
                dot_y - 3,
                x + 3,
                dot_y + 3,
                fill=color,
                outline="",
                tags="dynamic",
            )

    # ----- primitive drawing ----------------------------------------------

    def _draw_rounded_rect(self, x1, y1, x2, y2, r, fill, tag=""):
        # Tk lacks a native rounded rect; approximate with arcs + rectangles.
        r = max(0, min(r, (x2 - x1) // 2, (y2 - y1) // 2))
        items = []
        items.append(self.canvas.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline="", tags=tag))
        items.append(self.canvas.create_rectangle(x1, y1 + r, x2, y2 - r, fill=fill, outline="", tags=tag))
        items.append(self.canvas.create_oval(x1, y1, x1 + 2 * r, y1 + 2 * r, fill=fill, outline="", tags=tag))
        items.append(self.canvas.create_oval(x2 - 2 * r, y1, x2, y1 + 2 * r, fill=fill, outline="", tags=tag))
        items.append(self.canvas.create_oval(x1, y2 - 2 * r, x1 + 2 * r, y2, fill=fill, outline="", tags=tag))
        items.append(self.canvas.create_oval(x2 - 2 * r, y2 - 2 * r, x2, y2, fill=fill, outline="", tags=tag))
        return items

    def _draw_rounded_outline(self, x1, y1, x2, y2, r, color):
        # Thin outline using arcs + lines.
        self.canvas.create_arc(
            x1, y1, x1 + 2 * r, y1 + 2 * r, start=90, extent=90, style="arc", outline=color
        )
        self.canvas.create_arc(x2 - 2 * r, y1, x2, y1 + 2 * r, start=0, extent=90, style="arc", outline=color)
        self.canvas.create_arc(
            x1, y2 - 2 * r, x1 + 2 * r, y2, start=180, extent=90, style="arc", outline=color
        )
        self.canvas.create_arc(
            x2 - 2 * r, y2 - 2 * r, x2, y2, start=270, extent=90, style="arc", outline=color
        )
        self.canvas.create_line(x1 + r, y1, x2 - r, y1, fill=color)
        self.canvas.create_line(x1 + r, y2, x2 - r, y2, fill=color)
        self.canvas.create_line(x1, y1 + r, x1, y2 - r, fill=color)
        self.canvas.create_line(x2, y1 + r, x2, y2 - r, fill=color)

    def _draw_rounded_gradient(self, x1, y1, x2, y2, r, c_top, c_mid):
        """Vertical gradient clipped (visually) to a rounded rectangle."""
        height = y2 - y1
        steps = max(40, height // 4)
        c1 = self._hex_to_rgb(c_top)
        c2 = self._hex_to_rgb(c_mid)
        for i in range(steps):
            # Smooth 3-stop: top -> mid (around 55%) -> top-darker
            t = i / (steps - 1)
            if t < 0.55:
                k = t / 0.55
                rgb = self._lerp_rgb(c1, c2, k)
            else:
                k = (t - 0.55) / 0.45
                rgb = self._lerp_rgb(c2, c1, k)
            color = self._rgb_to_hex(rgb)
            yy1 = y1 + int(i * height / steps)
            yy2 = y1 + int((i + 1) * height / steps)
            self.canvas.create_rectangle(x1, yy1, x2, yy2, fill=color, outline="")

        # Re-mask the corners with transparent color to fake rounded edges.
        for cx, cy, sa, ea in (
            (x1, y1, 0, 90),
            (x2 - 2 * r, y1, 90, 180),
            (x1, y2 - 2 * r, 270, 360),
            (x2 - 2 * r, y2 - 2 * r, 180, 270),
        ):
            pass  # corners handled by outline + outer transparent fill
        # Top/bottom rounded mask: cover corners with outer transparent triangles
        self._mask_corners(x1, y1, x2, y2, r)

    def _mask_corners(self, x1, y1, x2, y2, r):
        bg = self._transparent_color
        # Top-left
        self.canvas.create_rectangle(x1 - 2, y1 - 2, x1 + r, y1 + r, fill=bg, outline="")
        self.canvas.create_arc(
            x1, y1, x1 + 2 * r, y1 + 2 * r, start=90, extent=90, fill=COLORS["bg_outer"], outline=""
        )
        # Top-right
        self.canvas.create_rectangle(x2 - r, y1 - 2, x2 + 2, y1 + r, fill=bg, outline="")
        self.canvas.create_arc(
            x2 - 2 * r, y1, x2, y1 + 2 * r, start=0, extent=90, fill=COLORS["bg_outer"], outline=""
        )
        # Bottom-left
        self.canvas.create_rectangle(x1 - 2, y2 - r, x1 + r, y2 + 2, fill=bg, outline="")
        self.canvas.create_arc(
            x1, y2 - 2 * r, x1 + 2 * r, y2, start=180, extent=90, fill=COLORS["bg_outer"], outline=""
        )
        # Bottom-right
        self.canvas.create_rectangle(x2 - r, y2 - r, x2 + 2, y2 + 2, fill=bg, outline="")
        self.canvas.create_arc(
            x2 - 2 * r, y2 - 2 * r, x2, y2, start=270, extent=90, fill=COLORS["bg_outer"], outline=""
        )

    def _draw_radial_glow(self, cx, cy, radius, inner, outer, steps=24):
        c_in = self._hex_to_rgb(inner)
        c_out = self._hex_to_rgb(outer)
        for i in range(steps, 0, -1):
            t = i / steps
            rgb = self._lerp_rgb(c_out, c_in, 1 - t)
            color = self._rgb_to_hex(rgb)
            rr = int(radius * t)
            self.canvas.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, fill=color, outline="")

    def _resolve_logo_path(self) -> Path:
        """Resolve logo_path against the project root if it isn't absolute."""
        p = Path(self.cfg.logo_path)
        if not p.is_absolute():
            p = _PROJECT_ROOT / p
        return p

    def _draw_logo_image(self, cx: int, cy: int) -> None:
        """Render the logo from an image file; fall back to canvas drawing on error."""
        try:
            from PIL import Image, ImageTk

            path = self._resolve_logo_path()
            if not path.exists():
                raise FileNotFoundError(f"Logo image not found: {path}")

            img = Image.open(path).convert("RGBA")
            target = self.cfg.logo_size
            img.thumbnail((target, target), Image.LANCZOS)

            # Keep a strong reference on self so Tk doesn't garbage-collect it.
            self._logo_img = ImageTk.PhotoImage(img)
            self.canvas.create_image(cx, cy, image=self._logo_img, anchor="center")
        except Exception as exc:
            print(f"[splash] failed to load logo image, using fallback: {exc}")
            self._draw_logo(cx, cy, size=78)

    def _draw_logo(self, cx, cy, size=78):
        """Minimal futuristic 'A' with an inset play triangle + gear behind."""
        s = size
        white = COLORS["text_primary"]

        # Gear silhouette (subtle, behind the A)
        gear_r = int(s * 0.95)
        teeth = 10
        gear_color = "#1B2540"  # subdued tooth color so it stays in background
        for i in range(teeth):
            a = (i / teeth) * 2 * math.pi
            x = cx + math.cos(a) * (gear_r - 4)
            y = cy + math.sin(a) * (gear_r - 4)
            self.canvas.create_oval(x - 6, y - 6, x + 6, y + 6, fill=gear_color, outline="")
        self.canvas.create_oval(
            cx - gear_r + 12,
            cy - gear_r + 12,
            cx + gear_r - 12,
            cy + gear_r - 12,
            fill=COLORS["bg_inner"],
            outline=gear_color,
        )

        # Letter A (two angled strokes + crossbar)
        top = (cx, cy - s)
        bl = (cx - int(s * 0.85), cy + int(s * 0.85))
        br = (cx + int(s * 0.85), cy + int(s * 0.85))
        # outer left stroke
        self.canvas.create_polygon(
            top[0],
            top[1],
            top[0] + 12,
            top[1] + 4,
            bl[0] + 24,
            bl[1],
            bl[0],
            bl[1],
            fill=white,
            outline="",
        )
        # outer right stroke
        self.canvas.create_polygon(
            top[0],
            top[1],
            top[0] - 12,
            top[1] + 4,
            br[0] - 24,
            br[1],
            br[0],
            br[1],
            fill=white,
            outline="",
        )
        # crossbar
        self.canvas.create_rectangle(
            cx - int(s * 0.42),
            cy + int(s * 0.18),
            cx + int(s * 0.42),
            cy + int(s * 0.30),
            fill=white,
            outline="",
        )

        # Play triangle inside the A's lower opening
        tri = [
            cx - int(s * 0.18),
            cy + int(s * 0.42),
            cx - int(s * 0.18),
            cy + int(s * 0.78),
            cx + int(s * 0.22),
            cy + int(s * 0.60),
        ]
        self.canvas.create_polygon(tri, fill=COLORS["accent"], outline="")

    # ----- color utils -----------------------------------------------------

    @staticmethod
    def _hex_to_rgb(h: str):
        h = h.lstrip("#")
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

    @staticmethod
    def _rgb_to_hex(rgb):
        return "#%02x%02x%02x" % (
            max(0, min(255, int(rgb[0]))),
            max(0, min(255, int(rgb[1]))),
            max(0, min(255, int(rgb[2]))),
        )

    @staticmethod
    def _lerp_rgb(a, b, t):
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)

    # ----- animation -------------------------------------------------------

    def _schedule_status_rotation(self) -> None:
        if self._closed or not self.cfg.rotate_status:
            return
        steps = DEFAULT_STATUS_STEPS
        self._status_text = steps[self._status_index % len(steps)]
        self._status_index += 1
        self._win.after(self.cfg.rotate_interval_ms, self._schedule_status_rotation)

    def _schedule_animation_tick(self) -> None:
        if self._closed:
            return

        # Smooth progress easing toward target
        diff = self._target_progress - self._progress_value
        if abs(diff) > 0.1:
            self._progress_value += diff * 0.18
        else:
            self._progress_value = self._target_progress

        # Pulse and dot phase
        self._pulse_phase += 0.12
        self._dot_phase += 1

        self._draw_dynamic()
        self._win.after(60, self._schedule_animation_tick)


__all__ = ["SplashScreen", "SplashConfig"]
