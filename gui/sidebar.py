import tkinter as tk
import ttkbootstrap as tb

from gui.components.status import StatusPill


class SidebarMixin:
    def create_sidebar(self, parent):
        spacing = getattr(getattr(self, "appearance", None), "spacing", {}) or {}
        sidebar_shell = tb.Frame(
            parent,
            style="Shadow.TFrame",
            width=int(spacing.get("sidebar_width", 236)),
            padding=(0, 0, 1, 0),
        )
        sidebar_shell.pack(side="left", fill="y")
        sidebar_shell.pack_propagate(False)

        sidebar = tb.Frame(sidebar_shell, style="Sidebar.TFrame", padding=(14, 14, 14, 10))
        sidebar.pack(fill="both", expand=True)

        logo = tb.Frame(sidebar, style="Sidebar.TFrame")
        logo.pack(fill="x", pady=(0, 14))
        tb.Label(logo, text="LDPlayer", style="SidebarTitle.TLabel").pack(anchor="w")
        tb.Label(logo, text="Manager v2.0", style="SidebarSub.TLabel").pack(anchor="w")

        self._nav_rows = {}
        nav_items = [
            ("analytics", "Analytics", lambda: self.notebook.select(0), "CONTROL", ""),
            ("dashboard", "Dashboard", self.show_dashboard, "CONTROL", ""),
            ("devices", "Devices", self._focus_devices, "CONTROL", "0"),
            ("automation", "Automation", lambda: self.notebook.select(3), "CONTROL", ""),
            ("accounts", "Accounts", self.show_account_manager, "CONTROL", ""),
            ("queue", "Task Queue", lambda: self.notebook.select(6), "CONTROL", "0"),
            ("schedule", "Scheduler", lambda: self.notebook.select(5), "MANAGE", ""),
            ("backups", "Backups", self.create_backup, "MANAGE", ""),
            ("logs", "Logs", lambda: self.notebook.select(7), "SYSTEM", ""),
            ("settings", "Settings", self.show_settings_dialog, "SYSTEM", ""),
            ("adb_tools", "ADB Tools", self.show_adb_tools, "SYSTEM", ""),
        ]

        current_section = None

        def _make_nav_row(parent_widget, key, text, badge_text, command):
            row = tk.Frame(parent_widget, bg=self.palette["surface"], height=max(30, int(spacing.get("tree_row_height", 28)) + 6))
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)

            accent = tk.Frame(row, width=3, bg=self.palette["primary"])
            accent.pack(side="left", fill="y")
            accent.pack_forget()

            btn = tk.Button(
                row,
                text=f"  {text}",
                anchor="w",
                relief="flat",
                bg=self.palette["surface"],
                fg=self.palette["muted"],
                activebackground=self.palette["surface_alt"],
                activeforeground=self.palette["text"],
                font=(self.display_font, 10),
                cursor="hand2",
                command=lambda k=key, c=command: self._on_sidebar_nav(k, c),
            )
            btn.pack(side="left", fill="both", expand=True)

            badge = tk.Label(
                row,
                text=badge_text,
                bg=self.palette["surface"],
                fg=self.palette["muted"],
                font=(self.mono_font, 9),
                padx=8,
            )
            badge.pack(side="right", padx=(6, 4))

            self._nav_rows[key] = {"row": row, "btn": btn, "accent": accent, "badge": badge}

            def _pointer_inside_row(target_row):
                try:
                    widget = target_row.winfo_containing(target_row.winfo_pointerx(), target_row.winfo_pointery())
                    while widget is not None:
                        if widget is target_row:
                            return True
                        widget = widget.master
                except Exception:
                    pass
                return False

            def _hover_in(_event=None, nav_key=key):
                if getattr(self, "_active_sidebar_key", None) != nav_key:
                    self._animate_nav_hover(nav_key, hover_in=True)

            def _hover_out(_event=None, nav_key=key):
                if getattr(self, "_active_sidebar_key", None) != nav_key:
                    parts = getattr(self, "_nav_rows", {}).get(nav_key, {})
                    if parts.get("row") is not None and _pointer_inside_row(parts["row"]):
                        return
                    self._animate_nav_hover(nav_key, hover_in=False)

            for widget in (row, btn, badge, accent):
                widget.bind("<Enter>", _hover_in, add="+")
                widget.bind("<Leave>", _hover_out, add="+")

        for key, text, command, section, badge_text in nav_items:
            if section != current_section:
                current_section = section
                tb.Label(sidebar, text=section, style="SidebarSection.TLabel").pack(anchor="w", pady=(8, 2))
            _make_nav_row(sidebar, key, text, badge_text, command)

        footer = tb.Frame(sidebar, style="Sidebar.TFrame")
        footer.pack(side="bottom", fill="x", pady=(8, 0))
        self.sidebar_status_pill = StatusPill(
            footer,
            "Waiting",
            palette=self.palette,
            text="ADB: checking...",
            font=(self.display_font, 9),
            pady=4,
        )
        self.sidebar_status_pill.pack(fill="x")

    def _focus_devices(self):
        if hasattr(self, "notebook"):
            self.notebook.select(2)
        if hasattr(self, "_render_devices_page"):
            self._render_devices_page()
        if hasattr(self, "devices_tree"):
            children = self.devices_tree.get_children()
            if children:
                self.devices_tree.selection_set(children[0])
                self.devices_tree.focus(children[0])
                self._update_device_focus_card()
        if hasattr(self, "_top_tab_buttons"):
            for label, btn in self._top_tab_buttons.items():
                btn.configure(bootstyle="info" if label == "Devices" else "secondary-link")

    def _animate_nav_hover(self, key, hover_in: bool):
        parts = getattr(self, "_nav_rows", {}).get(key)
        if not parts or getattr(self, "_active_sidebar_key", None) == key:
            return

        if not hasattr(self, "_nav_anim_tokens"):
            self._nav_anim_tokens = {}

        token = self._nav_anim_tokens.pop(key, None)
        if token is not None:
            try:
                self.root.after_cancel(token)
            except Exception:
                pass

        surface = self.palette["surface"]
        hover_bg = self.palette.get("hover_bg", self.palette["surface_alt"])
        muted = self.palette["muted"]
        text = self.palette["text"]

        bg_from = surface if hover_in else hover_bg
        bg_to = hover_bg if hover_in else surface
        fg_from = muted if hover_in else text
        fg_to = text if hover_in else muted
        frames = 6
        delay_ms = 16

        def _hex_to_rgb(value):
            value = str(value or "#000000").strip()
            if value.startswith("#"):
                value = value[1:]
            if len(value) == 3:
                value = "".join(ch * 2 for ch in value)
            try:
                return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
            except Exception:
                return (0, 0, 0)

        def _lerp_hex(start, end, progress):
            start_rgb = _hex_to_rgb(start)
            end_rgb = _hex_to_rgb(end)
            rgb = tuple(
                round(start_rgb[index] + (end_rgb[index] - start_rgb[index]) * progress)
                for index in range(3)
            )
            return "#{:02x}{:02x}{:02x}".format(*rgb)

        def _apply_colors(bg, fg):
            parts["row"].config(bg=bg)
            parts["btn"].config(bg=bg, fg=fg, activebackground=bg, activeforeground=fg)
            parts["badge"].config(bg=bg, fg=fg)

        if hover_in:
            parts["accent"].config(bg=self.palette["primary"])
            try:
                parts["accent"].pack(side="left", fill="y", before=parts["btn"])
            except Exception:
                parts["accent"].pack(side="left", fill="y")

        def _step(frame=0):
            if getattr(self, "_active_sidebar_key", None) == key:
                self._nav_anim_tokens.pop(key, None)
                return

            progress = min(1.0, frame / frames)
            _apply_colors(_lerp_hex(bg_from, bg_to, progress), _lerp_hex(fg_from, fg_to, progress))

            if frame >= frames:
                self._nav_anim_tokens.pop(key, None)
                if not hover_in and getattr(self, "_active_sidebar_key", None) != key:
                    parts["accent"].pack_forget()
                return

            self._nav_anim_tokens[key] = self.root.after(delay_ms, lambda: _step(frame + 1))

        _step()

    def _on_sidebar_nav(self, key, command):
        try:
            command()
        except Exception as exc:
            self.log(f"Navigation action failed: {exc}", "WARNING")
        self._set_sidebar_nav_active(key)

    def _set_sidebar_nav_active(self, active_key):
        self._active_sidebar_key = active_key
        if hasattr(self, "_nav_anim_tokens"):
            for key, token in list(self._nav_anim_tokens.items()):
                try:
                    self.root.after_cancel(token)
                except Exception:
                    pass
                self._nav_anim_tokens.pop(key, None)
        for key, parts in getattr(self, "_nav_rows", {}).items():
            if key == active_key:
                parts["row"].config(bg=self.palette["surface_alt"])
                parts["btn"].config(bg=self.palette["surface_alt"], fg=self.palette["primary"])
                parts["badge"].config(bg=self.palette["surface_alt"], fg=self.palette["muted"])
                parts["accent"].pack(side="left", fill="y")
            else:
                parts["row"].config(bg=self.palette["surface"])
                parts["btn"].config(bg=self.palette["surface"], fg=self.palette["muted"])
                parts["badge"].config(bg=self.palette["surface"], fg=self.palette["muted"])
                parts["accent"].pack_forget()
