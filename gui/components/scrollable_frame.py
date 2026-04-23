import tkinter as tk
import ttkbootstrap as tb


class ScrollableFrame(tk.Frame):
    """
    Reusable vertical-scroll container using Canvas + inner Frame pattern.

    Place child widgets inside ``self.body`` using standard pack/grid/place.
    Mouse-wheel scrolling works on Windows (delta) and Linux (Button-4/5)
    across *any* descendant of ``body`` — no per-widget wiring needed.

    The scroll container only scrolls vertically.  Horizontal layout is
    handled normally by the inner frame's pack/grid managers.

    Args:
        parent:           Parent widget.
        bg:               Background hex color for Canvas + inner Frame.
                          Pass palette["surface"] so it blends seamlessly.
        scrollbar_style:  ttkbootstrap scrollbar style name.
        fill_viewport_height:
                          When True, the inner frame is kept at least as tall
                          as the visible canvas so child layouts using
                          ``fill="both", expand=True`` still work while also
                          scrolling when content grows taller than the viewport.
        wheel_step:       Number of canvas units scrolled per wheel notch.
        nested_scroll_classes:
                          Widget classes that own their own wheel scrolling
                          (Treeview, Listbox, Text, Canvas). When the cursor
                          is over one of these, wheel events are left alone so
                          the nested widget scrolls itself.
    """

    _NESTED_SCROLL_CLASSES = ("Treeview", "Listbox", "Text", "TCombobox", "Spinbox")

    def __init__(
        self,
        parent,
        bg: str = "#0E1118",
        scrollbar_style: str = "Vertical.TScrollbar",
        fill_viewport_height: bool = False,
        wheel_step: int = 3,
        nested_scroll_classes=None,
        **kwargs,
    ):
        super().__init__(parent, bg=bg, **kwargs)
        self._bg = bg
        self._fill_viewport_height = fill_viewport_height
        self._wheel_step = max(1, int(wheel_step))
        self._nested_scroll_classes = set(nested_scroll_classes or self._NESTED_SCROLL_CLASSES)

        self._canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, takefocus=0)
        self._scrollbar = tb.Scrollbar(
            self,
            orient="vertical",
            command=self._canvas.yview,
            style=scrollbar_style,
        )
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

        self._scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        # Inner frame — widgets go here
        self.body = tk.Frame(self._canvas, bg=bg)
        self._inner_id = self._canvas.create_window((0, 0), window=self.body, anchor="nw")

        # Keep scroll region and inner width in sync.
        self.body.bind("<Configure>", self._on_body_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        # Install wheel handling when the cursor enters the scroll area
        # so *any* descendant (cards, labels, buttons) scrolls without
        # needing per-widget wiring.  Remove it on leave so multiple
        # ScrollableFrames on screen don't fight each other.
        self._wheel_bound = False
        for widget in (self, self._canvas, self.body):
            widget.bind("<Enter>", self._bind_wheel, add="+")
            widget.bind("<Leave>", self._unbind_wheel, add="+")

        # Keyboard scrolling for accessibility.
        self._canvas.bind("<Up>", lambda _e: self._canvas.yview_scroll(-1, "units"))
        self._canvas.bind("<Down>", lambda _e: self._canvas.yview_scroll(1, "units"))
        self._canvas.bind("<Prior>", lambda _e: self._canvas.yview_scroll(-1, "pages"))
        self._canvas.bind("<Next>", lambda _e: self._canvas.yview_scroll(1, "pages"))
        self._canvas.bind("<Home>", lambda _e: self._canvas.yview_moveto(0))
        self._canvas.bind("<End>", lambda _e: self._canvas.yview_moveto(1))

    # ------------------------------------------------------------------
    # Internal geometry callbacks
    # ------------------------------------------------------------------

    def _on_body_configure(self, _event=None):
        self._sync_inner_height()
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self._canvas.itemconfigure(self._inner_id, width=event.width)
        self._sync_inner_height(event.height)

    def _sync_inner_height(self, canvas_height=None):
        if not self._fill_viewport_height:
            return
        if canvas_height is None:
            canvas_height = self._canvas.winfo_height()
        body_height = self.body.winfo_reqheight()
        self._canvas.itemconfigure(self._inner_id, height=max(canvas_height, body_height))

    # ------------------------------------------------------------------
    # Mouse-wheel handling
    # ------------------------------------------------------------------

    def _is_over_nested_scroller(self):
        """True when the pointer is over a widget that scrolls itself."""
        try:
            x = self._canvas.winfo_pointerx()
            y = self._canvas.winfo_pointery()
            widget = self._canvas.winfo_containing(x, y)
        except Exception:
            return False

        while widget is not None and widget is not self:
            try:
                cls = widget.winfo_class()
            except Exception:
                break
            if cls in self._nested_scroll_classes:
                # Only treat as nested scroller if it actually has
                # scrollable content (avoids disabling wheel for
                # single-line entries that happen to be in the list).
                if self._widget_is_vscrollable(widget):
                    return True
            try:
                widget = widget.master
            except Exception:
                break
        return False

    @staticmethod
    def _widget_is_vscrollable(widget):
        try:
            cls = widget.winfo_class()
        except Exception:
            return False
        if cls in ("Treeview", "Listbox", "Text"):
            try:
                first, last = widget.yview()
                return (last - first) < 1.0
            except Exception:
                return True
        return False

    def _on_mouse_wheel(self, event):
        if self._is_over_nested_scroller():
            return  # let the nested widget handle it

        # Do nothing when content already fits inside the viewport.
        try:
            first, last = self._canvas.yview()
        except Exception:
            first, last = 0.0, 1.0
        if (last - first) >= 1.0:
            return "break"

        delta = 0
        if getattr(event, "delta", 0):
            # Windows/macOS: +120 per notch (macOS sends smaller values — we
            # still normalise to whole-unit steps for a consistent feel).
            raw = event.delta
            step = -1 if raw > 0 else 1
            magnitude = max(1, abs(raw) // 120)
            delta = step * magnitude * self._wheel_step
        elif getattr(event, "num", None) == 4:
            delta = -self._wheel_step
        elif getattr(event, "num", None) == 5:
            delta = self._wheel_step

        if delta:
            self._canvas.yview_scroll(delta, "units")
        return "break"

    def _bind_wheel(self, _event=None):
        if self._wheel_bound:
            return
        # bind_all so the wheel works over any descendant — but only while
        # the cursor is inside this frame (Enter/Leave toggle).
        self._canvas.bind_all("<MouseWheel>", self._on_mouse_wheel, add="+")
        self._canvas.bind_all("<Button-4>", self._on_mouse_wheel, add="+")
        self._canvas.bind_all("<Button-5>", self._on_mouse_wheel, add="+")
        self._wheel_bound = True

    def _unbind_wheel(self, event=None):
        # Only release when the pointer really left the scroll area.  Enter/
        # Leave fires between internal widgets too, so check geometry.
        if event is not None:
            try:
                x = self._canvas.winfo_pointerx()
                y = self._canvas.winfo_pointery()
                under = self._canvas.winfo_containing(x, y)
            except Exception:
                under = None
            w = under
            while w is not None:
                if w is self:
                    return
                try:
                    w = w.master
                except Exception:
                    break
        if not self._wheel_bound:
            return
        try:
            self._canvas.unbind_all("<MouseWheel>")
            self._canvas.unbind_all("<Button-4>")
            self._canvas.unbind_all("<Button-5>")
        except Exception:
            pass
        self._wheel_bound = False

    # ------------------------------------------------------------------
    # Public API (kept for backwards compatibility)
    # ------------------------------------------------------------------

    def bind_scroll(self, widget):
        """No-op kept for backwards compatibility.

        Wheel scrolling is now handled globally while the cursor is inside
        the scroll area, so explicit per-widget wiring is no longer needed.
        """
        return

    def bind_scroll_tree(self, widget, skip_widget_classes=None):
        """No-op kept for backwards compatibility.  See ``bind_scroll``."""
        return

    def scroll_to_top(self):
        """Jump the view back to the top of the content."""
        self._canvas.yview_moveto(0)

    def update_bg(self, new_bg: str):
        """Repaint all scroll-layer surfaces after a theme change."""
        self._bg = new_bg
        self.configure(bg=new_bg)
        self._canvas.configure(bg=new_bg)
        self.body.configure(bg=new_bg)
