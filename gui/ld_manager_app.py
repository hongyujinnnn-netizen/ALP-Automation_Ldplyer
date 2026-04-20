import os
import threading
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont
from tkinter.scrolledtext import ScrolledText
from tkinter import messagebox as MessageBox
from tkinter import filedialog
from tkinter import simpledialog
from datetime import datetime
import json
import time
from pathlib import Path
import subprocess
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
from controllers.app_controller import AppController
from controllers.emulator_controller import EmulatorController
from controllers.otp_controller import OTPController
from controllers.task_controller import TaskController
from core.paths import get_app_paths
from core.managers import AccountManager, ContentManager, BackupManager, SmartScheduler, TaskTemplates
from core.settings import AppSettings, ScheduleSettings
from services.scheduler_service import SchedulerService
from services.emulator_service import EmulatorService
from services.task_service import TaskService
from utils.performance_monitor import PerformanceMonitor
from utils.app_utils import AppUtils
from utils.ip_guard import check_ip_allowed
from services.logging_service import AppLogger
from services.settings_service import SettingsService
from gui.checkbox_treeview import CheckboxTreeview
from gui.components.cards import SectionCard
from gui.components.status import (
    status_background,
    status_color,
    status_filter_values,
    status_label,
    status_sort_key,
    status_table_text,
    status_tag,
)
from gui.mixins import ToolsMixin
from gui.gradient_progress import GradientProgressBar
from gui.styles import configure_styles
from gui.sidebar import SidebarMixin
from gui.topbar import TopBarMixin
from gui.status_bar import StatusBarMixin
from gui.menu_bar import MenuBarMixin
from gui.pages.dashboard_page import DashboardPageMixin
from gui.pages.devices_page import DevicesPageMixin
from gui.pages.tasks_page import TasksPageMixin
from gui.pages.schedule_page import SchedulePageMixin
from gui.pages.content_page import ContentPageMixin
from gui.pages.logs_page import LogsPageMixin
from gui.dialogs.settings_dialog import SettingsDialogMixin
from gui.dialogs.account_dialog import AccountDialogMixin
from gui.dialogs.tools_dialog import ToolsDialogMixin
from gui.dialogs.perf_dialog import PerformanceDialogMixin


