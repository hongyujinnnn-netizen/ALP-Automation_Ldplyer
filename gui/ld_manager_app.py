import os
import threading
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont
from tkinter.scrolledtext import ScrolledText
from tkinter import messagebox as MessageBox
from tkinter import filedialog
from tkinter import simpledialog
from datetime import datetime, timedelta
import json
import time
from pathlib import Path
import subprocess
import psutil
import random
import re
import sys
import zipfile
from abc import ABC, abstractmethod
import platform
import ttkbootstrap as tb
from ttkbootstrap.constants import *
from ttkbootstrap.scrolled import ScrolledText as tbScrolledText

# Import local modules
from core import settings as settings_store
from core.paths import get_app_paths
from core.emulator import ControlEmulator
from core.managers import AccountManager, ContentManager, BackupManager, SmartScheduler, TaskTemplates
from utils.performance_monitor import PerformanceMonitor
from utils.app_utils import AppUtils
from gui.checkbox_treeview import CheckboxTreeview
from gui.main_window import MainWindow
from gui.mixins import ToolsMixin


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

class LDManagerApp(ToolsMixin):
    def __init__(self, root):
        self.root = root
        self.root.title("LDPlayer Automation Manager")
        self.root.geometry("1540x940")
        self.root.minsize(1280, 780)
        
        # Apply a fixed dark theme to mirror the dashboard mockup style.
        self.style = tb.Style(theme="darkly")
        self.palette = {
            "app_bg": "#080B10",
            "surface": "#0E1118",
            "surface_alt": "#141820",
            "surface_alt_2": "#1A1F2C",
            "text": "#E2E8F0",
            "muted": "#64748B",
            "primary": "#00E5FF",
            "secondary": "#7C3AED",
            "success": "#10B981",
            "warning": "#F59E0B",
            "danger": "#EF4444",
            "border": "#1A2030",
            "border_alt": "#222B3A",
        }
        families = set(tkfont.families())
        self.mono_font = "Cascadia Mono" if "Cascadia Mono" in families else "Consolas"
        self.display_font = "Segoe UI Semibold"
        self._ld_snapshot = {}
        self._ld_status_cache = {}
        self._ld_account_cache = {}
        self._last_table_signature = None
        self._ld_search_job = None
        self._main_thread_id = threading.get_ident()
        self._ld_checked_names = set()
        self.ld_search_var = tk.StringVar()
        self.ld_sort_var = tk.StringVar(value="Status")
        self.ld_status_filter_var = tk.StringVar(value="All")
        self.ld_account_filter_var = tk.StringVar(value="All")
        
        # Configure custom styles
        self.configure_custom_styles()
        self.paths = get_app_paths()
        self.paths.ensure_runtime_dirs()
        
        try:
            self.emulator = ControlEmulator()
        except Exception as e:
            MessageBox.showerror("Initialization Error", f"Failed to initialize emulator control: {str(e)}")
            self.root.destroy()
            return
            
        # Initialize enhanced components
        self.performance_monitor = PerformanceMonitor()
        self.account_manager = AccountManager(self.paths)
        self.content_manager = ContentManager(self.paths)
        self.backup_manager = BackupManager(self.log, self.paths)
        self.smart_scheduler = SmartScheduler(self.log, self.paths)
        
        self.running_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()  # Start unpaused
        self.schedule_thread = None
        self.schedule_running = False
        self.schedule_settings_file = self.paths.schedule_settings_file
        self.settings_file = self.paths.settings_file
        
        # Initialize settings variables
        self.parallel_ld = tk.IntVar(value=2)
        self.boot_delay = tk.IntVar(value=10)
        self.task_duration = tk.IntVar(value=15)  # In minutes
        self.max_videos = tk.IntVar(value=2)
        self.schedule_time = tk.StringVar(value="09:00")
        self.schedule_daily = tk.BooleanVar(value=True)
        self.schedule_weekly = tk.BooleanVar(value=False)
        self.schedule_repeat_hours = tk.IntVar(value=0)  # 0 means no repeat
        self.start_same_time = tk.BooleanVar(value=False)
        self.use_content_queue = tk.BooleanVar(value=True)
        
        # Task type variables
        self.task_type_var = tk.StringVar(value="scroll")
        self.task_template_var = tk.StringVar(value="custom")
        self.task_type_var.trace_add("write", lambda *_: self._update_header_chips())
        
        # Days of week for scheduling
        self.schedule_days = {
            "Monday": tk.BooleanVar(value=False),
            "Tuesday": tk.BooleanVar(value=False),
            "Wednesday": tk.BooleanVar(value=False),
            "Thursday": tk.BooleanVar(value=False),
            "Friday": tk.BooleanVar(value=False),
            "Saturday": tk.BooleanVar(value=False),
            "Sunday": tk.BooleanVar(value=False)
        }
        
        self.setup_enhanced_ui()
        self.load_settings()
        self.load_schedule_settings()
        self.populate_ld_table()
        self.start_status_refresh()
        self.start_analytics_refresh()
        self.start_system_metrics_refresh()

    def configure_custom_styles(self):
        """Configure custom ttkbootstrap styles"""
        self.root.configure(bg=self.palette["app_bg"])

        self.style.configure(
            ".",
            font=(self.display_font, 10),
            background=self.palette["surface"],
            foreground=self.palette["text"],
        )
        self.style.configure(
            "TLabelframe",
            borderwidth=0,
            relief="flat",
            background=self.palette["surface"]
        )
        self.style.configure(
            "TLabelframe.Label",
            font=(self.display_font, 13),
            foreground=self.palette["text"],
            background=self.palette["surface"]
        )
        self.style.configure("TEntry", padding=(8, 8))
        self.style.configure("TCombobox", padding=(8, 8))
        self.style.configure("Card.TFrame", background=self.palette["surface"], borderwidth=0, relief="flat")
        self.style.configure("CardInner.TFrame", background=self.palette["surface"], borderwidth=0, relief="flat")
        self.style.configure("Shadow.TFrame", background=self.palette["border"])
        self.style.configure("Sidebar.TFrame", background=self.palette["surface"])
        self.style.configure("Topbar.TFrame", background=self.palette["surface"])
        self.style.configure("SidebarTitle.TLabel", font=(self.display_font, 14), foreground=self.palette["text"], background=self.palette["surface"])
        self.style.configure("SidebarSub.TLabel", font=(self.mono_font, 9), foreground=self.palette["primary"], background=self.palette["surface"])
        self.style.configure("TopTitle.TLabel", font=(self.display_font, 15), foreground=self.palette["text"], background=self.palette["surface"])
        self.style.configure("TopSub.TLabel", font=(self.mono_font, 9), foreground=self.palette["muted"], background=self.palette["surface"])
        self.style.configure("Nav.TButton", font=(self.display_font, 10), anchor="w", padding=(10, 8))
        self.style.map(
            "Nav.TButton",
            background=[("active", self.palette["surface_alt"])],
            foreground=[("active", self.palette["text"])]
        )
        self.style.configure("NavActive.TButton", font=(self.display_font, 10), anchor="w", padding=(10, 8))
        self.style.configure("SidebarSection.TLabel", font=(self.display_font, 9), foreground="#64748B", background=self.palette["surface"])
        self.style.configure("MetricLabel.TLabel", font=(self.display_font, 8), foreground="#6B7B90", background=self.palette["surface"])
        self.style.configure("MetricValue.TLabel", font=(self.mono_font, 28), foreground=self.palette["text"], background=self.palette["surface"])
        self.style.configure("MetricSub.TLabel", font=(self.mono_font, 9), foreground=self.palette["muted"], background=self.palette["surface"])

        self.style.configure(
            "TNotebook.Tab",
            padding=(16, 11),
            font=(self.display_font, 10)
        )
        self.style.map(
            "TNotebook.Tab",
            background=[("selected", self.palette["surface"]), ("!selected", self.palette["surface_alt"])],
            foreground=[("selected", self.palette["primary"]), ("!selected", self.palette["muted"])],
            bordercolor=[("selected", self.palette["primary"]), ("!selected", self.palette["border"])]
        )
        # Hidden tab style - used only for the outer main notebook (tabs navigated via top bar buttons)
        self.style.layout("Hidden.TNotebook.Tab", [])
        self.style.configure("Hidden.TNotebook", tabmargins=0)

        # Configure Treeview row height
        self.style.configure(
            "Custom.Treeview",
            rowheight=28,
            font=(self.mono_font, 9),
            background=self.palette["surface"],
            fieldbackground=self.palette["surface"],
            foreground=self.palette["text"],
            borderwidth=0
        )
        
        self.style.configure(
            "Custom.Treeview.Heading",
            font=(self.display_font, 10),
            padding=(8, 7),
            relief="flat",
            foreground=self.palette["muted"],
            background=self.palette["surface_alt"]
        )
        
        # Configure button styles
        for button_style in ("success.TButton", "danger.TButton", "warning.TButton", "info.TButton"):
            self.style.configure(button_style, font=(self.display_font, 10), padding=(10, 7))
        
        # Configure label styles
        self.style.configure(
            "Title.TLabel",
            font=(self.display_font, 18),
            foreground=self.palette["text"]
        )
        
        self.style.configure(
            "Subtitle.TLabel",
            font=(self.mono_font, 10),
            foreground=self.palette["muted"]
        )
        self.style.configure(
            "SectionTitle.TLabel",
            font=(self.display_font, 16),
            foreground=self.palette["text"]
        )
        self.style.configure(
            "HeroTitle.TLabel",
            font=(self.display_font, 21),
            foreground=self.palette["text"]
        )
        self.style.configure(
            "HeroSub.TLabel",
            font=(self.mono_font, 10),
            foreground=self.palette["muted"]
        )
        self.style.configure(
            "Chip.TLabel",
            font=(self.display_font, 9),
            foreground=self.palette["text"]
        )

        # Custom scrollbars
        self.style.configure(
            "Vertical.TScrollbar",
            background=self.palette["border"],
            troughcolor=self.palette["surface"],
            arrowcolor=self.palette["muted"],
            borderwidth=0,
            relief="flat",
            width=8,
        )
        self.style.configure(
            "Horizontal.TScrollbar",
            background=self.palette["border"],
            troughcolor=self.palette["surface"],
            arrowcolor=self.palette["muted"],
            borderwidth=0,
            relief="flat",
            width=6,
        )

        # Button hierarchy
        self.style.configure(
            "Primary.TButton",
            font=(self.display_font, 10),
            padding=(14, 8),
            background="#00C4D9",
            foreground="#040608",
        )
        self.style.map(
            "Primary.TButton",
            background=[("active", "#00E5FF"), ("disabled", "#1A2530")],
        )

        self.style.configure(
            "Ctrl.TButton",
            font=(self.display_font, 10),
            padding=(10, 7),
            background=self.palette["surface_alt"],
            foreground=self.palette["text"],
            bordercolor=self.palette["border_alt"],
            relief="solid",
            borderwidth=1,
        )

        self.style.configure(
            "Ghost.TButton",
            font=("Segoe UI", 10),
            padding=(8, 6),
            background=self.palette["surface"],
            foreground=self.palette["muted"],
        )
        self.style.map(
            "Ghost.TButton",
            foreground=[("active", self.palette["text"])],
        )

    def _create_card_section(self, parent, title, subtitle=None, pady=(0, 14), expand=False):
        """Create a lightweight card section with subtle shadow and generous spacing."""
        shadow = tb.Frame(parent, style="Shadow.TFrame", padding=(0, 0, 0, 1))
        shadow.pack(fill="both", expand=expand, pady=pady)

        card = tb.Frame(shadow, style="Card.TFrame", padding=14)
        card.pack(fill="both", expand=True, padx=(0, 1))

        tb.Label(card, text=title, style="SectionTitle.TLabel").pack(anchor="w")
        if subtitle:
            tb.Label(card, text=subtitle, style="Subtitle.TLabel").pack(anchor="w", pady=(2, 12))
        else:
            tb.Frame(card, height=8, style="CardInner.TFrame").pack(fill="x")
        content = tb.Frame(card, style="CardInner.TFrame")
        content.pack(fill="both", expand=True)
        return content

    def setup_enhanced_ui(self):
        self.create_enhanced_menu_bar()
        
        # Main shell with sidebar + content area.
        shell = tb.Frame(self.root, style="CardInner.TFrame")
        shell.pack(fill="both", expand=True)

        self.create_sidebar(shell)

        main_container = tb.Frame(shell, style="CardInner.TFrame", padding=(16, 14, 16, 8))
        main_container.pack(side="left", fill="both", expand=True)

        self.create_top_bar(main_container)

        content = tb.Frame(main_container, style="CardInner.TFrame", padding=(0, 8, 0, 0))
        content.pack(fill="both", expand=True)
        self.create_right_notebook_panel(content)
        
        # Status bar
        self.create_status_bar()

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

    def _make_chip(self, parent, text, bg, fg, border_color):
        frame = tk.Frame(parent, bg=border_color, padx=1, pady=1, highlightthickness=0)
        inner = tk.Frame(frame, bg=bg, padx=8, pady=3)
        inner.pack()
        lbl = tk.Label(inner, text=text, bg=bg, fg=fg, font=(self.display_font, 9))
        lbl.pack()
        frame.pack(side="left", padx=4)
        return lbl

    def create_top_bar(self, parent):
        """Top-level application header with global actions."""
        top_shadow = tb.Frame(parent, style="Shadow.TFrame", padding=(0, 0, 0, 1))
        top_shadow.pack(fill="x", side="top")
        top_bar = tb.Frame(top_shadow, style="Topbar.TFrame", padding=(16, 12))
        top_bar.pack(fill="x", padx=(0, 1))

        title_wrap = tb.Frame(top_bar, style="Topbar.TFrame")
        title_wrap.pack(side="left")

        tb.Label(
            title_wrap,
            text="Dashboard",
            style="TopTitle.TLabel"
        ).pack(anchor="w")
        self.top_status_label = tb.Label(
            title_wrap,
            text=f"System idle | {datetime.now().strftime('%d %b %Y %H:%M')}",
            style="TopSub.TLabel"
        )
        self.top_status_label.pack(anchor="w")

        center_meta = tb.Frame(top_bar, style="Topbar.TFrame")
        center_meta.pack(side="left", padx=(18, 0))
        self.top_selected_chip = self._make_chip(
            center_meta,
            "Selected: 0",
            bg="#071820",
            fg=self.palette["primary"],
            border_color="#00485A",
        )
        self.top_mode_chip = self._make_chip(
            center_meta,
            "Mode: Idle",
            bg="#0A1A10",
            fg=self.palette["success"],
            border_color="#1A5030",
        )
        self.top_task_chip = self._make_chip(
            center_meta,
            "Task: Scroll",
            bg="#10082A",
            fg=self.palette["secondary"],
            border_color="#3A1878",
        )

        tabs = tb.Frame(top_bar, style="Topbar.TFrame")
        tabs.pack(side="left", padx=(16, 0))
        self._top_tab_buttons = {}
        tab_defs = [
            ("Overview", 0, None),
            ("Devices", 0, self._focus_devices),
            ("Tasks", 1, None),
            ("Logs", 4, None),
        ]
        for label, idx, action in tab_defs:
            btn = tb.Button(
                tabs,
                text=label,
                bootstyle="secondary-link",
                command=(action if action is not None else (lambda i=idx: self.notebook.select(i) if hasattr(self, "notebook") else None)),
                width=9,
            )
            btn.pack(side="left", padx=2)
            self._top_tab_buttons[label] = btn

        actions = tb.Frame(top_bar, style="Topbar.TFrame")
        actions.pack(side="right")
        tb.Button(actions, text="⟳ Refresh", bootstyle="outline-info", command=self.refresh_all, width=10).pack(side="left", padx=4)
        tb.Button(actions, text="Stop All", bootstyle="danger", command=self.stop_automation, width=10).pack(side="left", padx=4)
        tb.Button(actions, text="▶ Start Automation", bootstyle="info", command=self.start_automation, width=16).pack(side="left", padx=4)
        self._update_header_chips()

    def _update_header_chips(self, mode_text=None):
        selected = 0
        if hasattr(self, "_ld_checked_names"):
            selected = len(self._ld_checked_names)
        if hasattr(self, "top_selected_chip"):
            self.top_selected_chip.config(text=f"Selected: {selected}")

        if hasattr(self, "top_mode_chip") and mode_text is not None:
            self.top_mode_chip.config(text=f"Mode: {mode_text}")

        task_label = {
            "scroll": "Scroll",
            "reels": "Reels",
            "autoscroll": "Auto Scroll",
            "likes": "Likes",
            "friends": "Add Friends",
        }.get(self.task_type_var.get(), self.task_type_var.get().title())
        if hasattr(self, "top_task_chip"):
            self.top_task_chip.config(text=f"Task: {task_label}")

    def _is_main_thread(self):
        return threading.get_ident() == self._main_thread_id

    def _schedule_ld_table_render(self, delay_ms=140):
        if self._ld_search_job is not None:
            try:
                self.root.after_cancel(self._ld_search_job)
            except Exception:
                pass
            self._ld_search_job = None
        self._ld_search_job = self.root.after(delay_ms, self._render_ld_table)

    def create_ld_table_panel(self, parent):
        """Create LD Players table panel"""
        table_frame = self._create_card_section(
            parent,
            "Emulator Instances",
            "Live fleet table with real status, account mapping, and batch selection.",
            pady=(0, 0),
            expand=True,
        )
        
        # Control buttons frame
        controls_frame = tb.Frame(table_frame)
        controls_frame.pack(fill="x", pady=(0, 10))
        
        # Control buttons
        control_configs = [
            ("Refresh", self.refresh_emulator_list, "outline-primary"),
            ("Select All", self.select_all, "outline-success"),
            ("Clear", self.deselect_all, "outline-danger"),
            ("Invert", self.invert_selection, "outline-warning")
        ]
        
        for text, command, style in control_configs:
            btn = tb.Button(
                controls_frame,
                text=text,
                command=command,
                bootstyle=style,
                width=11
            )
            btn.pack(side="left", padx=3)

        filter_frame = tb.Frame(table_frame)
        filter_frame.pack(fill="x", pady=(0, 10))
        tb.Label(filter_frame, text="Search", style="Subtitle.TLabel").pack(side="left")
        self.search_entry = tb.Entry(filter_frame, textvariable=self.ld_search_var, width=24)
        self.search_entry.pack(side="left", padx=(6, 12))
        self.search_entry.bind("<KeyRelease>", lambda _e: self._schedule_ld_table_render())

        tb.Label(filter_frame, text="Status", style="Subtitle.TLabel").pack(side="left")
        status_combo = tb.Combobox(
            filter_frame,
            textvariable=self.ld_status_filter_var,
            values=("All", "Running", "Active", "Inactive", "Paused", "Completed"),
            state="readonly",
            width=11
        )
        status_combo.pack(side="left", padx=(6, 12))
        status_combo.bind("<<ComboboxSelected>>", lambda _e: self._render_ld_table())

        tb.Label(filter_frame, text="Account", style="Subtitle.TLabel").pack(side="left")
        account_combo = tb.Combobox(
            filter_frame,
            textvariable=self.ld_account_filter_var,
            values=("All", "Has Account", "No Account"),
            state="readonly",
            width=12
        )
        account_combo.pack(side="left", padx=(6, 12))
        account_combo.bind("<<ComboboxSelected>>", lambda _e: self._render_ld_table())

        tb.Label(filter_frame, text="Sort", style="Subtitle.TLabel").pack(side="left")
        sort_combo = tb.Combobox(
            filter_frame,
            textvariable=self.ld_sort_var,
            values=("Status", "Name", "ADB", "Account"),
            state="readonly",
            width=11
        )
        sort_combo.pack(side="left", padx=(6, 0))
        sort_combo.bind("<<ComboboxSelected>>", lambda _e: self._render_ld_table())
        tb.Button(
            filter_frame,
            text="Clear Filters",
            bootstyle="outline-secondary",
            command=self.clear_ld_filters,
            width=12
        ).pack(side="right")

        # Selection info
        self.selection_info = tb.Label(
            controls_frame,
            text="Selected: 0/0",
            bootstyle="secondary",
            style="Chip.TLabel"
        )
        self.selection_info.pack(side="right", padx=5)

        fleet_stats = tb.Frame(table_frame)
        fleet_stats.pack(fill="x", pady=(0, 10))
        self.fleet_total_chip = tb.Label(fleet_stats, text="Total: 0", bootstyle="light", style="Chip.TLabel", padding=(8, 4))
        self.fleet_total_chip.pack(side="left", padx=(0, 6))
        self.fleet_online_chip = tb.Label(fleet_stats, text="Online: 0", bootstyle="success", style="Chip.TLabel", padding=(8, 4))
        self.fleet_online_chip.pack(side="left", padx=(0, 6))
        self.fleet_running_chip = tb.Label(fleet_stats, text="Running: 0", bootstyle="warning", style="Chip.TLabel", padding=(8, 4))
        self.fleet_running_chip.pack(side="left", padx=(0, 6))
        self.fleet_account_chip = tb.Label(fleet_stats, text="With Account: 0", bootstyle="info", style="Chip.TLabel", padding=(8, 4))
        self.fleet_account_chip.pack(side="left", padx=(0, 6))
        self.fleet_visible_chip = tb.Label(fleet_stats, text="Visible: 0", bootstyle="secondary", style="Chip.TLabel", padding=(8, 4))
        self.fleet_visible_chip.pack(side="right")
        
        # Treeview with custom style
        self.create_enhanced_treeview(table_frame)

    def create_enhanced_treeview(self, parent):
        """Create enhanced Treeview with better styling"""
        # Create frame for treeview and scrollbar
        tree_frame = tb.Frame(parent)
        tree_frame.pack(fill="both", expand=True)
        
        # Define columns
        columns = ("name", "serial", "status", "task", "progress", "account", "actions")
        
        # Create Treeview with custom style
        self.ld_table = CheckboxTreeview(
            tree_frame,
            columns=columns,
            show="tree headings",
            selectmode="none",
            height=15,
            style="Custom.Treeview"
        )

        self.ld_table.heading("#0", text="Sel", anchor="center")
        self.ld_table.column("#0", width=52, minwidth=48, anchor="center", stretch=False)

        # Configure columns
        self.ld_table.heading("name", text="LD Name", anchor="w")
        self.ld_table.column("name", width=110, anchor="w")
        
        self.ld_table.heading("serial", text="ADB Serial", anchor="w")
        self.ld_table.column("serial", width=120, anchor="w")
        
        self.ld_table.heading("status", text="Status", anchor="w")
        self.ld_table.column("status", width=88, anchor="w")

        self.ld_table.heading("task", text="Task", anchor="w")
        self.ld_table.column("task", width=100, anchor="w")

        self.ld_table.heading("progress", text="Progress", anchor="w")
        self.ld_table.column("progress", width=75, anchor="w")
        
        self.ld_table.heading("account", text="Account", anchor="w")
        self.ld_table.column("account", width=110, anchor="w")

        self.ld_table.heading("actions", text="Actions", anchor="w")
        self.ld_table.column("actions", width=88, anchor="w")
        
        # Configure tags with state colors
        self.ld_table.tag_configure("active", background="#0A1A20", foreground="#67E8F9")
        self.ld_table.tag_configure("inactive", background="#180D0D", foreground="#FCA5A5")
        self.ld_table.tag_configure("running", background="#0A1A14", foreground="#6EE7B7")
        self.ld_table.tag_configure("paused", background="#160F22", foreground="#C4B5FD")
        self.ld_table.tag_configure("completed", background="#0A1420", foreground="#93C5FD")
        self.ld_table.tag_configure("odd_row", background="#0C1016")
        self.ld_table.tag_configure("even_row", background=self.palette["surface"])
        
        # Scrollbars
        v_scrollbar = tb.Scrollbar(
            tree_frame,
            orient="vertical",
            command=self.ld_table.yview,
            style="Vertical.TScrollbar",
        )
        v_scrollbar.pack(side="right", fill="y")
        
        h_scrollbar = tb.Scrollbar(
            tree_frame,
            orient="horizontal",
            command=self.ld_table.xview,
            style="Horizontal.TScrollbar",
        )
        h_scrollbar.pack(side="bottom", fill="x")
        
        self.ld_table.configure(
            yscrollcommand=v_scrollbar.set,
            xscrollcommand=h_scrollbar.set
        )
        
        self.ld_table.pack(fill="both", expand=True)
        self.ld_table.bind("<Button-3>", self._show_instance_context_menu)
        self.ld_table.bind("<ButtonRelease-1>", lambda _e: self.update_selection_info(), add="+")

        self.instance_context_menu = tk.Menu(self.root, tearoff=0)
        self.instance_context_menu.add_command(label="Run Automation", command=self._context_run_automation)
        self.instance_context_menu.add_separator()
        self.instance_context_menu.add_command(label="Start", command=self._context_start_instance)
        self.instance_context_menu.add_command(label="Stop", command=self._context_stop_instance)
        self.instance_context_menu.add_command(label="Restart", command=self._context_restart_instance)
        self.instance_context_menu.add_separator()
        self.instance_context_menu.add_command(label="Copy ADB Serial", command=self._context_copy_serial)
        self.instance_context_menu.add_separator()
        self.instance_context_menu.add_command(label="Settings", command=self.show_settings_dialog)
        self._context_ld_name = None
        self._context_ld_serial = None

    def create_right_notebook_panel(self, parent):
        """Create right panel with Notebook tabs"""
        # Create Notebook
        self.notebook = tb.Notebook(parent, style="Hidden.TNotebook")
        self.notebook.pack(side="right", fill="both", expand=True)
        
        # Create tabs
        self.create_dashboard_tab()
        self.create_tasks_tab()
        self.create_schedule_tab()
        self.create_content_tab()
        self.create_logs_tab()
        self.notebook.bind("<<NotebookTabChanged>>", self._on_notebook_tab_changed)
        self._set_sidebar_nav_active("dashboard")
        self._on_notebook_tab_changed()

    def _on_notebook_tab_changed(self, _event=None):
        idx = self.notebook.index("current")
        tab_to_nav = {
            0: "dashboard",
            1: "automation",
            2: "schedule",
            3: "content",
            4: "logs",
        }
        self._set_sidebar_nav_active(tab_to_nav.get(idx, "dashboard"))
        if hasattr(self, "_top_tab_buttons"):
            active_label = "Overview"
            if idx == 1:
                active_label = "Tasks"
            elif idx == 4:
                active_label = "Logs"
            for label, btn in self._top_tab_buttons.items():
                btn.configure(bootstyle="info" if label == active_label else "secondary-link")

    def create_dashboard_tab(self):
        """Create Dashboard tab"""
        dashboard_tab = tb.Frame(self.notebook)
        self.notebook.add(dashboard_tab, text="Dashboard")
        
        # Analytics Dashboard
        self.create_analytics_dashboard(dashboard_tab)
        self.create_ld_table_panel(dashboard_tab)

        lower = ttk.Panedwindow(dashboard_tab, orient=tk.HORIZONTAL)
        lower.pack(fill="both", expand=True, pady=(2, 0))

        left = tb.Frame(lower, style="CardInner.TFrame", padding=(0, 0, 8, 0))
        right = tb.Frame(lower, style="CardInner.TFrame", padding=(8, 0, 0, 0))
        lower.add(left, weight=3)
        lower.add(right, weight=2)

        self.create_task_config_panel(left)
        self.create_schedule_overview_panel(left)
        self.create_system_health_panel(right)
        self.create_live_log_panel(right)

    def create_analytics_dashboard(self, parent):
        """Create analytics dashboard"""
        analytics_frame = self._create_card_section(
            parent,
            "Operations Overview",
            "Real-time fleet, task throughput, and failure summary."
        )
        
        # Metrics grid
        metrics_frame = tb.Frame(analytics_frame)
        metrics_frame.pack(fill="x", padx=4, pady=4)
        
        self.metric_labels = {}
        metrics = [
            ("total_instances", "TOTAL INSTANCES", "0", "0 selected", self.palette["primary"], "📱"),
            ("running_tasks", "RUNNING", "0", "Tasks in progress", self.palette["success"], "▶"),
            ("completed_tasks", "TASKS DONE", "0", "Today's total", self.palette["secondary"], "✓"),
            ("errors", "ERRORS", "0", "Needs attention", self.palette["warning"], "⚠"),
        ]
        
        self.metric_sub_labels = {}
        for i, (key, label, value, sub, accent, icon) in enumerate(metrics):
            metric_card = tb.Frame(metrics_frame)
            metric_card.grid(row=0, column=i, padx=8, pady=8, sticky="nsew")
            metrics_frame.columnconfigure(i, weight=1)
            
            # Card with border
            card_shadow = tb.Frame(metric_card, style="Shadow.TFrame", padding=(0, 0, 0, 1))
            card_shadow.pack(fill="both", expand=True, padx=1, pady=1)
            card = tb.Frame(card_shadow, style="Card.TFrame", padding=1)
            card.pack(fill="both", expand=True, padx=(0, 1))

            stripe = tk.Frame(card, bg=accent, height=3)
            stripe.pack(fill="x", side="top")

            inner_frame = tb.Frame(card, style="CardInner.TFrame", padding=12)
            inner_frame.pack(fill="both", expand=True)
            
            tb.Label(inner_frame, text=label, style="MetricLabel.TLabel").pack(anchor="w")
            
            value_label = tb.Label(
                inner_frame,
                text=value,
                style="MetricValue.TLabel",
                foreground=accent,
            )
            value_label.pack(anchor="w", pady=(6, 2))
            sub_label = tb.Label(inner_frame, text=sub, style="MetricSub.TLabel")
            sub_label.pack(anchor="w")
            self.metric_sub_labels[key] = sub_label
            tb.Label(inner_frame, text=icon, font=("Segoe UI Emoji", 20), foreground="#4A5568", background=self.palette["surface"]).place(relx=0.92, rely=0.05, anchor="ne")

            self.metric_labels[key] = value_label

    def create_batch_operations(self, parent):
        """Create batch operations section"""
        batch_frame = self._create_card_section(
            parent,
            "Fleet Controls",
            "Quick commands for selected emulator instances."
        )
        
        batch_btn_frame = tb.Frame(batch_frame)
        batch_btn_frame.pack(fill="x", padx=6, pady=6)
        
        # Start button
        self.batch_start_btn = tb.Button(
            batch_btn_frame,
            text="Start Selected",
            command=self.batch_start,
            bootstyle="success",
            width=15
        )
        self.batch_start_btn.pack(side="left", padx=5)
        
        # Stop button
        self.batch_stop_btn = tb.Button(
            batch_btn_frame,
            text="Stop Selected",
            command=self.batch_stop,
            bootstyle="danger",
            width=15
        )
        self.batch_stop_btn.pack(side="left", padx=5)
        
        # Restart button
        tb.Button(
            batch_btn_frame,
            text="Restart Selected",
            command=self.batch_restart,
            bootstyle="warning",
            width=15
        ).pack(side="left", padx=5)

    def create_system_health_panel(self, parent):
        panel = self._create_card_section(
            parent,
            "System Health",
            "Live host metrics while automation runs.",
            expand=True,
        )

        self.sys_rows = {}
        metrics = [
            ("cpu", "CPU"),
            ("ram", "RAM"),
            ("disk", "Disk"),
            ("temp", "Temp"),
        ]
        gradients = {
            "cpu": ("#0891B2", "#00E5FF"),
            "ram": ("#6D28D9", "#A78BFA"),
            "disk": ("#059669", "#10B981"),
            "temp": ("#D97706", "#F59E0B"),
        }

        for key, label in metrics:
            row = tb.Frame(panel, style="CardInner.TFrame")
            row.pack(fill="x", pady=7, padx=4)
            top = tb.Frame(row, style="CardInner.TFrame")
            top.pack(fill="x")
            tb.Label(top, text=label, style="MetricLabel.TLabel").pack(side="left")
            value_label = tk.Label(
                top,
                text="0%",
                bg=self.palette["surface"],
                fg=self.palette["text"],
                font=(self.mono_font, 9),
            )
            value_label.pack(side="right")
            c1, c2 = gradients[key]
            bar = GradientProgressBar(row, bg=self.palette["surface_alt"], color_start=c1, color_end=c2, height=5)
            bar.pack(fill="x", pady=(3, 0))
            self.sys_rows[key] = {"bar": bar, "value": value_label}

    def create_task_config_panel(self, parent):
        panel = self._create_card_section(
            parent,
            "Task Configuration",
            "Set behavior for selected LDPlayer instances.",
        )

        header = tb.Frame(panel, style="CardInner.TFrame")
        header.pack(fill="x", pady=(0, 8))
        tb.Label(header, text="Auto-batch", style="MetricSub.TLabel").pack(side="right")
        self.auto_batch_var = tk.BooleanVar(value=True)
        tb.Checkbutton(header, variable=self.auto_batch_var, bootstyle="success-round-toggle").pack(side="right", padx=(0, 6))

        type_row = tb.Frame(panel, style="CardInner.TFrame")
        type_row.pack(fill="x", pady=(0, 10))
        self._task_type_buttons = {}
        task_buttons = [
            ("📜 Scroll Feed", "scroll"),
            ("🎬 Watch Reels", "reels"),
            ("❤️ React Posts", "likes"),
            ("👥 Add Friends", "friends"),
        ]
        for text, value in task_buttons:
            btn = tb.Button(
                type_row,
                text=text,
                bootstyle="secondary-outline",
                command=lambda v=value: self._select_task_type(v),
                width=15,
            )
            btn.pack(side="left", padx=4, pady=2)
            self._task_type_buttons[value] = btn
        self._select_task_type(self.task_type_var.get())

        grid = tb.Frame(panel, style="CardInner.TFrame")
        grid.pack(fill="x")

        tb.Label(grid, text="Batch Size", style="MetricLabel.TLabel").grid(row=0, column=0, sticky="w", padx=6, pady=(0, 4))
        tb.Spinbox(grid, from_=1, to=10, textvariable=self.parallel_ld, width=10).grid(row=1, column=0, sticky="w", padx=6, pady=(0, 8))

        tb.Label(grid, text="Delay Range (s)", style="MetricLabel.TLabel").grid(row=0, column=1, sticky="w", padx=6, pady=(0, 4))
        self.delay_range_var = tk.StringVar(value=f"{max(1, self.boot_delay.get()-2)} - {self.boot_delay.get()+2}")
        tb.Entry(grid, textvariable=self.delay_range_var, width=14).grid(row=1, column=1, sticky="w", padx=6, pady=(0, 8))

        tb.Label(grid, text="Task Duration", style="MetricLabel.TLabel").grid(row=2, column=0, sticky="w", padx=6, pady=(0, 4))
        self.task_duration_choice = tk.StringVar(value="Until complete")
        tb.Combobox(
            grid,
            textvariable=self.task_duration_choice,
            state="readonly",
            values=("30 minutes", "1 hour", "2 hours", "Until complete"),
            width=16,
        ).grid(row=3, column=0, sticky="w", padx=6, pady=(0, 8))

        tb.Label(grid, text="On Crash", style="MetricLabel.TLabel").grid(row=2, column=1, sticky="w", padx=6, pady=(0, 4))
        self.on_crash_choice = tk.StringVar(value="Auto-restart")
        tb.Combobox(
            grid,
            textvariable=self.on_crash_choice,
            state="readonly",
            values=("Auto-restart", "Skip instance", "Stop all"),
            width=16,
        ).grid(row=3, column=1, sticky="w", padx=6, pady=(0, 8))

    def _select_task_type(self, value):
        # "friends" and "likes" are currently UI stubs. Backend supports scroll/reels.
        if value in ("scroll", "reels", "likes", "friends"):
            self.task_type_var.set(value)
        for key, btn in getattr(self, "_task_type_buttons", {}).items():
            btn.configure(bootstyle="info" if key == value else "secondary-outline")

    def create_schedule_overview_panel(self, parent):
        panel = self._create_card_section(
            parent,
            "Schedule",
            "Automation run windows and next-run preview.",
        )

        header = tb.Frame(panel, style="CardInner.TFrame")
        header.pack(fill="x", pady=(0, 8))
        tb.Label(header, text="Enabled", style="MetricSub.TLabel").pack(side="right")
        self.schedule_enabled_ui = tk.BooleanVar(value=self.schedule_running)
        tb.Checkbutton(
            header,
            variable=self.schedule_enabled_ui,
            command=self._toggle_schedule_from_dashboard,
            bootstyle="success-round-toggle",
        ).pack(side="right", padx=(0, 6))

        cards = tb.Frame(panel, style="CardInner.TFrame")
        cards.pack(fill="x")

        start_card = tb.Frame(cards, style="Card.TFrame", padding=10)
        stop_card = tb.Frame(cards, style="Card.TFrame", padding=10)
        next_card = tb.Frame(cards, style="Card.TFrame", padding=10)
        start_card.grid(row=0, column=0, sticky="nsew", padx=4)
        stop_card.grid(row=0, column=1, sticky="nsew", padx=4)
        next_card.grid(row=0, column=2, sticky="nsew", padx=4)
        cards.columnconfigure((0, 1, 2), weight=1)

        self.schedule_stop_time = tk.StringVar(value="22:00")
        self.next_run_preview = tk.StringVar(value="Tomorrow · Mon")

        self._build_schedule_card(start_card, "Start Time", self.schedule_time, active=True)
        self._build_schedule_card(stop_card, "Stop Time", self.schedule_stop_time, active=False)
        self._build_next_run_card(next_card)

    def _build_schedule_card(self, parent, title, time_var, active=True):
        tb.Label(parent, text=title.upper(), style="MetricLabel.TLabel").pack(anchor="w")
        tb.Entry(parent, textvariable=time_var, width=8).pack(anchor="w", pady=(6, 6))
        chips = tb.Frame(parent, style="CardInner.TFrame")
        chips.pack(anchor="w")
        for d in ("M", "T", "W", "T", "F", "S", "S"):
            style = "info" if (active and d in ("M", "T", "W", "F")) else "secondary"
            tb.Label(chips, text=d, bootstyle=style, style="Chip.TLabel", padding=(4, 1)).pack(side="left", padx=1)

    def _build_next_run_card(self, parent):
        tb.Label(parent, text="NEXT RUN", style="MetricLabel.TLabel").pack(anchor="w")
        tb.Label(parent, textvariable=self.schedule_time, bootstyle="info", font=("Segoe UI Semibold", 18)).pack(anchor="w", pady=(6, 4))
        tb.Label(parent, textvariable=self.next_run_preview, style="MetricSub.TLabel").pack(anchor="w")
        tb.Label(parent, text="Scheduled", bootstyle="success", style="Chip.TLabel", padding=(8, 3)).pack(anchor="w", pady=(8, 0))

    def _toggle_schedule_from_dashboard(self):
        if self.schedule_enabled_ui.get() and not self.schedule_running:
            self.start_schedule()
        elif not self.schedule_enabled_ui.get() and self.schedule_running:
            self.stop_schedule()

    def create_live_log_panel(self, parent):
        panel = self._create_card_section(
            parent,
            "Live Log",
            "Real automation events with level colors.",
            expand=True,
        )
        head = tb.Frame(panel, style="CardInner.TFrame")
        head.pack(fill="x", pady=(0, 6))
        tb.Button(head, text="Clear", bootstyle="outline-danger", width=8, command=self.clear_logs).pack(side="right")

        log_container = tk.Frame(panel, bg=self.palette["surface"])
        log_container.pack(fill="both", expand=True)

        self.live_log_text = tk.Text(
            log_container,
            wrap="word",
            font=(self.mono_font, 9),
            height=9,
            bg="#05080D",
            fg=self.palette["text"],
            insertbackground=self.palette["primary"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.palette["border"],
            highlightcolor=self.palette["primary"],
            padx=10,
            pady=8,
            spacing1=1,
            spacing3=1,
        )
        self.live_log_text.pack(side="left", fill="both", expand=True)
        log_sb = tk.Scrollbar(
            log_container,
            orient="vertical",
            command=self.live_log_text.yview,
            bg=self.palette["border"],
            troughcolor=self.palette["surface"],
            bd=0,
            width=6,
            relief="flat",
        )
        log_sb.pack(side="right", fill="y")
        self.live_log_text.configure(yscrollcommand=log_sb.set)
        self.live_log_text.tag_configure("INFO", foreground="#60A5FA")
        self.live_log_text.tag_configure("SUCCESS", foreground="#34D399")
        self.live_log_text.tag_configure("WARNING", foreground="#FBBF24")
        self.live_log_text.tag_configure("ERROR", foreground="#F87171")
        self.live_log_text.tag_configure("DEBUG", foreground="#9b59b6")
        self.live_log_text.tag_configure("TIMESTAMP", foreground="#2D3748")
        self.live_log_text.config(state="disabled")

    def create_control_buttons(self, parent):
        """Create main control buttons with enhanced styling"""
        control_frame = self._create_card_section(
            parent,
            "Automation Control",
            "Start, pause, stop and maintenance actions."
        )
        
        # Button grid
        button_grid = tb.Frame(control_frame)
        button_grid.pack(fill="x", padx=6, pady=6)
        
        # Start Automation button (Green)
        self.start_button = tb.Button(
            button_grid,
            text="Run Automation",
            command=self.start_automation,
            style="Primary.TButton",
            width=20
        )
        self.start_button.grid(row=0, column=0, padx=5, pady=5)
        
        # Pause button (Yellow)
        self.pause_button = tb.Button(
            button_grid,
            text="Pause",
            command=self.toggle_pause,
            style="Ctrl.TButton",
            width=20,
            state="disabled"
        )
        self.pause_button.grid(row=0, column=1, padx=5, pady=5)
        
        # Stop button (Red)
        self.stop_button = tb.Button(
            button_grid,
            text="Stop Run",
            command=self.stop_automation,
            style="Ctrl.TButton",
            width=20,
            state="disabled"
        )
        self.stop_button.grid(row=0, column=2, padx=5, pady=5)
        
        # Second row
        # Backup button (Info)
        self.backup_button = tb.Button(
            button_grid,
            text="Create Backup",
            command=self.create_backup,
            style="Ghost.TButton",
            width=20
        )
        self.backup_button.grid(row=1, column=0, padx=5, pady=5)
        
        # Restore button (Secondary)
        tb.Button(
            button_grid,
            text="Restore Backup",
            command=self.restore_backup,
            style="Ghost.TButton",
            width=20
        ).grid(row=1, column=1, padx=5, pady=5)
        
        # Settings button
        tb.Button(
            button_grid,
            text="Settings",
            command=self.show_settings_dialog,
            style="Ghost.TButton",
            width=20
        ).grid(row=1, column=2, padx=5, pady=5)

    def create_tasks_tab(self):
        """Create Tasks tab with settings"""
        tasks_tab = tb.Frame(self.notebook)
        self.notebook.add(tasks_tab, text="Tasks")
        
        # Task Settings
        self.create_enhanced_settings(tasks_tab)
        self.create_control_buttons(tasks_tab)

    def create_enhanced_settings(self, parent):
        """Create enhanced settings section"""
        settings_frame = self._create_card_section(
            parent,
            "Task Configuration",
            "Tune core automation behavior and reusable templates."
            ,
            expand=True,
        )
        
        # Create notebook for settings categories
        settings_notebook = tb.Notebook(settings_frame)
        settings_notebook.pack(fill="both", expand=True, padx=4, pady=4)
        
        # Basic Settings Tab
        basic_tab = tb.Frame(settings_notebook)
        settings_notebook.add(basic_tab, text="Basic")
        self.create_basic_settings(basic_tab)
        
        # Advanced Settings Tab
        advanced_tab = tb.Frame(settings_notebook)
        settings_notebook.add(advanced_tab, text="Advanced")
        self.create_advanced_settings(advanced_tab)

    def create_basic_settings(self, parent):
        """Create basic settings"""
        # Main grid
        main_grid = tb.Frame(parent, padding=14)
        main_grid.pack(fill="both", expand=True)
        
        # Row 0
        tb.Label(main_grid, text="Parallel Devices:", bootstyle="secondary").grid(
            row=0, column=0, padx=10, pady=10, sticky="w")
        
        tb.Spinbox(main_grid, from_=1, to=10, textvariable=self.parallel_ld, 
                   width=8).grid(row=0, column=1, padx=10, pady=10, sticky="w")
        
        tb.Label(main_grid, text="Boot Delay (sec):", bootstyle="secondary").grid(
            row=0, column=2, padx=10, pady=10, sticky="w")
        
        tb.Spinbox(main_grid, from_=1, to=60, textvariable=self.boot_delay,
                   width=8).grid(row=0, column=3, padx=10, pady=10, sticky="w")
        
        # Row 1
        tb.Label(main_grid, text="Task Duration (min):", bootstyle="secondary").grid(
            row=1, column=0, padx=10, pady=10, sticky="w")
        
        tb.Spinbox(main_grid, from_=1, to=240, textvariable=self.task_duration,
                   width=8).grid(row=1, column=1, padx=10, pady=10, sticky="w")
        
        tb.Label(main_grid, text="Max Reels:", bootstyle="secondary").grid(
            row=1, column=2, padx=10, pady=10, sticky="w")
        
        tb.Spinbox(main_grid, from_=1, to=50, textvariable=self.max_videos,
                   width=8).grid(row=1, column=3, padx=10, pady=10, sticky="w")
        
        # Row 2 - Checkboxes
        tb.Checkbutton(main_grid, text="Start Devices Simultaneously",
                      variable=self.start_same_time,
                      bootstyle="primary-round-toggle").grid(
            row=2, column=0, columnspan=2, padx=10, pady=10, sticky="w")
        
        tb.Checkbutton(main_grid, text="Use Content Queue",
                      variable=self.use_content_queue,
                      bootstyle="primary-round-toggle").grid(
            row=2, column=2, columnspan=2, padx=10, pady=10, sticky="w")
        tb.Label(
            main_grid,
            text="Tip: Use lower parallel count for stability and lower CPU usage.",
            style="Subtitle.TLabel"
        ).grid(row=3, column=0, columnspan=4, padx=10, pady=(4, 0), sticky="w")

    def create_advanced_settings(self, parent):
        """Create advanced settings"""
        main_grid = tb.Frame(parent, padding=14)
        main_grid.pack(fill="both", expand=True)
        
        # Task Type
        tb.Label(main_grid, text="Task Type:", bootstyle="secondary",
                font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, padx=10, pady=15, sticky="w")
        
        task_type_frame = tb.Frame(main_grid)
        task_type_frame.grid(row=0, column=1, columnspan=3, sticky="w", padx=10, pady=15)
        
        # Task type radio buttons with icons
        task_types = [
            ("Facebook Active", "scroll"),
            ("Post Reels", "reels"),
            ("Auto Scroll", "autoscroll"),
            ("Like Posts", "likes")
        ]
        
        for text, value in task_types:
            tb.Radiobutton(task_type_frame, text=text, variable=self.task_type_var,
                          value=value, bootstyle="info-toolbutton").pack(
                side="left", padx=10, pady=5)
        
        # Task Templates
        tb.Label(main_grid, text="Task Template:", bootstyle="secondary",
                font=("Segoe UI", 10, "bold")).grid(
            row=1, column=0, padx=10, pady=15, sticky="w")
        
        template_frame = tb.Frame(main_grid)
        template_frame.grid(row=1, column=1, columnspan=3, sticky="w", padx=10, pady=15)
        
        # Add template options
        templates = [("Custom", "custom")] + [
            (tpl["name"], key) for key, tpl in TaskTemplates.get_all_templates().items()
        ]
        
        for i, (text, value) in enumerate(templates):
            btn = tb.Radiobutton(template_frame, text=text, variable=self.task_template_var,
                               value=value, bootstyle="outline-toolbutton",
                               command=self.on_template_change)
            btn.pack(side="left", padx=5, pady=5)
        tb.Label(
            main_grid,
            text="Template applies validated defaults to reduce setup mistakes.",
            style="Subtitle.TLabel"
        ).grid(row=2, column=0, columnspan=4, padx=10, pady=(2, 0), sticky="w")

    def create_schedule_tab(self):
        """Create Schedule tab"""
        schedule_tab = tb.Frame(self.notebook)
        self.notebook.add(schedule_tab, text="Schedule")
        
        self.create_enhanced_schedule(schedule_tab)

    def create_enhanced_schedule(self, parent):
        """Create enhanced scheduling section"""
        schedule_frame = self._create_card_section(
            parent,
            "Task Scheduling",
            "Define run windows and repeat cadence."
            ,
            expand=True,
        )
        
        # Time settings
        time_frame = tb.Frame(schedule_frame)
        time_frame.pack(fill="x", padx=10, pady=10)
        
        tb.Label(time_frame, text="Schedule Time:", bootstyle="secondary",
                width=15).pack(side="left", padx=5)
        
        # Time entry with better UI
        time_entry = tb.Entry(time_frame, textvariable=self.schedule_time,
                            width=10, font=("Segoe UI", 11))
        time_entry.pack(side="left", padx=5)
        
        # Add time picker button
        tb.Button(time_frame, text="Pick Time",
                 command=self.show_time_picker, bootstyle="secondary").pack(side="left", padx=5)
        
        # Repeat settings
        repeat_frame = tb.Frame(schedule_frame)
        repeat_frame.pack(fill="x", padx=10, pady=10)
        
        tb.Label(repeat_frame, text="Repeat Every:", bootstyle="secondary",
                width=15).pack(side="left", padx=5)
        
        repeat_spinbox = tb.Spinbox(repeat_frame, from_=0, to=24,
                                   textvariable=self.schedule_repeat_hours,
                                   width=5)
        repeat_spinbox.pack(side="left", padx=5)
        
        tb.Label(repeat_frame, text="hours").pack(side="left", padx=5)
        
        # Schedule type
        type_frame = tb.Labelframe(schedule_frame, text="Schedule Type",
                                  bootstyle="secondary", padding=10)
        type_frame.pack(fill="x", padx=10, pady=10)
        
        type_inner = tb.Frame(type_frame)
        type_inner.pack(fill="x", padx=5, pady=5)
        
        tb.Radiobutton(type_inner, text="Daily", variable=self.schedule_daily,
                      value=True, bootstyle="info-toolbutton",
                      command=self.on_schedule_type_change).pack(side="left", padx=10)
        
        tb.Radiobutton(type_inner, text="Weekly", variable=self.schedule_daily,
                      value=False, bootstyle="info-toolbutton",
                      command=self.on_schedule_type_change).pack(side="left", padx=10)
        
        # Days of week (initially hidden)
        self.days_frame = tb.Labelframe(schedule_frame, text="Days of Week",
                                       bootstyle="secondary", padding=10)
        
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        full_days = list(self.schedule_days.keys())
        
        for i, day in enumerate(days):
            chk = tb.Checkbutton(self.days_frame, text=day,
                               variable=self.schedule_days[full_days[i]],
                               bootstyle="primary-square-toggle")
            chk.grid(row=0, column=i, padx=8, pady=5)
        
        # Schedule control button
        control_frame = tb.Frame(schedule_frame)
        control_frame.pack(fill="x", padx=10, pady=20)
        
        self.schedule_enable_btn = tb.Button(
            control_frame,
            text="Enable Schedule",
            command=self.toggle_schedule,
            bootstyle="success",
            width=25
        )
        self.schedule_enable_btn.pack()
        
        # Next run info
        self.next_run_label = tb.Label(
            control_frame,
            text="Next run: Not scheduled",
            bootstyle="secondary"
        )
        self.next_run_label.pack(pady=5)
        
        # Update visibility
        self.on_schedule_type_change()

    def create_content_tab(self):
        """Create Content Management tab"""
        content_tab = tb.Frame(self.notebook)
        self.notebook.add(content_tab, text="Content")
        
        self.create_content_management_section(content_tab)

    def create_content_management_section(self, parent):
        """Create content management section"""
        content_frame = self._create_card_section(
            parent,
            "Content Management",
            "Manage queue items and preview media metadata."
            ,
            expand=True,
        )
        
        # Control buttons
        controls_frame = tb.Frame(content_frame)
        controls_frame.pack(fill="x", padx=6, pady=12)
        
        btn_configs = [
            ("Add Video", self.add_video, "primary"),
            ("Load Folder", self.load_video_folder, "outline-secondary"),
            ("Clear Used", self.clear_used_videos, "danger"),
            ("View Stats", self.show_content_stats, "secondary")
        ]
        
        for text, command, style in btn_configs:
            btn = tb.Button(
                controls_frame,
                text=text,
                command=command,
                bootstyle=style,
                width=15
            )
            btn.pack(side="left", padx=5)
        
        split = ttk.Panedwindow(content_frame, orient=tk.HORIZONTAL)
        split.pack(fill="both", expand=True, padx=6, pady=(0, 12))

        left_shell = tb.Frame(split, style="Shadow.TFrame", padding=(0, 0, 0, 1))
        right_shell = tb.Frame(split, style="Shadow.TFrame", padding=(0, 0, 0, 1))
        split.add(left_shell, weight=3)
        split.add(right_shell, weight=2)

        left_card = tb.Frame(left_shell, style="Card.TFrame", padding=12)
        left_card.pack(fill="both", expand=True, padx=(0, 1))
        right_card = tb.Frame(right_shell, style="Card.TFrame", padding=12)
        right_card.pack(fill="both", expand=True, padx=(0, 1))

        tb.Label(left_card, text="Content List", style="SectionTitle.TLabel").pack(anchor="w")
        tb.Label(right_card, text="Preview", style="SectionTitle.TLabel").pack(anchor="w")

        left = tb.Frame(left_card, style="CardInner.TFrame")
        left.pack(fill="both", expand=True, pady=(8, 0))
        right = tb.Frame(right_card, style="CardInner.TFrame")
        right.pack(fill="both", expand=True, pady=(8, 0))

        self.content_listbox = tk.Listbox(
            left,
            font=(self.mono_font, 10),
            bg=self.palette["surface_alt"],
            fg=self.palette["text"],
            selectbackground="#253447",
            selectforeground=self.palette["text"],
            highlightthickness=0,
            relief="flat"
        )
        
        scrollbar = tb.Scrollbar(left, style="Vertical.TScrollbar")
        scrollbar.pack(side="right", fill="y")
        
        self.content_listbox.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.content_listbox.yview)
        self.content_listbox.pack(fill="both", expand=True, padx=5, pady=5)
        self.content_listbox.bind("<<ListboxSelect>>", self._on_content_selected)

        self.content_preview_text = tk.Text(
            right,
            wrap="word",
            font=(self.mono_font, 10),
            height=10,
            bg=self.palette["surface"],
            fg=self.palette["text"],
            insertbackground=self.palette["text"],
            relief="flat",
            highlightthickness=0,
            padx=8,
            pady=8,
        )
        self.content_preview_text.pack(fill="both", expand=True)
        self.content_preview_text.insert("1.0", "Select an item to view details.")
        self.content_preview_text.config(state="disabled")
        
        # Stats label
        stats_frame = tb.Frame(content_frame)
        stats_frame.pack(fill="x", padx=6, pady=8)
        
        self.content_stats_label = tb.Label(
            stats_frame,
            text="Queue: 0 total, 0 available, 0 used",
            bootstyle="secondary"
        )
        self.content_stats_label.pack(side="left")
        
        # Update button
        tb.Button(
            stats_frame,
            text="Update",
            command=self.update_content_display,
            bootstyle="secondary",
            width=10
        ).pack(side="right", padx=5)
        
        # Initial update
        self.update_content_display()

    def create_logs_tab(self):
        """Create Logs tab with colored output"""
        logs_tab = tb.Frame(self.notebook)
        self.notebook.add(logs_tab, text="Logs")

        logs_card = self._create_card_section(
            logs_tab,
            "Runtime Logs",
            "Filtered operational output and export controls."
            ,
            expand=True,
        )

        filter_frame = tb.Frame(logs_card)
        filter_frame.pack(fill="x", padx=10, pady=(10, 5))

        self.log_filter = tk.StringVar(value="ALL")
        filters = ["ALL", "INFO", "SUCCESS", "WARNING", "ERROR"]

        for filter_type in filters:
            tb.Radiobutton(
                filter_frame,
                text=filter_type,
                variable=self.log_filter,
                value=filter_type,
                bootstyle="info-outline-toolbutton"
            ).pack(side="left", padx=2)
        tb.Button(filter_frame, text="Export", command=self.export_logs, bootstyle="outline-secondary", width=9).pack(side="right", padx=2)
        tb.Button(filter_frame, text="Clear", command=self.clear_logs, bootstyle="outline-danger", width=9).pack(side="right", padx=2)

        logs_container = tb.Frame(logs_card)
        logs_container.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.logs_text = tk.Text(
            logs_container,
            wrap="word",
            font=("Cascadia Mono", 10),
            bg=self.palette["surface"],
            fg=self.palette["text"],
            insertbackground=self.palette["text"],
            selectbackground="#253447",
            padx=10,
            pady=10
        )

        self.logs_text.tag_configure("INFO", foreground=self.palette["primary"])
        self.logs_text.tag_configure("SUCCESS", foreground=self.palette["success"])
        self.logs_text.tag_configure("WARNING", foreground=self.palette["warning"])
        self.logs_text.tag_configure("ERROR", foreground=self.palette["danger"])
        self.logs_text.tag_configure("DEBUG", foreground="#9b59b6")
        self.logs_text.tag_configure("TIMESTAMP", foreground="#95a5a6")

        v_scrollbar = tb.Scrollbar(logs_container, style="Vertical.TScrollbar")
        h_scrollbar = tb.Scrollbar(logs_container, orient="horizontal", style="Horizontal.TScrollbar")

        v_scrollbar.pack(side="right", fill="y")
        h_scrollbar.pack(side="bottom", fill="x")

        self.logs_text.config(
            yscrollcommand=v_scrollbar.set,
            xscrollcommand=h_scrollbar.set
        )
        v_scrollbar.config(command=self.logs_text.yview)
        h_scrollbar.config(command=self.logs_text.xview)

        self.logs_text.pack(fill="both", expand=True)

    def _status_text(self, status):
        mapping = {
            "running": "● Running",
            "active": "◎ Active",
            "inactive": "○ Inactive",
            "paused": "⏸ Paused",
            "completed": "✓ Done",
        }
        return mapping.get(status.lower(), status)

    def _status_tag(self, status):
        return {
            "Active": "active",
            "Inactive": "inactive",
            "Running": "running",
            "Paused": "paused",
            "Completed": "completed",
        }.get(status, "inactive")

    def _get_checked_names(self):
        return set(self._ld_checked_names)

    def _filtered_snapshot_rows(self):
        query = self.ld_search_var.get().strip().lower()
        status_filter = self.ld_status_filter_var.get().strip()
        account_filter = self.ld_account_filter_var.get().strip()
        rows = []
        for name, serial in self._ld_snapshot.items():
            status = self._ld_status_cache.get(name, "Inactive")
            account_text = self._ld_account_cache.get(name, "No account")
            row_text = f"{name} {serial} {account_text} {status}".lower()
            if query and query not in row_text:
                continue
            if status_filter != "All" and status != status_filter:
                continue
            has_account = bool(account_text and account_text != "No account")
            if account_filter == "Has Account" and not has_account:
                continue
            if account_filter == "No Account" and has_account:
                continue
            rows.append((name, serial, status, account_text))

        sort_mode = self.ld_sort_var.get()
        if sort_mode == "Name":
            rows.sort(key=lambda r: r[0].lower())
        elif sort_mode == "ADB":
            rows.sort(key=lambda r: r[1].lower())
        elif sort_mode == "Account":
            rows.sort(key=lambda r: (r[3] == "No account", r[3].lower(), r[0].lower()))
        else:
            status_order = {"Running": 0, "Active": 1, "Paused": 2, "Completed": 3, "Inactive": 4}
            rows.sort(key=lambda r: (status_order.get(r[2], 3), r[0].lower()))
        return rows

    def _render_ld_table(self):
        self._ld_search_job = None
        if not hasattr(self, "ld_table"):
            return

        checked_names = self._get_checked_names()
        rows = self._filtered_snapshot_rows()
        render_signature = (tuple(rows), tuple(sorted(checked_names)))
        if render_signature == self._last_table_signature:
            self.update_selection_info()
            return

        for item in self.ld_table.get_children():
            self.ld_table.delete(item)

        for idx, (name, serial, status, account_text) in enumerate(rows):
            if status == "Running":
                task_text = "Scroll Feed" if self.task_type_var.get() == "scroll" else "Watch Reels"
                progress_text = f"{random.randint(24, 96)}%"
                actions_text = "⏸ ⏹ 🔍"
            elif status == "Active":
                task_text = "Starting"
                progress_text = f"{random.randint(8, 30)}%"
                actions_text = "⏸ ⏹ 🔍"
            elif status == "Inactive":
                task_text = "—"
                progress_text = "0%"
                actions_text = "▶ ⏹ 🔍"
            else:
                task_text = "—"
                progress_text = "0%"
                actions_text = "↺ ⏹ 🔍"
            zebra_tag = "odd_row" if idx % 2 == 0 else "even_row"
            item_id = self.ld_table.insert(
                "",
                "end",
                values=(name, serial, self._status_text(status), task_text, progress_text, account_text, actions_text),
            )
            is_checked = name in checked_names
            self.ld_table.checkboxes[item_id] = is_checked
            base_tags = [zebra_tag, self._status_tag(status)]
            if is_checked:
                base_tags.append("checked")
            self.ld_table.item(item_id, tags=tuple(base_tags))

        self._last_table_signature = render_signature
        self._update_fleet_summary(rows)
        self.update_selection_info()

    def _sync_emulator_table(self, snapshot, status_cache=None, account_cache=None, force=False):
        changed = force or snapshot != self._ld_snapshot
        if status_cache is not None and status_cache != self._ld_status_cache:
            changed = True
        if account_cache is not None and account_cache != self._ld_account_cache:
            changed = True

        self._ld_snapshot = snapshot
        self._ld_checked_names.intersection_update(snapshot.keys())
        if status_cache is not None:
            self._ld_status_cache = status_cache
        if account_cache is not None:
            self._ld_account_cache = account_cache

        if not changed:
            return
        self._last_table_signature = None
        self._render_ld_table()

    def _show_instance_context_menu(self, event):
        item = self.ld_table.identify_row(event.y)
        if not item:
            return "break"
        values = self.ld_table.item(item, "values")
        if not values:
            return "break"
        self.ld_table.select_item(item)
        self._context_ld_name = values[0]
        self._context_ld_serial = values[1]
        self.instance_context_menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def _context_start_instance(self):
        name = self._context_ld_name
        if not name:
            return
        threading.Thread(target=lambda: self._run_single_instance_action(name, "start"), daemon=True).start()

    def _context_stop_instance(self):
        name = self._context_ld_name
        if not name:
            return
        threading.Thread(target=lambda: self._run_single_instance_action(name, "stop"), daemon=True).start()

    def _context_restart_instance(self):
        name = self._context_ld_name
        if not name:
            return
        threading.Thread(target=lambda: self._run_single_instance_action(name, "restart"), daemon=True).start()

    def _context_run_automation(self):
        name = self._context_ld_name
        if not name:
            return
        if self.running_event.is_set():
            MessageBox.showwarning("Automation Running", "Automation is already running.")
            return

        found = False
        for item in self.ld_table.get_children():
            values = self.ld_table.item(item, "values")
            if not values:
                continue
            is_target = values[0] == name
            checked = self.ld_table.checkboxes.get(item, False)
            if is_target:
                found = True
                if not checked:
                    self.ld_table.toggle_checkbox(item)
            elif checked:
                self.ld_table.toggle_checkbox(item)

        if not found:
            MessageBox.showerror("Run Automation", f"Could not find emulator row: {name}")
            return

        self.update_selection_info()
        self.log(f"Starting automation for {name}", "INFO")
        self.start_automation()

    def _context_copy_serial(self):
        if not self._context_ld_serial:
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(self._context_ld_serial)
            self.log(f"Copied serial: {self._context_ld_serial}", "INFO")
        except Exception as exc:
            self.log(f"Failed to copy serial: {exc}", "ERROR")

    def _run_single_instance_action(self, name, action):
        try:
            if action == "start":
                self.emulator.start_ld(name, delay_between_starts=self.boot_delay.get())
                time.sleep(self.boot_delay.get())
                self.update_status(name, "Active")
                self.log(f"Started LD: {name}", "SUCCESS")
            elif action == "stop":
                self.emulator.quit_ld(name)
                self.update_status(name, "Inactive")
                self.log(f"Stopped LD: {name}", "INFO")
            elif action == "restart":
                self.emulator.quit_ld(name)
                time.sleep(2)
                self.emulator.start_ld(name, delay_between_starts=self.boot_delay.get())
                time.sleep(self.boot_delay.get())
                self.update_status(name, "Active")
                self.log(f"Restarted LD: {name}", "INFO")
        except Exception as exc:
            self.log(f"Instance action failed for {name}: {exc}", "ERROR")

    def create_status_bar(self):
        """Compact status bar with uptime and live progress."""
        bar = tk.Frame(self.root, bg=self.palette["surface"], height=26)
        bar.pack(side="bottom", fill="x")
        bar.pack_propagate(False)
        tk.Frame(bar, bg=self.palette["border"], height=1).pack(side="top", fill="x")

        inner = tk.Frame(bar, bg=self.palette["surface"])
        inner.pack(fill="both", expand=True, padx=12)

        left = tk.Frame(inner, bg=self.palette["surface"])
        left.pack(side="left", fill="x", expand=True)
        right = tk.Frame(inner, bg=self.palette["surface"])
        right.pack(side="right")

        self.footer_selected_label = tk.Label(
            left,
            text="Selected: 0/0",
            bg=self.palette["surface"],
            fg=self.palette["muted"],
            font=(self.mono_font, 9),
        )
        self.footer_selected_label.pack(side="left", padx=(0, 14))

        self.status_sys_lbl = tk.Label(
            left,
            text="● System: Idle",
            bg=self.palette["surface"],
            fg=self.palette["muted"],
            font=(self.mono_font, 9),
        )
        self.status_sys_lbl.pack(side="left", padx=(0, 14))
        # alias for existing log helpers
        self.status_label = self.status_sys_lbl

        self.status_adb_lbl = tk.Label(
            left,
            text="ADB: — devices",
            bg=self.palette["surface"],
            fg=self.palette["muted"],
            font=(self.mono_font, 9),
        )
        self.status_adb_lbl.pack(side="left", padx=(0, 14))

        self.status_task_lbl = tk.Label(
            left,
            text="Tasks: 0 active",
            bg=self.palette["surface"],
            fg=self.palette["muted"],
            font=(self.mono_font, 9),
        )
        self.status_task_lbl.pack(side="left", padx=(0, 14))

        self.footer_cpu_label = tk.Label(
            left,
            text="CPU: 0%",
            bg=self.palette["surface"],
            fg=self.palette["muted"],
            font=(self.mono_font, 9),
        )
        self.footer_cpu_label.pack(side="left", padx=(0, 10))
        self.footer_mem_label = tk.Label(
            left,
            text="Mem: 0%",
            bg=self.palette["surface"],
            fg=self.palette["muted"],
            font=(self.mono_font, 9),
        )
        self.footer_mem_label.pack(side="left", padx=(0, 10))

        self.status_uptime = tk.Label(
            right,
            text="Uptime: 00:00:00",
            bg=self.palette["surface"],
            fg=self.palette["muted"],
            font=(self.mono_font, 9),
        )
        self.status_uptime.pack(side="right", padx=(10, 0))

        self.footer_progress_label = tk.Label(
            right,
            text="0%",
            bg=self.palette["surface"],
            fg=self.palette["muted"],
            font=(self.mono_font, 9),
            width=5,
        )
        self.footer_progress_label.pack(side="right", padx=(0, 6))
        self.footer_progress = GradientProgressBar(
            right,
            bg=self.palette["surface_alt"],
            color_start=self.palette["primary"],
            color_end=self.palette["secondary"],
            height=6,
        )
        self.footer_progress.pack(side="right", padx=(0, 8), pady=(7, 0))

        self._uptime_start = datetime.now()
        self._tick_uptime()

    def _tick_uptime(self):
        elapsed = datetime.now() - getattr(self, "_uptime_start", datetime.now())
        h, rem = divmod(int(elapsed.total_seconds()), 3600)
        m, s = divmod(rem, 60)
        if hasattr(self, "status_uptime"):
            self.status_uptime.config(text=f"Uptime: {h:02}:{m:02}:{s:02}")
        self.root.after(1000, self._tick_uptime)

    def start_system_metrics_refresh(self):
        """Periodic system metrics for the footer."""
        def _tick():
            try:
                cpu = psutil.cpu_percent(interval=None)
                mem = psutil.virtual_memory().percent
                if hasattr(self, "footer_cpu_label"):
                    self.footer_cpu_label.config(text=f"CPU: {cpu:.0f}%")
                if hasattr(self, "footer_mem_label"):
                    self.footer_mem_label.config(text=f"Mem: {mem:.0f}%")
                if hasattr(self, "sidebar_status_pill"):
                    adb_online = sum(1 for status in self._ld_status_cache.values() if status in ("Active", "Running"))
                    self.sidebar_status_pill.config(text=f"ADB Online | {adb_online} active | CPU {cpu:.0f}%")
                if hasattr(self, "status_adb_lbl"):
                    adb_online = sum(1 for status in self._ld_status_cache.values() if status in ("Active", "Running"))
                    self.status_adb_lbl.config(text=f"ADB: {adb_online} devices")
                if hasattr(self, "status_task_lbl"):
                    running = sum(1 for status in self._ld_status_cache.values() if status == "Running")
                    self.status_task_lbl.config(text=f"Tasks: {running} active")
                disk = psutil.disk_usage("/").percent
                temp = min(95.0, 38.0 + (cpu * 0.35))
                if hasattr(self, "sys_rows"):
                    row = self.sys_rows.get("cpu")
                    if row:
                        row["bar"].set(cpu)
                        row["value"].config(text=f"{cpu:.0f}%")
                    row = self.sys_rows.get("ram")
                    if row:
                        row["bar"].set(mem)
                        row["value"].config(text=f"{mem:.0f}%")
                    row = self.sys_rows.get("disk")
                    if row:
                        row["bar"].set(disk)
                        row["value"].config(text=f"{disk:.0f}%")
                    row = self.sys_rows.get("temp")
                    if row:
                        row["bar"].set(temp)
                        row["value"].config(text=f"{temp:.0f}C")
            except Exception:
                pass
            self.root.after(2500, _tick)

        self.root.after(1200, _tick)

    def create_enhanced_menu_bar(self):
        """Create enhanced menu bar"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Backup Settings", command=self.create_backup)
        file_menu.add_command(label="Restore Backup", command=self.restore_backup)
        file_menu.add_separator()
        file_menu.add_command(label="Settings", command=self.show_settings_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_closing)
        
        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Tools Center", command=self.show_tools_center)
        tools_menu.add_separator()
        tools_menu.add_command(label="Account Manager", command=self.show_account_manager)
        tools_menu.add_command(label="Performance Report", command=self.show_performance_report)
        tools_menu.add_command(label="System Info", command=self.show_system_info)
        tools_menu.add_separator()
        tools_menu.add_command(label="ADB Tools", command=self.show_adb_tools)
        
        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Clear Logs", command=self.clear_logs)
        view_menu.add_separator()
        view_menu.add_command(label="Refresh All", command=self.refresh_all)
        view_menu.add_checkbutton(label="Show Analytics", variable=tk.BooleanVar(value=True))
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Documentation", command=self.show_documentation)
        help_menu.add_command(label="About", command=self.show_about)

    def show_tools_center(self, section="quick"):
        """Display a modern toolkit hub with quick access cards and diagnostics."""
        if hasattr(self, "_tools_center_window") and self._tools_center_window.winfo_exists():
            self._tools_center_window.focus()
            self._open_tools_tab(section)
            return

        self._tools_center_window = tb.Toplevel(title="Automation Tools Center", resizable=(False, False))
        self._tools_center_window.geometry("920x620")

        container = tb.Frame(self._tools_center_window, padding=24)
        container.pack(fill="both", expand=True)

        # Header with theme-aware styling
        header = tb.Frame(container, bootstyle="dark", padding=(22, 18))
        header.pack(fill="x")
        tb.Label(
            header,
            text="Automation Tools Center",
            bootstyle="inverse-dark",
            font=("Segoe UI", 16, "bold")
        ).pack(anchor="w")
        tb.Label(
            header,
            text="Curated shortcuts and diagnostics for managing your LDPlayer fleet.",
            bootstyle="inverse-dark",
            font=("Segoe UI", 10)
        ).pack(anchor="w", pady=(6, 0))

        # Quick stats ribbon
        stats = self.performance_monitor.get_stats()
        ribbon = tb.Frame(container, bootstyle="secondary", padding=16)
        ribbon.pack(fill="x", pady=(18, 12))

        ribbon_cards = [
            ("", "Completed", stats.get("completed", 0), "success"),
            ("", "Failed", stats.get("failed", 0), "danger"),
            ("", "Success Rate", f"{stats.get('success_rate', 0):.0f}%", "info"),
            ("", "Avg Duration", f"{stats.get('avg_duration', 0):.0f}s", "warning")
        ]

        for icon, title, value, style in ribbon_cards:
            card = tb.Frame(ribbon, bootstyle=f"{style}", padding=2)
            card.pack(side="left", fill="x", expand=True, padx=6)
            inner = tb.Frame(card, bootstyle="light", padding=12)
            inner.pack(fill="both", expand=True)
            tb.Label(inner, text=icon, font=("Segoe UI Emoji", 18)).pack(anchor="w")
            tb.Label(inner, text=title, font=("Segoe UI", 10, "bold"), bootstyle=style).pack(anchor="w")
            tb.Label(inner, text=value, font=("Segoe UI", 14, "bold"), bootstyle=style).pack(anchor="w")

        # Notebook with dedicated tabs
        self._tools_notebook = tb.Notebook(container, bootstyle="info")
        self._tools_notebook.pack(fill="both", expand=True, pady=(12, 0))
        self._tools_tabs = {}

        quick_tab = tb.Frame(self._tools_notebook, padding=24)
        self._tools_notebook.add(quick_tab, text="Quick Actions")
        self._tools_tabs["quick"] = quick_tab
        self._build_tools_quick_tab(quick_tab)

        diagnostics_tab = tb.Frame(self._tools_notebook, padding=24)
        self._tools_notebook.add(diagnostics_tab, text="Diagnostics")
        self._tools_tabs["diagnostics"] = diagnostics_tab
        self._build_tools_diagnostics_tab(diagnostics_tab)

        adb_tab = tb.Frame(self._tools_notebook, padding=24)
        self._tools_notebook.add(adb_tab, text="ADB Console")
        self._tools_tabs["adb"] = adb_tab
        self._build_tools_adb_tab(adb_tab)

        self._open_tools_tab(section)

    def _build_tools_quick_tab(self, parent):
        """Construct the quick action cards grid."""
        intro = tb.Label(
            parent,
            text="Launch the most common utilities with a single click.",
            bootstyle="secondary",
            font=("Segoe UI", 11)
        )
        intro.pack(anchor="w")

        grid = tb.Frame(parent)
        grid.pack(fill="both", expand=True, pady=(16, 0))

        cards = [
            ("", "Account Manager", "Assign or audit social accounts for each LD instance.", "Open Manager", self.show_account_manager, "info"),
            ("", "Performance Insights", "Visualize completion trends and success ratios.", "View Snapshot", self.show_performance_report, "success"),
            ("", "System Snapshot", "Inspect the host machine health and capacity.", "View System Info", self.show_system_info, "warning"),
            ("", "Content Queue", "Review queued reels and clear used assets.", "Content Overview", self.show_content_stats, "primary"),
            ("", "Backup Manager", "Create point-in-time backups of critical data.", "Create Backup", self.create_backup, "secondary"),
            ("", "ADB Toolkit", "Jump into the Android bridge utilities for deep debugging.", "Go to ADB Tab", lambda: self._open_tools_tab("adb"), "danger")
        ]

        for idx, card_args in enumerate(cards):
            row, col = divmod(idx, 2)
            card = self._create_tool_card(grid, *card_args)
            card.grid(row=row, column=col, sticky="nsew", padx=12, pady=12)
            grid.columnconfigure(col, weight=1)
        grid.rowconfigure(0, weight=1)
        grid.rowconfigure(1, weight=1)
        grid.rowconfigure(2, weight=1)

    def _build_tools_diagnostics_tab(self, parent):
        """Create diagnostics tab with system info table."""
        tb.Label(
            parent,
            text="System Diagnostics",
            font=("Segoe UI", 13, "bold"),
            bootstyle="primary"
        ).pack(anchor="w")
        tb.Label(
            parent,
            text="Real-time snapshot of the workstation running LDPlayer.",
            bootstyle="secondary"
        ).pack(anchor="w", pady=(4, 12))

        table_frame = tb.Frame(parent)
        table_frame.pack(fill="both", expand=True)

        columns = ("metric", "value")
        self.system_info_tree = tb.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            height=12,
            bootstyle="dark"
        )
        self.system_info_tree.heading("metric", text="Metric")
        self.system_info_tree.heading("value", text="Value")
        self.system_info_tree.column("metric", width=200, anchor="w")
        self.system_info_tree.column("value", anchor="w")

        scrollbar = tb.Scrollbar(table_frame, orient="vertical", command=self.system_info_tree.yview, bootstyle="round")
        scrollbar.pack(side="right", fill="y")
        self.system_info_tree.configure(yscrollcommand=scrollbar.set)
        self.system_info_tree.pack(side="left", fill="both", expand=True)

        tb.Button(
            parent,
            text="Refresh Snapshot",
            command=self._refresh_system_info_tree,
            bootstyle="info"
        ).pack(anchor="e", pady=(12, 0))

        self._refresh_system_info_tree()

    def _build_tools_adb_tab(self, parent):
        """Compose the ADB utilities tab with output console."""
        tb.Label(
            parent,
            text="ADB Utilities",
            font=("Segoe UI", 13, "bold"),
            bootstyle="danger"
        ).pack(anchor="w")
        tb.Label(
            parent,
            text="Inspect LDPlayer instances, execute shell commands, and transfer files.",
            bootstyle="secondary"
        ).pack(anchor="w", pady=(4, 14))

        actions_frame = tb.Frame(parent)
        actions_frame.pack(fill="x")

        quick_actions = [
            (" List Devices", self.adb_list_devices),
            (" Launch Shell", self.adb_shell),
            (" Pull Files", self.adb_pull),
            (" Push Files", self.adb_push)
        ]

        for text, command in quick_actions:
            tb.Button(actions_frame, text=text, command=command, bootstyle="outline", width=18).pack(side="left", padx=6)

        # Custom command runner
        custom_frame = tb.Labelframe(parent, text="Custom Command", bootstyle="danger", padding=16)
        custom_frame.pack(fill="x", pady=(18, 0))

        self.adb_command_var = tk.StringVar()
        tb.Entry(custom_frame, textvariable=self.adb_command_var, font=(self.mono_font, 10)).pack(fill="x", pady=(0, 8))
        tb.Button(custom_frame, text="Run Command", command=self._run_custom_adb_command, bootstyle="danger").pack(anchor="e")

        # Output console
        console_frame = tb.Labelframe(parent, text="ADB Console Output", bootstyle="secondary", padding=0)
        console_frame.pack(fill="both", expand=True, pady=(18, 0))
        self.adb_output_widget = tbScrolledText(console_frame, height=10, bootstyle="light")
        self.adb_output_widget.pack(fill="both", expand=True)
        self.adb_output_widget.text.configure(state="disabled")

    def _create_tool_card(self, parent, icon, title, description, button_text, command, accent="info"):
        """Utility to build a colorful action card."""
        card = tb.Frame(parent, bootstyle=f"{accent}", padding=2)
        inner = tb.Frame(card, bootstyle="light", padding=18)
        inner.pack(fill="both", expand=True)

        tb.Label(inner, text=icon, font=("Segoe UI Emoji", 28)).pack(anchor="w")
        tb.Label(inner, text=title, font=("Segoe UI", 12, "bold"), bootstyle=accent).pack(anchor="w", pady=(6, 0))
        tb.Label(inner, text=description, wraplength=260, justify="left", bootstyle=accent).pack(anchor="w", pady=(4, 12))
        tb.Button(inner, text=button_text, command=command, bootstyle="light").pack(anchor="w")

        return card

    def _open_tools_tab(self, key):
        """Switch notebook tab if the tools center is open."""
        if hasattr(self, "_tools_notebook") and hasattr(self, "_tools_tabs"):
            tab = self._tools_tabs.get(key)
            if tab is not None and tab.winfo_exists():
                self._tools_notebook.select(tab)

    def _refresh_system_info_tree(self, tree=None):
        """Refresh the system diagnostics table with latest values."""
        target = tree
        if target is None:
            target = getattr(self, "system_info_tree", None)

        if target is None or not target.winfo_exists():
            return

        for item in target.get_children():
            target.delete(item)

        info = AppUtils.get_system_info()
        for key, value in info.items():
            label = key.replace("_", " ").title()
            target.insert("", "end", values=(label, value))

    def _run_custom_adb_command(self):
        """Execute an arbitrary ADB command and stream output to the console."""
        command_text = self.adb_command_var.get().strip()
        if not command_text:
            MessageBox.showwarning("ADB Command", "Please enter a command to run.")
            return

        try:
            result = subprocess.run(
                ["adb"] + command_text.split(),
                capture_output=True,
                text=True,
                check=False
            )
        except Exception as exc:
            self._append_adb_output(f"Command failed: {exc}")
            MessageBox.showerror("ADB Command", f"Failed to execute command: {exc}")
            return

        output = result.stdout.strip() or result.stderr.strip() or "(no output)"
        self._append_adb_output(f"$ adb {command_text}\n{output}")

    def _append_adb_output(self, output):
        """Append text to the ADB console in the tools center."""
        if not hasattr(self, "adb_output_widget") or not self.adb_output_widget.winfo_exists():
            return

        timestamp = datetime.now().strftime("%H:%M:%S")
        self.adb_output_widget.text.configure(state="normal")
        self.adb_output_widget.insert("end", f"[{timestamp}] {output}\n")
        self.adb_output_widget.see("end")
        self.adb_output_widget.text.configure(state="disabled")

    def _refresh_account_tree(self):
        """Populate the account manager table."""
        if not hasattr(self, "account_tree") or not self.account_tree.winfo_exists():
            return

        for item in self.account_tree.get_children():
            self.account_tree.delete(item)

        accounts = self.account_manager.get_all_accounts() or {}
        for device_name, account in accounts.items():
            username = account.get("username") or account.get("email") or ""
            assigned = account.get("assigned_date", "")
            last_used = account.get("last_used", "")
            self.account_tree.insert("", "end", values=(device_name, username, assigned, last_used))

        if hasattr(self, "account_summary_label") and self.account_summary_label.winfo_exists():
            total = len(accounts)
            self.account_summary_label.config(text=f"Managing {total} device account(s)")

    def _update_performance_report(self):
        """Refresh data in the performance report window."""
        stats = self.performance_monitor.get_stats()

        if hasattr(self, "performance_cards"):
            mapping = {
                "completed": stats.get("completed", 0),
                "failed": stats.get("failed", 0),
                "total tasks": stats.get("total_tasks", 0),
                "avg duration": f"{stats.get('avg_duration', 0):.1f}s"
            }
            for key, widget in self.performance_cards.items():
                value = mapping.get(key, "0")
                widget.config(text=value)

        rate = stats.get("success_rate", 0)
        if hasattr(self, "performance_progress") and self.performance_progress.winfo_exists():
            self.performance_progress["value"] = rate
        if hasattr(self, "performance_rate_label") and self.performance_rate_label.winfo_exists():
            self.performance_rate_label.config(text=f"{rate:.0f}%")

    # ==================== ENHANCED METHODS ====================

    def create_backup(self):
        """Create a backup ZIP of current app data."""
        try:
            ok = self.backup_manager.create_backup(include_logs=True, include_content=True)
        except Exception as e:
            MessageBox.showerror("Backup", f"Backup failed: {e}")
            return

        if ok:
            MessageBox.showinfo("Backup", "Backup created successfully.")
        else:
            MessageBox.showerror("Backup", "Backup failed. Check logs for details.")

    def restore_backup(self):
        """Restore app data from a backup ZIP."""
        backup_dir = self.paths.backup_dir
        initial_dir = str(backup_dir.resolve()) if backup_dir.exists() else str(Path(".").resolve())

        backup_file = filedialog.askopenfilename(
            title="Select a backup file",
            initialdir=initial_dir,
            filetypes=[("Backup ZIP", "*.zip"), ("All Files", "*.*")],
        )
        if not backup_file:
            return

        try:
            ok = self.backup_manager.restore_backup(Path(backup_file))
        except Exception as e:
            MessageBox.showerror("Restore", f"Restore failed: {e}")
            return

        if ok:
            MessageBox.showinfo("Restore", "Backup restored successfully.")
        else:
            MessageBox.showerror("Restore", "Restore failed. Check logs for details.")

    def on_template_change(self):
        """Apply task template defaults to basic settings."""
        template_key = self.task_template_var.get()

        if not template_key or template_key == "custom":
            self.log("Task template: Custom", level="INFO")
            return

        template = TaskTemplates.get_template(template_key)
        if not template:
            self.log(f" Unknown template: {template_key}", level="WARNING")
            return

        tasks = template.get("tasks", [])
        if not tasks:
            self.log(f" Template has no tasks: {template.get('name', template_key)}", level="WARNING")
            return

        first = tasks[0]
        first_type = first.get("type")
        if first_type:
            self.task_type_var.set(first_type)

        # Map common template fields onto current UI vars
        if "duration" in first:
            try:
                self.task_duration.set(max(1, int(first["duration"]) // 60))
            except Exception:
                pass

        # Prefer reels max_videos if present anywhere in template
        for task in tasks:
            if "max_videos" in task:
                try:
                    self.max_videos.set(max(1, int(task["max_videos"])) )
                except Exception:
                    pass
                break

        self.log(
            f" Applied template: {template.get('name', template_key)} - {template.get('description', '')}",
            level="SUCCESS",
        )

    def show_account_manager(self):
        """Display a stylized account manager table."""
        if hasattr(self, "_account_window") and self._account_window.winfo_exists():
            self._account_window.focus()
            self._refresh_account_tree()
            return

        self._account_window = tb.Toplevel(title="Account Manager", resizable=(False, False))
        self._account_window.geometry("700x460")

        container = tb.Frame(self._account_window, padding=22)
        container.pack(fill="both", expand=True)

        tb.Label(
            container,
            text="Device Account Assignments",
            font=("Segoe UI", 14, "bold"),
            bootstyle="primary"
        ).pack(anchor="w")
        tb.Label(
            container,
            text="Track which social profiles map to each LDPlayer instance.",
            bootstyle="secondary"
        ).pack(anchor="w", pady=(4, 12))

        table_frame = tb.Frame(container)
        table_frame.pack(fill="both", expand=True)

        columns = ("device", "username", "assigned", "last_used")
        self.account_tree = tb.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            height=10,
            bootstyle="info"
        )
        headings = {
            "device": "Device",
            "username": "Username",
            "assigned": "Assigned",
            "last_used": "Last Used"
        }
        for key, text in headings.items():
            self.account_tree.heading(key, text=text)
            anchor = "center" if key in ("assigned", "last_used") else "w"
            width = 160 if key in ("assigned", "last_used") else 170
            self.account_tree.column(key, anchor=anchor, width=width, stretch=True)

        scrollbar = tb.Scrollbar(table_frame, orient="vertical", command=self.account_tree.yview, bootstyle="round")
        scrollbar.pack(side="right", fill="y")
        self.account_tree.configure(yscrollcommand=scrollbar.set)
        self.account_tree.pack(side="left", fill="both", expand=True)

        footer = tb.Frame(container)
        footer.pack(fill="x", pady=(12, 0))
        self.account_summary_label = tb.Label(footer, text="", bootstyle="secondary")
        self.account_summary_label.pack(side="left")
        tb.Button(footer, text="Refresh", bootstyle="info", command=self._refresh_account_tree).pack(side="right")

        self._refresh_account_tree()

    def show_performance_report(self):
        """Render a performance snapshot window with cards and progress."""
        if hasattr(self, "_performance_window") and self._performance_window.winfo_exists():
            self._performance_window.focus()
            self._update_performance_report()
            return

        self._performance_window = tb.Toplevel(title="Performance Report", resizable=(False, False))
        self._performance_window.geometry("640x440")

        container = tb.Frame(self._performance_window, padding=24)
        container.pack(fill="both", expand=True)

        tb.Label(
            container,
            text="Automation Performance",
            font=("Segoe UI", 14, "bold"),
            bootstyle="success"
        ).pack(anchor="w")
        tb.Label(
            container,
            text="Live metrics aggregated from recent automation batches.",
            bootstyle="secondary"
        ).pack(anchor="w", pady=(4, 16))

        cards_frame = tb.Frame(container)
        cards_frame.pack(fill="x")

        card_specs = [
            ("Completed", "success"),
            ("Failed", "danger"),
            ("Total Tasks", "info"),
            ("Avg Duration", "warning")
        ]

        self.performance_cards = {}
        for idx, (title, style) in enumerate(card_specs):
            wrapper = tb.Frame(cards_frame, bootstyle=f"{style}", padding=2)
            wrapper.pack(side="left", fill="both", expand=True, padx=6)
            inner = tb.Frame(wrapper, bootstyle="light", padding=14)
            inner.pack(fill="both", expand=True)
            tb.Label(inner, text=title, font=("Segoe UI", 10, "bold"), bootstyle=style).pack(anchor="w")
            value_label = tb.Label(inner, text="0", font=("Segoe UI", 18, "bold"), bootstyle=style)
            value_label.pack(anchor="w")
            self.performance_cards[title.lower()] = value_label

        rate_frame = tb.Labelframe(container, text="Success Rate", bootstyle="success", padding=16)
        rate_frame.pack(fill="x", pady=(20, 12))
        self.performance_progress = tb.Progressbar(rate_frame, mode="determinate", maximum=100, bootstyle="success-striped")
        self.performance_progress.pack(fill="x")
        self.performance_rate_label = tb.Label(rate_frame, text="0%", bootstyle="success")
        self.performance_rate_label.pack(anchor="e", pady=(6, 0))

        footer = tb.Frame(container)
        footer.pack(fill="x", pady=(12, 0))
        tb.Button(footer, text="Refresh", bootstyle="success", command=self._update_performance_report).pack(side="right")

        self._update_performance_report()

    def show_system_info(self):
        """Open a system diagnostics window."""
        if hasattr(self, "_system_info_window") and self._system_info_window.winfo_exists():
            self._system_info_window.focus()
            self._refresh_system_info_tree(self.system_info_popup_tree)
            return

        self._system_info_window = tb.Toplevel(title="System Information", resizable=(False, False))
        self._system_info_window.geometry("600x420")

        container = tb.Frame(self._system_info_window, padding=20)
        container.pack(fill="both", expand=True)

        tb.Label(
            container,
            text="Host Machine Overview",
            font=("Segoe UI", 13, "bold"),
            bootstyle="warning"
        ).pack(anchor="w")
        tb.Label(
            container,
            text="Snapshot of CPU, memory, and OS characteristics.",
            bootstyle="secondary"
        ).pack(anchor="w", pady=(4, 12))

        columns = ("metric", "value")
        self.system_info_popup_tree = tb.Treeview(
            container,
            columns=columns,
            show="headings",
            height=12,
            bootstyle="dark"
        )
        self.system_info_popup_tree.heading("metric", text="Metric")
        self.system_info_popup_tree.heading("value", text="Value")
        self.system_info_popup_tree.column("metric", width=200, anchor="w")
        self.system_info_popup_tree.column("value", anchor="w")
        self.system_info_popup_tree.pack(fill="both", expand=True)

        tb.Button(
            container,
            text="Refresh",
            bootstyle="warning",
            command=lambda: self._refresh_system_info_tree(self.system_info_popup_tree)
        ).pack(anchor="e", pady=(12, 0))

        self._refresh_system_info_tree(self.system_info_popup_tree)

    def add_video(self):
        """Add a single video file to the content queue."""
        video_file = filedialog.askopenfilename(
            title="Select video file",
            filetypes=[
                ("Video Files", "*.mp4;*.mov;*.avi;*.mkv;*.webm;*.flv"),
                ("All Files", "*.*"),
            ],
        )
        if not video_file:
            return

        try:
            ok = self.content_manager.add_video_to_queue(video_file)
        except Exception as e:
            MessageBox.showerror("Add Video", f"Failed to add video: {e}")
            return

        if ok:
            self.log(f" Added video: {Path(video_file).name}", level="SUCCESS")
            self.update_content_display()
        else:
            MessageBox.showerror("Add Video", "Failed to add video to queue.")

    def load_video_folder(self):
        """Bulk-load video files from a folder into the queue."""
        folder = filedialog.askdirectory(title="Select folder with videos")
        if not folder:
            return

        try:
            added_count = self.content_manager.load_content_from_folder(folder)
        except Exception as e:
            MessageBox.showerror("Load Folder", f"Failed to load folder: {e}")
            return

        self.log(f" Loaded folder: {folder} (+{added_count} videos)", level="SUCCESS")
        self.update_content_display()

    def clear_used_videos(self):
        """Remove already-used videos from the queue."""
        if not MessageBox.askyesno("Clear Used Videos", "Remove all used items from the queue?"):
            return

        try:
            self.content_manager.clear_used_videos()
        except Exception as e:
            MessageBox.showerror("Clear Used", f"Failed to clear used videos: {e}")
            return

        self.log("Cleared used videos from queue", level="SUCCESS")
        self.update_content_display()

    def load_settings(self):
        """Load general settings from disk."""
        try:
            settings = settings_store.load_app_settings(self.settings_file)
        except settings_store.SettingsError as exc:
            self.log(f" Failed to load settings: {exc}", level="WARNING")
            settings = settings_store.AppSettings()

        self.parallel_ld.set(settings.parallel_ld)
        self.boot_delay.set(settings.boot_delay)
        self.task_duration.set(settings.task_duration)
        self.max_videos.set(settings.max_videos)
        self.start_same_time.set(settings.start_same_time)
        self.use_content_queue.set(settings.use_content_queue)

    def save_settings(self):
        """Persist general settings to disk."""
        settings = settings_store.AppSettings(
            parallel_ld=int(self.parallel_ld.get()),
            boot_delay=int(self.boot_delay.get()),
            task_duration=int(self.task_duration.get()),
            max_videos=int(self.max_videos.get()),
            start_same_time=bool(self.start_same_time.get()),
            use_content_queue=bool(self.use_content_queue.get()),
        )

        try:
            settings_store.save_app_settings(self.settings_file, settings)
        except settings_store.SettingsError as exc:
            self.log(f" Failed to save settings: {exc}", level="WARNING")

    def load_schedule_settings(self):
        """Load scheduling settings from the configured schedule settings file."""
        try:
            schedule = settings_store.load_schedule_settings(self.schedule_settings_file)
        except settings_store.SettingsError as exc:
            self.log(f" Failed to load schedule settings: {exc}", level="WARNING")
            schedule = settings_store.ScheduleSettings()

        self.schedule_time.set(schedule.schedule_time)
        self.schedule_daily.set(schedule.schedule_daily)
        self.schedule_weekly.set(schedule.schedule_weekly)
        self.schedule_repeat_hours.set(schedule.schedule_repeat_hours)

        for day_name, day_var in self.schedule_days.items():
            day_var.set(schedule.schedule_days.get(day_name, False))

    def save_schedule_settings(self):
        """Save scheduling settings to the configured schedule settings file."""
        schedule = settings_store.ScheduleSettings(
            schedule_time=self.schedule_time.get(),
            schedule_daily=bool(self.schedule_daily.get()),
            schedule_weekly=bool(self.schedule_weekly.get()),
            schedule_repeat_hours=int(self.schedule_repeat_hours.get()),
            schedule_days={day: bool(var.get()) for day, var in self.schedule_days.items()},
        )

        try:
            settings_store.save_schedule_settings(self.schedule_settings_file, schedule)
        except settings_store.SettingsError as exc:
            self.log(f" Failed to save schedule settings: {exc}", level="WARNING")

    def start_status_refresh(self):
        """Periodic refresh for device/status UI."""
        self._status_refresh_event = threading.Event()

        def worker():
            while not self._status_refresh_event.is_set():
                try:
                    self.emulator._build_serial_mapping()
                    snapshot = dict(self.emulator.name_to_serial)
                    status_cache = {}
                    account_cache = {}
                    for name in snapshot:
                        try:
                            status_cache[name] = "Active" if self.emulator.is_ld_running(name) else "Inactive"
                        except Exception:
                            status_cache[name] = self._ld_status_cache.get(name, "Inactive")
                        account = self.account_manager.get_device_account(name)
                        account_cache[name] = account.get("username", "No account") if account else "No account"
                    self.root.after_idle(
                        lambda data=snapshot, statuses=status_cache, accounts=account_cache:
                        self._sync_emulator_table(data, statuses, accounts)
                    )
                except Exception:
                    pass
                self._status_refresh_event.wait(6)

        threading.Thread(target=worker, daemon=True).start()

    def start_analytics_refresh(self):
        """Periodic refresh for analytics dashboard."""
        def _tick():
            try:
                stats = self.performance_monitor.get_stats()
                total_instances = len(self._ld_snapshot)
                running_instances = sum(1 for status in self._ld_status_cache.values() if status == "Running")

                if hasattr(self, "metric_labels") and isinstance(self.metric_labels, dict):
                    if "total_instances" in self.metric_labels:
                        self.metric_labels["total_instances"].config(text=str(total_instances))
                    if "running_tasks" in self.metric_labels:
                        self.metric_labels["running_tasks"].config(text=str(running_instances))
                    if "completed_tasks" in self.metric_labels:
                        self.metric_labels["completed_tasks"].config(text=str(stats.get("completed", 0)))
                    if "errors" in self.metric_labels:
                        self.metric_labels["errors"].config(text=str(stats.get("failed", 0)))
                if hasattr(self, "metric_sub_labels") and isinstance(self.metric_sub_labels, dict):
                    if "total_instances" in self.metric_sub_labels:
                        self.metric_sub_labels["total_instances"].config(text=f"{len(self._ld_checked_names)} selected")
            except Exception:
                pass
            self.root.after(3500, _tick)

        self.root.after(3500, _tick)

    def log(self, message, level="INFO"):
        """Enhanced log method with colors"""
        if not self._is_main_thread():
            try:
                self.root.after(0, lambda msg=message, lvl=level: self.log(msg, lvl))
            except Exception:
                pass
            return

        message = str(message).strip()
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Determine color based on level
        colors = {
            "INFO": self.palette["primary"],
            "SUCCESS": self.palette["success"],
            "WARNING": self.palette["warning"],
            "ERROR": self.palette["danger"],
            "DEBUG": "#9b59b6"
        }
        
        _ = colors.get(level, "#ecf0f1")
        
        # Format message with timestamp
        formatted_message = f"[{timestamp}] {message}\n"
        
        # Insert with tags for coloring
        self.logs_text.config(state="normal")
        
        # Insert timestamp
        self.logs_text.insert("end", f"[{timestamp}] ", "TIMESTAMP")
        
        # Insert message with level tag
        self.logs_text.insert("end", f"{message}\n", level)
        
        # Auto-scroll to end
        self.logs_text.see("end")
        self.logs_text.config(state="disabled")

        if hasattr(self, "live_log_text"):
            self.live_log_text.config(state="normal")
            self.live_log_text.insert("end", f"[{timestamp}] ", "TIMESTAMP")
            self.live_log_text.insert("end", f"{message}\n", level)
            if int(float(self.live_log_text.index("end-1c").split(".")[0])) > 300:
                self.live_log_text.delete("1.0", "120.0")
            self.live_log_text.see("end")
            self.live_log_text.config(state="disabled")
        
        # Update status label for important messages
        if level in ["SUCCESS", "ERROR", "WARNING"]:
            self.status_label.config(text=f"System: {message[:40]}")
            self._update_header_chips(mode_text="Running" if self.running_event.is_set() else "Idle")
        
        # Also print to console
        print(f"[{level}] {formatted_message.strip()}")

    def update_content_display(self):
        """Update content listbox display"""
        self.content_listbox.delete(0, tk.END)
        self._content_display_items = []
        
        # Get content from manager
        content_items = self.content_manager.get_queue_items()
        
        for item in content_items:
            filename = os.path.basename(item['path'])
            status = "[USED]" if item.get('used', False) else "[NEW]"
            self.content_listbox.insert(
                tk.END,
                f"{status} {filename[:30]:30} | Caption: {item.get('caption', 'N/A')[:20]}..."
            )
            self._content_display_items.append(item)
            
            # Color used items differently
            if item.get('used', False):
                self.content_listbox.itemconfig(tk.END, {'fg': '#95a5a6'})
        
        self.update_content_stats()
        if content_items:
            self.content_listbox.selection_clear(0, tk.END)
            self.content_listbox.selection_set(0)
            self._on_content_selected()

    def _on_content_selected(self, _event=None):
        """Update right-side preview panel for selected content."""
        if not hasattr(self, "content_preview_text"):
            return

        selected = self.content_listbox.curselection()
        if not selected:
            preview = "Select an item to view details."
        else:
            idx = selected[0]
            item = self._content_display_items[idx] if idx < len(self._content_display_items) else {}
            preview = (
                f"File: {Path(item.get('path', '')).name}\n"
                f"Status: {'Used' if item.get('used', False) else 'Available'}\n"
                f"Caption: {item.get('caption', 'N/A')}\n\n"
                f"Path:\n{item.get('path', 'N/A')}"
            )

        self.content_preview_text.config(state="normal")
        self.content_preview_text.delete("1.0", "end")
        self.content_preview_text.insert("1.0", preview)
        self.content_preview_text.config(state="disabled")

    def update_content_stats(self):
        """Update content queue statistics"""
        stats = self.content_manager.get_queue_stats()
        self.content_stats_label.config(
            text=f"Queue: {stats['total']} total, {stats['available']} available, {stats['used']} used"
        )

    def show_time_picker(self):
        """Show time picker dialog"""
        # Simplified time picker
        time_str = simpledialog.askstring(
            "Time Picker",
            "Enter time (HH:MM):",
            initialvalue=self.schedule_time.get()
        )
        if time_str:
            self.schedule_time.set(time_str)

    def show_settings_dialog(self):
        """Show settings dialog with validation and persistence."""
        if hasattr(self, "_settings_dialog") and self._settings_dialog.winfo_exists():
            self._settings_dialog.focus()
            return

        dialog = tb.Toplevel(title="Settings", resizable=(False, False))
        dialog.geometry("620x520")
        dialog.transient(self.root)
        dialog.grab_set()
        self._settings_dialog = dialog

        parallel_var = tk.IntVar(value=self.parallel_ld.get())
        boot_delay_var = tk.IntVar(value=self.boot_delay.get())
        task_duration_var = tk.IntVar(value=self.task_duration.get())
        max_videos_var = tk.IntVar(value=self.max_videos.get())
        start_same_time_var = tk.BooleanVar(value=self.start_same_time.get())
        use_content_queue_var = tk.BooleanVar(value=self.use_content_queue.get())

        schedule_time_var = tk.StringVar(value=self.schedule_time.get())
        schedule_repeat_var = tk.IntVar(value=self.schedule_repeat_hours.get())
        schedule_mode_var = tk.StringVar(value="daily" if self.schedule_daily.get() else "weekly")
        day_vars = {day: tk.BooleanVar(value=var.get()) for day, var in self.schedule_days.items()}

        def update_day_controls():
            state = "disabled" if schedule_mode_var.get() == "daily" else "normal"
            for child in days_grid.winfo_children():
                child.configure(state=state)

        def reset_defaults():
            defaults = settings_store.AppSettings()
            schedule_defaults = settings_store.ScheduleSettings()
            parallel_var.set(defaults.parallel_ld)
            boot_delay_var.set(defaults.boot_delay)
            task_duration_var.set(defaults.task_duration)
            max_videos_var.set(defaults.max_videos)
            start_same_time_var.set(defaults.start_same_time)
            use_content_queue_var.set(defaults.use_content_queue)
            schedule_time_var.set(schedule_defaults.schedule_time)
            schedule_repeat_var.set(schedule_defaults.schedule_repeat_hours)
            schedule_mode_var.set("daily" if schedule_defaults.schedule_daily else "weekly")
            for day_name, var in day_vars.items():
                var.set(schedule_defaults.schedule_days.get(day_name, False))
            update_day_controls()

        def open_folder(path_obj: Path):
            path_obj.mkdir(parents=True, exist_ok=True)
            try:
                if os.name == "nt":
                    os.startfile(str(path_obj))
                elif platform.system() == "Darwin":
                    subprocess.Popen(["open", str(path_obj)])
                else:
                    subprocess.Popen(["xdg-open", str(path_obj)])
            except Exception as exc:
                MessageBox.showerror("Open Folder", f"Could not open folder:\n{path_obj}\n\n{exc}")

        def validate_inputs():
            try:
                values = {
                    "Parallel Devices": int(parallel_var.get()),
                    "Boot Delay": int(boot_delay_var.get()),
                    "Task Duration": int(task_duration_var.get()),
                    "Max Reels": int(max_videos_var.get()),
                    "Repeat Hours": int(schedule_repeat_var.get()),
                }
            except Exception:
                MessageBox.showerror("Settings", "Please enter valid numeric values.")
                return False

            rules = [
                ("Parallel Devices", 1, 20),
                ("Boot Delay", 1, 120),
                ("Task Duration", 1, 720),
                ("Max Reels", 1, 200),
                ("Repeat Hours", 0, 24),
            ]
            for label, min_value, max_value in rules:
                value = values[label]
                if not (min_value <= value <= max_value):
                    MessageBox.showerror("Settings", f"{label} must be between {min_value} and {max_value}.")
                    return False

            try:
                datetime.strptime(schedule_time_var.get().strip(), "%H:%M")
            except ValueError:
                MessageBox.showerror("Settings", "Schedule time must use HH:MM format.")
                return False

            if schedule_mode_var.get() == "weekly" and not any(var.get() for var in day_vars.values()):
                MessageBox.showerror("Settings", "Select at least one weekday for weekly scheduling.")
                return False

            return True

        def apply_settings(close_after=False):
            if not validate_inputs():
                return

            self.parallel_ld.set(int(parallel_var.get()))
            self.boot_delay.set(int(boot_delay_var.get()))
            self.task_duration.set(int(task_duration_var.get()))
            self.max_videos.set(int(max_videos_var.get()))
            self.start_same_time.set(bool(start_same_time_var.get()))
            self.use_content_queue.set(bool(use_content_queue_var.get()))

            self.schedule_time.set(schedule_time_var.get().strip())
            self.schedule_repeat_hours.set(int(schedule_repeat_var.get()))
            is_daily = schedule_mode_var.get() == "daily"
            self.schedule_daily.set(is_daily)
            self.schedule_weekly.set(not is_daily)
            for day_name, day_var in self.schedule_days.items():
                day_var.set(bool(day_vars[day_name].get()))

            self.save_settings()
            self.save_schedule_settings()
            self.on_schedule_type_change()
            self.log("Settings updated and saved", "SUCCESS")

            if close_after:
                dialog.destroy()

        container = tb.Frame(dialog, padding=14)
        container.pack(fill="both", expand=True)

        tb.Label(
            container,
            text="Application Settings",
            style="Title.TLabel"
        ).pack(anchor="w")
        tb.Label(
            container,
            text="Control startup behavior, automation defaults, and scheduling.",
            style="Subtitle.TLabel"
        ).pack(anchor="w", pady=(2, 10))

        notebook = tb.Notebook(container)
        notebook.pack(fill="both", expand=True)

        general_tab = tb.Frame(notebook, padding=12)
        schedule_tab = tb.Frame(notebook, padding=12)
        data_tab = tb.Frame(notebook, padding=12)
        notebook.add(general_tab, text="General")
        notebook.add(schedule_tab, text="Schedule")
        notebook.add(data_tab, text="Data")

        general_grid = tb.Frame(general_tab)
        general_grid.pack(fill="x")

        tb.Label(general_grid, text="Parallel Devices").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=8)
        tb.Spinbox(general_grid, from_=1, to=20, textvariable=parallel_var, width=8).grid(row=0, column=1, sticky="w", pady=8)
        tb.Label(general_grid, text="Boot Delay (sec)").grid(row=0, column=2, sticky="w", padx=(18, 8), pady=8)
        tb.Spinbox(general_grid, from_=1, to=120, textvariable=boot_delay_var, width=8).grid(row=0, column=3, sticky="w", pady=8)

        tb.Label(general_grid, text="Task Duration (min)").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=8)
        tb.Spinbox(general_grid, from_=1, to=720, textvariable=task_duration_var, width=8).grid(row=1, column=1, sticky="w", pady=8)
        tb.Label(general_grid, text="Max Reels per Run").grid(row=1, column=2, sticky="w", padx=(18, 8), pady=8)
        tb.Spinbox(general_grid, from_=1, to=200, textvariable=max_videos_var, width=8).grid(row=1, column=3, sticky="w", pady=8)

        tb.Checkbutton(
            general_grid,
            text="Start selected emulators at the same time",
            variable=start_same_time_var,
            bootstyle="primary-round-toggle"
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(10, 4))
        tb.Checkbutton(
            general_grid,
            text="Use content queue when posting",
            variable=use_content_queue_var,
            bootstyle="primary-round-toggle"
        ).grid(row=3, column=0, columnspan=4, sticky="w", pady=(4, 6))

        tb.Label(
            general_grid,
            text="These defaults are used by batch start and automation runs.",
            style="Subtitle.TLabel"
        ).grid(row=4, column=0, columnspan=4, sticky="w", pady=(8, 0))

        schedule_grid = tb.Frame(schedule_tab)
        schedule_grid.pack(fill="x")

        tb.Label(schedule_grid, text="Run Time (HH:MM)").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=8)
        tb.Entry(schedule_grid, textvariable=schedule_time_var, width=10).grid(row=0, column=1, sticky="w", pady=8)
        tb.Label(schedule_grid, text="Repeat Every (hours)").grid(row=0, column=2, sticky="w", padx=(18, 8), pady=8)
        tb.Spinbox(schedule_grid, from_=0, to=24, textvariable=schedule_repeat_var, width=8).grid(row=0, column=3, sticky="w", pady=8)

        mode_frame = tb.Labelframe(schedule_tab, text="Schedule Mode", bootstyle="secondary", padding=10)
        mode_frame.pack(fill="x", pady=(10, 8))
        tb.Radiobutton(
            mode_frame,
            text="Daily",
            variable=schedule_mode_var,
            value="daily",
            bootstyle="info-toolbutton",
            command=update_day_controls
        ).pack(side="left", padx=6)
        tb.Radiobutton(
            mode_frame,
            text="Weekly",
            variable=schedule_mode_var,
            value="weekly",
            bootstyle="info-toolbutton",
            command=update_day_controls
        ).pack(side="left", padx=6)

        days_frame = tb.Labelframe(schedule_tab, text="Weekdays", bootstyle="secondary", padding=10)
        days_frame.pack(fill="x")
        days_grid = tb.Frame(days_frame)
        days_grid.pack(fill="x")
        for idx, day_name in enumerate(self.schedule_days.keys()):
            tb.Checkbutton(
                days_grid,
                text=day_name[:3],
                variable=day_vars[day_name],
                bootstyle="primary-square-toggle"
            ).grid(row=0, column=idx, padx=4, pady=2)
        update_day_controls()

        tb.Label(
            schedule_tab,
            text="Changes here apply to the scheduler in the Schedule tab.",
            style="Subtitle.TLabel"
        ).pack(anchor="w", pady=(8, 0))

        data_wrap = tb.Frame(data_tab)
        data_wrap.pack(fill="both", expand=True)

        tb.Label(data_wrap, text="Quick Access", style="Title.TLabel").pack(anchor="w")
        tb.Label(
            data_wrap,
            text="Open storage folders and run maintenance actions.",
            style="Subtitle.TLabel"
        ).pack(anchor="w", pady=(2, 10))

        actions = [
            ("Open Config Folder", lambda: open_folder(self.paths.config_dir), "outline-primary"),
            ("Open Logs Folder", lambda: open_folder(self.paths.logs_dir), "outline-secondary"),
            ("Open Backups Folder", lambda: open_folder(self.paths.backup_dir), "outline-info"),
            ("Create Backup Now", self.create_backup, "outline-success"),
            ("Clear Used Queue Items", self.clear_used_videos, "outline-warning"),
        ]
        for text, command, style in actions:
            tb.Button(data_wrap, text=text, command=command, bootstyle=style, width=24).pack(anchor="w", pady=4)

        btn_frame = tb.Frame(container)
        btn_frame.pack(fill="x", pady=(12, 0))
        tb.Button(btn_frame, text="Reset Defaults", bootstyle="outline-secondary", command=reset_defaults).pack(side="left")
        tb.Button(btn_frame, text="Apply", bootstyle="outline-primary", command=apply_settings).pack(side="right", padx=(6, 0))
        tb.Button(btn_frame, text="Save & Close", bootstyle="success", command=lambda: apply_settings(close_after=True)).pack(side="right", padx=(6, 0))
        tb.Button(btn_frame, text="Cancel", bootstyle="secondary", command=dialog.destroy).pack(side="right")

    def export_logs(self):
        """Export logs to file"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".log",
            filetypes=[("Log files", "*.log"), ("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(self.logs_text.get("1.0", "end-1c"))
                self.log(f" Logs exported to {filename}", "SUCCESS")
            except Exception as e:
                self.log(f" Failed to export logs: {e}", "ERROR")

    def show_content_stats(self):
        """Show detailed content statistics"""
        stats = self.content_manager.get_queue_stats()
        details = self.content_manager.get_queue_details()
        
        stats_text = f"""
 Content Queue Statistics:
===========================
Total Items: {stats['total']}
Available: {stats['available']}
Used: {stats['used']}
Queue Size: {stats['queue_size']}

Recent Items:
-------------
"""
        for item in details[:10]:  # Show first 10 items
            filename = os.path.basename(item['path'])
            stats_text += f" {filename}\n"
        
        MessageBox.showinfo("Content Statistics", stats_text)

    def batch_restart(self):
        """Restart selected LDs"""
        selected_items = self.ld_table.get_checked_items()
        if not selected_items:
            MessageBox.showerror("Error", "No LDs selected. Please select at least one LD to restart.")
            return
            
        selected_ld_names = [self.ld_table.item(item)["values"][0] for item in selected_items]
        
        def restart_thread():
            for name in selected_ld_names:
                if not self.running_event.is_set():
                    self.emulator.quit_ld(name)
                    time.sleep(2)
                    self.emulator.start_ld(name, delay_between_starts=self.boot_delay.get())
                    time.sleep(self.boot_delay.get())
                    self.update_status(name, "Active")
                    self.log(f" Restarted LD: {name}", "INFO")
            
        threading.Thread(target=restart_thread, daemon=True).start()

    def update_progress(self, value):
        """Update progress bar"""
        if not self._is_main_thread():
            try:
                self.root.after(0, lambda v=value: self.update_progress(v))
            except Exception:
                pass
            return
        if hasattr(self, "footer_progress"):
            self.footer_progress.set(value)
        if hasattr(self, "footer_progress_label"):
            self.footer_progress_label.config(text=f"{int(value)}%")
        
    def update_selection_info(self):
        """Update the selection info label"""
        visible_rows = {}
        for item in self.ld_table.get_children():
            values = self.ld_table.item(item, "values")
            if values:
                visible_rows[item] = values[0]
        checked_visible = {
            visible_rows[item]
            for item in self.ld_table.get_checked_items()
            if item in visible_rows
        }
        self._ld_checked_names.difference_update(visible_rows.values())
        self._ld_checked_names.update(checked_visible)

        total = len(self.ld_table.get_children())
        selected_visible = len(checked_visible)
        selected_all = len(self._ld_checked_names)
        self.selection_info.config(text=f"Selected: {selected_visible}/{total}  Fleet: {selected_all}")
        
        # Update status bar
        if hasattr(self, "footer_selected_label"):
            self.footer_selected_label.config(text=f"Selected: {selected_all} / {len(self._ld_snapshot)}")
        self._update_header_chips()

    def _update_fleet_summary(self, filtered_rows):
        total = len(self._ld_snapshot)
        online = sum(1 for status in self._ld_status_cache.values() if status in ("Active", "Running"))
        running = sum(1 for status in self._ld_status_cache.values() if status == "Running")
        errors = sum(1 for status in self._ld_status_cache.values() if status not in ("Active", "Running", "Inactive", "Paused", "Completed"))
        with_account = sum(1 for account in self._ld_account_cache.values() if account and account != "No account")
        visible = len(filtered_rows)
        if hasattr(self, "fleet_total_chip"):
            self.fleet_total_chip.config(text=f"Total: {total}")
        if hasattr(self, "fleet_online_chip"):
            self.fleet_online_chip.config(text=f"Online: {online}")
        if hasattr(self, "fleet_running_chip"):
            self.fleet_running_chip.config(text=f"Running: {running}")
        if hasattr(self, "fleet_account_chip"):
            self.fleet_account_chip.config(text=f"With Account: {with_account}")
        if hasattr(self, "fleet_visible_chip"):
            self.fleet_visible_chip.config(text=f"Visible: {visible}")
        badge_values = {
            "dashboard": str(total),
            "devices": str(online),
            "automation": str(running),
            "queue": str(len(self.content_manager.get_queue_items())) if hasattr(self, "content_manager") else "0",
            "analytics": str(errors),
            "schedule": "ON" if self.schedule_running else "OFF",
        }
        for key, value in badge_values.items():
            nav = getattr(self, "_nav_rows", {}).get(key)
            if nav:
                nav["badge"].config(text=value)

    def clear_ld_filters(self):
        self.ld_search_var.set("")
        self.ld_status_filter_var.set("All")
        self.ld_account_filter_var.set("All")
        self.ld_sort_var.set("Status")
        self._render_ld_table()
        self.log("Device filters cleared", "INFO")

    def select_by_status(self, target_status):
        matched = 0
        for item in self.ld_table.get_children():
            values = self.ld_table.item(item, "values")
            if not values:
                continue
            name = values[0]
            status = self._ld_status_cache.get(name, "Inactive")
            if status == target_status and not self.ld_table.checkboxes.get(item, False):
                self.ld_table.toggle_checkbox(item)
                matched += 1
        self.update_selection_info()
        self.log(f"Selected {matched} item(s) with status: {target_status}", "INFO")

    def select_online(self):
        matched = 0
        for item in self.ld_table.get_children():
            values = self.ld_table.item(item, "values")
            if not values:
                continue
            name = values[0]
            status = self._ld_status_cache.get(name, "Inactive")
            if status in ("Active", "Running") and not self.ld_table.checkboxes.get(item, False):
                self.ld_table.toggle_checkbox(item)
                matched += 1
        self.update_selection_info()
        self.log(f"Selected {matched} online item(s)", "INFO")

    # ==================== EXISTING METHODS ====================

    def refresh_emulator_list(self):
        """Refresh the emulator list from LDPlayer"""
        try:
            self.emulator = ControlEmulator()
            self.populate_ld_table()
            self.log("Emulator list refreshed", "SUCCESS")
        except Exception as e:
            self.log(f" Error refreshing emulator list: {e}", "ERROR")

    def populate_ld_table(self):
        """Populate LD table with current emulators"""
        self.emulator._build_serial_mapping()
        snapshot = dict(self.emulator.name_to_serial)
        status_cache = {name: self._ld_status_cache.get(name, "Inactive") for name in snapshot}
        account_cache = {name: self._ld_account_cache.get(name, "No account") for name in snapshot}
        self._sync_emulator_table(snapshot, status_cache, account_cache, force=True)

    def select_all(self):
        """Select all items in the table"""
        for item in self.ld_table.get_children():
            if not self.ld_table.checkboxes[item]:
                self.ld_table.toggle_checkbox(item)
        self.update_selection_info()
        self.log("All LDs selected", "INFO")

    def deselect_all(self):
        """Deselect all items in the table"""
        for item in self.ld_table.get_children():
            if self.ld_table.checkboxes[item]:
                self.ld_table.toggle_checkbox(item)
        self.update_selection_info()
        self.log("All LDs deselected", "INFO")

    def invert_selection(self):
        """Invert the current selection"""
        for item in self.ld_table.get_children():
            self.ld_table.toggle_checkbox(item)
        self.update_selection_info()
        self.log("Selection inverted", "INFO")

    def batch_start(self):
        """Start selected LDs"""
        selected_items = self.ld_table.get_checked_items()
        if not selected_items:
            MessageBox.showerror("Error", "No LDs selected. Please select at least one LD to start.")
            return
            
        selected_ld_names = [self.ld_table.item(item)["values"][0] for item in selected_items]
        
        def start_thread():
            for name in selected_ld_names:
                if not self.running_event.is_set():
                    self.emulator.start_ld(name, delay_between_starts=self.boot_delay.get())
                    time.sleep(self.boot_delay.get())
                    self.update_status(name, "Active")
                    self.log(f" Started LD: {name}", "SUCCESS")
            
        threading.Thread(target=start_thread, daemon=True).start()

    def batch_stop(self):
        """Stop selected LDs"""
        selected_items = self.ld_table.get_checked_items()
        if not selected_items:
            MessageBox.showerror("Error", "No LDs selected. Please select at least one LD to stop.")
            return
        if not MessageBox.askyesno("Stop LDs", "Stop all selected LD instances?"):
            return
            
        selected_ld_names = [self.ld_table.item(item)["values"][0] for item in selected_items]
        
        def stop_thread():
            for name in selected_ld_names:
                self.emulator.quit_ld(name)
                self.update_status(name, "Inactive")
                self.log(f" Stopped LD: {name}", "INFO")
            
        threading.Thread(target=stop_thread, daemon=True).start()

    def update_status(self, ld_name, status):
        """Update status of an LD in the table"""
        if not self._is_main_thread():
            try:
                self.root.after(0, lambda name=ld_name, state=status: self.update_status(name, state))
            except Exception:
                pass
            return

        self._ld_status_cache[ld_name] = status
        self._last_table_signature = None
        for item in self.ld_table.get_children():
            values = self.ld_table.item(item)["values"]
            if values[0] == ld_name:
                # Update values
                task_text = values[3] if len(values) > 3 else "—"
                progress_text = values[4] if len(values) > 4 else "0%"
                account_text = values[5] if len(values) > 5 else "No account"
                actions_text = values[6] if len(values) > 6 else "⏸ ⏹ 🔍"
                if status == "Inactive":
                    task_text = "—"
                    progress_text = "0%"
                    actions_text = "▶ ⏹ 🔍"
                elif status == "Running" and task_text in ("—", "Starting"):
                    task_text = "Scroll Feed" if self.task_type_var.get() == "scroll" else "Watch Reels"
                    actions_text = "⏸ ⏹ 🔍"
                self.ld_table.item(
                    item,
                    values=(values[0], values[1], self._status_text(status), task_text, progress_text, account_text, actions_text),
                )
                
                # Update tags
                tags = list(self.ld_table.item(item, "tags"))
                tags = [t for t in tags if t not in ("active", "inactive", "running", "paused")]
                tags.append(self._status_tag(status))
                self.ld_table.item(item, tags=tags)
                break

    def start_automation(self):
        """Start automation process"""
        selected_items = self.ld_table.get_checked_items()
        if not selected_items:
            MessageBox.showerror("Error", "No LDs selected. Please select at least one LD to automate.")
            return

        selected_ld_names = [self.ld_table.item(item)["values"][0] for item in selected_items]

        # Update emulator settings
        self.emulator.boot_delay = self.boot_delay.get()
        self.emulator.task_duration = self.task_duration.get() * 60

        # Determine task type
        task_type = self.task_type_var.get()

        if task_type == "scroll":
            from core.task_handlers import ScrollTaskHandler
            task_handler = ScrollTaskHandler(
                self.emulator,
                self.log,
                self.pause_event,
                lambda: self.running_event.is_set()
            )
        elif task_type == "reels":
            from core.task_handlers import ReelsTaskHandler
            task_handler = ReelsTaskHandler(
                self.emulator,
                self.log,
                self.pause_event,
                lambda: self.running_event.is_set(),
                self.content_manager if self.use_content_queue.get() else None
            )
        else:
            MessageBox.showwarning(
                "Task Not Implemented",
                "This task type is UI-only right now. Please use Scroll Feed or Watch Reels."
            )
            return

        # Start performance monitoring
        self.performance_monitor.start_task_timer(f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}")

        # Start automation
        self.running_event.set()
        self.pause_event.set()
        self.start_button.config(state="disabled")
        self.pause_button.config(state="normal")
        self.stop_button.config(state="normal")
        if hasattr(self, "top_status_label"):
            self.top_status_label.config(text=f"System: Running  |  {datetime.now().strftime('%A, %d %b %Y')}")
        if hasattr(self, "status_sys_lbl"):
            self.status_sys_lbl.config(text="● System: Running", fg=self.palette["success"])
        if hasattr(self, "status_task_lbl"):
            self.status_task_lbl.config(text=f"Tasks: {len(selected_ld_names)} active")
        self._update_header_chips(mode_text="Running")

        self.log(f" Starting automation for {len(selected_ld_names)} LDs", "SUCCESS")
        self.log(f"Task type: {task_type}, Duration: {self.task_duration.get()} minutes", "INFO")

        # Create automation thread
        def automation_thread():
            try:
                main_window = MainWindow(
                    selected_ld_names,
                    lambda: self.running_event.is_set(),
                    self.parallel_ld.get(),
                    self.log,
                    self.start_same_time.get(),
                    task_type,
                    task_handler,
                    self.update_progress,
                    self.boot_delay.get(),
                    self.task_duration.get() * 60,
                    self.max_videos.get(),
                    emulator=self.emulator
                )

                main_window.main()
                self.performance_monitor.end_task_timer(True)

            except Exception as e:
                self.log(f" Error in automation: {str(e)}", "ERROR")
                self.performance_monitor.end_task_timer(False)
                MessageBox.showerror("Error", f"Automation error: {str(e)}")
            finally:
                self.stop_automation(confirm=False)

        threading.Thread(target=automation_thread, daemon=True).start()

    def toggle_pause(self):
        """Toggle pause state"""
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.pause_button.config(text="Resume")
            if hasattr(self, "top_status_label"):
                self.top_status_label.config(text=f"System: Paused  |  {datetime.now().strftime('%A, %d %b %Y')}")
            if hasattr(self, "status_sys_lbl"):
                self.status_sys_lbl.config(text="◎ System: Paused", fg=self.palette["warning"])
            self._update_header_chips(mode_text="Paused")
            self.log("Automation paused", "WARNING")
        else:
            self.pause_event.set()
            self.pause_button.config(text="Pause")
            if hasattr(self, "top_status_label"):
                self.top_status_label.config(text=f"System: Running  |  {datetime.now().strftime('%A, %d %b %Y')}")
            if hasattr(self, "status_sys_lbl"):
                self.status_sys_lbl.config(text="● System: Running", fg=self.palette["success"])
            self._update_header_chips(mode_text="Running")
            self.log("Automation resumed", "SUCCESS")

    def stop_automation(self, confirm=True):
        """Stop automation process"""
        if confirm and self.running_event.is_set() and not MessageBox.askyesno("Stop Automation", "Stop current automation run?"):
            return

        self.running_event.clear()
        self.pause_event.set()
        self.start_button.config(state="normal")
        self.pause_button.config(state="disabled")
        self.stop_button.config(state="disabled")
        self.pause_button.config(text="Pause")
        if hasattr(self, "top_status_label"):
            self.top_status_label.config(text=f"System: Idle  |  {datetime.now().strftime('%A, %d %b %Y')}")
        if hasattr(self, "status_sys_lbl"):
            self.status_sys_lbl.config(text="○ System: Idle", fg=self.palette["muted"])
        if hasattr(self, "status_task_lbl"):
            self.status_task_lbl.config(text="Tasks: 0 active")
        self._update_header_chips(mode_text="Idle")
        self.log("Automation stopped", "INFO")
        self.update_progress(0)

    def on_schedule_type_change(self):
        """Show/hide days of week based on schedule type"""
        if self.schedule_daily.get():
            self.days_frame.pack_forget()
        else:
            self.days_frame.pack(fill="x", padx=10, pady=10)

    def toggle_schedule(self):
        """Toggle schedule on/off"""
        if self.schedule_running:
            self.stop_schedule()
        else:
            self.start_schedule()

    def start_schedule(self):
        """Start scheduling"""
        if not self.validate_schedule():
            return
            
        self.schedule_running = True
        if hasattr(self, "schedule_enabled_ui"):
            self.schedule_enabled_ui.set(True)
        self.schedule_enable_btn.config(text="Disable Schedule", bootstyle="warning")
        self.log("Scheduling enabled", "SUCCESS")
        
        self.save_schedule_settings()
        
        if self.schedule_thread is None or not self.schedule_thread.is_alive():
            self.schedule_thread = threading.Thread(target=self.schedule_monitor, daemon=True)
            self.schedule_thread.start()

    def stop_schedule(self):
        """Stop scheduling"""
        self.schedule_running = False
        if hasattr(self, "schedule_enabled_ui"):
            self.schedule_enabled_ui.set(False)
        self.schedule_enable_btn.config(text="Enable Schedule", bootstyle="success")
        self.log("Scheduling disabled", "INFO")

    def validate_schedule(self):
        """Validate schedule settings"""
        try:
            datetime.strptime(self.schedule_time.get(), "%H:%M")
        except ValueError:
            MessageBox.showerror("Error", "Invalid time format. Please use HH:MM format.")
            return False
            
        repeat_hours = self.schedule_repeat_hours.get()
        if repeat_hours < 0:
            MessageBox.showerror("Error", "Repeat interval must be a positive number.")
            return False
            
        if not self.schedule_daily.get() and not any(var.get() for var in self.schedule_days.values()):
            MessageBox.showerror("Error", "Please select at least one day for scheduling.")
            return False
            
        return True

    def schedule_monitor(self):
        """Monitor schedule and trigger tasks"""
        while self.schedule_running:
            try:
                now = datetime.now()
                current_time = now.strftime("%H:%M")
                current_day = now.strftime("%A")
                
                if current_time == self.schedule_time.get():
                    should_run = False
                    
                    if self.schedule_daily.get():
                        should_run = True
                    elif any(self.schedule_days[day].get() for day in self.schedule_days if day == current_day):
                        should_run = True
                        
                    if should_run and not self.running_event.is_set():
                        self.log(f" Scheduled task triggered at {current_time}", "INFO")
                        self.root.after(0, self.start_automation)
                        
                        repeat_hours = self.schedule_repeat_hours.get()
                        if repeat_hours > 0:
                            next_time = (now + timedelta(hours=repeat_hours)).strftime("%H:%M")
                            self.schedule_time.set(next_time)
                            self.log(f"Next run scheduled for {next_time}", "INFO")
                
                time.sleep(30)
            except Exception as e:
                self.log(f"Error in schedule monitor: {e}", "ERROR")
                time.sleep(60)

   

    def clear_logs(self):
        """Clear logs with confirmation"""
        if MessageBox.askyesno("Clear Logs", "Are you sure you want to clear all logs?"):
            if hasattr(self, "logs_text"):
                self.logs_text.config(state="normal")
                self.logs_text.delete("1.0", "end")
                self.logs_text.config(state="disabled")
            if hasattr(self, "live_log_text"):
                self.live_log_text.config(state="normal")
                self.live_log_text.delete("1.0", "end")
                self.live_log_text.config(state="disabled")
            self.log("Logs cleared", "INFO")

    def refresh_all(self):
        """Refresh everything"""
        self.refresh_emulator_list()
        self.update_content_display()
        self.log("All data refreshed", "SUCCESS")

    def on_closing(self):
        """Handle application closing"""
        if hasattr(self, "_status_refresh_event"):
            self._status_refresh_event.set()
        self.save_settings()
        self.stop_schedule()
        self.stop_automation(confirm=False)
        self.root.destroy()
