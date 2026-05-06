import tkinter as tk
from tkinter import ttk
import time

from gui.components.status import DEFAULT_PALETTE, configure_status_tree_tags, status_tag


def _hex_to_rgb(value):
    value = (value or "").lstrip("#")
    if len(value) != 6:
        return (255, 255, 255)
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, int(c))) for c in rgb))


def _blend(fg, bg, alpha):
    fr, fgn, fb = _hex_to_rgb(fg)
    br, bgn, bb = _hex_to_rgb(bg)
    return _rgb_to_hex(
        (
            fr * alpha + br * (1 - alpha),
            fgn * alpha + bgn * (1 - alpha),
            fb * alpha + bb * (1 - alpha),
        )
    )


def build_checkbox_image_set(palette=None, *, size=18):
    """Build the unchecked / checked / hover PhotoImage trio from a palette.

    Returns ``{}`` if PhotoImage construction fails (e.g. exotic Tk build) so
    callers can fall back to text glyphs without crashing.
    """
    palette = palette or DEFAULT_PALETTE
    surface = palette.get("surface_alt", "#141820")
    success = palette.get("success", "#10B981")
    muted = palette.get("muted", "#64748B")
    primary = palette.get("primary", "#00E5FF")
    try:
        return {
            "unchecked": _build_checkbox_image(
                size=size,
                fill=_blend(muted, surface, 0.18),
                border=_blend(muted, surface, 0.55),
                check=None,
                bg=surface,
            ),
            "checked": _build_checkbox_image(
                size=size,
                fill=_blend(success, surface, 0.85),
                border=success,
                check="#FFFFFF",
                bg=surface,
            ),
            "hover": _build_checkbox_image(
                size=size,
                fill=_blend(muted, surface, 0.30),
                border=primary,
                check=None,
                bg=surface,
            ),
        }
    except Exception:
        return {}


