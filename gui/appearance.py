from __future__ import annotations

from dataclasses import dataclass
from typing import Any

THEME_PRESETS = {
    "dark": {"label": "Dark", "ttk_theme": "darkly", "mode": "dark"},
    "light": {"label": "Light", "ttk_theme": "flatly", "mode": "light"},
}

ACCENT_COLORS = {
    "cyan": {"label": "Cyan", "color": "#00E5FF"},
    "blue": {"label": "Blue", "color": "#2563EB"},
    "purple": {"label": "Purple", "color": "#7C3AED"},
    "green": {"label": "Green", "color": "#10B981"},
}

UI_DENSITIES = {
    "compact": {
        "label": "Compact",
        "card_padding": 12,
        "section_gap": 10,
        "content_pad": (12, 10, 12, 6),
        "input_pad": (6, 5),
        "button_pad": (9, 5),
        "primary_button_pad": (11, 6),
        "nav_pad": (8, 6),
        "notebook_tab_pad": (12, 8),
        "tree_row_height": 24,
        "tree_heading_pad": (6, 5),
        "status_pad": (7, 2),
        "status_bar_height": 24,
        "sidebar_width": 222,
    },
    "comfortable": {
        "label": "Comfortable",
        "card_padding": 14,
        "section_gap": 14,
        "content_pad": (16, 14, 16, 8),
        "input_pad": (8, 8),
        "button_pad": (10, 7),
        "primary_button_pad": (14, 8),
        "nav_pad": (10, 8),
        "notebook_tab_pad": (16, 11),
        "tree_row_height": 28,
        "tree_heading_pad": (8, 7),
        "status_pad": (8, 3),
        "status_bar_height": 26,
        "sidebar_width": 236,
    },
    "spacious": {
        "label": "Spacious",
        "card_padding": 18,
        "section_gap": 18,
        "content_pad": (20, 18, 20, 10),
        "input_pad": (10, 10),
        "button_pad": (12, 9),
        "primary_button_pad": (16, 10),
        "nav_pad": (12, 10),
        "notebook_tab_pad": (18, 13),
        "tree_row_height": 34,
        "tree_heading_pad": (10, 9),
        "status_pad": (9, 4),
        "status_bar_height": 30,
        "sidebar_width": 252,
    },
}

UI_SCALES = {
    "small": {"label": "Small", "font_delta": -1},
    "normal": {"label": "Normal", "font_delta": 0},
    "large": {"label": "Large", "font_delta": 2},
}

DEFAULT_APPEARANCE_SETTINGS = {
    "theme_preset": "light",
    "accent_color": "cyan",
    "ui_density": "comfortable",
    "ui_scale": "normal",
}


@dataclass(frozen=True, slots=True)
class ResolvedAppearance:
    theme_preset: str
    accent_color: str
    ui_density: str
    ui_scale: str
    ttk_theme: str
    palette: dict[str, str]
    spacing: dict[str, Any]
    font_sizes: dict[str, int]


def normalize_theme_preset(value: Any) -> str:
    value = str(value or "").strip().lower()
    return value if value in THEME_PRESETS else DEFAULT_APPEARANCE_SETTINGS["theme_preset"]


def normalize_accent_color(value: Any) -> str:
    value = str(value or "").strip().lower()
    return value if value in ACCENT_COLORS else DEFAULT_APPEARANCE_SETTINGS["accent_color"]


def normalize_ui_density(value: Any) -> str:
    value = str(value or "").strip().lower()
    return value if value in UI_DENSITIES else DEFAULT_APPEARANCE_SETTINGS["ui_density"]


def normalize_ui_scale(value: Any) -> str:
    value = str(value or "").strip().lower()
    return value if value in UI_SCALES else DEFAULT_APPEARANCE_SETTINGS["ui_scale"]


def appearance_values_from_settings(settings: Any) -> dict[str, str]:
    return normalize_appearance_values(
        getattr(settings, "theme_preset", DEFAULT_APPEARANCE_SETTINGS["theme_preset"]),
        getattr(settings, "accent_color", DEFAULT_APPEARANCE_SETTINGS["accent_color"]),
        getattr(settings, "ui_density", DEFAULT_APPEARANCE_SETTINGS["ui_density"]),
        getattr(settings, "ui_scale", DEFAULT_APPEARANCE_SETTINGS["ui_scale"]),
    )


def normalize_appearance_values(
    theme_preset: Any,
    accent_color: Any,
    ui_density: Any,
    ui_scale: Any,
) -> dict[str, str]:
    return {
        "theme_preset": normalize_theme_preset(theme_preset),
        "accent_color": normalize_accent_color(accent_color),
        "ui_density": normalize_ui_density(ui_density),
        "ui_scale": normalize_ui_scale(ui_scale),
    }


