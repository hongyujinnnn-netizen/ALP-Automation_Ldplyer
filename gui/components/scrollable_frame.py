import tkinter as tk
import ttkbootstrap as tb


class ScrollableFrame(tk.Frame):
    """
    Reusable vertical-scroll container using Canvas + inner Frame pattern.

    Place child widgets inside `self.body` using standard pack/grid/place.
    The inner frame width always tracks the visible canvas width.
    Mouse-wheel scrolling works on Windows (delta) and Linux (Button-4/5).

    Usage:
        scroller = ScrollableFrame(parent, bg=palette["surface"])
        scroller.pack(fill="both", expand=True)

        tb.Label(scroller.body, text="Row 1").pack(anchor="w", fill="x")
        tb.Label(scroller.body, text="Row 2").pack(anchor="w", fill="x")

    The scroll container only scrolls vertically.  Horizontal layout is
    handled normally by the inner frame's pack/grid managers.

    Args:
        parent:           Parent widget.
        bg:               Background hex color for Canvas + inner Frame.
                          Pass palette["surface"] so it blends seamlessly.
        scrollbar_style:  ttkbootstrap scrollbar style name.
        fill_viewport_height:
                          When True, the inner frame is kept at least as tall
                          as the visible canvas. This lets child layouts that
                          use ``fill="both", expand=True`` behave like they
                          did in a normal frame while still scrolling when
                          content grows taller than the viewport.
    """

    def __init__(
        self,
        parent,
        bg: str = "#0E1118",
        scrollbar_style: str = "Vertical.TScrollbar",
        fill_viewport_height: bool = False,
        **kwargs,
    ):
        super().__init__(parent, bg=bg, **kwargs)
        self._bg = bg
        self._fill_viewport_height = fill_viewport_height

        self._canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
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

        # Keep scroll region and inner width in sync
        self.body.bind("<Configure>", self._on_body_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        # Wire mouse-wheel on the outer shell, the canvas, and the body so
        # that any empty area in the tab still scrolls.
        self._handler = self._build_handler()
        for widget in (self, self._canvas, self.body):
            self._wire(widget)

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
    # Mouse-wheel
    # ------------------------------------------------------------------

    def _build_handler(self):
        canvas = self._canvas

        def _handler(event):
            delta = 0
            if getattr(event, "delta", 0):
                delta = -1 * int(event.delta / 120)
            elif getattr(event, "num", None) == 4:
                delta = -1
            elif getattr(event, "num", None) == 5:
                delta = 1
            if delta:
                canvas.yview_scroll(delta, "units")

        return _handler

    def _wire(self, widget):
        fn = self._handler
        widget.bind("<MouseWheel>", fn, add="+")
        widget.bind("<Button-4>", fn, add="+")
        widget.bind("<Button-5>", fn, add="+")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def bind_scroll(self, widget):
        """
        Route mouse-wheel events from *widget* into this scroll container.

        Call this for intermediate container frames nested inside ``body``
        that sit under the cursor and capture events before they can bubble
        up (rare in practice, but useful for deep widget hierarchies).
        """
        self._wire(widget)

    def bind_scroll_tree(self, widget, skip_widget_classes=None):
        """
        Route mouse-wheel events from a widget subtree into this scroll
        container, while preserving native scrolling for nested scrollable
        controls such as Treeview and Listbox.
        """
        skip_widget_classes = set(skip_widget_classes or ("Treeview", "Listbox", "Text"))
        if widget.winfo_class() in skip_widget_classes:
            return

        self._wire(widget)
        for child in widget.winfo_children():
            self.bind_scroll_tree(child, skip_widget_classes)

    def scroll_to_top(self):
        """Jump the view back to the top of the content."""
        self._canvas.yview_moveto(0)

    def update_bg(self, new_bg: str):
        """Repaint all scroll-layer surfaces after a theme change."""
        self._bg = new_bg
        self.configure(bg=new_bg)
        self._canvas.configure(bg=new_bg)
        self.body.configure(bg=new_bg)