def _build_checkbox_image(*, size=18, fill, border, check=None, bg):
    """Draw a square checkbox PhotoImage with optional check glyph.

    Pixels outside the rounded box are made transparent so the image blends
    with whichever row background is active (hover/selected/zebra).
    """
    img = tk.PhotoImage(width=size, height=size)
    img.put(bg, to=(0, 0, size, size))

    pad = 2
    inner = size - pad * 2
    # Box body fill
    img.put(fill, to=(pad, pad, pad + inner, pad + inner))
    # 1px border on the box
    img.put(border, to=(pad, pad, pad + inner, pad + 1))
    img.put(border, to=(pad, pad + inner - 1, pad + inner, pad + inner))
    img.put(border, to=(pad, pad, pad + 1, pad + inner))
    img.put(border, to=(pad + inner - 1, pad, pad + inner, pad + inner))

    if check:
        # Hand-drawn check glyph using a small pixel matrix scaled to box size.
        # 9x9 mask; 1 = check pixel
        mask = [
            "         ",
            "         ",
            "       1 ",
            "      11 ",
            " 1   11  ",
            " 11 11   ",
            "  111    ",
            "   1     ",
            "         ",
        ]
        ox = pad + 1
        oy = pad + 1
        cell = max(1, (inner - 2) // 9)
        for row, line in enumerate(mask):
            for col, ch in enumerate(line):
                if ch == "1":
                    x0 = ox + col * cell
                    y0 = oy + row * cell
                    img.put(check, to=(x0, y0, x0 + cell, y0 + cell))

    # Mark the corner padding transparent so the box doesn't sit on a colored card.
    try:
        for x in range(size):
            for y in range(size):
                if x < pad or x >= size - pad or y < pad or y >= size - pad:
                    img.transparency_set(x, y, True)
    except tk.TclError:
        pass
    return img


class CheckboxTreeview(ttk.Treeview):
    def __init__(self, master=None, **kwargs):
        self.palette = kwargs.pop("palette", DEFAULT_PALETTE)
        super().__init__(master, **kwargs)
        self.checkboxes = {}
        self.selection_enabled = True
        self._clicked_item = None
        self._click_time = 0

        # Drawn checkbox images give a clearer visual than thin Unicode glyphs.
        self._checkbox_images = {}
        self._build_checkbox_images()

        self.tag_configure("checked", background="", foreground="")
        self.tag_configure("unchecked", background="", foreground="")
        self.apply_palette(self.palette)

        # Bind events
        self.bind("<Button-1>", self._on_click)
        self.bind("<Double-1>", self._on_double_click)
        self.bind("<Control-a>", self._select_all)
        self.bind("<Control-A>", self._select_all)
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)

        # Right-click context menu
        self.context_menu = tk.Menu(
            self,
            tearoff=0,
            bg=self.palette.get("context_bg", "#343A40"),
            fg=self.palette.get("context_fg", "white"),
        )
        self.context_menu.add_command(label="Select", command=self._context_select)
        self.context_menu.add_command(label="Deselect", command=self._context_deselect)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Select All", command=self._context_select_all)
        self.context_menu.add_command(label="Deselect All", command=self._context_deselect_all)
        self.bind("<Button-3>", self._show_context_menu)

        self.context_item = None
        self.hover_item = None

    def _build_checkbox_images(self):
        self._checkbox_images = build_checkbox_image_set(self.palette)

    def _checkbox_image(self, key):
        return self._checkbox_images.get(key)

    def _checkbox_text(self, checked):
        # Fallback glyphs when image creation is unavailable.
        return "☑" if checked else "☐"

    def apply_palette(self, palette):
        self.palette = palette or DEFAULT_PALETTE
        configure_status_tree_tags(self, self.palette)
        self.tag_configure(
            "selected",
            background=self.palette.get("selected_bg", self.palette["primary"]),
            foreground=self.palette.get("selected_fg", "#0A0C10"),
        )
        self.tag_configure("hover", background=self.palette.get("hover_bg", self.palette["surface_alt"]))
        # Subtle accent so checked rows stand out without overpowering status colors.
        checked_tint = _blend(
            self.palette.get("success", "#10B981"), self.palette.get("surface", "#0E1118"), 0.12
        )
        self.tag_configure("checked", background=checked_tint, foreground=self.palette.get("text", "#E2E8F0"))
        self.tag_configure("unchecked", background="", foreground="")
        if hasattr(self, "context_menu"):
            self.context_menu.configure(
                bg=self.palette.get("context_bg", "#343A40"),
                fg=self.palette.get("context_fg", "white"),
            )
        # Rebuild images so they pick up new palette colors.
        self._build_checkbox_images()
        # Refresh existing rows.
        for item, checked in list(self.checkboxes.items()):
            if self.exists(item):
                self._apply_checkbox_visual(item, checked)

    def _apply_checkbox_visual(self, item, checked):
        image = self._checkbox_image("checked" if checked else "unchecked")
        if image is not None:
            self.item(item, image=image, text="")
        else:
            self.item(item, image="", text=self._checkbox_text(checked))

    def _on_click(self, event):
        item = self.identify_row(event.y)
        if item:
            self._clicked_item = item
            self._click_time = time.time()
            self.select_item(item)

    def select_item(self, item):
        for iid in self.get_children():
            current_tags = list(self.item(iid, "tags"))
            if "selected" in current_tags:
                current_tags.remove("selected")
                self.item(iid, tags=current_tags)

        if item:
            current_tags = list(self.item(item, "tags"))
            if "selected" not in current_tags:
                current_tags.append("selected")
            self.item(item, tags=current_tags)

    def insert(self, parent, index, iid=None, **kwargs):
        kwargs.pop("text", None)
        item = super().insert(parent, index, iid, **kwargs)
        self.checkboxes[item] = False

        values = kwargs.get("values", [])
        if len(values) > 2:
            tags = ("unchecked", status_tag(values[2]))
        else:
            tags = ("unchecked", "inactive")

        self.item(item, tags=tags)
        self._apply_checkbox_visual(item, False)
        return item

    def _on_double_click(self, event):
        item = self.identify_row(event.y)
        if item:
            self.toggle_checkbox(item)

    def get_selected_item(self):
        for item in self.get_children():
            if "selected" in self.item(item, "tags"):
                return item
        return None

    def _select_all(self, event):
        for item in self.get_children():
            if not self.checkboxes[item]:
                self.toggle_checkbox(item)
        return "break"

    def _show_context_menu(self, event):
        item = self.identify_row(event.y)
        if item:
            self.context_item = item
            self.context_menu.post(event.x_root, event.y_root)

    def _on_motion(self, event):
        item = self.identify_row(event.y)
        if item == self.hover_item:
            return
        self._clear_hover()
        self.hover_item = item
        if not item:
            return
        tags = list(self.item(item, "tags"))
        if "hover" not in tags:
            tags.append("hover")
            self.item(item, tags=tags)
        # Show hover variant only for unchecked rows; checked stays accented.
        if not self.checkboxes.get(item, False):
            hover_image = self._checkbox_image("hover")
            if hover_image is not None:
                self.item(item, image=hover_image)

    def _on_leave(self, _event):
        self._clear_hover()

    def _clear_hover(self):
        if not self.hover_item:
            return
        if self.exists(self.hover_item):
            tags = [t for t in self.item(self.hover_item, "tags") if t != "hover"]
            self.item(self.hover_item, tags=tags)
            # Restore the proper checkbox image after leaving hover.
            self._apply_checkbox_visual(self.hover_item, self.checkboxes.get(self.hover_item, False))
        self.hover_item = None

    def toggle_checkbox(self, item):
        if item in self.checkboxes:
            self.checkboxes[item] = not self.checkboxes[item]
        else:
            self.checkboxes[item] = True

        current_tags = list(self.item(item, "tags"))
        new_tags = [t for t in current_tags if t not in ("checked", "unchecked")]

        if self.checkboxes[item]:
            new_tags.append("checked")
        else:
            new_tags.append("unchecked")

        self.item(item, tags=new_tags)
        self._apply_checkbox_visual(item, self.checkboxes[item])

    def _context_select(self):
        if self.context_item:
            if not self.checkboxes[self.context_item]:
                self.toggle_checkbox(self.context_item)

    def _context_deselect(self):
        if self.context_item:
            if self.checkboxes[self.context_item]:
                self.toggle_checkbox(self.context_item)

    def _context_select_all(self):
        for item in self.get_children():
            if not self.checkboxes[item]:
                self.toggle_checkbox(item)

    def _context_deselect_all(self):
        for item in self.get_children():
            if self.checkboxes[item]:
                self.toggle_checkbox(item)

    def get_checked_items(self):
        return [item for item, checked in self.checkboxes.items() if checked]

    def delete(self, *items):
        result = super().delete(*items)
        for item in items:
            self.checkboxes.pop(item, None)
        return result
