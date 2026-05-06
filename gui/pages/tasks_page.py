import tkinter as tk

import ttkbootstrap as tb

from gui.components.scrollable_frame import ScrollableFrame

# ── Tasks page accent palette (kept local so the page can have its own identity) ── #
_TASKS_PRIMARY = "#22D3EE"
_TASKS_PRIMARY_HOVER = "#67E8F9"
_TASKS_DANGER = "#F43F5E"
_TASKS_DANGER_HOVER = "#FB7185"
_TASKS_WARNING = "#F59E0B"
_TASKS_WARNING_HOVER = "#FBBF24"
_TASKS_MUTED = "#475569"
_TASKS_MUTED_HOVER = "#64748B"


class TasksPageMixin:
    # ─────────────────────────────────────────────────────────────────── #
    # Task taxonomy

    TASK_TYPE_OPTIONS = [
        ("Facebook Active", "scroll"),
        ("Register Account", "reg_account"),
        ("Post Reels", "reels"),
        ("Test Feature", "test_feature"),
    ]

    TASK_TYPE_LABELS = {
        "scroll": "Facebook Active",
        "reg_account": "Register Account",
        "login": "Login Account",
        "reels": "Post Reels",
        "test_feature": "Test Feature",
    }

    # Visual metadata per task tile: (icon, short description, accent, badge tag)
    TASK_TYPE_META = {
        "scroll": ("◉", "Keep accounts active by browsing the feed.", "#22D3EE", "Engage"),
        "reg_account": ("✦", "Register and verify new Facebook accounts.", "#A855F7", "Onboard"),
        "reels": ("▶", "Post reels across pages with rotation.", "#F43F5E", "Publish"),
        "test_feature": ("✱", "Run experimental modules safely.", "#F59E0B", "Beta"),
    }

    # ─────────────────────────────────────────────────────────────────── #
    # Page entry

    def create_tasks_tab(self):
        """Create the Tasks workspace with hero, selectors, settings, and controls."""
        tasks_tab = tb.Frame(self.notebook, style="CardInner.TFrame")
        self.notebook.add(tasks_tab, text="Tasks")

        scroller = ScrollableFrame(tasks_tab, bg=self.palette["surface"])
        scroller.pack(fill="both", expand=True)
        body = scroller.body

        self._tasks_status_word = "Ready"

        self._build_tasks_hero(body)
        self._build_task_type_panel(body)
        self._build_settings_row(body)

        self._refresh_tasks_summary()
        self._bind_summary_traces()

    # ─────────────────────────────────────────────────────────────────── #
    # Hero banner

    def _build_tasks_hero(self, parent):
        # Outer wrapper — hosts the hero shell plus a thin cyan accent line beneath.
        wrapper = tk.Frame(parent, bg=self.palette["surface"])
        wrapper.pack(fill="x", pady=(0, 14))

        shell = tk.Frame(wrapper, bg=self.palette["surface_alt"], highlightthickness=0, bd=0)
        shell.pack(fill="x")

        tk.Frame(shell, bg=_TASKS_PRIMARY, width=5).pack(side="left", fill="y")

        inner = tk.Frame(shell, bg=self.palette["surface_alt"], padx=22, pady=20)
        inner.pack(side="left", fill="both", expand=True)

        # Eyebrow label: small cyan tag above the title
        eyebrow_row = tk.Frame(inner, bg=self.palette["surface_alt"])
        eyebrow_row.pack(fill="x")
        tk.Label(
            eyebrow_row,
            text="◆ AUTOMATION WORKSPACE",
            bg=self.palette["surface_alt"],
            fg=_TASKS_PRIMARY,
            font=(self.mono_font, 9, "bold"),
        ).pack(side="left")
        self._tasks_status_chip = tk.Label(
            eyebrow_row,
            text="● READY",
            bg=self.palette["surface_alt"],
            fg="#10B981",
            font=(self.mono_font, 9, "bold"),
            padx=10,
            pady=2,
        )
        self._tasks_status_chip.pack(side="right", anchor="ne")

        # Title row: live task name (large, accent-colored)
        title_row = tk.Frame(inner, bg=self.palette["surface_alt"])
        title_row.pack(fill="x", pady=(6, 0))
        self._tasks_hero_title = tk.Label(
            title_row,
            text=self._task_display_name(),
            bg=self.palette["surface_alt"],
            fg=_TASKS_PRIMARY,
            font=(self.display_font, 20, "bold"),
        )
        self._tasks_hero_title.pack(side="left", anchor="w")

        # Subtitle row — three colored segments separated by muted dots
        subtitle_row = tk.Frame(inner, bg=self.palette["surface_alt"])
        subtitle_row.pack(anchor="w", pady=(8, 14))

        def _seg(text, color):
            lbl = tk.Label(
                subtitle_row,
                text=text,
                bg=self.palette["surface_alt"],
                fg=color,
                font=(self.mono_font, 10, "bold"),
            )
            lbl.pack(side="left")
            return lbl

        def _sep():
            tk.Label(
                subtitle_row,
                text="·",
                bg=self.palette["surface_alt"],
                fg=self.palette["muted"],
                font=(self.mono_font, 10),
            ).pack(side="left", padx=8)

        self._hero_status_seg = _seg("Ready", "#10B981")
        _sep()
        self._hero_devices_seg = _seg("— devices", _TASKS_PRIMARY)
        _sep()
        self._hero_ending_seg = _seg("— run", _TASKS_WARNING)

        # Thin cyan accent line below the hero — the "dynamic" rail of the page
        tk.Frame(wrapper, bg=_TASKS_PRIMARY, height=2).pack(fill="x", pady=(0, 0))

        # Run / Pause / Stop controls live in the top bar — keeping them off the
        # Tasks page so this surface stays focused on configuration.

    # ─────────────────────────────────────────────────────────────────── #
    # Task type panel — visual tiles

    def _build_task_type_panel(self, parent):
        card_body = self._create_card_section(
            parent,
            "Choose Task",
            "Pick the automation module to configure.",
        )

        grid = tb.Frame(card_body, style="CardInner.TFrame")
        grid.pack(fill="x", padx=2, pady=(4, 8))

        columns = min(4, max(2, len(self.TASK_TYPE_OPTIONS)))
        for column in range(columns):
            grid.grid_columnconfigure(column, weight=1, uniform="task_tiles")

        self._task_tile_widgets = {}
        for index, (label, value) in enumerate(self.TASK_TYPE_OPTIONS):
            icon, desc, accent, tag = self.TASK_TYPE_META.get(value, ("●", "", _TASKS_PRIMARY, "Task"))
            tile = self._build_task_tile(grid, value, label, desc, icon, accent, tag)
            tile.grid(
                row=index // columns,
                column=index % columns,
                padx=8,
                pady=8,
                sticky="nsew",
            )
            self._task_tile_widgets[value] = tile

        self._sync_task_tile_selection()

    def _build_task_tile(self, parent, value, label, desc, icon, accent, tag):
        # Outer frame doubles as a 1px border that we recolor for hover/selected states.
        outer = tk.Frame(
            parent,
            bg=self.palette["border"],
            highlightthickness=0,
            bd=0,
        )

        # Top accent rail — visible only when selected
        rail = tk.Frame(outer, bg=self.palette["surface_alt"], height=3)
        rail.pack(fill="x", padx=1, pady=(1, 0))

        inner = tk.Frame(outer, bg=self.palette["surface_alt"], padx=16, pady=14)
        inner.pack(fill="both", expand=True, padx=1, pady=(0, 1))

        # Header: icon badge (left) + tag chip (right)
        head = tk.Frame(inner, bg=self.palette["surface_alt"])
        head.pack(fill="x")

        badge_outer = tk.Frame(head, bg=self.palette["border"], width=42, height=42)
        badge_outer.pack(side="left")
        badge_outer.pack_propagate(False)
        icon_lbl = tk.Label(
            badge_outer,
            text=icon,
            bg=self.palette["border"],
            fg=self.palette["muted"],
            font=(self.display_font, 17, "bold"),
        )
        icon_lbl.pack(expand=True, fill="both")

        tag_lbl = tk.Label(
            head,
            text=tag.upper(),
            bg=self.palette["surface_alt"],
            fg=self.palette["muted"],
            font=(self.mono_font, 8, "bold"),
            padx=8,
            pady=2,
        )
        tag_lbl.pack(side="right", anchor="ne")

        # Title row with selection check on the right
        title_row = tk.Frame(inner, bg=self.palette["surface_alt"])
        title_row.pack(fill="x", pady=(12, 0))
        title_lbl = tk.Label(
            title_row,
            text=label,
            bg=self.palette["surface_alt"],
            fg=self.palette["text"],
            font=(self.display_font, 13, "bold"),
        )
        title_lbl.pack(side="left")
        check_lbl = tk.Label(
            title_row,
            text="✓",
            bg=self.palette["surface_alt"],
            fg=accent,
            font=(self.display_font, 13, "bold"),
        )
        # Initially hidden; shown via _sync_task_tile_selection
        check_lbl.pack_forget()

        desc_lbl = tk.Label(
            inner,
            text=desc,
            bg=self.palette["surface_alt"],
            fg=self.palette["muted"],
            font=(self.mono_font, 9),
            wraplength=260,
            justify="left",
        )
        desc_lbl.pack(anchor="w", pady=(6, 0))

        widgets = (
            outer,
            inner,
            head,
            badge_outer,
            icon_lbl,
            tag_lbl,
            title_row,
            title_lbl,
            check_lbl,
            desc_lbl,
        )

        def _select(_event=None):
            if self.task_type_var.get() != value:
                self.task_type_var.set(value)
            self._sync_task_tile_selection()
            self.render_task_settings()

        def _on_enter(_event=None):
            if self.task_type_var.get() != value:
                outer.configure(bg=accent)

        def _on_leave(_event=None):
            self._sync_task_tile_selection()

        # Don't bind hover on the icon badge itself — it would flicker its bg.
        click_targets = (outer, inner, head, tag_lbl, title_row, title_lbl, check_lbl, desc_lbl)
        for widget in click_targets:
            widget.bind("<Button-1>", _select)
            widget.bind("<Enter>", _on_enter)
            widget.bind("<Leave>", _on_leave)
            widget.configure(cursor="hand2")
        # Badge stays clickable but doesn't drive hover recolor
        for widget in (badge_outer, icon_lbl):
            widget.bind("<Button-1>", _select)
            widget.configure(cursor="hand2")

        outer._task_value = value
        outer._task_accent = accent
        outer._task_rail = rail
        outer._task_check = check_lbl
        outer._task_title_row = title_row
        outer._task_badge_outer = badge_outer
        outer._task_icon_lbl = icon_lbl
        outer._task_tag_lbl = tag_lbl
        return outer

    def _sync_task_tile_selection(self):
        active = self.task_type_var.get()
        for value, tile in getattr(self, "_task_tile_widgets", {}).items():
            accent = getattr(tile, "_task_accent", _TASKS_PRIMARY)
            rail = getattr(tile, "_task_rail", None)
            check = getattr(tile, "_task_check", None)
            title_row = getattr(tile, "_task_title_row", None)
            badge_outer = getattr(tile, "_task_badge_outer", None)
            icon_lbl = getattr(tile, "_task_icon_lbl", None)
            tag_lbl = getattr(tile, "_task_tag_lbl", None)

            if value == active:
                tile.configure(bg=accent)
                if rail is not None:
                    rail.configure(bg=accent)
                if check is not None and title_row is not None:
                    if not check.winfo_ismapped():
                        check.pack(in_=title_row, side="right")
                if badge_outer is not None:
                    badge_outer.configure(bg=accent)
                if icon_lbl is not None:
                    icon_lbl.configure(bg=accent, fg="#0B1220")
                if tag_lbl is not None:
                    tag_lbl.configure(fg=accent)
            else:
                tile.configure(bg=self.palette["border"])
                if rail is not None:
                    rail.configure(bg=self.palette["surface_alt"])
                if check is not None and check.winfo_ismapped():
                    check.pack_forget()
                if badge_outer is not None:
                    badge_outer.configure(bg=self.palette["border"])
                if icon_lbl is not None:
                    icon_lbl.configure(bg=self.palette["border"], fg=self.palette["muted"])
                if tag_lbl is not None:
                    tag_lbl.configure(fg=self.palette["muted"])

    # ─────────────────────────────────────────────────────────────────── #
    # Settings row — active task + common settings side by side

    def _build_settings_row(self, parent):
        row = tb.Frame(parent, style="CardInner.TFrame")
        row.pack(fill="both", expand=True, pady=(0, 0))
        row.grid_columnconfigure(0, weight=5, uniform="task_settings")
        row.grid_columnconfigure(1, weight=5, uniform="task_settings")

        active_col = tb.Frame(row, style="CardInner.TFrame")
        active_col.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        common_col = tb.Frame(row, style="CardInner.TFrame")
        common_col.grid(row=0, column=1, sticky="nsew", padx=(7, 0))

        self.dynamic_task_body = tb.Frame(active_col, style="CardInner.TFrame")
        self.dynamic_task_body.pack(fill="both", expand=True)
        self._active_task_settings_type = None
        self.render_task_settings()

        self.create_common_task_settings(common_col)

    # ─────────────────────────────────────────────────────────────────── #
    # Templates panel

    # ─────────────────────────────────────────────────────────────────── #
    # ─────────────────────────────────────────────────────────────────── #
    # Compatibility wrappers (kept so older call sites keep working)

    def create_control_buttons(self, parent):
        """Compatibility shim — controls now live in the hero banner."""
        return None

    def create_enhanced_settings(self, parent):
        """Compatibility shim — layout is now driven by create_tasks_tab."""
        self.create_task_selector(parent)
        self.dynamic_task_body = tb.Frame(parent, style="CardInner.TFrame")
        self.dynamic_task_body.pack(fill="x")
        self._active_task_settings_type = None
        self.render_task_settings()
        self.create_common_task_settings(parent)

    def create_task_selector(self, parent):
        """Compatibility shim — replaced by visual tiles in _build_task_type_panel."""
        self._build_task_type_panel(parent)

    def create_basic_settings(self, parent):
        self.create_common_task_settings(parent)

    def create_advanced_settings(self, parent):
        self.create_task_selector(parent)

    # ─────────────────────────────────────────────────────────────────── #
    # Dynamic task settings rendering

    def render_task_settings(self):
        """Render only the settings panel for the selected task type."""
        parent = getattr(self, "dynamic_task_body", None)
        if parent is None or not parent.winfo_exists():
            return

        task_type = self.task_type_var.get()
        if getattr(self, "_active_task_settings_type", None) == task_type and parent.winfo_children():
            self._sync_task_tile_selection()
            self._refresh_tasks_summary()
            return

        self._active_task_settings_type = task_type
        for child in parent.winfo_children():
            child.destroy()

        renderers = {
            "reels": self.create_reels_task_settings,
            "reg_account": self.create_register_task_settings,
            "scroll": self.create_scroll_task_settings,
            "test_feature": self.create_autoscroll_task_settings,
            # Legacy keys (kept so older state files don't crash)
            "autoscroll": self.create_autoscroll_task_settings,
            "likes": self.create_like_task_settings,
        }
        renderers.get(task_type, self.create_autoscroll_task_settings)(parent)
        parent.update_idletasks()
        self._sync_task_tile_selection()
        self._refresh_tasks_summary()

    def _add_active_task_accent(self, card):
        """Add a thin accent stripe at the top of an Active Task card body so
        the panel visibly recolors when the user switches tasks."""
        accent = self.TASK_TYPE_META.get(self.task_type_var.get(), ("", "", _TASKS_PRIMARY, ""))[2]
        tk.Frame(card, bg=accent, height=2).pack(fill="x", pady=(0, 8))

    def create_reels_task_settings(self, parent):
        card = self._create_card_section(
            parent,
            f"Active Task — {self._task_display_name()}",
            "Posting controls for page rotation and reels workflow.",
        )
        self._add_active_task_accent(card)
        grid = self._create_settings_grid(card)

        self._add_spinbox_setting(grid, 0, 0, "Post Pages", self.page_per_account, 1, 20)
        self._add_spinbox_setting(grid, 0, 1, "Max Reels", self.max_videos, 1, 50)
        self._add_toggle_setting(grid, 1, 0, "Use Content Queue", self.use_content_queue)
        self._add_toggle_setting(grid, 1, 1, "Scroll After Post", self.scroll_after_post)

    def create_register_task_settings(self, parent):
        card = self._create_card_section(
            parent,
            f"Active Task — {self._task_display_name()}",
            "Registration controls for account creation loops.",
        )
        self._add_active_task_accent(card)
        grid = self._create_settings_grid(card)

        self._add_spinbox_setting(grid, 0, 0, "Accounts per LD", self.accounts_per_ld, 1, 20)
        self._add_toggle_setting(grid, 0, 1, "Verify Account", self.verify_account)
        self._add_toggle_setting(grid, 1, 0, "Clear Cache", self.clear_cache)

    def create_scroll_task_settings(self, parent):
        card = self._create_card_section(
            parent,
            f"Active Task — {self._task_display_name()}",
            "Time-bounded browsing — runs for the duration set below, then stops.",
        )
        self._add_active_task_accent(card)
        grid = self._create_settings_grid(card)
        self._add_spinbox_setting(grid, 0, 0, "Task Duration (min)", self.task_duration, 1, 240)
        self._add_toggle_setting(grid, 0, 1, "Random Like Posts", self.random_like)
        tb.Label(
            grid,
            text="Other tasks finish on their own flow and ignore this value.",
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, columnspan=4, padx=10, pady=(0, 10), sticky="w")

    def create_autoscroll_task_settings(self, parent):
        card = self._create_card_section(
            parent,
            f"Active Task — {self._task_display_name()}",
            "This task ends automatically when its flow completes.",
        )
        self._add_active_task_accent(card)
        grid = self._create_settings_grid(card)
        self._add_empty_task_settings_note(grid)

    def create_like_task_settings(self, parent):
        card = self._create_card_section(
            parent,
            f"Active Task — {self._task_display_name()}",
            "Minimal controls for engagement tasks.",
        )
        self._add_active_task_accent(card)
        grid = self._create_settings_grid(card)
        self._add_empty_task_settings_note(grid)

    def create_common_task_settings(self, parent):
        card = self._create_card_section(
            parent,
            "Common Settings",
            "Shared runtime, launch, and shutdown controls.",
        )

        run_box = self._create_group_box(card, "RUN  TIMING", _TASKS_PRIMARY)
        run_grid = self._create_settings_grid(run_box)
        self._add_spinbox_setting(run_grid, 0, 0, "Parallel Devices", self.parallel_ld, 1, 10)
        self._add_spinbox_setting(run_grid, 1, 0, "Boot Delay (sec)", self.boot_delay, 1, 60)

        launch_box = self._create_group_box(card, "LAUNCH  OPTIONS", _TASKS_WARNING)
        launch_grid = self._create_settings_grid(launch_box)
        self._add_toggle_setting(launch_grid, 0, 0, "Start Devices Simultaneously", self.start_same_time)
        self._add_toggle_setting(launch_grid, 1, 0, "Auto Arrange LD", self.auto_arrange_ld)

        danger_box = self._create_group_box(card, "DANGER  ZONE", _TASKS_DANGER)
        danger_grid = self._create_settings_grid(danger_box)
        self._add_toggle_setting(
            danger_grid,
            0,
            0,
            "Auto Shutdown PC After Task",
            self.auto_shutdown_pc,
            bootstyle="danger-round-toggle",
        )

    def _create_group_box(self, parent, title, color):
        section = tk.Frame(
            parent,
            bg=self.palette["surface"],
            bd=0,
            padx=8,
            pady=6,
        )
        section.pack(fill="x", padx=8, pady=(8, 6))

        header = tk.Frame(section, bg=self.palette["surface"])
        header.pack(fill="x", pady=(0, 6))

        tk.Frame(header, bg=color, width=3, height=14).pack(side="left", padx=(0, 8))

        title_box = tk.Frame(
            header,
            bg=self.palette["surface"],
            highlightbackground=color,
            highlightthickness=1,
            bd=0,
            padx=8,
            pady=3,
        )
        title_box.pack(side="left")

        title_label = tk.Label(
            title_box,
            text=title,
            bg=self.palette["surface"],
            fg=color,
            font=(self.mono_font, 9, "bold"),
        )
        title_label.pack(side="left")
        title_label.configure(fg=color)

        content = tk.Frame(section, bg=self.palette["surface"], padx=12)
        content.pack(fill="x")
        return content

    def _add_section_header(self, parent, row, text, color=None):
        accent = color or _TASKS_PRIMARY
        bg = self.palette["surface"]
        wrap = tk.Frame(parent, bg=bg)
        wrap.grid(row=row, column=0, columnspan=4, padx=8, pady=(12, 4), sticky="ew")

        # Tiny colored bar on the left
        tk.Frame(wrap, bg=accent, width=3, height=14).pack(side="left", padx=(0, 8))
        label_box = tk.Frame(
            wrap,
            bg=bg,
            highlightbackground=accent,
            highlightthickness=1,
            bd=0,
            padx=8,
            pady=3,
        )
        label_box.pack(side="left", anchor="w")

        text_label = tk.Label(
            label_box,
            text=text,
            bg=bg,
            fg=accent,
            foreground=accent,
            activeforeground=accent,
            font=(self.mono_font, 9, "bold"),
        )
        text_label.pack(side="left", anchor="center")
        text_label.configure(fg=accent, foreground=accent)

        # Thin trailing line that fades into the section
        line = tk.Frame(wrap, bg=accent, height=1)
        line.pack(side="left", fill="x", expand=True, padx=(10, 0), pady=(7, 0))

    # ─────────────────────────────────────────────────────────────────── #
    # Helpers

    def _task_display_name(self, task_type=None):
        return self.TASK_TYPE_LABELS.get(task_type or self.task_type_var.get(), "Custom Task")

    def _create_settings_grid(self, parent):
        grid = tb.Frame(parent, style="CardInner.TFrame", padding=(6, 4))
        grid.pack(fill="x")
        for column in range(4):
            grid.grid_columnconfigure(column, weight=1 if column in (1, 3) else 0)
        return grid

    def _add_spinbox_setting(self, parent, row, column, label, variable, from_, to, width=8):
        label_column = column * 2
        input_column = label_column + 1

        tb.Label(parent, text=f"{label}", style="MetricLabel.TLabel").grid(
            row=row,
            column=label_column,
            padx=(8, 6),
            pady=8,
            sticky="w",
        )
        tb.Spinbox(
            parent,
            from_=from_,
            to=to,
            textvariable=variable,
            width=width,
        ).grid(row=row, column=input_column, padx=(0, 14), pady=8, sticky="w")

    def _add_toggle_setting(self, parent, row, column, text, variable, bootstyle="primary-round-toggle"):
        tb.Checkbutton(
            parent,
            text=text,
            variable=variable,
            bootstyle=bootstyle,
        ).grid(
            row=row,
            column=column * 2,
            columnspan=2,
            padx=8,
            pady=8,
            sticky="w",
        )

    def _add_empty_task_settings_note(self, parent):
        tb.Label(
            parent,
            text="No extra task-specific controls",
            style="CardItemTitle.TLabel",
        ).grid(row=0, column=0, columnspan=4, padx=10, pady=(10, 2), sticky="w")
        tb.Label(
            parent,
            text="This task uses the common run settings on the right.",
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, columnspan=4, padx=10, pady=(0, 10), sticky="w")

    # ─────────────────────────────────────────────────────────────────── #
    # Summary + status helpers

    def _bind_summary_traces(self):
        """Refresh hero summary chips when key vars change."""
        for var in (
            self.task_type_var,
            self.parallel_ld,
            self.task_duration,
        ):
            try:
                var.trace_add("write", lambda *_: self._refresh_tasks_summary())
            except Exception:
                pass

    _TASKS_STATUS_MAP = {
        "ready": ("Ready", "● READY", "#10B981"),
        "running": ("Running", "● RUNNING", _TASKS_PRIMARY),
        "paused": ("Paused", "● PAUSED", _TASKS_WARNING),
        "stopped": ("Stopped", "● STOPPED", _TASKS_DANGER),
    }

    def _refresh_tasks_summary(self):
        title_lbl = getattr(self, "_tasks_hero_title", None)
        if title_lbl is None:
            return

        # The big hero title takes the active task's accent so the page
        # visibly recolors when the user picks a different task tile.
        task_type = self.task_type_var.get()
        accent = self.TASK_TYPE_META.get(task_type, ("", "", _TASKS_PRIMARY, ""))[2]
        title_lbl.configure(text=self._task_display_name(), fg=accent)

        try:
            devices = int(self.parallel_ld.get())
            devices_text = f"{devices} devices"
        except Exception:
            devices_text = "— devices"

        if task_type == "scroll":
            try:
                mins = int(self.task_duration.get())
                ending_text = f"{mins} min run" if mins < 60 else f"{mins / 60:.1f}h run"
            except Exception:
                ending_text = "— run"
            ending_color = _TASKS_WARNING
        else:
            ending_text = "ends on flow"
            ending_color = "#10B981"

        # Status segment color follows the live status word.
        status_word = getattr(self, "_tasks_status_word", "Ready")
        status_color = {
            "Ready": "#10B981",
            "Running": _TASKS_PRIMARY,
            "Paused": _TASKS_WARNING,
            "Stopped": _TASKS_DANGER,
        }.get(status_word, "#10B981")

        if hasattr(self, "_hero_status_seg"):
            self._hero_status_seg.configure(text=status_word, fg=status_color)
        if hasattr(self, "_hero_devices_seg"):
            self._hero_devices_seg.configure(text=devices_text, fg=_TASKS_PRIMARY)
        if hasattr(self, "_hero_ending_seg"):
            self._hero_ending_seg.configure(text=ending_text, fg=ending_color)

    def set_tasks_status(self, status):
        """Update the hero status chip ('ready', 'running', 'paused', 'stopped')."""
        word, chip_text, color = self._TASKS_STATUS_MAP.get(
            str(status).lower(), ("Ready", "● READY", "#10B981")
        )
        self._tasks_status_word = word

        chip = getattr(self, "_tasks_status_chip", None)
        if chip is not None and chip.winfo_exists():
            chip.configure(text=chip_text, fg=color)

        self._refresh_tasks_summary()
