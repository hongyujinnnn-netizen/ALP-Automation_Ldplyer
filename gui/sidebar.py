import tkinter as tk
import ttkbootstrap as tb


class SidebarMixin:
    def create_sidebar(self, parent):
        sidebar_shell = tb.Frame(parent, style="Shadow.TFrame", width=236, padding=(0, 0, 1, 0))
        sidebar_shell.pack(side="left", fill="y")
        sidebar_shell.pack_propagate(False)

        sidebar = tb.Frame(sidebar_shell, style="Sidebar.TFrame", padding=(14, 14, 14, 10))
        sidebar.pack(fill="both", expand=True)

        logo = tb.Frame(sidebar, style="Sidebar.TFrame")
        logo.pack(fill="x", pady=(0, 14))
        tb.Label(logo, text="⚡ LDPlayer", style="SidebarTitle.TLabel").pack(anchor="w")
        tb.Label(logo, text="Manager v2.0", style="SidebarSub.TLabel").pack(anchor="w")

        self._nav_rows = {}
        nav_items = [
            ("dashboard", "📊 Dashboard", lambda: self.notebook.select(0), "CONTROL", ""),
            ("devices", "📱 Devices", self._focus_devices, "CONTROL", "0"),
            ("automation", "🤖 Automation", lambda: self.notebook.select(1), "CONTROL", ""),
            ("queue", "📋 Task Queue", lambda: self.notebook.select(3), "CONTROL", "0"),
            ("accounts", "👤 Accounts", self.show_account_manager, "MANAGE", ""),
            ("schedule", "🗓️ Scheduler", lambda: self.notebook.select(2), "MANAGE", ""),
            ("backups", "💾 Backups", self.create_backup, "MANAGE", ""),
            ("analytics", "📈 Analytics", lambda: self.notebook.select(0), "MANAGE", ""),
            ("settings", "⚙️ Settings", self.show_settings_dialog, "SYSTEM", ""),
            ("adb_tools", "🔌 ADB Tools", self.show_adb_tools, "SYSTEM", ""),
        ]

        current_section = None

        def _make_nav_row(parent, key, text, badge_text, command):
            row = tk.Frame(parent, bg=self.palette["surface"], height=34)
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

        for key, text, command, section, badge_text in nav_items:
            if section != current_section:
                current_section = section
                tb.Label(sidebar, text=section, style="SidebarSection.TLabel").pack(anchor="w", pady=(8, 2))
            _make_nav_row(sidebar, key, text, badge_text, command)

        footer = tb.Frame(sidebar, style="Sidebar.TFrame")
        footer.pack(side="bottom", fill="x", pady=(8, 0))
        self.sidebar_status_pill = tb.Label(
            footer,
            text="ADB: checking...",
            bootstyle="success",
            style="Chip.TLabel",
            padding=(8, 5),
        )
        self.sidebar_status_pill.pack(fill="x")

    def _focus_devices(self):
        if hasattr(self, "notebook"):
            self.notebook.select(0)
        if hasattr(self, "search_entry"):
            self.search_entry.focus_set()
        if hasattr(self, "_top_tab_buttons"):
            for label, btn in self._top_tab_buttons.items():
                btn.configure(bootstyle="info" if label == "Devices" else "secondary-link")

    def _on_sidebar_nav(self, key, command):
        try:
            command()
        except Exception as exc:
            self.log(f"Navigation action failed: {exc}", "WARNING")
        self._set_sidebar_nav_active(key)

    def _set_sidebar_nav_active(self, active_key):
        for key, parts in getattr(self, "_nav_rows", {}).items():
            if key == active_key:
                parts["row"].config(bg=self.palette["surface_alt"])
                parts["btn"].config(bg=self.palette["surface_alt"], fg=self.palette["primary"])
                parts["accent"].pack(side="left", fill="y")
            else:
                parts["row"].config(bg=self.palette["surface"])
                parts["btn"].config(bg=self.palette["surface"], fg=self.palette["muted"])
                parts["accent"].pack_forget()
