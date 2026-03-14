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
from gui.gradient_progress import GradientProgressBar
from gui.styles import configure_styles
from gui.sidebar import SidebarMixin
from gui.topbar import TopBarMixin
from gui.status_bar import StatusBarMixin
from gui.menu_bar import MenuBarMixin
from gui.pages.dashboard_page import DashboardPageMixin
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
        self._last_table_signature = None
        self._ld_search_job = None
        self._main_thread_id = threading.get_ident()
        self._ld_checked_names = set()
        self.ld_search_var = tk.StringVar()
        self.ld_sort_var = tk.StringVar(value="Status")
        self.ld_status_filter_var = tk.StringVar(value="All")
        self.ld_account_filter_var = tk.StringVar(value="All")
        
        # Configure custom styles
        configure_styles(self.root, self.style, self.palette, self.display_font, self.mono_font)
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
        # Keep inactive rows uncolored; zebra striping will handle contrast.
        self.ld_table.tag_configure("inactive", background="", foreground="")
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
            is_checked = name in checked_names
            item_id = self.ld_table.insert(
                "",
                "end",
                text="☑" if is_checked else "☐",
                values=(name, serial, self._status_text(status), task_text, progress_text, account_text, actions_text),
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