def resolve_appearance(settings: Any = None, **overrides: Any) -> ResolvedAppearance:
    values = dict(DEFAULT_APPEARANCE_SETTINGS)
    if settings is not None:
        values.update(appearance_values_from_settings(settings))
    values.update({key: value for key, value in overrides.items() if value is not None})
    values = normalize_appearance_values(
        values["theme_preset"],
        values["accent_color"],
        values["ui_density"],
        values["ui_scale"],
    )

    preset = THEME_PRESETS[values["theme_preset"]]
    mode = preset["mode"]
    accent = ACCENT_COLORS[values["accent_color"]]["color"]
    spacing = dict(UI_DENSITIES[values["ui_density"]])
    font_delta = int(UI_SCALES[values["ui_scale"]]["font_delta"])

    return ResolvedAppearance(
        theme_preset=values["theme_preset"],
        accent_color=values["accent_color"],
        ui_density=values["ui_density"],
        ui_scale=values["ui_scale"],
        ttk_theme=preset["ttk_theme"],
        palette=build_palette(mode, accent, values["accent_color"]),
        spacing=spacing,
        font_sizes=build_font_sizes(font_delta),
    )


def build_font_sizes(delta: int) -> dict[str, int]:
    return {
        "body": max(8, 10 + delta),
        "small": max(7, 8 + delta),
        "meta": max(8, 9 + delta),
        "subtitle": max(8, 10 + delta),
        "card_title": max(9, 11 + delta),
        "section": max(11, 16 + delta),
        "title": max(12, 18 + delta),
        "hero": max(14, 21 + delta),
        "sidebar_title": max(11, 14 + delta),
        "top_title": max(12, 15 + delta),
        "metric": max(18, 28 + (delta * 2)),
        "dialog_title": max(14, 20 + delta),
        "button": max(8, 10 + delta),
    }


def build_palette(mode: str, accent: str, accent_key: str) -> dict[str, str]:
    secondary = "#00B8D4" if accent_key == "purple" else "#7C3AED"
    success = "#10B981" if mode == "dark" else "#059669"
    warning = "#F59E0B" if mode == "dark" else "#D97706"
    danger = "#EF4444" if mode == "dark" else "#DC2626"

    if mode == "light":
        palette = {
            "app_bg": "#F3F6FA",
            "surface": "#FFFFFF",
            "surface_alt": "#F6F8FB",
            "surface_alt_2": "#EEF2F7",
            "text": "#172033",
            "muted": "#64748B",
            "primary": accent,
            "secondary": secondary,
            "success": success,
            "warning": warning,
            "danger": danger,
            "border": "#D8E0EA",
            "border_alt": "#C7D2E0",
        }
        palette.update(
            {
                "primary_fg": contrast_text(accent),
                "primary_active": _blend(accent, "#111827", 0.10),
                "selected_bg": _blend(accent, "#FFFFFF", 0.84),
                "selected_fg": "#0F172A",
                "hover_bg": "#E8EEF6",
                "nav_active_bg": "#EAF4FA",
                "tip_bg": "#ECF7FB",
                "primary_bg": _blend(accent, "#FFFFFF", 0.88),
                "secondary_bg": "#F0EAFD",
                "success_bg": "#E7F8F1",
                "warning_bg": "#FFF4DB",
                "danger_bg": "#FEECEC",
                "muted_bg": "#EDF2F7",
                "tree_odd": "#F9FBFD",
                "context_bg": "#FFFFFF",
                "context_fg": "#172033",
                "primary_border": _blend(accent, "#0F172A", 0.45),
                "secondary_border": "#D3C5F6",
            }
        )
        return palette

    palette = {
        "app_bg": "#080B10",
        "surface": "#0E1118",
        "surface_alt": "#141820",
        "surface_alt_2": "#1A1F2C",
        "text": "#E2E8F0",
        "muted": "#64748B",
        "primary": accent,
        "secondary": secondary,
        "success": success,
        "warning": warning,
        "danger": danger,
        "border": "#1A2030",
        "border_alt": "#222B3A",
    }
    palette.update(
        {
            "primary_fg": contrast_text(accent),
            "primary_active": _blend(accent, "#FFFFFF", 0.14),
            "selected_bg": accent,
            "selected_fg": "#0A0C10",
            "hover_bg": "#1E2330",
            "nav_active_bg": "#112132",
            "tip_bg": "#0B1B2B",
            "primary_bg": "#0A1A20",
            "secondary_bg": "#160F22",
            "success_bg": "#081C14",
            "warning_bg": "#111827",
            "danger_bg": "#1F1720",
            "muted_bg": "#0E1118",
            "tree_odd": "#0C1016",
            "context_bg": "#343A40",
            "context_fg": "#FFFFFF",
            "primary_border": _blend(accent, "#000000", 0.62),
            "secondary_border": "#3A1878",
        }
    )
    return palette


def label_for(collection: dict[str, dict[str, Any]], key: str) -> str:
    return str(collection.get(key, {}).get("label", key.title()))


def contrast_text(hex_color: str) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#040608" if luminance > 0.56 else "#FFFFFF"


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = str(hex_color or "#000000").strip().lstrip("#")
    if len(hex_color) != 6:
        return 0, 0, 0
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(
        max(0, min(255, rgb[0])),
        max(0, min(255, rgb[1])),
        max(0, min(255, rgb[2])),
    )


def _blend(foreground: str, background: str, amount: float) -> str:
    fg = _hex_to_rgb(foreground)
    bg = _hex_to_rgb(background)
    amount = max(0.0, min(1.0, float(amount)))
    return _rgb_to_hex(
        (
            int(fg[0] * (1 - amount) + bg[0] * amount),
            int(fg[1] * (1 - amount) + bg[1] * amount),
            int(fg[2] * (1 - amount) + bg[2] * amount),
        )
    )
