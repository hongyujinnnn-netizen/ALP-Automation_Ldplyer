import tkinter as tk


class GradientProgressBar(tk.Canvas):
    """Canvas-based progress bar with a cached gradient fill."""

    _gradient_cache = {}

    def __init__(self, parent, bg="#0E1118", height=6, color_start="#00E5FF", color_end="#7C3AED", **kwargs):
        super().__init__(
            parent,
            height=height,
            bg=bg,
            highlightthickness=0,
            bd=0,
            **kwargs,
        )
        self._value = 0
        self._color_start = color_start
        self._color_end = color_end
        self._image_id = None
        self._cached_key = None
        self._cached_image = None
        self.bind("<Configure>", lambda _e: self._draw())

    def set(self, value):
        self._value = max(0, min(100, float(value)))
        self._draw()

    def configure_colors(self, color_start, color_end):
        self._color_start = color_start
        self._color_end = color_end
        self._draw()

    @staticmethod
    def _hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))

    @classmethod
    def _get_gradient_image(cls, width, height, color_start, color_end):
        key = (width, height, color_start, color_end)
        img = cls._gradient_cache.get(key)
        if img is not None:
            return img

        img = tk.PhotoImage(width=width, height=height)
        r1, g1, b1 = cls._hex_to_rgb(color_start)
        r2, g2, b2 = cls._hex_to_rgb(color_end)
        denom = max(width - 1, 1)
        # Build one horizontal row then stamp it down.
        row = []
        for x in range(width):
            t = x / denom
            r = int(r1 + t * (r2 - r1))
            g = int(g1 + t * (g2 - g1))
            b = int(b1 + t * (b2 - b1))
            row.append(f"#{r:02x}{g:02x}{b:02x}")
        row_str = "{" + " ".join(row) + "}"
        img.put(" ".join([row_str] * height))

        # Bounded cache so theme switches don't leak.
        if len(cls._gradient_cache) > 32:
            cls._gradient_cache.pop(next(iter(cls._gradient_cache)))
        cls._gradient_cache[key] = img
        return img

    def _draw(self):
        width = self.winfo_width()
        height = self.winfo_height()
        if width <= 1 or height <= 1:
            return

        fill_w = int(width * self._value / 100)
        if fill_w <= 0:
            if self._image_id is not None:
                self.delete(self._image_id)
                self._image_id = None
            return

        key = (width, height, self._color_start, self._color_end)
        if key != self._cached_key:
            self._cached_image = self._get_gradient_image(width, height, self._color_start, self._color_end)
            self._cached_key = key
            if self._image_id is not None:
                self.delete(self._image_id)
                self._image_id = None

        if self._image_id is None:
            self._image_id = self.create_image(0, 0, anchor="nw", image=self._cached_image)
        # Clip by moving a cover rectangle; simplest: redraw clip rect on right side.
        self.delete("clip")
        if fill_w < width:
            self.create_rectangle(
                fill_w,
                0,
                width,
                height,
                fill=self["bg"],
                outline="",
                tags="clip",
            )