class LDManagerApp(
    SidebarMixin,
    TopBarMixin,
    StatusBarMixin,
    MenuBarMixin,
    DashboardPageMixin,
    DevicesPageMixin,
    TasksPageMixin,
    SchedulePageMixin,
    ContentPageMixin,
    LogsPageMixin,
    SettingsDialogMixin,
    AccountDialogMixin,
    ToolsDialogMixin,
    PerformanceDialogMixin,
    ToolsMixin,
):
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
        self._device_runtime_state = {}
        self.dashboard_events = []
        self._last_table_signature = None
        self._ld_search_job = None
        self._main_thread_id = threading.get_ident()
        self._ld_checked_names = set()
        self.ld_search_var = tk.StringVar()
        self.ld_sort_var = tk.StringVar(value="Status")
        self.ld_status_filter_var = tk.StringVar(value="All")
        self.ld_account_filter_var = tk.StringVar(value="All")
        self.ld_group_filter_var = tk.StringVar(value="All Groups")
        self._ld_groups = {}
        
        # Configure custom styles
        configure_styles(self.root, self.style, self.palette, self.display_font, self.mono_font)
        self.paths = get_app_paths()
        self.paths.ensure_runtime_dirs()
        self.app_logger = AppLogger(self.paths)
        self.settings_service = SettingsService(self.paths)
        self.controller = AppController(self.settings_service, log_func=self.log)
        self.otp_controller = OTPController(
            self.settings_service,
            ui_log_func=self.log,
            structured_log_func=self.app_logger.log,
        )
        self.task_service = TaskService()
        self.scheduler_service = SchedulerService()

        try:
            self.emulator = EmulatorService()
        except Exception as e:
            MessageBox.showerror("Initialization Error", f"Failed to initialize emulator control: {str(e)}")
            self.root.destroy()
            return
        self.emulator_controller = EmulatorController(self.emulator)
        self.task_controller = TaskController(self.task_service)
            
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
        self.page_per_account = tk.IntVar(value=2)
        self.accounts_per_ld = tk.IntVar(value=1)
        self.schedule_time = tk.StringVar(value="09:00")
        self.schedule_daily = tk.BooleanVar(value=True)
        self.schedule_weekly = tk.BooleanVar(value=False)
        self.schedule_repeat_hours = tk.IntVar(value=0)  # 0 means no repeat
        self.start_same_time = tk.BooleanVar(value=False)
        self.use_content_queue = tk.BooleanVar(value=True)
        self.auto_arrange_ld = tk.BooleanVar(value=False)
        self.auto_shutdown_pc = tk.BooleanVar(value=False)
        self.scroll_after_post = tk.BooleanVar(value=True)
        self.clear_cache = tk.BooleanVar(value=True)
        self.verify_account = tk.BooleanVar(value=True)
        self.reg_contact_mode = tk.StringVar(value="random_phone")
        self.reg_contact_value = tk.StringVar(value="")
        self.reg_phone_prefix = tk.StringVar(value="+1")
        self.email_provider = tk.StringVar(value="yandex")
        self.email_address = tk.StringVar(value="")
        self.email_app_password = tk.StringVar(value="")
        self.email_imap_server = tk.StringVar(value="imap.yandex.com")
        self.email_imap_port = tk.IntVar(value=993)
        self.email_mailbox = tk.StringVar(value="INBOX")
        self.email_use_ssl = tk.BooleanVar(value=True)
        self.email_unread_only = tk.BooleanVar(value=True)
        self.email_sender_filter = tk.StringVar(value="")
        self.email_subject_filter = tk.StringVar(value="")
        self.email_timeout_seconds = tk.IntVar(value=90)
        self.email_poll_interval_seconds = tk.IntVar(value=5)
        self.email_mark_as_seen = tk.BooleanVar(value=False)
        # Comma-separated list of blocked ISO country codes for IP guard.
        self.blocked_countries = tk.StringVar(
            value="US,KH,CN,TH,VN,PH,ID,MY,LA,MM"
        )
        
        # Task type variables
        self.task_type_var = tk.StringVar(value="scroll")
        self.task_template_var = tk.StringVar(value="custom")
        self.task_type_var.trace_add("write", lambda *_: self._handle_task_type_change())
        
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
        self.root.after(0, self._maximize_on_startup)
        self.load_schedule_settings()
        self.populate_ld_table()
        self.start_status_refresh()
        self.start_analytics_refresh()
        self.start_system_metrics_refresh()

    def _maximize_on_startup(self):
        """Open the main window maximized as soon as the UI is ready."""
        try:
            if platform.system().lower() == "windows":
                self.root.state("zoomed")
                return
        except Exception:
            pass

        try:
            self.root.attributes("-zoomed", True)
            return
        except Exception:
            pass

        try:
            width = self.root.winfo_screenwidth()
            height = self.root.winfo_screenheight()
            self.root.geometry(f"{width}x{height}+0+0")
        except Exception:
            pass

    def _create_card_section(self, parent, title, subtitle=None, pady=(0, 14), expand=False):
        """Compatibility wrapper for the shared SectionCard component."""
        section = SectionCard(parent, title, subtitle, palette=self.palette)
        section.pack(fill="both", expand=expand, pady=pady)
        section.body.section_card = section
        return section.body

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


    def _is_main_thread(self):
        return threading.get_ident() == self._main_thread_id

    def _handle_task_type_change(self):
        self._update_header_chips()

    def _set_system_status(self, status):
        label = status_label(status)
        if hasattr(self, "top_status_label"):
            self.top_status_label.config(text=f"System: {label}  |  {datetime.now().strftime('%A, %d %b %Y')}")
        if hasattr(self, "status_sys_pill"):
            self.status_sys_pill.set_status(status, text=f"System: {label}")

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
            ("Select Online", self.select_online, "outline-info"),
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
            values=status_filter_values(),
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

        tb.Label(filter_frame, text="Group", style="Subtitle.TLabel").pack(side="left")
        self.group_filter_combo = tb.Combobox(
            filter_frame,
            textvariable=self.ld_group_filter_var,
            values=("All Groups", "Ungrouped"),
            state="readonly",
            width=14
        )
        self.group_filter_combo.pack(side="left", padx=(6, 12))
        self.group_filter_combo.bind("<<ComboboxSelected>>", lambda _e: self._render_ld_table())

        tb.Label(filter_frame, text="Sort", style="Subtitle.TLabel").pack(side="left")
        sort_combo = tb.Combobox(
            filter_frame,
            textvariable=self.ld_sort_var,
            values=("Status", "Name", "ADB", "Account", "Group"),
            state="readonly",
            width=11
        )
        sort_combo.pack(side="left", padx=(6, 0))
        sort_combo.bind("<<ComboboxSelected>>", lambda _e: self._render_ld_table())
        tb.Button(
            filter_frame,
            text="Create Group",
            bootstyle="outline-primary",
            command=self.create_ld_group,
            width=12
        ).pack(side="right", padx=(8, 0))
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
        columns = ("name", "serial", "status", "task", "progress", "account", "groups")
        
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
        self.ld_table.column("name", width=118, anchor="w")
        
        self.ld_table.heading("serial", text="ADB Serial", anchor="w")
        self.ld_table.column("serial", width=128, anchor="w")
        
        self.ld_table.heading("status", text="Status", anchor="w")
        self.ld_table.column("status", width=92, anchor="w")

        self.ld_table.heading("task", text="Task", anchor="w")
        self.ld_table.column("task", width=128, anchor="w")

        self.ld_table.heading("progress", text="Progress", anchor="w")
        self.ld_table.column("progress", width=84, anchor="w")
        
        self.ld_table.heading("account", text="Account", anchor="w")
        self.ld_table.column("account", width=124, anchor="w")

        self.ld_table.heading("groups", text="Groups", anchor="w")
        self.ld_table.column("groups", width=180, anchor="w")
        
        # Configure tags with state colors
        self.ld_table.tag_configure("active", background=status_background("Active"), foreground=status_color("Active", self.palette))
        # Keep inactive rows uncolored; zebra striping will handle contrast.
        self.ld_table.tag_configure("inactive", background="", foreground="")
        self.ld_table.tag_configure("running", background=status_background("Running"), foreground=status_color("Running", self.palette))
        self.ld_table.tag_configure("paused", background=status_background("Paused"), foreground=status_color("Paused", self.palette))
        self.ld_table.tag_configure("completed", background=status_background("Completed"), foreground=status_color("Completed", self.palette))
        self.ld_table.tag_configure("queued", background=status_background("Queued"), foreground=status_color("Queued", self.palette))
        self.ld_table.tag_configure("attention", background=status_background("Attention"), foreground=status_color("Attention", self.palette))
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
        self.ld_table.bind("<ButtonRelease-1>", lambda _e: (self.update_selection_info(), self._update_device_focus_card()), add="+")

        self.instance_context_menu = tk.Menu(self.root, tearoff=0)
        self.instance_context_menu.add_command(label="Select All", command=self.select_all)
        self.instance_context_menu.add_command(label="Clear Selection", command=self.deselect_all)
        self.instance_context_menu.add_separator()
        self.instance_context_menu.add_command(label="Run Automation", command=self._context_run_automation)
        self.instance_context_menu.add_separator()
        self.instance_context_menu.add_command(label="Start", command=self._context_start_instance)
        self.instance_context_menu.add_command(label="Stop", command=self._context_stop_instance)
        self.instance_context_menu.add_command(label="Restart", command=self._context_restart_instance)
        self.instance_context_menu.add_separator()
        self.instance_group_menu = tk.Menu(self.instance_context_menu, tearoff=0)
        self.instance_context_menu.add_cascade(label="Groups", menu=self.instance_group_menu)
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
        self.create_devices_tab()
        self.create_tasks_tab()
        self.create_schedule_tab()
        self.create_content_tab()
        self.create_logs_tab()
        self.notebook.bind("<<NotebookTabChanged>>", self._on_notebook_tab_changed)
        self._set_sidebar_nav_active("analytics")
        self._on_notebook_tab_changed()

    def _on_notebook_tab_changed(self, _event=None):
        idx = self.notebook.index("current")
        tab_to_nav = {
            0: "analytics",
            1: "devices",
            2: "automation",
            3: "schedule",
            4: "content",
            5: "logs",
        }
        self._set_sidebar_nav_active(tab_to_nav.get(idx, "analytics"))
        if hasattr(self, "_top_tab_buttons"):
            active_label = "Analytics"
            if idx == 1:
                active_label = "Devices"
            elif idx == 2:
                active_label = "Tasks"
            elif idx == 5:
                active_label = "Logs"
            for label, btn in self._top_tab_buttons.items():
                btn.configure(bootstyle="info" if label == active_label else "secondary-link")

    def _status_text(self, status):
        return status_table_text(status)

    def _status_tag(self, status):
        return status_tag(status)

    def _ensure_device_runtime_entry(self, ld_name):
        entry = self._device_runtime_state.setdefault(
            ld_name,
            {
                "state": "Idle",
                "task": "Waiting for selection",
                "progress": 0,
                "queue_label": "-",
            },
        )
        serial = self._ld_snapshot.get(ld_name) or self.emulator.name_to_serial.get(ld_name)
        if serial:
            entry["serial"] = serial
        return entry

    def update_device_runtime_state(self, ld_name, payload=None, **kwargs):
        if not self._is_main_thread():
            merged = {}
            if payload:
                merged.update(payload)
            merged.update(kwargs)
            try:
                self.root.after(0, lambda name=ld_name, data=merged: self.update_device_runtime_state(name, data))
            except Exception:
                pass
            return

        entry = self._ensure_device_runtime_entry(ld_name)
        if payload:
            entry.update(payload)
        if kwargs:
            entry.update(kwargs)
        timestamp = datetime.now().isoformat()
        entry.setdefault("started_at", timestamp)
        entry["updated_at"] = timestamp
        self._render_devices_page()
        if hasattr(self, "_refresh_dashboard"):
            self._refresh_dashboard()

    def _mark_selected_devices_as_queued(self, selected_ld_names):
        timestamp = datetime.now().isoformat()
        selected_set = set(selected_ld_names)
        for order, name in enumerate(selected_ld_names, start=1):
            self.update_device_runtime_state(
                name,
                state="Queued",
                task="Waiting to start task",
                progress=0,
                queue_label=f"#{order}",
                started_at=timestamp,
            )
        for name in list(self._device_runtime_state.keys()):
            if name not in selected_set and self._device_runtime_state[name].get("state") == "Queued":
                self.update_device_runtime_state(name, state="Idle", task="Waiting for selection", progress=0, queue_label="-")

    def _get_checked_names(self):
        return set(self._ld_checked_names)

    def _collect_selected_ld_names(self):
        selected_names = set(self._ld_checked_names)
        if hasattr(self, "ld_table"):
            for item in self.ld_table.get_checked_items():
                values = self.ld_table.item(item, "values")
                if values:
                    selected_names.add(values[0])
        return selected_names

    def _normalize_ld_groups(self, groups=None):
        source = groups if groups is not None else self._ld_groups
        normalized = {}
        for raw_name, raw_members in (source or {}).items():
            name = str(raw_name).strip()
            if not name:
                continue
            members = []
            for member in raw_members or []:
                member_name = str(member).strip()
                if member_name and member_name not in members:
                    members.append(member_name)
            normalized[name] = sorted(members, key=str.lower)
        return normalized

    def _sync_ld_groups_with_snapshot(self):
        snapshot_names = set(self._ld_snapshot.keys())
        normalized = {}
        changed = False
        for group_name, members in self._normalize_ld_groups().items():
            kept = list(members) if not snapshot_names else [name for name in members if name in snapshot_names]
            normalized[group_name] = kept
            if kept != members:
                changed = True
        if normalized != self._ld_groups:
            self._ld_groups = normalized
            changed = True
        self._refresh_group_ui()
        if changed:
            self.save_settings()

    def _device_groups(self, ld_name):
        return [group_name for group_name, members in self._ld_groups.items() if ld_name in members]

    def _device_group_text(self, ld_name):
        groups = self._device_groups(ld_name)
        return ", ".join(groups) if groups else "Ungrouped"

    def _refresh_group_ui(self):
        group_names = sorted(self._ld_groups.keys(), key=str.lower)
        group_values = ["All Groups", "Ungrouped", *group_names]
        if hasattr(self, "group_filter_combo"):
            self.group_filter_combo.configure(values=group_values)
        current_filter = self.ld_group_filter_var.get().strip() or "All Groups"
        if current_filter not in group_values:
            self.ld_group_filter_var.set("All Groups")

        if hasattr(self, "device_group_list"):
            selected_group = self._get_active_group_name()
            self.device_group_list.delete(0, "end")
            for group_name in group_names:
                count = len(self._ld_groups.get(group_name, []))
                self.device_group_list.insert("end", f"{group_name}  ({count})")
            if selected_group in group_names:
                index = group_names.index(selected_group)
                self.device_group_list.selection_set(index)
        if hasattr(self, "device_group_summary"):
            assigned = sum(len(members) for members in self._ld_groups.values())
            self.device_group_summary.config(text=f"{len(group_names)} groups  |  {assigned} assigned")

    def _extract_group_name(self, display_text):
        if not display_text:
            return None
        return str(display_text).rsplit("  (", 1)[0].strip()

    def _get_active_group_name(self):
        if hasattr(self, "device_group_list"):
            selection = self.device_group_list.curselection()
            if selection:
                return self._extract_group_name(self.device_group_list.get(selection[0]))
        current_filter = self.ld_group_filter_var.get().strip()
        if current_filter not in ("", "All Groups", "Ungrouped"):
            return current_filter
        return None

    def _sync_group_filter_from_list(self):
        group_name = self._get_active_group_name()
        if group_name:
            self.ld_group_filter_var.set(group_name)
            self._render_ld_table()

    def create_ld_group(self):
        group_name = simpledialog.askstring("Create Group", "Group name:", parent=self.root)
        group_name = (group_name or "").strip()
        if not group_name:
            return
        if group_name in self._ld_groups:
            MessageBox.showwarning("Create Group", f"Group '{group_name}' already exists.")
            return
        self._ld_groups[group_name] = []
        self._refresh_group_ui()
        self.save_settings()
        self.log(f"Created group: {group_name}", "SUCCESS")

    def rename_selected_ld_group(self):
        current_name = self._get_active_group_name()
        if not current_name:
            MessageBox.showerror("Rename Group", "Select a group first.")
            return
        new_name = simpledialog.askstring("Rename Group", "New group name:", initialvalue=current_name, parent=self.root)
        new_name = (new_name or "").strip()
        if not new_name or new_name == current_name:
            return
        if new_name in self._ld_groups:
            MessageBox.showwarning("Rename Group", f"Group '{new_name}' already exists.")
            return
        self._ld_groups[new_name] = self._ld_groups.pop(current_name, [])
        if self.ld_group_filter_var.get() == current_name:
            self.ld_group_filter_var.set(new_name)
        self._refresh_group_ui()
        self.save_settings()
        self._render_ld_table()
        self.log(f"Renamed group: {current_name} -> {new_name}", "SUCCESS")

    def delete_selected_ld_group(self):
        group_name = self._get_active_group_name()
        if not group_name:
            MessageBox.showerror("Delete Group", "Select a group first.")
            return
        if not MessageBox.askyesno("Delete Group", f"Delete group '{group_name}'?"):
            return
        self._ld_groups.pop(group_name, None)
        if self.ld_group_filter_var.get() == group_name:
            self.ld_group_filter_var.set("All Groups")
        self._refresh_group_ui()
        self.save_settings()
        self._render_ld_table()
        self.log(f"Deleted group: {group_name}", "INFO")

    def assign_selected_to_group(self):
        self.update_selection_info()
        target_group = self._get_active_group_name()
        if not target_group:
            target_group = simpledialog.askstring("Assign Group", "Assign selected LDs to group:", parent=self.root)
            target_group = (target_group or "").strip()
        if not target_group:
            return
        if target_group not in self._ld_groups:
            self._ld_groups[target_group] = []
        selected_names = sorted(self._collect_selected_ld_names(), key=str.lower)
        if not selected_names and self._context_ld_name:
            selected_names = [self._context_ld_name]
        if not selected_names:
            MessageBox.showerror("Assign Group", "Select at least one LD first.")
            return
        members = set(self._ld_groups.get(target_group, []))
        members.update(name for name in selected_names if name in self._ld_snapshot)
        self._ld_groups[target_group] = sorted(members, key=str.lower)
        self._refresh_group_ui()
        self.save_settings()
        self._render_ld_table()
        self.log(f"Assigned {len(selected_names)} LD(s) to group: {target_group}", "SUCCESS")

    def select_active_group_devices(self):
        group_name = self._get_active_group_name()
        if not group_name:
            MessageBox.showerror("Select Group", "Select a group first.")
            return
        members = [name for name in self._ld_groups.get(group_name, []) if name in self._ld_snapshot]
        if not members:
            MessageBox.showwarning("Select Group", f"Group '{group_name}' has no active LD instances.")
            return
        self._ld_checked_names = set(members)
        self._render_ld_table()
        self.log(f"Selected {len(members)} LD(s) from group: {group_name}", "INFO")

    def _filtered_snapshot_rows(self):
        query = self.ld_search_var.get().strip().lower()
        status_filter = self.ld_status_filter_var.get().strip()
        account_filter = self.ld_account_filter_var.get().strip()
        group_filter = self.ld_group_filter_var.get().strip()
        rows = []
        for name, serial in self._ld_snapshot.items():
            status = self._ld_status_cache.get(name, "Inactive")
            account_text = self._ld_account_cache.get(name, "No account")
            group_text = self._device_group_text(name)
            device_groups = self._device_groups(name)
            row_text = f"{name} {serial} {account_text} {status} {group_text}".lower()
            if query and query not in row_text:
                continue
            if status_filter != "All" and status != status_filter:
                continue
            has_account = bool(account_text and account_text != "No account")
            if account_filter == "Has Account" and not has_account:
                continue
            if account_filter == "No Account" and has_account:
                continue
            if group_filter == "Ungrouped" and device_groups:
                continue
            if group_filter not in ("", "All Groups", "Ungrouped") and group_filter not in device_groups:
                continue
            rows.append((name, serial, status, account_text, group_text))

        sort_mode = self.ld_sort_var.get()
        if sort_mode == "Name":
            rows.sort(key=lambda r: r[0].lower())
        elif sort_mode == "ADB":
            rows.sort(key=lambda r: r[1].lower())
        elif sort_mode == "Account":
            rows.sort(key=lambda r: (r[3] == "No account", r[3].lower(), r[0].lower()))
        elif sort_mode == "Group":
            rows.sort(key=lambda r: (r[4] == "Ungrouped", r[4].lower(), r[0].lower()))
        else:
            rows.sort(key=lambda r: (status_sort_key(r[2]), r[0].lower()))
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

        for idx, (name, serial, status, account_text, group_text) in enumerate(rows):
            if status == "Running":
                task_text = {
                    "scroll": "Scroll Feed",
                    "reels": "Watch Reels",
                    "reg_account": "Register Account",
                    "test_feature": "Test Feature",
                }.get(self.task_type_var.get(), self.task_type_var.get().title())
                progress_text = f"{random.randint(24, 96)}%"
            elif status == "Active":
                task_text = "Starting"
                progress_text = f"{random.randint(8, 30)}%"
            elif status == "Inactive":
                task_text = "—"
                progress_text = "0%"
            else:
                task_text = "—"
                progress_text = "0%"
            zebra_tag = "odd_row" if idx % 2 == 0 else "even_row"
            is_checked = name in checked_names
            item_id = self.ld_table.insert(
                "",
                "end",
                text="☑" if is_checked else "☐",
                values=(name, serial, self._status_text(status), task_text, progress_text, account_text, group_text),
            )
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
        self._sync_ld_groups_with_snapshot()
        if status_cache is not None:
            self._ld_status_cache = status_cache
        if account_cache is not None:
            self._ld_account_cache = account_cache

        if not changed:
            return
        self._last_table_signature = None
        self._render_ld_table()
        if hasattr(self, "_render_devices_page"):
            self._render_devices_page()
        if hasattr(self, "_refresh_dashboard"):
            self._refresh_dashboard()

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
        self._rebuild_instance_group_menu()
        self.instance_context_menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def _rebuild_instance_group_menu(self):
        self.instance_group_menu.delete(0, "end")
        self.instance_group_menu.add_command(label="Create Group...", command=self.create_ld_group)
        self.instance_group_menu.add_separator()
        target_names = self._context_target_ld_names()
        current_groups = set(self._device_groups(self._context_ld_name))
        if not self._ld_groups:
            self.instance_group_menu.add_command(label="No groups yet", state="disabled")
        else:
            for group_name in sorted(self._ld_groups.keys(), key=str.lower):
                prefix = "Remove from" if len(target_names) == 1 and group_name in current_groups else "Assign to"
                self.instance_group_menu.add_command(
                    label=f"{prefix} {group_name}",
                    command=lambda group=group_name: self._toggle_context_group(group),
                )
        self.instance_group_menu.add_separator()
        self.instance_group_menu.add_command(label="Remove From All Groups", command=self._remove_context_ld_from_groups)

    def _context_target_ld_names(self):
        selected_names = sorted(self._collect_selected_ld_names(), key=str.lower)
        if selected_names:
            if self._context_ld_name and self._context_ld_name not in selected_names:
                selected_names.append(self._context_ld_name)
                selected_names.sort(key=str.lower)
            return selected_names
        return [self._context_ld_name] if self._context_ld_name else []

    def _toggle_context_group(self, group_name):
        target_names = self._context_target_ld_names()
        if not target_names or group_name not in self._ld_groups:
            return
        members = set(self._ld_groups.get(group_name, []))
        target_set = set(target_names)
        if len(target_names) == 1 and target_names[0] in members:
            members.remove(target_names[0])
            action = "Removed"
        else:
            members.update(name for name in target_names if name in self._ld_snapshot)
            action = "Assigned"
        if members:
            self._ld_groups[group_name] = sorted(members, key=str.lower)
        else:
            self._ld_groups.pop(group_name, None)
        self._refresh_group_ui()
        self.save_settings()
        self._render_ld_table()
        self.log(f"{action} {len(target_names)} LD(s) {'from' if action == 'Removed' else 'to'} group: {group_name}", "INFO")

    def _remove_context_ld_from_groups(self):
        target_names = set(self._context_target_ld_names())
        if not target_names:
            return
        changed = False
        for group_name in list(self._ld_groups.keys()):
            members = [name for name in self._ld_groups[group_name] if name not in target_names]
            if len(members) != len(self._ld_groups[group_name]):
                changed = True
            if members:
                self._ld_groups[group_name] = members
            else:
                self._ld_groups.pop(group_name, None)
        if not changed:
            return
        self._refresh_group_ui()
        self.save_settings()
        self._render_ld_table()
        self.log(f"Removed {len(target_names)} LD(s) from all groups", "INFO")

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

        # Keep existing multi-select checks; only ensure the clicked row is included.
        target_item = None
        for item in self.ld_table.get_children():
            values = self.ld_table.item(item, "values")
            if values and values[0] == name:
                target_item = item
                break

        if not target_item:
            MessageBox.showerror("Run Automation", f"Could not find emulator row: {name}")
            return

        if not self.ld_table.checkboxes.get(target_item, False):
            self.ld_table.toggle_checkbox(target_item)

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

    def cleanup_old_backups(self):
        """Delete older backup ZIPs while keeping the most recent set."""
        if not MessageBox.askyesno(
            "Clean Old Backups",
            "Delete older backup archives and keep only the most recent 10?",
        ):
            return

        try:
            self.backup_manager.cleanup_old_backups(keep_count=10)
        except Exception as exc:
            MessageBox.showerror("Backup Cleanup", f"Cleanup failed: {exc}")
            return

        MessageBox.showinfo(
            "Backup Cleanup",
            "Old backups cleaned up. The most recent 10 archives were kept.",
        )

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

        for task in tasks:
            if "page_per_account" in task:
                try:
                    self.page_per_account.set(max(1, int(task["page_per_account"])))
                except Exception:
                    pass
                break

        for task in tasks:
            if "accounts_per_ld" in task:
                try:
                    self.accounts_per_ld.set(max(1, int(task["accounts_per_ld"])))
                except Exception:
                    pass
                break

        for task in tasks:
            if task.get("type") == "reels" and "scroll_after_post" in task:
                try:
                    self.scroll_after_post.set(bool(task["scroll_after_post"]))
                except Exception:
                    pass
                break

        for task in tasks:
            if task.get("type") == "reels" and "clear_cache" in task:
                try:
                    self.clear_cache.set(bool(task["clear_cache"]))
                except Exception:
                    pass
                break

        self.log(
            f" Applied template: {template.get('name', template_key)} - {template.get('description', '')}",
            level="SUCCESS",
        )

    def load_settings(self):
        """Load general settings from disk."""
        settings = self.controller.load_app_settings()
        email_config, email_request = self.otp_controller.load_email_settings()

        self.parallel_ld.set(settings.parallel_ld)
        self.boot_delay.set(settings.boot_delay)
        self.task_duration.set(settings.task_duration)
        self.max_videos.set(settings.max_videos)
        self.page_per_account.set(settings.page_per_account)
        self.accounts_per_ld.set(settings.accounts_per_ld)
        self.start_same_time.set(settings.start_same_time)
        self.use_content_queue.set(settings.use_content_queue)
        self.auto_arrange_ld.set(settings.auto_arrange_ld)
        self.auto_shutdown_pc.set(settings.auto_shutdown_pc)
        self.task_type_var.set(settings.task_type)
        self.task_template_var.set(settings.task_template)
        self.scroll_after_post.set(settings.scroll_after_post)
        self.clear_cache.set(settings.clear_cache)
        self.verify_account.set(settings.verify_account)
        self.reg_contact_mode.set(settings.reg_contact_mode)
        self.reg_contact_value.set(settings.reg_contact_value)
        self.reg_phone_prefix.set(settings.reg_phone_prefix)
        self.email_provider.set(email_config.provider)
        self.email_address.set(email_config.email_address)
        self.email_app_password.set(email_config.app_password)
        self.email_imap_server.set(email_config.imap_server)
        self.email_imap_port.set(email_config.imap_port)
        self.email_mailbox.set(email_config.mailbox)
        self.email_use_ssl.set(email_config.use_ssl)
        self.email_unread_only.set(email_request.unread_only)
        self.email_sender_filter.set(email_request.sender_filter)
        self.email_subject_filter.set(email_request.subject_filter)
        self.email_timeout_seconds.set(email_request.timeout_seconds)
        self.email_poll_interval_seconds.set(email_request.poll_interval_seconds)
        self.email_mark_as_seen.set(email_request.mark_as_seen)
        self._ld_groups = self._normalize_ld_groups(settings.ld_groups)
        self._refresh_group_ui()
        try:
            # Store as comma-separated, upper-case country codes.
            blocked = ",".join(settings.blocked_countries)
            self.blocked_countries.set(blocked)
        except Exception:
            # Fallback to default if anything goes wrong.
            self.blocked_countries.set("US,KH,CN,TH,VN,PH,ID,MY,LA,MM")

    def save_settings(self):
        """Persist general settings to disk."""
        settings = AppSettings(
            parallel_ld=int(self.parallel_ld.get()),
            boot_delay=int(self.boot_delay.get()),
            task_duration=int(self.task_duration.get()),
            max_videos=int(self.max_videos.get()),
            page_per_account=int(self.page_per_account.get()),
            accounts_per_ld=int(self.accounts_per_ld.get()),
            start_same_time=bool(self.start_same_time.get()),
            use_content_queue=bool(self.use_content_queue.get()),
            auto_arrange_ld=bool(self.auto_arrange_ld.get()),
            auto_shutdown_pc=bool(self.auto_shutdown_pc.get()),
            task_type=str(self.task_type_var.get()),
            task_template=str(self.task_template_var.get()),
            scroll_after_post=bool(self.scroll_after_post.get()),
            clear_cache=bool(self.clear_cache.get()),
            verify_account=bool(self.verify_account.get()),
            reg_contact_mode=str(self.reg_contact_mode.get()),
            reg_contact_value=str(self.reg_contact_value.get()),
            reg_phone_prefix=str(self.reg_phone_prefix.get()),
            email_provider=str(self.email_provider.get()),
            email_address=str(self.email_address.get()),
            email_app_password=str(self.email_app_password.get()),
            email_imap_server=str(self.email_imap_server.get()),
            email_imap_port=int(self.email_imap_port.get()),
            email_mailbox=str(self.email_mailbox.get()),
            email_use_ssl=bool(self.email_use_ssl.get()),
            email_unread_only=bool(self.email_unread_only.get()),
            email_sender_filter=str(self.email_sender_filter.get()),
            email_subject_filter=str(self.email_subject_filter.get()),
            email_timeout_seconds=int(self.email_timeout_seconds.get()),
            email_poll_interval_seconds=int(self.email_poll_interval_seconds.get()),
            email_mark_as_seen=bool(self.email_mark_as_seen.get()),
            ld_groups=self._normalize_ld_groups(),
            blocked_countries=[
                code.strip().upper()
                for code in self.blocked_countries.get().split(",")
                if code.strip()
            ],
        )

        self.controller.save_app_settings(settings)

    def load_schedule_settings(self):
        """Load scheduling settings from the configured schedule settings file."""
        schedule = self.controller.load_schedule_settings()

        self.schedule_time.set(schedule.schedule_time)
        self.schedule_daily.set(schedule.schedule_daily)
        self.schedule_weekly.set(schedule.schedule_weekly)
        self.schedule_repeat_hours.set(schedule.schedule_repeat_hours)

        for day_name, day_var in self.schedule_days.items():
            day_var.set(schedule.schedule_days.get(day_name, False))

    def save_schedule_settings(self):
        """Save scheduling settings to the configured schedule settings file."""
        schedule = ScheduleSettings(
            schedule_time=self.schedule_time.get(),
            schedule_daily=bool(self.schedule_daily.get()),
            schedule_weekly=bool(self.schedule_weekly.get()),
            schedule_repeat_hours=int(self.schedule_repeat_hours.get()),
            schedule_days={day: bool(var.get()) for day, var in self.schedule_days.items()},
        )

        self.controller.save_schedule_settings(schedule)

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
                if hasattr(self, "_refresh_dashboard"):
                    self._refresh_dashboard()
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
        tag = "EMULATOR_COUNT" if message.startswith("Available emulators:") else level
        
        # Determine color based on level
        colors = {
            "INFO": self.palette["primary"],
            "SUCCESS": self.palette["success"],
            "WARNING": self.palette["warning"],
            "ERROR": self.palette["danger"],
            "DEBUG": "#9b59b6"
        }
        
        _ = colors.get(level, "#ecf0f1")
        
        self._record_dashboard_event(timestamp, message, level)
        
        # Insert with tags for coloring
        self.logs_text.config(state="normal")
        
        # Insert timestamp
        self.logs_text.insert("end", f"[{timestamp}] ", "TIMESTAMP")
        
        # Insert message with level tag
        self.logs_text.insert("end", f"{message}\n", tag)
        
        # Auto-scroll to end
        self.logs_text.see("end")
        self.logs_text.config(state="disabled")

        # Keep the system pill reserved for mode state; important messages live in logs/events.
        if level in ["SUCCESS", "ERROR", "WARNING"]:
            mode_text = "Idle"
            if getattr(self, "running_event", None) and self.running_event.is_set():
                mode_text = "Paused" if getattr(self, "pause_event", None) and not self.pause_event.is_set() else "Running"
            self._update_header_chips(
                mode_text=mode_text
            )

        self.app_logger.log(
            level,
            message,
            running=bool(getattr(self, "running_event", None) and self.running_event.is_set()),
            schedule_running=bool(getattr(self, "schedule_running", False)),
        )

    def _record_dashboard_event(self, timestamp, message, level):
        """Keep a compact high-signal event buffer for the dashboard."""
        important_terms = (
            "automation",
            "scheduled",
            "schedule",
            "started",
            "stopped",
            "restarted",
            "completed",
            "failed",
            "error",
            "warning",
            "queue",
            "backup",
            "restore",
            "account",
        )
        normalized_level = str(level).upper()
        normalized_message = str(message).strip()
        is_important = normalized_level in {"SUCCESS", "WARNING", "ERROR"}
        is_important = is_important or any(term in normalized_message.lower() for term in important_terms)
        if not is_important:
            return

        if not hasattr(self, "dashboard_events"):
            self.dashboard_events = []
        self.dashboard_events.append({
            "time": timestamp,
            "level": normalized_level,
            "message": normalized_message[:160],
        })
        self.dashboard_events = self.dashboard_events[-80:]
        if hasattr(self, "dashboard_recent_events_frame"):
            self._render_recent_events()

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
        self._mark_selected_devices_as_queued(selected_ld_names)
        
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
        if hasattr(self, "_render_devices_page"):
            self._render_devices_page()

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
            "analytics": str(total),
            "devices": str(online),
            "automation": str(running),
            "queue": str(len(self.content_manager.get_queue_items())) if hasattr(self, "content_manager") else "0",
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
        self.ld_group_filter_var.set("All Groups")
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
            self.emulator = EmulatorService()
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
                    self.emulator_controller.start_emulator(name, delay_between_starts=self.boot_delay.get())
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
                self.emulator_controller.stop_emulator(name)
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
        runtime_defaults = {"state": status}
        if status == "Inactive":
            runtime_defaults.update({"task": "Waiting for selection", "progress": 0, "queue_label": "-"})
        elif status == "Active":
            runtime_defaults.update({"task": "Device active", "progress": 30})
        elif status == "Running":
            runtime_defaults.update({
                "task": {
                    "scroll": "Scroll Feed",
                    "reels": "Watch Reels",
                    "reg_account": "Register Account",
                    "test_feature": "Test Feature",
                }.get(self.task_type_var.get(), self.task_type_var.get().title()),
                "progress": 72,
            })
        elif status == "Completed":
            runtime_defaults.update({"task": "Task completed", "progress": 100})
        self.update_device_runtime_state(ld_name, runtime_defaults)
        self._last_table_signature = None
        for item in self.ld_table.get_children():
            values = self.ld_table.item(item)["values"]
            if values[0] == ld_name:
                # Update values
                task_text = values[3] if len(values) > 3 else "-"
                progress_text = values[4] if len(values) > 4 else "0%"
                account_text = values[5] if len(values) > 5 else "No account"
                group_text = values[6] if len(values) > 6 else self._device_group_text(ld_name)
                if status == "Inactive":
                    task_text = "-"
                    progress_text = "0%"
                elif status == "Running" and task_text in ("-", "Starting"):
                    task_text = {
                        "scroll": "Scroll Feed",
                        "reels": "Watch Reels",
                        "reg_account": "Register Account",
                        "test_feature": "Test Feature",
                    }.get(self.task_type_var.get(), self.task_type_var.get().title())
                self.ld_table.item(
                    item,
                    values=(values[0], values[1], self._status_text(status), task_text, progress_text, account_text, group_text),
                )
                
                # Update tags
                tags = list(self.ld_table.item(item, "tags"))
                tags = [t for t in tags if t not in ("active", "inactive", "running", "paused", "completed", "queued", "attention")]
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
            from core.logic.task_scroll import ScrollTaskHandler
            task_handler = ScrollTaskHandler(
                self.emulator,
                self.log,
                self.pause_event,
                lambda: self.running_event.is_set()
            )
            # Pass blocked countries for per-LD IP guard inside the handler.
            task_handler.blocked_countries = [
                code.strip().upper()
                for code in self.blocked_countries.get().split(",")
                if code.strip()
            ]
            task_handler.contact_mode = self.reg_contact_mode.get()
            task_handler.contact_value = self.reg_contact_value.get().strip()
            task_handler.phone_prefix = self.reg_phone_prefix.get().strip()
            task_handler.auto_arrange_ld = bool(self.auto_arrange_ld.get())
            task_handler.state_callback = self.update_device_runtime_state
        elif task_type == "reg_account":
            from core.logic.reg_account import RegAccountTaskHandler
            task_handler = RegAccountTaskHandler(
                self.emulator,
                self.log,
                self.pause_event,
                lambda: self.running_event.is_set(),
            )
            task_handler.blocked_countries = [
                code.strip().upper()
                for code in self.blocked_countries.get().split(",")
                if code.strip()
            ]
            task_handler.contact_mode = self.reg_contact_mode.get()
            task_handler.contact_value = self.reg_contact_value.get().strip()
            task_handler.phone_prefix = self.reg_phone_prefix.get().strip()
            task_handler.auto_arrange_ld = bool(self.auto_arrange_ld.get())
            task_handler.state_callback = self.update_device_runtime_state
        elif task_type == "reels":
            from core.logic.task_reels import ReelsTaskHandler
            task_handler = ReelsTaskHandler(
                self.emulator,
                self.log,
                self.pause_event,
                lambda: self.running_event.is_set(),
                self.content_manager if self.use_content_queue.get() else None
            )
            task_handler.blocked_countries = [
                code.strip().upper()
                for code in self.blocked_countries.get().split(",")
                if code.strip()
            ]
            task_handler.auto_arrange_ld = bool(self.auto_arrange_ld.get())
            task_handler.state_callback = self.update_device_runtime_state
        elif task_type == "test_feature":
            from tests.test_feature import TestFeatureTaskHandler
            task_handler = TestFeatureTaskHandler(
                self.emulator,
                self.log,
                self.pause_event,
                lambda: self.running_event.is_set(),
            )
            task_handler.auto_arrange_ld = bool(self.auto_arrange_ld.get())
            task_handler.state_callback = self.update_device_runtime_state
        else:
            MessageBox.showwarning(
                "Task Not Implemented",
                "This task type is UI-only right now. Please use Scroll Feed, Register Account, Watch Reels, or Test Feature."
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
        self._set_system_status("Running")
        if hasattr(self, "status_task_lbl"):
            self.status_task_lbl.config(text=f"Tasks: {len(selected_ld_names)} active")
        self._update_header_chips(mode_text="Running")

        self.log(f" Starting automation for {len(selected_ld_names)} LDs", "SUCCESS")
        self.log(f"Task type: {task_type}, Duration: {self.task_duration.get()} minutes", "INFO")

        # Create automation thread
        def automation_thread():
            completed_normally = False
            try:
                request = self.task_controller.build_request(
                    selected_ld_names=selected_ld_names,
                    task_type=task_type,
                    task_template=self.task_template_var.get(),
                    parallel_ld=self.parallel_ld.get(),
                    start_same_time=self.start_same_time.get(),
                    auto_arrange_ld=self.auto_arrange_ld.get(),
                    boot_delay=self.boot_delay.get(),
                    task_duration_seconds=self.task_duration.get() * 60,
                    max_videos=self.max_videos.get(),
                    page_per_account=self.page_per_account.get(),
                    accounts_per_ld=self.accounts_per_ld.get(),
                    scroll_after_post=self.scroll_after_post.get(),
                    clear_cache=self.clear_cache.get(),
                    verify_account=self.verify_account.get(),
                )
                main_window = self.task_controller.create_runner(
                    request=request,
                    running_flag=lambda: self.running_event.is_set(),
                    log_func=self.log,
                    task_handler=task_handler,
                    progress_callback=self.update_progress,
                    emulator=self.emulator,
                    state_callback=self.update_device_runtime_state,
                )

                main_window.main()
                completed_normally = self.running_event.is_set()
                self.performance_monitor.end_task_timer(True)

            except Exception as e:
                self.log(f" Error in automation: {str(e)}", "ERROR")
                self.performance_monitor.end_task_timer(False)
                MessageBox.showerror("Error", f"Automation error: {str(e)}")
            finally:
                self.stop_automation(confirm=False)
                if completed_normally and self.auto_shutdown_pc.get():
                    self.root.after(0, self._schedule_pc_shutdown)

        threading.Thread(target=automation_thread, daemon=True).start()

    def _schedule_pc_shutdown(self):
        """Schedule a PC shutdown after automation completes."""
        if platform.system().lower() != "windows":
            self.log("Auto shutdown is only supported on Windows.", "WARNING")
            return

        try:
            subprocess.Popen(
                [
                    "shutdown",
                    "/s",
                    "/t",
                    "30",
                    "/c",
                    "ALP Automation completed all selected tasks.",
                ]
            )
            self.log(
                "Automation completed. PC shutdown scheduled in 30 seconds. Run 'shutdown /a' to cancel.",
                "WARNING",
            )
        except Exception as exc:
            self.log(f"Failed to schedule PC shutdown: {exc}", "ERROR")

    def toggle_pause(self):
        """Toggle pause state"""
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.pause_button.config(text="Resume")
            self._set_system_status("Paused")
            self._update_header_chips(mode_text="Paused")
            self.log("Automation paused", "WARNING")
        else:
            self.pause_event.set()
            self.pause_button.config(text="Pause")
            self._set_system_status("Running")
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
        self._set_system_status("Idle")
        if hasattr(self, "status_task_lbl"):
            self.status_task_lbl.config(text="Tasks: 0 active")
        self._update_header_chips(mode_text="Idle")
        self.log("Automation stopped", "INFO")
        self.update_progress(0)
        for name in list(self._device_runtime_state.keys()):
            current_state = self._device_runtime_state[name].get("state", "")
            if current_state not in ("Completed", "Idle"):
                self.update_device_runtime_state(name, state="Idle", task="Waiting for next run", progress=0, queue_label="-")

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
        if hasattr(self, "_refresh_dashboard"):
            self._refresh_dashboard()
        
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
        if hasattr(self, "_refresh_dashboard"):
            self._refresh_dashboard()

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
                should_run = self.scheduler_service.should_run(
                    now=now,
                    schedule_time=self.schedule_time.get(),
                    schedule_daily=self.schedule_daily.get(),
                    schedule_days={day: var.get() for day, var in self.schedule_days.items()},
                    is_running=self.running_event.is_set(),
                )

                if should_run:
                    self.log(f" Scheduled task triggered at {now.strftime('%H:%M')}", "INFO")
                    self.root.after(0, self.start_automation)

                    decision = self.scheduler_service.apply_repeat_interval(
                        now,
                        self.schedule_repeat_hours.get(),
                    )
                    if decision.next_time:
                        self.schedule_time.set(decision.next_time)
                        self.log(f"Next run scheduled for {decision.next_time}", "INFO")
                
                time.sleep(30)
            except Exception as e:
                self.log(f"Error in schedule monitor: {e}", "ERROR")
                time.sleep(60)

   

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
        if hasattr(self, "app_logger"):
            self.app_logger.close()
        self.root.destroy()
