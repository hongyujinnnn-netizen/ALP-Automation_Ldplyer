import tkinter as tk
import ttkbootstrap as tb


class SettingsDialogMixin:
    def show_settings_dialog(self):
        dialog = getattr(self, "_settings_dialog", None)
        if dialog is not None and dialog.winfo_exists():
            dialog.focus()
            return

        P = self.palette
        dialog = tk.Toplevel(self.root)
        dialog.title("Control Settings")
        dialog.geometry("1040x700")
        dialog.minsize(1040, 700)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg=P["surface"])
        dialog.protocol("WM_DELETE_WINDOW", lambda: self._close_settings_dialog(dialog))
        self._settings_dialog = dialog

        parallel_var = tk.IntVar(value=self.parallel_ld.get())
        boot_delay_var = tk.IntVar(value=self.boot_delay.get())
        task_duration_var = tk.IntVar(value=self.task_duration.get())
        max_videos_var = tk.IntVar(value=self.max_videos.get())
        start_same_var = tk.BooleanVar(value=self.start_same_time.get())
        use_queue_var = tk.BooleanVar(value=self.use_content_queue.get())
        # Reuse the main app variable for blocked countries so changes are live.
        blocked_countries_var = getattr(self, "blocked_countries", tk.StringVar(value=""))

        shell = tk.Frame(dialog, bg=P["surface"], padx=18, pady=18)
        shell.pack(fill="both", expand=True)

        self._build_settings_shell(
            shell,
            P,
            dialog,
            parallel_var,
            boot_delay_var,
            task_duration_var,
            max_videos_var,
            start_same_var,
            use_queue_var,
        )

    def _build_settings_shell(
        self,
        parent,
        palette,
        dialog,
        parallel_var,
        boot_delay_var,
        task_duration_var,
        max_videos_var,
        start_same_var,
        use_queue_var,
    ):
        wrapper = tk.Frame(parent, bg=palette["border_alt"], padx=1, pady=1)
        wrapper.pack(fill="both", expand=True)

        container = tk.Frame(wrapper, bg=palette["surface"])
        container.pack(fill="both", expand=True)

        self._build_premium_header(
            container,
            palette,
            parallel_var,
            task_duration_var,
            use_queue_var,
        )

        body = tk.Frame(container, bg=palette["surface"])
        body.pack(fill="both", expand=True, padx=18, pady=(0, 14))

        sidebar = tk.Frame(body, bg=palette["surface_alt"], width=260)
        sidebar.pack(side="left", fill="y", padx=(0, 16))
        sidebar.pack_propagate(False)

        content = tk.Frame(body, bg=palette["surface"])
        content.pack(side="left", fill="both", expand=True)

        self._settings_nav_buttons = {}
        self._settings_pages = {}
        self._settings_overview_var = tk.StringVar()

        self._build_premium_sidebar(
            sidebar,
            palette,
            parallel_var,
            boot_delay_var,
            task_duration_var,
            max_videos_var,
            start_same_var,
            use_queue_var,
        )

        for key in ("general", "behavior", "profiles", "summary"):
            page = tk.Frame(content, bg=palette["surface"])
            page.place(relx=0, rely=0, relwidth=1, relheight=1)
            self._settings_pages[key] = page

        self._build_general_page(
            self._settings_pages["general"],
            palette,
            parallel_var,
            boot_delay_var,
            task_duration_var,
            max_videos_var,
        )
        self._build_behavior_page(
            self._settings_pages["behavior"],
            palette,
            start_same_var,
            use_queue_var,
            parallel_var,
            boot_delay_var,
            task_duration_var,
            max_videos_var,
        )
        self._build_profiles_page(
            self._settings_pages["profiles"],
            palette,
            parallel_var,
            boot_delay_var,
            task_duration_var,
            max_videos_var,
            start_same_var,
            use_queue_var,
        )
        self._build_summary_page(
            self._settings_pages["summary"],
            palette,
            parallel_var,
            boot_delay_var,
            task_duration_var,
            max_videos_var,
            start_same_var,
            use_queue_var,
        )

        self._build_premium_footer(
            container,
            palette,
            dialog,
            parallel_var,
            boot_delay_var,
            task_duration_var,
            max_videos_var,
            start_same_var,
            use_queue_var,
        )

        self._bind_summary_refresh(
            parallel_var,
            boot_delay_var,
            task_duration_var,
            max_videos_var,
            start_same_var,
            use_queue_var,
        )
        self._open_settings_page("general")

    def _build_premium_header(self, parent, palette, parallel_var, task_duration_var, use_queue_var):
        header = tk.Frame(parent, bg=palette["surface"], pady=18, padx=18)
        header.pack(fill="x")

        left = tk.Frame(header, bg=palette["surface"])
        left.pack(side="left", fill="x", expand=True)

        badge_wrap = tk.Frame(left, bg=palette["surface"])
        badge_wrap.pack(anchor="w")

        icon = tk.Frame(badge_wrap, bg="#0B1B2B", width=68, height=68, highlightthickness=1, highlightbackground=palette["border_alt"])
        icon.pack(side="left")
        icon.pack_propagate(False)
        tk.Label(icon, text="CTRL", bg="#0B1B2B", fg=palette["primary"], font=(self.display_font, 12)).pack(expand=True)

        title_wrap = tk.Frame(badge_wrap, bg=palette["surface"], padx=14)
        title_wrap.pack(side="left", fill="x", expand=True)
        tk.Label(title_wrap, text="Control Settings", bg=palette["surface"], fg=palette["text"], font=(self.display_font, 20)).pack(anchor="w")
        tk.Label(
            title_wrap,
            text="Premium control center for launch pacing, behavior, presets, and review.",
            bg=palette["surface"],
            fg=palette["muted"],
            font=(self.mono_font, 9),
        ).pack(anchor="w", pady=(4, 0))

        status = tk.Frame(header, bg=palette["surface_alt"], padx=14, pady=10, highlightthickness=1, highlightbackground=palette["border"])
        status.pack(side="right")
        tk.Label(status, text="ACTIVE MODE", bg=palette["surface_alt"], fg=palette["muted"], font=(self.mono_font, 8)).pack(anchor="e")
        self._header_status_var = tk.StringVar(value="Balanced")
        tk.Label(status, textvariable=self._header_status_var, bg=palette["surface_alt"], fg=palette["primary"], font=(self.display_font, 12)).pack(anchor="e")
        self._header_meta_var = tk.StringVar(value="Ready • Queue On")
        tk.Label(status, textvariable=self._header_meta_var, bg=palette["surface_alt"], fg=palette["text"], font=(self.mono_font, 8)).pack(anchor="e", pady=(2, 0))

    def _build_premium_sidebar(
        self,
        parent,
        palette,
        parallel_var,
        boot_delay_var,
        task_duration_var,
        max_videos_var,
        start_same_var,
        use_queue_var,
    ):
        inner = tk.Frame(parent, bg=palette["surface_alt"], padx=16, pady=18)
        inner.pack(fill="both", expand=True)

        tk.Label(inner, text="SETTINGS MENU", bg=palette["surface_alt"], fg=palette["muted"], font=(self.mono_font, 8)).pack(anchor="w")
        tk.Label(
            inner,
            textvariable=self._settings_overview_var,
            bg=palette["surface_alt"],
            fg=palette["primary"],
            justify="left",
            wraplength=210,
            font=(self.mono_font, 9),
        ).pack(anchor="w", pady=(8, 18))

        menu_items = [
            ("general", "⚙", "General", "Core launch and session values"),
            ("behavior", "⇄", "Behavior", "Queue and dispatch options"),
            ("profiles", "◈", "Profiles", "Fast preset modes"),
            ("summary", "▣", "Summary", "Review current control state"),
        ]

        for key, icon, title, desc in menu_items:
            outer = tk.Frame(inner, bg=palette["surface_alt"])
            outer.pack(fill="x", pady=5)

            accent = tk.Frame(outer, bg=palette["surface_alt"], width=4)
            accent.pack(side="left", fill="y")

            btn = tk.Frame(outer, bg=palette["surface_alt"], padx=12, pady=10, cursor="hand2")
            btn.pack(side="left", fill="x", expand=True)

            top = tk.Frame(btn, bg=palette["surface_alt"])
            top.pack(fill="x")
            tk.Label(top, text=icon, bg=palette["surface_alt"], fg=palette["primary"], font=(self.display_font, 11)).pack(side="left")
            tk.Label(top, text=title, bg=palette["surface_alt"], fg=palette["text"], font=(self.display_font, 11)).pack(side="left", padx=(8, 0))
            tk.Label(btn, text=desc, bg=palette["surface_alt"], fg=palette["muted"], font=(self.mono_font, 8), justify="left").pack(anchor="w", pady=(4, 0))

            for widget in (outer, accent, btn, top):
                widget.bind("<Button-1>", lambda e, page=key: self._open_settings_page(page))
            for child in btn.winfo_children():
                child.bind("<Button-1>", lambda e, page=key: self._open_settings_page(page))
            for child in top.winfo_children():
                child.bind("<Button-1>", lambda e, page=key: self._open_settings_page(page))

            self._settings_nav_buttons[key] = (outer, accent, btn)

        tip = tk.Frame(inner, bg="#0B1B2B", padx=12, pady=12, highlightthickness=1, highlightbackground=palette["border_alt"])
        tip.pack(fill="x", side="bottom", pady=(18, 0))
        tk.Label(tip, text="RECOMMENDATION", bg="#0B1B2B", fg=palette["primary"], font=(self.mono_font, 8)).pack(anchor="w")
        tk.Label(
            tip,
            text="Use Balanced profile first, then adjust only one or two values.",
            bg="#0B1B2B",
            fg=palette["text"],
            wraplength=210,
            justify="left",
            font=(self.mono_font, 8),
        ).pack(anchor="w", pady=(6, 0))

    def _page_heading(self, parent, palette, eyebrow, title, subtitle):
        wrap = tk.Frame(parent, bg=palette["surface"])
        wrap.pack(fill="x", pady=(0, 14))
        tk.Label(wrap, text=eyebrow, bg=palette["surface"], fg=palette["primary"], font=(self.mono_font, 8)).pack(anchor="w")
        tk.Label(wrap, text=title, bg=palette["surface"], fg=palette["text"], font=(self.display_font, 18)).pack(anchor="w", pady=(4, 0))
        tk.Label(wrap, text=subtitle, bg=palette["surface"], fg=palette["muted"], font=(self.mono_font, 9)).pack(anchor="w", pady=(4, 0))

    def _premium_card(self, parent, palette, title, subtitle=None, padding=16):
        outer = tk.Frame(parent, bg=palette["border"], padx=1, pady=1)
        card = tk.Frame(outer, bg=palette["surface_alt"], padx=padding, pady=padding)
        card.pack(fill="both", expand=True)
        if title:
            tk.Label(card, text=title, bg=palette["surface_alt"], fg=palette["text"], font=(self.display_font, 12)).pack(anchor="w")
        if subtitle:
            tk.Label(card, text=subtitle, bg=palette["surface_alt"], fg=palette["muted"], font=(self.mono_font, 8)).pack(anchor="w", pady=(4, 10))
        return outer, card

    def _metric_card(self, parent, palette, title, variable, unit, help_text, step=1, min_value=0):
        outer, card = self._premium_card(parent, palette, title, help_text)
        outer.pack(side="left", fill="both", expand=True, padx=6)

        value_row = tk.Frame(card, bg=palette["surface_alt"])
        value_row.pack(fill="x", pady=(6, 0))

        minus = tk.Button(value_row, text="−", relief="flat", bg=palette["surface"], fg=palette["text"], activebackground=palette["border_alt"], activeforeground=palette["text"], font=(self.display_font, 14), width=3, cursor="hand2", command=lambda: variable.set(max(min_value, variable.get() - step)))
        minus.pack(side="left")

        center = tk.Frame(value_row, bg=palette["surface_alt"])
        center.pack(side="left", fill="both", expand=True)
        tk.Label(center, textvariable=variable, bg=palette["surface_alt"], fg=palette["primary"], font=(self.display_font, 24)).pack()
        tk.Label(center, text=unit, bg=palette["surface_alt"], fg=palette["muted"], font=(self.mono_font, 8)).pack()

        plus = tk.Button(value_row, text="+", relief="flat", bg=palette["surface"], fg=palette["text"], activebackground=palette["border_alt"], activeforeground=palette["text"], font=(self.display_font, 13), width=3, cursor="hand2", command=lambda: variable.set(variable.get() + step))
        plus.pack(side="right")

        return outer

    def _build_general_page(self, parent, palette, parallel_var, boot_delay_var, task_duration_var, max_videos_var):
        self._page_heading(parent, palette, "GENERAL", "Launch & Session Controls", "Tune your main runtime values with cleaner, more readable controls.")

        grid1 = tk.Frame(parent, bg=palette["surface"])
        grid1.pack(fill="x", pady=(0, 12))
        self._metric_card(grid1, palette, "Parallel LDs", parallel_var, "active devices", "Recommended: 1–2 for mid-range PCs.", min_value=1)
        self._metric_card(grid1, palette, "Boot Delay", boot_delay_var, "seconds", "Increase if emulator startup is unstable.", min_value=1)

        grid2 = tk.Frame(parent, bg=palette["surface"])
        grid2.pack(fill="x", pady=(0, 12))
        self._metric_card(grid2, palette, "Task Duration", task_duration_var, "minutes", "Target session runtime per account.", min_value=1)
        self._metric_card(grid2, palette, "Max Reels", max_videos_var, "per cycle", "Use lower values for a safer behavior pattern.", min_value=1)

        outer, notes = self._premium_card(parent, palette, "Performance Notes", "Quick guidance based on current setup.")
        outer.pack(fill="x", pady=(2, 0))
        self._info_row(notes, palette, "System load", "Higher parallel counts increase CPU, RAM, and ADB contention.")
        self._info_row(notes, palette, "Safer setup", "Balanced pacing usually gives more stable startup and fewer connection issues.")
        self._info_row(notes, palette, "Best practice", "Change one value at a time, then test the workflow before raising throughput.")

    def _build_behavior_page(self, parent, palette, start_same_var, use_queue_var, parallel_var, boot_delay_var, task_duration_var, max_videos_var):
        self._page_heading(parent, palette, "BEHAVIOR", "Dispatch & Queue Logic", "Configure how sessions start and how content is delivered during execution.")

        self._toggle_feature_card(parent, palette, "Start at Same Time", "Launch all selected instances together for faster startup on stronger machines.", start_same_var)
        self._toggle_feature_card(parent, palette, "Use Content Queue", "Enable a safer and more organized content delivery flow during the session.", use_queue_var)

        # Country / IP guard configuration
        outer, card = self._premium_card(
            parent,
            palette,
            "IP / Country Guard",
            "Block automation when your public IP is detected in selected countries.",
        )
        outer.pack(fill="x", pady=(12, 0))

        row = tk.Frame(card, bg=palette["surface_alt"])
        row.pack(fill="x", pady=(8, 0))

        tk.Label(
            row,
            text="Blocked Countries (ISO codes)",
            bg=palette["surface_alt"],
            fg=palette["text"],
            font=(self.mono_font, 8),
        ).pack(anchor="w")

        hint = (
            "Examples: US, KH, CN, TH, VN, PH, ID, MY, LA, MM\n"
            "Automation will not start if your public IP is in any blocked country."
        )
        tk.Label(
            card,
            text=hint,
            bg=palette["surface_alt"],
            fg=palette["muted"],
            justify="left",
            wraplength=520,
            font=(self.mono_font, 8),
        ).pack(anchor="w", pady=(2, 8))

        # Use the main app's StringVar so changes are saved directly.
        entry = tk.Entry(
            card,
            textvariable=getattr(self, "blocked_countries", None),
            bg=palette["surface"],
            fg=palette["text"],
            insertbackground=palette["text"],
        )
        entry.pack(fill="x")

        outer, notes = self._premium_card(parent, palette, "Operational Notes", "Behavior settings should match your hardware and launch pacing.")
        outer.pack(fill="x", pady=(12, 0))
        self._info_row(notes, palette, "Parallel impact", f"Current parallel load: {parallel_var.get()} device(s).")
        self._info_row(notes, palette, "Boot pacing", f"Current startup delay: {boot_delay_var.get()} second(s).")
        self._info_row(notes, palette, "Session target", f"{task_duration_var.get()} min / {max_videos_var.get()} reels configured.")

    def _toggle_feature_card(self, parent, palette, title, description, variable):
        outer = tk.Frame(parent, bg=palette["border"], padx=1, pady=1)
        outer.pack(fill="x", pady=6)
        card = tk.Frame(outer, bg=palette["surface_alt"], padx=16, pady=14)
        card.pack(fill="x")

        left = tk.Frame(card, bg=palette["surface_alt"])
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text=title, bg=palette["surface_alt"], fg=palette["text"], font=(self.display_font, 12)).pack(anchor="w")
        tk.Label(left, text=description, bg=palette["surface_alt"], fg=palette["muted"], justify="left", wraplength=520, font=(self.mono_font, 8)).pack(anchor="w", pady=(5, 0))

        right = tk.Frame(card, bg=palette["surface_alt"])
        right.pack(side="right")

        state_var = tk.StringVar()
        state = tk.Label(right, textvariable=state_var, bg=palette["surface_alt"], fg=palette["primary"], font=(self.mono_font, 8))
        state.pack(anchor="e", pady=(0, 6))

        switch_shell = tk.Frame(right, bg=palette["surface"], width=64, height=30, cursor="hand2")
        switch_shell.pack(anchor="e")
        switch_shell.pack_propagate(False)
        knob = tk.Frame(switch_shell, bg=palette["text"], width=24, height=24)

        def redraw(*_):
            enabled = bool(variable.get())
            state_var.set("ENABLED" if enabled else "DISABLED")
            card.config(bg="#112132" if enabled else palette["surface_alt"])
            left.config(bg="#112132" if enabled else palette["surface_alt"])
            right.config(bg="#112132" if enabled else palette["surface_alt"])
            state.config(bg="#112132" if enabled else palette["surface_alt"], fg=palette["primary"] if enabled else palette["muted"])
            switch_shell.config(bg=palette["primary"] if enabled else palette["surface"])
            knob.place(x=36 if enabled else 4, y=3)

        def toggle(_event=None):
            variable.set(not variable.get())

        for widget in (outer, card, left, right, state, switch_shell, knob):
            widget.bind("<Button-1>", toggle)
        for child in left.winfo_children():
            child.bind("<Button-1>", toggle)

        variable.trace_add("write", redraw)
        redraw()

    def _build_profiles_page(self, parent, palette, parallel_var, boot_delay_var, task_duration_var, max_videos_var, start_same_var, use_queue_var):
        self._page_heading(parent, palette, "PROFILES", "Preset Profiles", "Apply a starter preset, then fine-tune individual values if needed.")

        profiles = [
            ("Safe", "#38BDF8", "Low load and safer startup pacing for weaker hardware.", (1, 12, 10, 1, False, True), "Stable first"),
            ("Balanced", palette["primary"], "Best default profile for most daily usage.", (2, 8, 15, 2, False, True), "Recommended"),
            ("Aggressive", "#F59E0B", "Higher throughput for stronger hardware and faster cycles.", (4, 3, 25, 5, True, True), "High load"),
        ]

        for name, color, desc, values, tag in profiles:
            outer = tk.Frame(parent, bg=palette["border"], padx=1, pady=1)
            outer.pack(fill="x", pady=6)
            card = tk.Frame(outer, bg=palette["surface_alt"])
            card.pack(fill="x")

            accent = tk.Frame(card, bg=color, width=6)
            accent.pack(side="left", fill="y")

            content = tk.Frame(card, bg=palette["surface_alt"], padx=14, pady=14)
            content.pack(side="left", fill="both", expand=True)

            top = tk.Frame(content, bg=palette["surface_alt"])
            top.pack(fill="x")
            tk.Label(top, text=name, bg=palette["surface_alt"], fg=color, font=(self.display_font, 13)).pack(side="left")
            tk.Label(top, text=tag, bg=palette["surface"], fg=color, font=(self.mono_font, 8), padx=8, pady=3).pack(side="left", padx=(10, 0))
            tk.Button(
                top,
                text="Apply",
                relief="flat",
                bg=palette["surface"],
                fg=color,
                activebackground=palette["border_alt"],
                activeforeground=color,
                font=(self.mono_font, 9),
                padx=14,
                pady=6,
                cursor="hand2",
                command=lambda vals=values, profile_name=name: self._apply_settings_profile(
                    vals,
                    profile_name,
                    parallel_var,
                    boot_delay_var,
                    task_duration_var,
                    max_videos_var,
                    start_same_var,
                    use_queue_var,
                ),
            ).pack(side="right")

            tk.Label(content, text=desc, bg=palette["surface_alt"], fg=palette["muted"], font=(self.mono_font, 8), justify="left").pack(anchor="w", pady=(6, 10))

            stats = tk.Frame(content, bg=palette["surface_alt"])
            stats.pack(fill="x")
            labels = [
                f"LDs {values[0]}",
                f"Delay {values[1]}s",
                f"Duration {values[2]}m",
                f"Reels {values[3]}",
                "Sync On" if values[4] else "Sync Off",
                "Queue On" if values[5] else "Queue Off",
            ]
            for text in labels:
                tk.Label(stats, text=text, bg=palette["surface"], fg=palette["text"], font=(self.mono_font, 8), padx=8, pady=4).pack(side="left", padx=(0, 6))

    def _build_summary_page(self, parent, palette, parallel_var, boot_delay_var, task_duration_var, max_videos_var, start_same_var, use_queue_var):
        self._page_heading(parent, palette, "SUMMARY", "Configuration Review", "Read the current setup before saving changes.")

        row = tk.Frame(parent, bg=palette["surface"])
        row.pack(fill="x", pady=(0, 12))

        self._summary_stat_card(row, palette, "Devices", parallel_var, "parallel")
        self._summary_stat_card(row, palette, "Startup", boot_delay_var, "sec")
        self._summary_stat_card(row, palette, "Session", task_duration_var, "min")
        self._summary_stat_card(row, palette, "Reels", max_videos_var, "items")

        outer, detail = self._premium_card(parent, palette, "Live Readout", "Human-readable review of the active configuration.")
        outer.pack(fill="x", pady=(0, 12))
        self._summary_text_var = tk.StringVar()
        self._summary_detail_var = tk.StringVar()
        tk.Label(detail, textvariable=self._summary_text_var, bg=palette["surface_alt"], fg=palette["text"], justify="left", wraplength=640, font=(self.mono_font, 9)).pack(anchor="w")
        tk.Label(detail, textvariable=self._summary_detail_var, bg=palette["surface_alt"], fg=palette["muted"], justify="left", wraplength=640, font=(self.mono_font, 8)).pack(anchor="w", pady=(8, 0))

        outer2, impact = self._premium_card(parent, palette, "Impact Estimate", "Quick interpretation of the current setup.")
        outer2.pack(fill="x")
        self._impact_var = tk.StringVar()
        tk.Label(impact, textvariable=self._impact_var, bg=palette["surface_alt"], fg=palette["primary"], justify="left", wraplength=640, font=(self.mono_font, 9)).pack(anchor="w")

    def _summary_stat_card(self, parent, palette, title, variable, unit):
        outer, card = self._premium_card(parent, palette, title)
        outer.pack(side="left", fill="both", expand=True, padx=6)
        tk.Label(card, textvariable=variable, bg=palette["surface_alt"], fg=palette["primary"], font=(self.display_font, 22)).pack(anchor="w", pady=(6, 0))
        tk.Label(card, text=unit, bg=palette["surface_alt"], fg=palette["muted"], font=(self.mono_font, 8)).pack(anchor="w")

    def _build_premium_footer(self, parent, palette, dialog, parallel_var, boot_delay_var, task_duration_var, max_videos_var, start_same_var, use_queue_var):
        footer = tk.Frame(parent, bg=palette["surface_alt"], padx=18, pady=14, highlightthickness=1, highlightbackground=palette["border_alt"])
        footer.pack(fill="x")

        left = tk.Frame(footer, bg=palette["surface_alt"])
        left.pack(side="left", fill="x", expand=True)
        self._footer_state_var = tk.StringVar(value="Changes are local until saved.")
        tk.Label(left, textvariable=self._footer_state_var, bg=palette["surface_alt"], fg=palette["muted"], font=(self.mono_font, 9)).pack(anchor="w")

        right = tk.Frame(footer, bg=palette["surface_alt"])
        right.pack(side="right")

        self._footer_button(right, palette, "Cancel", palette["muted"], palette["surface"], lambda: self._close_settings_dialog(dialog))
        self._footer_button(
            right,
            palette,
            "Reset Defaults",
            "#F59E0B",
            palette["surface"],
            lambda: self._apply_settings_profile((2, 8, 15, 2, False, True), "Balanced", parallel_var, boot_delay_var, task_duration_var, max_videos_var, start_same_var, use_queue_var),
        )
        self._footer_button(
            right,
            palette,
            "Save Settings",
            palette["surface"],
            palette["primary"],
            lambda: self._save_settings_from_dialog(dialog, parallel_var, boot_delay_var, task_duration_var, max_videos_var, start_same_var, use_queue_var),
            filled=True,
        )

    def _footer_button(self, parent, palette, text, fg, bg, command, filled=False):
        wrap = tk.Frame(parent, bg=bg, padx=1, pady=1)
        wrap.pack(side="right", padx=4)
        tk.Button(
            wrap,
            text=text,
            relief="flat",
            bg=bg if filled else palette["surface_alt"],
            fg=fg,
            activebackground=palette["border_alt"],
            activeforeground=fg,
            font=(self.mono_font, 9),
            padx=14,
            pady=7,
            cursor="hand2",
            command=command,
        ).pack()

    def _bind_summary_refresh(self, parallel_var, boot_delay_var, task_duration_var, max_videos_var, start_same_var, use_queue_var):
        def refresh(*_):
            profile = self._detect_profile(parallel_var.get(), boot_delay_var.get(), task_duration_var.get(), max_videos_var.get(), bool(start_same_var.get()), bool(use_queue_var.get()))
            self._header_status_var.set(profile)
            self._header_meta_var.set(f"{parallel_var.get()} LD • {'Queue On' if use_queue_var.get() else 'Queue Off'}")
            self._settings_overview_var.set(
                f"{parallel_var.get()} LD • {boot_delay_var.get()}s boot\n{task_duration_var.get()} min session • {max_videos_var.get()} reels"
            )
            if hasattr(self, "_summary_text_var"):
                self._summary_text_var.set(
                    f"Profile: {profile}\nParallel launch: {parallel_var.get()} device(s)\nBoot delay: {boot_delay_var.get()} second(s)\nTask duration: {task_duration_var.get()} minute(s)\nMax reels: {max_videos_var.get()} item(s)\nStart same time: {'Enabled' if start_same_var.get() else 'Disabled'}\nUse queue: {'Enabled' if use_queue_var.get() else 'Disabled'}"
                )
            if hasattr(self, "_summary_detail_var"):
                self._summary_detail_var.set(
                    "Balanced pacing is recommended for most systems. Aggressive values increase throughput but also raise system load and startup risk."
                )
            if hasattr(self, "_impact_var"):
                load = "High" if parallel_var.get() >= 4 or start_same_var.get() else "Medium" if parallel_var.get() >= 2 else "Low"
                self._impact_var.set(f"Estimated load: {load}. Keep queue enabled for a cleaner execution flow.")
            if hasattr(self, "_footer_state_var"):
                self._footer_state_var.set(f"Current profile: {profile}. Review summary before saving.")

        for var in (parallel_var, boot_delay_var, task_duration_var, max_videos_var, start_same_var, use_queue_var):
            var.trace_add("write", refresh)
        refresh()

    def _detect_profile(self, parallel, delay, duration, reels, start_same, use_queue):
        profiles = {
            "Safe": (1, 12, 10, 1, False, True),
            "Balanced": (2, 8, 15, 2, False, True),
            "Aggressive": (4, 3, 25, 5, True, True),
        }
        current = (parallel, delay, duration, reels, start_same, use_queue)
        for name, values in profiles.items():
            if current == values:
                return name
        return "Custom"

    def _info_row(self, parent, palette, label, text):
        row = tk.Frame(parent, bg=palette["surface_alt"])
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label.upper(), bg=palette["surface_alt"], fg=palette["primary"], font=(self.mono_font, 8), width=15, anchor="w").pack(side="left")
        tk.Label(row, text=text, bg=palette["surface_alt"], fg=palette["text"], font=(self.mono_font, 8), anchor="w", justify="left", wraplength=520).pack(side="left", fill="x", expand=True)

    def _open_settings_page(self, key):
        for name, page in getattr(self, "_settings_pages", {}).items():
            if name == key:
                page.lift()
        for name, widgets in getattr(self, "_settings_nav_buttons", {}).items():
            outer, accent, btn = widgets
            active = name == key
            outer.config(bg=self.palette["border_alt"] if active else self.palette["surface_alt"])
            accent.config(bg=self.palette["primary"] if active else self.palette["surface_alt"])
            btn.config(bg="#112132" if active else self.palette["surface_alt"])
            for child in btn.winfo_children():
                try:
                    child.config(bg="#112132" if active else self.palette["surface_alt"])
                except Exception:
                    pass
                for sub in getattr(child, "winfo_children", lambda: [])():
                    try:
                        sub.config(bg="#112132" if active else self.palette["surface_alt"])
                    except Exception:
                        pass

    def _apply_settings_profile(self, values, profile_name, parallel_var, boot_delay_var, task_duration_var, max_videos_var, start_same_var, use_queue_var):
        parallel, delay, duration, reels, start_same, use_queue = values
        parallel_var.set(parallel)
        boot_delay_var.set(delay)
        task_duration_var.set(duration)
        max_videos_var.set(reels)
        start_same_var.set(start_same)
        use_queue_var.set(use_queue)
        if hasattr(self, "_footer_state_var"):
            self._footer_state_var.set(f"Applied profile: {profile_name}.")

    def _save_settings_from_dialog(self, dialog, parallel_var, boot_delay_var, task_duration_var, max_videos_var, start_same_var, use_queue_var):
        self.parallel_ld.set(parallel_var.get())
        self.boot_delay.set(boot_delay_var.get())
        self.task_duration.set(task_duration_var.get())
        self.max_videos.set(max_videos_var.get())
        self.start_same_time.set(start_same_var.get())
        self.use_content_queue.set(use_queue_var.get())
        if hasattr(self, "save_settings"):
            try:
                self.save_settings()
            except Exception:
                pass
        self._close_settings_dialog(dialog)

    def _close_settings_dialog(self, dialog):
        current = getattr(self, "_settings_dialog", None)
        if current is dialog:
            self._settings_dialog = None
        try:
            if dialog.winfo_exists():
                try:
                    dialog.grab_release()
                except Exception:
                    pass
                dialog.destroy()
        except Exception:
            pass
