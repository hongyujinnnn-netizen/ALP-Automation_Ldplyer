import tkinter as tk

class GradientProgressBar(tk.Canvas):
    """Canvas-based progress bar with gradient fill."""

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
        self.bind("<Configure>", lambda _e: self._draw())

    def set(self, value):
        """Update progress between 0-100."""
        self._value = max(0, min(100, float(value)))
        self._draw()

    def configure_colors(self, color_start, color_end):
        self._color_start = color_start
        self._color_end = color_end
        self._draw()

    def _hex_to_rgb(self, hex_color):
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))

    def _draw(self):
        self.delete("all")
        width = self.winfo_width()
        height = self.winfo_height()
        fill_w = int(width * self._value / 100)
        if fill_w <= 0:
            return

        r1, g1, b1 = self._hex_to_rgb(self._color_start)
        r2, g2, b2 = self._hex_to_rgb(self._color_end)
        steps = max(fill_w, 1)
        for i in range(steps):
            t = i / max(steps - 1, 1)
            r = int(r1 + t * (r2 - r1))
            g = int(g1 + t * (g2 - g1))
            b = int(b1 + t * (b2 - b1))
            color = f"#{r:02x}{g:02x}{b:02x}"
            self.create_line(i, 0, i, height, fill=color, width=1)

