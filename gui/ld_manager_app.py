import os
import threading
import tkinter as tk
from tkinter import ttk
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
import colorsys
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

class LDManagerApp(ToolsMixin):
    def __init__(self, root):
        self.root = root
        self.root.title("ALP Automation Control Center")
        self.root.geometry("1540x940")
        self.root.minsize(1280, 780)
        
        # Apply a single fixed ttkbootstrap theme
        self.style = tb.Style(theme="flatly")
        self.palette = {
            "app_bg": "#EEF2F7",
            "surface": "#FFFFFF",
            "surface_alt": "#F6F8FB",
            "text": "#122033",
            "muted": "#5B6A7D",
            "primary": "#155EEF",
            "success": "#087443",
            "warning": "#B54708",
            "danger": "#B42318",
            "border": "#D9E0EA",
        }
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
        
        # Initialize footer animation variables
        self.footer_effect_canvas = None
        self.footer_phase = 0
        self.footer_particles = []
        self.footer_text_main = None
        self.footer_text_sub = None
        
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
            font=("Segoe UI", 10)
        )
        self.style.configure(
            "TLabelframe",
            borderwidth=0,
            relief="flat",
            background=self.palette["surface"]
        )
        self.style.configure(
            "TLabelframe.Label",
            font=("Segoe UI Semibold", 13),
            foreground=self.palette["text"],
            background=self.palette["surface"]
        )
        self.style.configure("TEntry", padding=(8, 8))
        self.style.configure("TCombobox", padding=(8, 8))
        self.style.configure("Card.TFrame", background=self.palette["surface"], borderwidth=0, relief="flat")
        self.style.configure("CardInner.TFrame", background=self.palette["surface"], borderwidth=0, relief="flat")
        self.style.configure("Shadow.TFrame", background="#D8E0EA")

        self.style.configure(
            "TNotebook.Tab",
            padding=(16, 11),
            font=("Segoe UI Semibold", 10)
        )
        self.style.map(
            "TNotebook.Tab",
            background=[("selected", self.palette["surface"]), ("!selected", self.palette["surface_alt"])],
            foreground=[("selected", self.palette["primary"]), ("!selected", self.palette["muted"])]
        )

        # Configure Treeview row height
        self.style.configure(
            "Custom.Treeview",
            rowheight=32,
            font=("Segoe UI", 10),
            background=self.palette["surface"],
            fieldbackground=self.palette["surface"],
            borderwidth=0
        )
        
        self.style.configure(
            "Custom.Treeview.Heading",
            font=("Segoe UI Semibold", 10),
            padding=(8, 7),
            relief="flat",
            foreground=self.palette["text"]
        )
        
        # Configure button styles
        for button_style in ("success.TButton", "danger.TButton", "warning.TButton", "info.TButton"):
            self.style.configure(button_style, font=("Segoe UI Semibold", 10), padding=(10, 7))
        
        # Configure label styles
        self.style.configure(
            "Title.TLabel",
            font=("Segoe UI Semibold", 18),
            foreground=self.palette["text"]
        )
        
        self.style.configure(
            "Subtitle.TLabel",
            font=("Segoe UI", 11),
            foreground=self.palette["muted"]
        )
        self.style.configure(
            "SectionTitle.TLabel",
            font=("Segoe UI Semibold", 16),
            foreground=self.palette["text"]
        )
        self.style.configure(
            "HeroTitle.TLabel",
            font=("Segoe UI Semibold", 21),
            foreground=self.palette["text"]
        )
        self.style.configure(
            "HeroSub.TLabel",
            font=("Segoe UI", 11),
            foreground=self.palette["muted"]
        )
        self.style.configure(
            "Chip.TLabel",
            font=("Segoe UI Semibold", 9),
            foreground=self.palette["text"]
        )

    def _create_card_section(self, parent, title, subtitle=None, pady=(0, 14), expand=False):
        """Create a lightweight card section with subtle shadow and generous spacing."""
        shadow = tb.Frame(parent, style="Shadow.TFrame", padding=(0, 0, 0, 1))
        shadow.pack(fill="both", expand=expand, pady=pady)

        card = tb.Frame(shadow, style="Card.TFrame", padding=18)
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
        self.create_top_bar()
        
        # Main container with left and right panels
        main_container = tb.Frame(self.root, bootstyle="light", padding=18)
        main_container.pack(fill="both", expand=True)

        split = ttk.Panedwindow(main_container, orient=tk.HORIZONTAL)
        split.pack(fill="both", expand=True)

        left_panel = tb.Frame(split, padding=(0, 0, 12, 0))
        right_panel = tb.Frame(split, padding=(12, 0, 0, 0))
        split.add(left_panel, weight=3)
        split.add(right_panel, weight=7)

        # LD Players Table
        self.create_ld_table_panel(left_panel)
        
        # Right panel with Notebook
        self.create_right_notebook_panel(right_panel)
        
        # Status bar
        self.create_status_bar()

    def create_top_bar(self):
        """Top-level application header with global actions."""
        top_shadow = tb.Frame(self.root, style="Shadow.TFrame", padding=(0, 0, 0, 1))
        top_shadow.pack(fill="x", side="top")
        top_bar = tb.Frame(top_shadow, style="Card.TFrame", padding=(18, 14))
        top_bar.pack(fill="x", padx=(0, 1))

        title_wrap = tb.Frame(top_bar)
        title_wrap.pack(side="left")

        tb.Label(
            title_wrap,
            text="ALP Automation Control Center",
            style="HeroTitle.TLabel"
        ).pack(anchor="w")
        self.top_status_label = tb.Label(
            title_wrap,
            text=f"System: Idle  |  {datetime.now().strftime('%A, %d %b %Y')}",
            style="HeroSub.TLabel"
        )
        self.top_status_label.pack(anchor="w")

        center_meta = tb.Frame(top_bar)
        center_meta.pack(side="left", padx=(28, 0))
        self.top_selected_chip = tb.Label(center_meta, text="Selected: 0", bootstyle="info", style="Chip.TLabel", padding=(10, 6))
        self.top_selected_chip.pack(side="left", padx=(0, 8))
        self.top_mode_chip = tb.Label(center_meta, text="Mode: Idle", bootstyle="secondary", style="Chip.TLabel", padding=(10, 6))
        self.top_mode_chip.pack(side="left", padx=(0, 8))
        self.top_task_chip = tb.Label(center_meta, text="Task: Scroll", bootstyle="primary", style="Chip.TLabel", padding=(10, 6))
        self.top_task_chip.pack(side="left")

        actions = tb.Frame(top_bar, style="CardInner.TFrame")
        actions.pack(side="right")
        tb.Button(actions, text="Refresh All", bootstyle="outline-primary", command=self.refresh_all, width=12).pack(side="left", padx=4)
        tb.Button(actions, text="Tools Center", bootstyle="outline-secondary", command=self.show_tools_center, width=12).pack(side="left", padx=4)
        tb.Button(actions, text="Settings", bootstyle="secondary", command=self.show_settings_dialog, width=10).pack(side="left", padx=4)
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
            "Device Fleet",
            "Manage emulator selection, status filtering, and batch actions.",
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
        columns = ("name", "serial", "status", "account", "progress")
        
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
        self.ld_table.column("name", width=180, anchor="w")
        
        self.ld_table.heading("serial", text="ADB Serial", anchor="w")
        self.ld_table.column("serial", width=150, anchor="w")
        
        self.ld_table.heading("status", text="State", anchor="w")
        self.ld_table.column("status", width=120, anchor="w")
        
        self.ld_table.heading("account", text="Account", anchor="w")
        self.ld_table.column("account", width=120, anchor="w")
        
        self.ld_table.heading("progress", text="Progress", anchor="w")
        self.ld_table.column("progress", width=100, anchor="w")
        
        # Configure tags with state colors
        self.ld_table.tag_configure("active", background="#ECFDF3", foreground="#14532D")
        self.ld_table.tag_configure("inactive", background="#FEF2F2", foreground="#7F1D1D")
        self.ld_table.tag_configure("running", background="#FFFBEB", foreground="#78350F")
        self.ld_table.tag_configure("paused", background="#EFF6FF", foreground="#1E3A8A")
        self.ld_table.tag_configure("completed", background="#EEF2FF", foreground="#3730A3")
        
        # Scrollbars
        v_scrollbar = tb.Scrollbar(
            tree_frame,
            orient="vertical",
            command=self.ld_table.yview,
            bootstyle="round"
        )
        v_scrollbar.pack(side="right", fill="y")
        
        h_scrollbar = tb.Scrollbar(
            tree_frame,
            orient="horizontal",
            command=self.ld_table.xview,
            bootstyle="round"
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
        self.notebook = tb.Notebook(parent, bootstyle="primary")
        self.notebook.pack(side="right", fill="both", expand=True)
        
        # Create tabs
        self.create_dashboard_tab()
        self.create_tasks_tab()
        self.create_schedule_tab()
        self.create_content_tab()
        self.create_logs_tab()

    def create_dashboard_tab(self):
        """Create Dashboard tab"""
        dashboard_tab = tb.Frame(self.notebook)
        self.notebook.add(dashboard_tab, text="Dashboard")
        
        # Analytics Dashboard
        self.create_analytics_dashboard(dashboard_tab)
        
        # Batch operations
        self.create_batch_operations(dashboard_tab)
        
        # Control buttons with enhanced styling
        self.create_control_buttons(dashboard_tab)

    def create_analytics_dashboard(self, parent):
        """Create analytics dashboard"""
        analytics_frame = self._create_card_section(
            parent,
            "Operations Overview",
            "Live fleet metrics and health summary."
        )
        
        # Metrics grid
        metrics_frame = tb.Frame(analytics_frame)
        metrics_frame.pack(fill="x", padx=4, pady=4)
        
        self.metric_labels = {}
        metrics = [
            ("total_instances", "Total Instances", "0", "primary"),
            ("active_instances", "Active", "0", "success"),
            ("running_tasks", "Running Tasks", "0", "warning"),
            ("errors", "Errors", "0", "danger")
        ]
        
        for i, (key, label, value, style) in enumerate(metrics):
            metric_card = tb.Frame(metrics_frame)
            metric_card.grid(row=0, column=i, padx=8, pady=8, sticky="nsew")
            metrics_frame.columnconfigure(i, weight=1)
            
            # Card with border
            card_shadow = tb.Frame(metric_card, style="Shadow.TFrame", padding=(0, 0, 0, 1))
            card_shadow.pack(fill="both", expand=True, padx=1, pady=1)
            card = tb.Frame(card_shadow, bootstyle=style, padding=1)
            card.pack(fill="both", expand=True, padx=(0, 1))
            
            inner_frame = tb.Frame(card, padding=16)
            inner_frame.pack(fill="both", expand=True)
            
            # Label
            tb.Label(
                inner_frame,
                text=label,
                bootstyle=f"{style}-inverse",
                font=("Segoe UI", 10)
            ).pack(pady=(0, 5))
            
            # Value
            value_label = tb.Label(
                inner_frame,
                text=value,
                font=("Segoe UI", 16, "bold"),
                bootstyle=f"{style}-inverse"
            )
            value_label.pack()

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
            bootstyle="success",
            width=20
        )
        self.start_button.grid(row=0, column=0, padx=8, pady=8)
        
        # Pause button (Yellow)
        self.pause_button = tb.Button(
            button_grid,
            text="Pause",
            command=self.toggle_pause,
            bootstyle="warning",
            width=20,
            state="disabled"
        )
        self.pause_button.grid(row=0, column=1, padx=8, pady=8)
        
        # Stop button (Red)
        self.stop_button = tb.Button(
            button_grid,
            text="Stop Run",
            command=self.stop_automation,
            bootstyle="danger",
            width=20,
            state="disabled"
        )
        self.stop_button.grid(row=0, column=2, padx=8, pady=8)
        
        # Second row
        # Backup button (Info)
        self.backup_button = tb.Button(
            button_grid,
            text="Create Backup",
            command=self.create_backup,
            bootstyle="info",
            width=20
        )
        self.backup_button.grid(row=1, column=0, padx=8, pady=8)
        
        # Restore button (Secondary)
        tb.Button(
            button_grid,
            text="Restore Backup",
            command=self.restore_backup,
            bootstyle="secondary",
            width=20
        ).grid(row=1, column=1, padx=8, pady=8)
        
        # Settings button
        tb.Button(
            button_grid,
            text="Settings",
            command=self.show_settings_dialog,
            bootstyle="secondary",
            width=20
        ).grid(row=1, column=2, padx=8, pady=8)

    def create_tasks_tab(self):
        """Create Tasks tab with settings"""
        tasks_tab = tb.Frame(self.notebook)
        self.notebook.add(tasks_tab, text="Tasks")
        
        # Task Settings
        self.create_enhanced_settings(tasks_tab)

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
            font=("Consolas", 10),
            bg=self.palette["surface_alt"],
            fg=self.palette["text"],
            selectbackground="#d9edf7",
            selectforeground=self.palette["text"],
            highlightthickness=0,
            relief="flat"
        )
        
        scrollbar = tb.Scrollbar(left, bootstyle="dark-round")
        scrollbar.pack(side="right", fill="y")
        
        self.content_listbox.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.content_listbox.yview)
        self.content_listbox.pack(fill="both", expand=True, padx=5, pady=5)
        self.content_listbox.bind("<<ListboxSelect>>", self._on_content_selected)

        self.content_preview_text = tk.Text(
            right,
            wrap="word",
            font=("Consolas", 10),
            height=10,
            bg=self.palette["surface"],
            fg=self.palette["text"],
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
            selectbackground="#d9edf7",
            padx=10,
            pady=10
        )

        self.logs_text.tag_configure("INFO", foreground=self.palette["primary"])
        self.logs_text.tag_configure("SUCCESS", foreground=self.palette["success"])
        self.logs_text.tag_configure("WARNING", foreground=self.palette["warning"])
        self.logs_text.tag_configure("ERROR", foreground=self.palette["danger"])
        self.logs_text.tag_configure("DEBUG", foreground="#9b59b6")
        self.logs_text.tag_configure("TIMESTAMP", foreground="#95a5a6")

        v_scrollbar = tb.Scrollbar(logs_container, bootstyle="dark-round")
        h_scrollbar = tb.Scrollbar(logs_container, orient="horizontal", bootstyle="dark-round")

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
            "Active": "● Active",
            "Inactive": "● Inactive",
            "Running": "● Running",
            "Paused": "● Paused",
            "Completed": "● Completed",
        }
        return mapping.get(status, status)

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

        for name, serial, status, account_text in rows:
            item_id = self.ld_table.insert(
                "",
                "end",
                values=(name, serial, self._status_text(status), account_text, "0%"),
            )
            is_checked = name in checked_names
            self.ld_table.checkboxes[item_id] = is_checked
            base_tags = [self._status_tag(status), "checked" if is_checked else "unchecked"]
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
        """Create status bar with progress."""
        status_bar = tb.Frame(self.root, bootstyle="light", padding=(14, 9))
        status_bar.pack(fill="x", side="bottom")

        self.footer_selected_label = tb.Label(
            status_bar,
            text="Selected: 0 / 0",
            bootstyle="secondary",
            style="Chip.TLabel",
            padding=(8, 4)
        )
        self.footer_selected_label.pack(side="left", padx=(0, 12))

        self.status_label = tb.Label(status_bar, text="System: Idle", bootstyle="secondary", style="Chip.TLabel", padding=(8, 4))
        self.status_label.pack(side="left", padx=(0, 12))
        self.footer_cpu_label = tb.Label(status_bar, text="CPU: 0%", bootstyle="secondary", style="Chip.TLabel", padding=(8, 4))
        self.footer_cpu_label.pack(side="left", padx=(0, 12))
        self.footer_mem_label = tb.Label(status_bar, text="Memory: 0%", bootstyle="secondary", style="Chip.TLabel", padding=(8, 4))
        self.footer_mem_label.pack(side="left")

        self.progress = tb.Progressbar(
            status_bar,
            orient="horizontal",
            mode="determinate",
            bootstyle="success-striped",
            length=280
        )
        self.progress.pack(side="right")

        self.progress_label = tb.Label(
            status_bar,
            text="0%",
            bootstyle="secondary",
            width=5
        )
        self.progress_label.pack(side="right", padx=(0, 6))

        self.activity_spinner = tb.Progressbar(
            status_bar,
            orient="horizontal",
            mode="indeterminate",
            length=90,
            bootstyle="info-striped",
        )
        self.activity_spinner.pack(side="right", padx=(0, 8))
        self.activity_spinner.stop()

    def start_system_metrics_refresh(self):
        """Periodic system metrics for the footer."""
        def _tick():
            try:
                cpu = psutil.cpu_percent(interval=None)
                mem = psutil.virtual_memory().percent
                if hasattr(self, "footer_cpu_label"):
                    self.footer_cpu_label.config(text=f"CPU: {cpu:.0f}%")
                if hasattr(self, "footer_mem_label"):
                    self.footer_mem_label.config(text=f"Memory: {mem:.0f}%")
            except Exception:
                pass
            self.root.after(2500, _tick)

        self.root.after(1200, _tick)

    def animate_footer_effect(self):
        """Animate the footer canvas to show a glowing gradient with moving particles"""
        if not hasattr(self, "footer_effect_canvas") or self.footer_effect_canvas is None:
            return

        width = max(self.footer_effect_canvas.winfo_width(), 320)
        height = max(self.footer_effect_canvas.winfo_height(), 50)

        base_color = self._hsv_to_hex(self.footer_phase, saturation=0.82, value=0.95)
        accent_color = self._hsv_to_hex((self.footer_phase + 45) % 360, saturation=0.7, value=0.94)

        self.footer_effect_canvas.delete("bg")
        self.footer_effect_canvas.create_rectangle(
            0, 0, width, height,
            fill=base_color,
            outline="",
            tags="bg"
        )
        self.footer_effect_canvas.create_rectangle(
            0, height * 0.35, width, height,
            fill=accent_color,
            outline="",
            stipple="gray25",
            tags="bg"
        )

        self._ensure_footer_particles(width, height)
        self.footer_effect_canvas.delete("particle")
        for particle in self.footer_particles:
            particle["x"] += particle["speed"]
            if particle["x"] - particle["radius"] > width:
                particle["x"] = -particle["radius"]

            particle_color = self._hsv_to_hex(
                (self.footer_phase + particle["radius"] * 4) % 360,
                saturation=0.95,
                value=0.85
            )
            y_pos = height - 6
            self.footer_effect_canvas.create_oval(
                particle["x"] - particle["radius"],
                y_pos - particle["radius"] * 0.3,
                particle["x"] + particle["radius"],
                y_pos + particle["radius"] * 0.3,
                fill=particle_color,
                outline="",
                tags="particle"
            )

        if not self.footer_text_main:
            self.footer_text_main = self.footer_effect_canvas.create_text(
                width / 2,
                height / 2 - 8,
                text="Automation Flow",
                font=("Segoe UI", 12, "bold"),
                fill="#f8f9ff",
                tags="footer_text"
            )
            self.footer_text_sub = self.footer_effect_canvas.create_text(
                width / 2,
                height / 2 + 12,
                text=self.status_label.cget("text"),
                font=("Segoe UI", 9),
                fill="#dfe4ff",
                tags="footer_text"
            )
        else:
            if self.footer_text_main is not None and self.footer_effect_canvas is not None:
                self.footer_effect_canvas.coords(self.footer_text_main, width / 2, height / 2 - 8)
            if self.footer_text_sub is not None and self.footer_effect_canvas is not None:
                self.footer_effect_canvas.coords(self.footer_text_sub, width / 2, height / 2 + 12)

        status_text = self.status_label.cget("text") if hasattr(self, "status_label") else ""
        self.footer_effect_canvas.itemconfig(self.footer_text_sub, text=status_text)

        self.footer_phase = (self.footer_phase + 1.5) % 360
        self.footer_effect_canvas.after(90, self.animate_footer_effect)

    def _ensure_footer_particles(self, width, _height):
        """Create particle data once so animation can reuse it"""
        if self.footer_particles:
            return

        for _ in range(7):
            self.footer_particles.append({
                "x": random.uniform(-width * 0.2, width),
                "radius": random.uniform(10, 24),
                "speed": random.uniform(0.8, 2.2)
            })

    def _hsv_to_hex(self, hue, saturation=0.8, value=0.9):
        """Convert HSV color space to hex string"""
        rgb = colorsys.hsv_to_rgb(hue / 360, saturation, value)
        return "#{:02x}{:02x}{:02x}".format(
            int(rgb[0] * 255),
            int(rgb[1] * 255),
            int(rgb[2] * 255)
        )

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
        tb.Entry(custom_frame, textvariable=self.adb_command_var, font=("Consolas", 10)).pack(fill="x", pady=(0, 8))
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
                active_instances = sum(1 for status in self._ld_status_cache.values() if status in ("Active", "Running"))
                running_instances = sum(1 for status in self._ld_status_cache.values() if status == "Running")

                if hasattr(self, "metric_labels") and isinstance(self.metric_labels, dict):
                    if "total_instances" in self.metric_labels:
                        self.metric_labels["total_instances"].config(text=str(total_instances))
                    if "active_instances" in self.metric_labels:
                        self.metric_labels["active_instances"].config(text=str(active_instances))
                    if "running_tasks" in self.metric_labels:
                        self.metric_labels["running_tasks"].config(text=str(running_instances))
                    if "errors" in self.metric_labels:
                        self.metric_labels["errors"].config(text=str(stats.get("failed", 0)))
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
        self.progress["value"] = value
        self.progress_label.config(text=f"{int(value)}%")
        if value < 35:
            self.progress.configure(bootstyle="danger-striped")
        elif value < 70:
            self.progress.configure(bootstyle="warning-striped")
        else:
            self.progress.configure(bootstyle="success-striped")
        
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
                self.ld_table.item(item, values=(values[0], values[1], self._status_text(status), values[3], values[4]))
                
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
            MessageBox.showerror("Error", "Please select a valid task type.")
            return

        # Start performance monitoring
        self.performance_monitor.start_task_timer(f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}")

        # Start automation
        self.running_event.set()
        self.pause_event.set()
        self.start_button.config(state="disabled")
        self.pause_button.config(state="normal")
        self.stop_button.config(state="normal")
        if hasattr(self, "activity_spinner"):
            self.activity_spinner.start(12)
        if hasattr(self, "top_status_label"):
            self.top_status_label.config(text=f"System: Running  |  {datetime.now().strftime('%A, %d %b %Y')}")
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
            self.pause_button.config(text="Resume", bootstyle="success")
            if hasattr(self, "top_status_label"):
                self.top_status_label.config(text=f"System: Paused  |  {datetime.now().strftime('%A, %d %b %Y')}")
            self._update_header_chips(mode_text="Paused")
            self.log("Automation paused", "WARNING")
        else:
            self.pause_event.set()
            self.pause_button.config(text="Pause", bootstyle="warning")
            if hasattr(self, "top_status_label"):
                self.top_status_label.config(text=f"System: Running  |  {datetime.now().strftime('%A, %d %b %Y')}")
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
        self.pause_button.config(text="Pause", bootstyle="warning")
        if hasattr(self, "activity_spinner"):
            self.activity_spinner.stop()
        if hasattr(self, "top_status_label"):
            self.top_status_label.config(text=f"System: Idle  |  {datetime.now().strftime('%A, %d %b %Y')}")
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
        self.schedule_enable_btn.config(text="Disable Schedule", bootstyle="warning")
        self.log("Scheduling enabled", "SUCCESS")
        
        self.save_schedule_settings()
        
        if self.schedule_thread is None or not self.schedule_thread.is_alive():
            self.schedule_thread = threading.Thread(target=self.schedule_monitor, daemon=True)
            self.schedule_thread.start()

    def stop_schedule(self):
        """Stop scheduling"""
        self.schedule_running = False
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
            self.logs_text.config(state="normal")
            self.logs_text.delete("1.0", "end")
            self.logs_text.config(state="disabled")
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




