import json
import os
import platform
import random
import re
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, simpledialog, ttk
from tkinter import font as tkfont
from tkinter import messagebox as MessageBox
from tkinter.scrolledtext import ScrolledText

import ttkbootstrap as tb
from ttkbootstrap.constants import *

# Import local modules
from controllers.app_controller import AppController
from controllers.automation_controller import AutomationController, AutomationState
from controllers.emulator_controller import EmulatorController
from controllers.otp_controller import OTPController
from controllers.task_controller import TaskController
from core.managers import AccountManager, BackupManager, ContentManager, SmartScheduler, TaskTemplates
from core.paths import get_app_paths
from core.settings import AppSettings, ScheduleSettings
from gui.appearance import resolve_appearance
from gui.checkbox_treeview import CheckboxTreeview
from gui.components.cards import SectionCard
from gui.components.command_palette import Command, CommandPalette
from gui.components.state_views import StateView
from gui.components.status import (
    StatusPill,
    configure_status_tree_tags,
    status_filter_values,
    status_label,
    status_sort_key,
    status_table_text,
    status_tag,
)
from gui.dialogs.perf_dialog import PerformanceDialogMixin
from gui.dialogs.settings_dialog import SettingsDialogMixin
from gui.dialogs.tools_dialog import ToolsDialogMixin
from gui.gradient_progress import GradientProgressBar
from gui.menu_bar import MenuBarMixin
from gui.mixins import ToolsMixin
from gui.pages.account_page import AccountDialogMixin
from gui.pages.analytics_page import DashboardPageMixin
from gui.pages.backup_page import BackupPageMixin
from gui.pages.content_page import ContentPageMixin
from gui.pages.dashboard_page import DashboardDialogMixin
from gui.pages.devices_page import DevicesPageMixin
from gui.pages.logs_page import LogsPageMixin
from gui.pages.schedule_page import SchedulePageMixin
from gui.pages.tasks_page import TasksPageMixin
from gui.sidebar import SidebarMixin
from gui.status_bar import StatusBarMixin
from gui.styles import configure_styles
from gui.topbar import TopBarMixin
from services.emulator_service import EmulatorService
from services.logging_service import AppLogger
from services.scheduler_service import SchedulerService
from services.settings_service import SettingsService
from services.task_handler_factory import (
    TaskHandlerContext,
    TaskHandlerFactory,
    UnsupportedTaskTypeError,
)
from services.task_service import TaskService
from utils.app_utils import AppUtils
from utils.ip_guard import check_ip_allowed
from utils.performance_monitor import PerformanceMonitor
from utils.system_power import schedule_pc_shutdown

_DEV_EMULATOR_NAMES = ("US - clone", "US - 01", "US - 02", "US - 03", "US - 04", "US - 05")


class LDManagerApp(
    SidebarMixin,
    TopBarMixin,
    StatusBarMixin,
    MenuBarMixin,
    DashboardPageMixin,
    DevicesPageMixin,
    TasksPageMixin,
    BackupPageMixin,
    SchedulePageMixin,
    ContentPageMixin,
    LogsPageMixin,
    SettingsDialogMixin,
    AccountDialogMixin,
    ToolsDialogMixin,
    PerformanceDialogMixin,
    DashboardDialogMixin,
    ToolsMixin,
):
    def __init__(self, root):
        self.root = root
        self.root.title("LDPlayer Automation Manager")
        self.root.geometry("1540x940")
        self.root.minsize(1280, 780)

        self.paths = get_app_paths()
        self.paths.ensure_runtime_dirs()
        self.settings_service = SettingsService(self.paths)
        try:
            startup_settings = self.settings_service.load_app_settings()
        except Exception:
            startup_settings = AppSettings()

        self.appearance = resolve_appearance(startup_settings)
        self.palette = self.appearance.palette
        self.style = tb.Style(theme=self.appearance.ttk_theme)
        families = set(tkfont.families())
        self.mono_font = "Cascadia Mono" if "Cascadia Mono" in families else "Consolas"
        self.display_font = "Segoe UI Semibold"
        self._ld_snapshot = {}
        self._ld_status_cache = {}
        self._ld_account_cache = {}
        self._device_runtime_state = {}
        self.dashboard_events = []
        self.log_records = []
        self._max_log_records = 5000
        self._known_log_devices = set()
        self._has_general_log_records = False
        self._last_table_signature = None
        self._ld_search_job = None
        self._ld_right_hold_job = None
        self._ld_right_hold_item = None
        self._ld_right_hold_triggered = False
        self._ld_right_hold_delay_ms = 550
        self._ld_drag_toggle_anchor = None
        self._ld_drag_toggle_last = None
        self._ld_drag_toggle_active = False
        self._ld_drag_toggle_target = None
        self._ld_drag_toggle_visited = set()
        self._main_thread_id = threading.get_ident()
        self._ld_checked_names = set()
        self._command_palette = None
        self._fleet_load_state = "loading"
        self._fleet_error_message = ""
        self.ld_search_var = tk.StringVar()
        self.ld_sort_var = tk.StringVar(value="Status")
        self.ld_status_filter_var = tk.StringVar(value="All")
        self.ld_account_filter_var = tk.StringVar(value="All")
        self.ld_group_filter_var = tk.StringVar(value="All Groups")
        self._ld_groups = {}

        # Configure custom styles
        configure_styles(
            self.root, self.style, self.palette, self.display_font, self.mono_font, self.appearance
        )
        self.app_logger = AppLogger(self.paths)
        self.controller = AppController(self.settings_service, log_func=self.log)
        self.otp_controller = OTPController(
            self.settings_service,
            ui_log_func=self.log,
            structured_log_func=self.app_logger.log,
        )
        self.task_service = TaskService()
        self.task_handler_factory = TaskHandlerFactory()
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

        # Lifecycle state is owned by AutomationController. The two
        # attributes below remain as direct references to the controller's
        # events so the many existing call sites that read
        # ``self.running_event.is_set()`` or ``self.pause_event`` keep
        # working unchanged during the transition.
        self.automation_controller = AutomationController()
        self.running_event = self.automation_controller.running_event
        self.pause_event = self.automation_controller.pause_event
        self.automation_controller.add_state_listener(self._on_automation_state)
        self.schedule_thread = None
        self.schedule_running = False
        self.schedule_settings_file = self.paths.schedule_settings_file
        self.settings_file = self.paths.settings_file

        # Initialize settings variables
        self.parallel_ld = tk.IntVar(value=2)
        self.boot_delay = tk.IntVar(value=10)
        self.facebook_start_delay_seconds = tk.IntVar(value=8)
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
        self.random_like = tk.BooleanVar(value=True)
        self.clear_cache = tk.BooleanVar(value=True)
        self.verify_account = tk.BooleanVar(value=True)
        self.verify_2fa = tk.BooleanVar(value=True)
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
        self.theme_preset = tk.StringVar(value=self.appearance.theme_preset)
        self.accent_color = tk.StringVar(value=self.appearance.accent_color)
        self.ui_density = tk.StringVar(value=self.appearance.ui_density)
        self.ui_scale = tk.StringVar(value=self.appearance.ui_scale)
        # Comma-separated list of blocked ISO country codes for IP guard.
        self.blocked_countries = tk.StringVar(value="US,KH,CN,TH,VN,PH,ID,MY,LA,MM")

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
            "Sunday": tk.BooleanVar(value=False),
        }

        self.setup_enhanced_ui()
        self._command_palette_commands = self._build_command_palette_commands()
        self._bind_command_palette_shortcut()
        self.load_settings()
        self.root.after(0, self._maximize_on_startup)
        self.load_schedule_settings()
        self.populate_ld_table()
        self.start_status_refresh()
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

    def _dashboard_snapshot_from_json(self):
        """Return LD names saved by the dashboard persistence file."""
        try:
            path = self.paths.config_dir / "dashboard_instances.json"
            if not path.exists():
                return {}
            data = json.loads(path.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}

        if isinstance(data, list):
            instances = data
        elif isinstance(data, dict):
            instances = data.get("instances") or []
        else:
            instances = []

        snapshot = {}
        for raw in instances:
            if isinstance(raw, dict):
                name = str(raw.get("name") or "").strip()
                serial = str(
                    raw.get("serial") or raw.get("adb_serial") or raw.get("device_serial") or ""
                ).strip()
            else:
                name = str(raw or "").strip()
                serial = ""
            if name and name not in snapshot:
                snapshot[name] = serial
        return snapshot

    def _is_dev_emulator_snapshot(self, snapshot):
        names = set((snapshot or {}).keys())
        return bool(names) and names == set(_DEV_EMULATOR_NAMES)

    def _snapshot_with_dashboard_fallback(self, snapshot):
        snapshot = dict(snapshot or {})
        dashboard_snapshot = self._dashboard_snapshot_from_json()
        if not dashboard_snapshot:
            return snapshot
        if snapshot and not self._is_dev_emulator_snapshot(snapshot):
            return snapshot

        try:
            mapping = self.emulator.name_to_serial
            mapping.clear()
            mapping.update(dashboard_snapshot)
        except Exception:
            pass
        return dashboard_snapshot

    def setup_enhanced_ui(self):
        self.create_enhanced_menu_bar()

        # Main shell with sidebar + content area.
        shell = tb.Frame(self.root, style="CardInner.TFrame")
        shell.pack(fill="both", expand=True)

        self.create_sidebar(shell)

        main_container = tb.Frame(
            shell,
            style="CardInner.TFrame",
            padding=self.appearance.spacing.get("content_pad", (16, 14, 16, 8)),
        )
        main_container.pack(side="left", fill="both", expand=True)

        self.create_top_bar(main_container)

        content = tb.Frame(main_container, style="CardInner.TFrame", padding=(0, 8, 0, 0))
        content.pack(fill="both", expand=True)
        self.create_right_notebook_panel(content)

        # Status bar
        self.create_status_bar()

    def apply_appearance_settings(self):
        """Resolve, persist in memory, and apply the current appearance variables."""
        old_palette = dict(getattr(self, "palette", {}) or {})
        self.appearance = resolve_appearance(
            theme_preset=self.theme_preset.get(),
            accent_color=self.accent_color.get(),
            ui_density=self.ui_density.get(),
            ui_scale=self.ui_scale.get(),
        )
        self.palette = self.appearance.palette

        try:
            self.style.theme_use(self.appearance.ttk_theme)
        except Exception:
            self.style = tb.Style(theme=self.appearance.ttk_theme)

        configure_styles(
            self.root, self.style, self.palette, self.display_font, self.mono_font, self.appearance
        )
        self._refresh_appearance_on_existing_widgets(old_palette, self.palette)
        self._refresh_tree_appearance()
        self._refresh_log_appearance()
        if hasattr(self, "_set_sidebar_nav_active"):
            try:
                self._set_sidebar_nav_active(getattr(self, "_active_sidebar_key", "analytics"))
            except Exception:
                pass

    def _refresh_appearance_on_existing_widgets(self, old_palette, new_palette):
        color_map = self._appearance_color_map(old_palette, new_palette)

        def walk(widget):
            self._refresh_widget_appearance(widget, color_map, new_palette)
            for child in getattr(widget, "winfo_children", lambda: [])():
                walk(child)

        walk(self.root)

    def _appearance_color_map(self, old_palette, new_palette):
        color_map = {}
        for key, old_value in old_palette.items():
            new_value = new_palette.get(key)
            if old_value and new_value:
                color_map[str(old_value).lower()] = new_value

        legacy_roles = {
            "#00c4d9": "primary",
            "#00e5ff": "primary",
            "#040608": "primary_fg",
            "#1a2530": "surface_alt_2",
            "#64748b": "muted",
            "#6b7b90": "muted",
            "#112132": "nav_active_bg",
            "#0b1b2b": "tip_bg",
            "#071820": "primary_bg",
            "#00485a": "primary_border",
            "#10082a": "secondary_bg",
            "#3a1878": "secondary_border",
            "#0c1016": "tree_odd",
            "#1e2330": "hover_bg",
            "#343a40": "context_bg",
            "#ffffff": "context_fg",
        }
        for legacy, role in legacy_roles.items():
            color_map[legacy] = new_palette.get(role, new_palette.get("surface", legacy))
        return color_map

    def _refresh_widget_appearance(self, widget, color_map, palette):
        if hasattr(widget, "update_palette") and callable(widget.update_palette):
            try:
                widget.update_palette(palette)
            except Exception:
                pass
        elif hasattr(widget, "apply_palette") and callable(widget.apply_palette):
            try:
                widget.apply_palette(palette)
            except Exception:
                pass
        elif hasattr(widget, "palette"):
            try:
                widget.palette = palette
            except Exception:
                pass

        if isinstance(widget, GradientProgressBar):
            try:
                widget.configure(bg=palette["surface_alt"])
                widget.configure_colors(palette["primary"], palette["secondary"])
            except Exception:
                pass

        for option in (
            "background",
            "foreground",
            "activebackground",
            "activeforeground",
            "insertbackground",
            "highlightbackground",
            "highlightcolor",
            "selectbackground",
            "selectforeground",
            "troughcolor",
        ):
            try:
                current = str(widget.cget(option)).lower()
            except Exception:
                continue
            replacement = color_map.get(current)
            if replacement:
                try:
                    widget.configure(**{option: replacement})
                except Exception:
                    pass

        self._refresh_widget_font(widget)

    def _refresh_widget_font(self, widget):
        try:
            current_font = widget.cget("font")
        except Exception:
            return
        if not current_font:
            return
        try:
            actual = tkfont.Font(font=current_font).actual()
        except Exception:
            return
        current_size = abs(int(actual.get("size", 10) or 10))
        old_size = getattr(widget, "_appearance_base_font_size", None)
        if old_size is None:
            old_size = current_size
            try:
                widget._appearance_base_font_size = old_size
            except Exception:
                pass
        if int(old_size) <= 8:
            role = "small"
        elif int(old_size) <= 9:
            role = "meta"
        elif int(old_size) <= 10:
            role = "body"
        elif int(old_size) <= 12:
            role = "card_title"
        elif int(old_size) <= 15:
            role = "top_title"
        elif int(old_size) <= 17:
            role = "section"
        elif int(old_size) <= 19:
            role = "title"
        else:
            role = "hero"
        new_size = self.appearance.font_sizes.get(role, int(old_size))
        family = actual.get("family", self.display_font)
        parts = [family, new_size]
        if actual.get("weight") == "bold":
            parts.append("bold")
        if actual.get("slant") == "italic":
            parts.append("italic")
        try:
            widget.configure(font=tuple(parts))
        except Exception:
            pass

    def _refresh_tree_appearance(self):
        for attr in ("ld_table", "devices_tree", "account_tree"):
            tree = getattr(self, attr, None)
            if tree is None:
                continue
            try:
                if hasattr(tree, "apply_palette"):
                    tree.apply_palette(self.palette)
                else:
                    configure_status_tree_tags(tree, self.palette, include_zebra=True)
            except Exception:
                pass

    def _refresh_log_appearance(self):
        logs_text = getattr(self, "logs_text", None)
        if logs_text is None:
            return
        try:
            logs_text.configure(
                bg=self.palette["surface"],
                fg=self.palette["text"],
                insertbackground=self.palette["text"],
                selectbackground=self.palette["surface_alt"],
                selectforeground=self.palette["text"],
                highlightbackground=self.palette["border"],
            )
            logs_text.tag_configure("INFO", foreground=self.palette["primary"])
            logs_text.tag_configure("SUCCESS", foreground=self.palette["success"])
            logs_text.tag_configure("WARNING", foreground=self.palette["warning"])
            logs_text.tag_configure("ERROR", foreground=self.palette["danger"])
            logs_text.tag_configure("CATEGORY", foreground=self.palette["muted"])
            logs_text.tag_configure("MESSAGE", foreground=self.palette["text"])
            logs_text.tag_configure("EMPTY", foreground=self.palette["muted"])
        except Exception:
            pass

    def _bind_command_palette_shortcut(self):
        """Bind the global command palette launcher."""
        self.root.bind_all("<Control-k>", self.open_command_palette, add="+")
        self.root.bind_all("<Control-K>", self.open_command_palette, add="+")

    def open_command_palette(self, _event=None):
        """Open or focus the command palette."""
        palette = getattr(self, "_command_palette", None)
        if palette is not None and palette.winfo_exists():
            palette.focus_search()
            return "break"

        self._command_palette = CommandPalette(
            self.root,
            self._command_palette_commands,
            palette=self.palette,
            display_font=self.display_font,
            mono_font=self.mono_font,
        )
        self._command_palette.bind(
            "<Destroy>",
            lambda event: self._clear_command_palette_reference(event.widget),
            add="+",
        )
        return "break"

    def _clear_command_palette_reference(self, widget):
        if widget is getattr(self, "_command_palette", None):
            self._command_palette = None

    def _select_main_page(self, index):
        """Switch notebook pages through the app's real navigation surface."""
        if hasattr(self, "notebook"):
            self.notebook.select(index)
            self._on_notebook_tab_changed()
        if index == 2 and hasattr(self, "_render_devices_page"):
            self._render_devices_page()

    def _build_command_palette_commands(self):
        return [
            Command(
                id="go_dashboard",
                label="Go to Dashboard",
                category="Navigation",
                keywords=("dashboard", "home", "overview", "metrics"),
                hint="Open the dashboard workspace",
                action=lambda: self._select_main_page(1),
            ),
            Command(
                id="go_devices",
                label="Go to Devices",
                category="Navigation",
                keywords=("fleet", "emulators", "ldplayer", "instances"),
                hint="Open the LDPlayer fleet page",
                action=self._focus_devices,
            ),
            Command(
                id="go_tasks",
                label="Go to Tasks",
                category="Navigation",
                keywords=("automation", "task settings", "run controls"),
                hint="Open automation task controls",
                action=lambda: self._select_main_page(2),
            ),
            Command(
                id="go_schedule",
                label="Go to Schedule",
                category="Navigation",
                keywords=("scheduler", "time", "daily", "weekly"),
                hint="Open scheduling controls",
                action=lambda: self._select_main_page(3),
            ),
            Command(
                id="go_content",
                label="Go to Content",
                category="Navigation",
                keywords=("queue", "videos", "media", "captions"),
                hint="Open content queue management",
                action=lambda: self._select_main_page(4),
            ),
            Command(
                id="go_logs",
                label="Go to Logs",
                category="Navigation",
                keywords=("events", "output", "debug", "history"),
                hint="Open application logs",
                action=lambda: self._select_main_page(5),
            ),
            Command(
                id="refresh_emulators",
                label="Refresh emulator list",
                category="Devices",
                keywords=("refresh", "reload", "ld", "emulator", "fleet"),
                hint="Reload LDPlayer instances",
                action=self.refresh_emulator_list,
            ),
            Command(
                id="select_all_devices",
                label="Select all devices",
                category="Devices",
                keywords=("all", "check", "fleet", "emulators"),
                hint="Select every visible LD row",
                action=self.select_all,
            ),
            Command(
                id="select_online_devices",
                label="Select online devices",
                category="Devices",
                keywords=("active", "running", "online", "available"),
                hint="Select active or running LD rows",
                action=self.select_online,
            ),
            Command(
                id="clear_device_selection",
                label="Clear device selection",
                category="Devices",
                keywords=("deselect", "uncheck", "clear", "selection"),
                hint="Deselect all LD rows",
                action=self.deselect_all,
            ),
            Command(
                id="invert_device_selection",
                label="Invert device selection",
                category="Devices",
                keywords=("toggle", "reverse", "selection", "checked"),
                hint="Flip checked and unchecked rows",
                action=self.invert_selection,
            ),
            Command(
                id="clear_device_filters",
                label="Clear device filters",
                category="Devices",
                keywords=("search", "status", "account", "group", "sort"),
                hint="Reset fleet search, filters, and sorting",
                action=self.clear_ld_filters,
            ),
            Command(
                id="start_selected_devices",
                label="Start selected devices",
                category="Batch Actions",
                keywords=("boot", "launch", "start ld", "selected"),
                hint="Start checked LDPlayer instances",
                action=self.batch_start,
            ),
            Command(
                id="stop_selected_devices",
                label="Stop selected devices",
                category="Batch Actions",
                keywords=("quit", "shutdown", "stop ld", "selected"),
                hint="Stop checked LDPlayer instances",
                action=self.batch_stop,
            ),
            Command(
                id="restart_selected_devices",
                label="Restart selected devices",
                category="Batch Actions",
                keywords=("reboot", "restart ld", "selected"),
                hint="Restart checked LDPlayer instances",
                action=self.batch_restart,
            ),
            Command(
                id="start_automation",
                label="Start automation",
                category="Automation",
                keywords=("run", "begin", "task", "workflow"),
                hint="Run the selected task for checked devices",
                action=self.start_automation,
            ),
            Command(
                id="pause_automation",
                label="Pause automation",
                category="Automation",
                keywords=("resume", "toggle", "hold", "automation"),
                hint="Toggle pause or resume for the current run",
                action=self.toggle_pause,
            ),
            Command(
                id="stop_automation",
                label="Stop automation",
                category="Automation",
                keywords=("cancel", "halt", "end", "automation"),
                hint="Stop the current automation run",
                action=self.stop_automation,
            ),
            Command(
                id="enable_schedule",
                label="Enable schedule",
                category="Schedule",
                keywords=("start scheduler", "daily", "weekly", "time"),
                hint="Start the scheduler with current settings",
                action=self.start_schedule,
            ),
            Command(
                id="disable_schedule",
                label="Disable schedule",
                category="Schedule",
                keywords=("stop scheduler", "off", "pause schedule"),
                hint="Stop the scheduler",
                action=self.stop_schedule,
            ),
            Command(
                id="open_settings",
                label="Open Settings",
                category="Dialogs",
                keywords=("preferences", "config", "behavior", "profile"),
                hint="Open the control settings dialog",
                action=self.show_settings_dialog,
            ),
            Command(
                id="open_tools_center",
                label="Open Tools Center",
                category="Dialogs",
                keywords=("tools", "adb", "diagnostics", "utilities"),
                hint="Open quick tools and diagnostics",
                action=self.show_tools_center,
            ),
            Command(
                id="open_performance_dialog",
                label="Open Performance dialog",
                category="Dialogs",
                keywords=("performance", "metrics", "cpu", "ram", "report"),
                hint="Open live resource and task metrics",
                action=self.show_performance_report,
            ),
            Command(
                id="create_backup",
                label="Create backup",
                category="Maintenance",
                keywords=("backup", "archive", "settings", "content"),
                hint="Create a ZIP backup of app data",
                action=self.create_backup,
            ),
            Command(
                id="restore_backup",
                label="Restore backup",
                category="Maintenance",
                keywords=("restore", "import", "recover", "zip"),
                hint="Restore app data from a backup ZIP",
                action=self.restore_backup,
            ),
            Command(
                id="clean_old_backups",
                label="Clean old backups",
                category="Maintenance",
                keywords=("cleanup", "delete", "archives", "backup"),
                hint="Keep the 10 most recent backup archives",
                action=self.cleanup_old_backups,
            ),
            Command(
                id="show_content_stats",
                label="Show content stats",
                category="Maintenance",
                keywords=("content", "queue", "videos", "stats"),
                hint="Show content queue totals and recent items",
                action=self.show_content_stats,
            ),
        ]

    def _is_main_thread(self):
        return threading.get_ident() == self._main_thread_id

    def _handle_task_type_change(self):
        self._update_header_chips()
        if hasattr(self, "render_task_settings"):
            self.render_task_settings()

    def _on_automation_state(self, state: AutomationState) -> None:
        """Apply UI effects for an AutomationController state transition.

        Registered as a listener on ``self.automation_controller``. May be
        invoked from a worker thread (e.g. the ``finally`` block in
        ``automation_thread`` calls ``stop_automation`` which calls
        ``controller.stop()``). Widget calls here follow the same pattern
        the previous inline code used; if Tk thread-safety becomes a
        concern, marshal via ``self.root.after(0, ...)``.
        """
        if state is AutomationState.RUNNING:
            if hasattr(self, "start_button"):
                self.start_button.config(state="disabled")
                self.pause_button.config(state="normal")
                self.stop_button.config(state="normal")
                self.pause_button.config(text="Pause")
            self._set_system_status("Running")
            self._update_header_chips(mode_text="Running")
            if hasattr(self, "set_top_action_state"):
                self.set_top_action_state("running")
        elif state is AutomationState.PAUSED:
            if hasattr(self, "pause_button"):
                self.pause_button.config(text="Resume")
            self._set_system_status("Paused")
            self._update_header_chips(mode_text="Paused")
            if hasattr(self, "set_top_action_state"):
                self.set_top_action_state("paused")
        elif state is AutomationState.IDLE:
            if hasattr(self, "start_button"):
                self.start_button.config(state="normal")
                self.pause_button.config(state="disabled")
                self.stop_button.config(state="disabled")
                self.pause_button.config(text="Pause")
            self._set_system_status("Idle")
            self._update_header_chips(mode_text="Idle")
            if hasattr(self, "set_top_action_state"):
                self.set_top_action_state("idle")

    def _set_system_status(self, status):
        label = status_label(status)
        if hasattr(self, "top_status_label"):
            self.top_status_label.config(
                text=f"System: {label}  |  {datetime.now().strftime('%A, %d %b %Y')}"
            )
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
            ("Invert", self.invert_selection, "outline-warning"),
        ]

        for text, command, style in control_configs:
            btn = tb.Button(controls_frame, text=text, command=command, bootstyle=style, width=11)
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
            width=11,
        )
        status_combo.pack(side="left", padx=(6, 12))
        status_combo.bind("<<ComboboxSelected>>", lambda _e: self._render_ld_table())

        tb.Label(filter_frame, text="Account", style="Subtitle.TLabel").pack(side="left")
        account_combo = tb.Combobox(
            filter_frame,
            textvariable=self.ld_account_filter_var,
            values=("All", "Has Account", "No Account"),
            state="readonly",
            width=12,
        )
        account_combo.pack(side="left", padx=(6, 12))
        account_combo.bind("<<ComboboxSelected>>", lambda _e: self._render_ld_table())

        tb.Label(filter_frame, text="Group", style="Subtitle.TLabel").pack(side="left")
        self.group_filter_combo = tb.Combobox(
            filter_frame,
            textvariable=self.ld_group_filter_var,
            values=("All Groups", "Ungrouped"),
            state="readonly",
            width=14,
        )
        self.group_filter_combo.pack(side="left", padx=(6, 12))
        self.group_filter_combo.bind(
            "<<ComboboxSelected>>", lambda _e: self._set_ld_group_filter(self.ld_group_filter_var.get())
        )

        tb.Label(filter_frame, text="Sort", style="Subtitle.TLabel").pack(side="left")
        sort_combo = tb.Combobox(
            filter_frame,
            textvariable=self.ld_sort_var,
            values=("Status", "Name", "ADB", "Account", "Group"),
            state="readonly",
            width=11,
        )
        sort_combo.pack(side="left", padx=(6, 0))
        sort_combo.bind("<<ComboboxSelected>>", lambda _e: self._render_ld_table())
        tb.Button(
            filter_frame,
            text="Create Group",
            bootstyle="outline-primary",
            command=self.create_ld_group,
            width=12,
        ).pack(side="right", padx=(8, 0))
        tb.Button(
            filter_frame,
            text="Clear Filters",
            bootstyle="outline-secondary",
            command=self.clear_ld_filters,
            width=12,
        ).pack(side="right")

        # Selection info
        self.selection_info = tb.Label(
            controls_frame, text="Selected: 0/0", bootstyle="secondary", style="Chip.TLabel"
        )
        self.selection_info.pack(side="right", padx=5)

        fleet_stats = tb.Frame(table_frame)
        fleet_stats.pack(fill="x", pady=(0, 10))
        self.fleet_total_chip = StatusPill(
            fleet_stats,
            "Info",
            palette=self.palette,
            text="Total: 0",
            font=(self.display_font, 9),
            padx=8,
            pady=3,
        )
        self.fleet_total_chip.pack(side="left", padx=(0, 6))
        self.fleet_online_chip = StatusPill(
            fleet_stats,
            "Active",
            palette=self.palette,
            text="Online: 0",
            font=(self.display_font, 9),
            padx=8,
            pady=3,
        )
        self.fleet_online_chip.pack(side="left", padx=(0, 6))
        self.fleet_running_chip = StatusPill(
            fleet_stats,
            "Running",
            palette=self.palette,
            text="Running: 0",
            font=(self.display_font, 9),
            padx=8,
            pady=3,
        )
        self.fleet_running_chip.pack(side="left", padx=(0, 6))
        self.fleet_account_chip = StatusPill(
            fleet_stats,
            "Ready",
            palette=self.palette,
            text="With Account: 0",
            font=(self.display_font, 9),
            padx=8,
            pady=3,
        )
        self.fleet_account_chip.pack(side="left", padx=(0, 6))
        self.fleet_visible_chip = StatusPill(
            fleet_stats,
            "Idle",
            palette=self.palette,
            text="Visible: 0",
            font=(self.display_font, 9),
            padx=8,
            pady=3,
        )
        self.fleet_visible_chip.pack(side="right")

        # Treeview with custom style
        self.create_enhanced_treeview(table_frame)

    def create_enhanced_treeview(self, parent):
        """Create enhanced Treeview with better styling"""
        # Create frame for treeview and scrollbar
        self.ld_table_state_view = StateView(
            parent,
            kind="loading",
            title="Scanning emulator fleet...",
            message="Looking for LDPlayer instances and current ADB state.",
            actions=[
                {"text": "Refresh", "command": self.refresh_emulator_list, "bootstyle": "outline-info"},
                {"text": "Tools", "command": self.show_tools_center, "bootstyle": "outline-secondary"},
            ],
            palette=self.palette,
            display_font=self.display_font,
            mono_font=self.mono_font,
        )
        self.ld_table_state_view.pack(fill="x", pady=(0, 10))

        tree_frame = tb.Frame(parent)
        self.ld_table_frame = tree_frame
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
            palette=self.palette,
            style="Custom.Treeview",
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

        configure_status_tree_tags(self.ld_table, self.palette, include_zebra=True)

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

        self.ld_table.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)

        self.ld_table.pack(fill="both", expand=True)
        self.ld_table.bind("<ButtonPress-1>", self._on_ld_drag_toggle_start, add="+")
        self.ld_table.bind("<B1-Motion>", self._on_ld_drag_toggle_motion, add="+")
        self.ld_table.bind("<ButtonRelease-1>", self._on_ld_drag_toggle_end, add="+")
        self.ld_table.bind("<ButtonPress-3>", self._on_ld_table_right_press)
        self.ld_table.bind("<ButtonRelease-3>", self._on_ld_table_right_release)

        self.instance_context_menu = tk.Menu(self.root, tearoff=0)
        self.instance_context_menu.add_command(label="Select All", command=self.select_all)
        self.instance_context_menu.add_command(label="Clear Selection", command=self.deselect_all)
        self.instance_context_menu.add_separator()
        self.instance_context_menu.add_command(label="Run Automation", command=self._context_run_automation)
        self.instance_context_menu.add_separator()
        self.instance_context_menu.add_command(label="Start", command=self._context_start_instance)
        self.instance_context_menu.add_command(label="Stop", command=self._context_stop_instance)
        self.instance_context_menu.add_command(label="Restart", command=self._context_restart_instance)
        self.instance_context_menu.add_command(label="Rename...", command=self._context_rename_instance)
        self.instance_context_menu.add_command(label="Delete...", command=self._context_delete_instance)
        self.instance_context_menu.add_command(
            label="Shared Folder...", command=self._context_set_shared_folder
        )
        self.instance_context_menu.add_command(
            label="Health Check & Recover", command=self._context_health_check
        )
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
        self.create_dashboard_hub_tab()
        self.create_devices_tab()
        self.create_tasks_tab()
        self.create_account_hub_tab()
        self.create_backup_hub_tab()
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
            1: "dashboard",
            2: "devices",
            3: "automation",
            4: "accounts",
            5: "backups",
            6: "schedule",
            7: "content",
            8: "logs",
        }
        self._set_sidebar_nav_active(tab_to_nav.get(idx, "analytics"))
        tab_titles = {
            0: ("Analytics", "Live device + automation overview"),
            1: ("Dashboard", "Manage devices and shared folders"),
            2: ("Devices", "Configure and inspect LD instances"),
            3: ("Tasks", "Run and monitor automation tasks"),
            4: ("Account", "Browse and manage Snapchat accounts"),
            5: ("Backups", "Snapshot and restore Snapchat data"),
            6: ("Schedule", "Plan recurring automation"),
            7: ("Content Library", "Manage videos across all LD shared folders"),
            8: ("Logs", "Inspect activity logs and history"),
        }
        title, subtitle = tab_titles.get(idx, ("Analytics", ""))
        if hasattr(self, "set_top_title"):
            self.set_top_title(title, subtitle)
        if hasattr(self, "_top_tab_buttons"):
            active_label = "Analytics"
            if idx == 1:
                active_label = "Dashboard"
            elif idx == 2:
                active_label = "Devices"
            elif idx == 3:
                active_label = "Tasks"
            elif idx == 4:
                active_label = "Account"
            elif idx == 5:
                active_label = "Backups"
            elif idx == 8:
                active_label = "Logs"
            for label, btn in self._top_tab_buttons.items():
                btn.configure(bootstyle="info" if label == active_label else "secondary-link")
        # Refresh the dashboard immediately when the user enters the Analytics tab
        # so they never see stale data after switching from another tab.
        if idx == 0:
            self.request_dashboard_refresh(force=True)
        elif idx == 1:
            self.request_embedded_dashboard_refresh()
        elif idx == 4:
            self.request_embedded_account_refresh()
        elif idx == 5:
            self.request_backup_refresh()

    def request_dashboard_refresh(self, force=True):
        if hasattr(self, "_refresh_dashboard"):
            try:
                self._refresh_dashboard()
            except Exception:
                pass

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
                self.root.after(
                    0, lambda name=ld_name, data=merged: self.update_device_runtime_state(name, data)
                )
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
                self.update_device_runtime_state(
                    name, state="Idle", task="Waiting for selection", progress=0, queue_label="-"
                )

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
            kept = (
                list(members) if not snapshot_names else [name for name in members if name in snapshot_names]
            )
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
            current_filter = "All Groups"
            self.ld_group_filter_var.set(current_filter)

        assigned_total = sum(len(members) for members in self._ld_groups.values())
        snapshot_total = len(getattr(self, "_ld_snapshot", {}) or {})
        ungrouped_total = max(0, snapshot_total - assigned_total)

        if hasattr(self, "device_group_list"):
            tree = self.device_group_list
            selected_group = current_filter if current_filter in self._ld_groups else None
            query = ""
            if hasattr(self, "device_group_search_var"):
                query = (self.device_group_search_var.get() or "").strip().lower()

            self._suppress_group_filter_sync = True
            try:
                for item in tree.get_children():
                    tree.delete(item)

                visible_count = 0
                for idx, group_name in enumerate(group_names):
                    if query and query not in group_name.lower():
                        continue
                    count = len(self._ld_groups.get(group_name, []))
                    share_pct = (count / snapshot_total * 100) if snapshot_total else 0
                    tags = ["even_row" if idx % 2 == 0 else "odd_row"]
                    if count == 0:
                        tags.append("group_empty")
                    if group_name == selected_group:
                        tags.append("group_active")
                    try:
                        tree.insert(
                            "",
                            "end",
                            iid=group_name,
                            values=(group_name, str(count), f"{share_pct:.0f}%"),
                            tags=tuple(tags),
                        )
                    except Exception:
                        pass
                    visible_count += 1

                if selected_group and selected_group in group_names:
                    try:
                        if tree.exists(selected_group):
                            tree.selection_set(selected_group)
                            tree.see(selected_group)
                    except Exception:
                        pass
                else:
                    selected_items = tree.selection()
                    if selected_items:
                        tree.selection_remove(selected_items)
            except Exception:
                visible_count = 0
            try:
                self.root.after_idle(lambda: setattr(self, "_suppress_group_filter_sync", False))
            except Exception:
                self._suppress_group_filter_sync = False

            if hasattr(self, "device_group_empty"):
                empty_widget = self.device_group_empty
                try:
                    if visible_count == 0:
                        if not empty_widget.winfo_ismapped():
                            empty_widget.pack(fill="x", pady=(8, 0))
                        if not group_names:
                            empty_widget.configure(text="No groups yet — click Create to add one.")
                        else:
                            empty_widget.configure(text="No groups match your search.")
                    else:
                        empty_widget.pack_forget()
                except Exception:
                    pass

        if hasattr(self, "device_group_total_chip"):
            self.device_group_total_chip.set_status(
                "info", text=f"{len(group_names)} group{'s' if len(group_names) != 1 else ''}"
            )
        if hasattr(self, "device_group_assigned_chip"):
            self.device_group_assigned_chip.set_status("success", text=f"{assigned_total} assigned")
        if hasattr(self, "device_group_unassigned_chip"):
            self.device_group_unassigned_chip.set_status("muted", text=f"{ungrouped_total} ungrouped")
        if hasattr(self, "device_group_summary"):
            try:
                self.device_group_summary.config(
                    text=f"{len(group_names)} groups  |  {assigned_total} assigned"
                )
            except Exception:
                pass

    def _get_active_group_name(self):
        current_filter = self.ld_group_filter_var.get().strip()
        if current_filter in getattr(self, "_ld_groups", {}):
            return current_filter
        if current_filter in ("All Groups", "Ungrouped"):
            return None
        if hasattr(self, "device_group_list"):
            tree = self.device_group_list
            try:
                sel = tree.selection()
                if sel:
                    return str(sel[0])
            except Exception:
                pass
        if current_filter:
            return current_filter
        return None

    def _set_ld_group_filter(self, group_filter, render=True):
        group_filter = (group_filter or "All Groups").strip() or "All Groups"
        group_names = set(getattr(self, "_ld_groups", {}) or {})
        if group_filter not in ("All Groups", "Ungrouped") and group_filter not in group_names:
            group_filter = "All Groups"

        self.ld_group_filter_var.set(group_filter)
        if hasattr(self, "device_group_list"):
            tree = self.device_group_list
            self._suppress_group_filter_sync = True
            try:
                if group_filter in group_names and tree.exists(group_filter):
                    if tree.selection() != (group_filter,):
                        tree.selection_set(group_filter)
                    tree.see(group_filter)
                else:
                    selected_items = tree.selection()
                    if selected_items:
                        tree.selection_remove(selected_items)
            except Exception:
                pass
            try:
                self.root.after_idle(lambda: setattr(self, "_suppress_group_filter_sync", False))
            except Exception:
                self._suppress_group_filter_sync = False

        if render:
            self._render_ld_table()

    def _sync_group_filter_from_list(self):
        if getattr(self, "_suppress_group_filter_sync", False):
            return
        group_name = None
        if hasattr(self, "device_group_list"):
            try:
                selected = self.device_group_list.selection()
                if selected:
                    group_name = str(selected[0])
            except Exception:
                group_name = None
        if not group_name:
            group_name = self._get_active_group_name()
        if not group_name:
            return
        if self.ld_group_filter_var.get().strip() == group_name:
            return
        self._set_ld_group_filter(group_name)

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
        new_name = simpledialog.askstring(
            "Rename Group", "New group name:", initialvalue=current_name, parent=self.root
        )
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
            target_group = simpledialog.askstring(
                "Assign Group", "Assign selected LDs to group:", parent=self.root
            )
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
        self._sync_fleet_state_view(rows)
        render_signature = (tuple(rows), tuple(sorted(checked_names)))
        if render_signature == self._last_table_signature:
            self.update_selection_info()
            return

        # Diff-based update — preserves iids and only mutates changed rows.
        existing_iids = list(self.ld_table.get_children())
        existing_set = set(existing_iids)
        new_names = {row[0] for row in rows}
        for iid in existing_iids:
            if iid not in new_names:
                self.ld_table.delete(iid)
                self.ld_table.checkboxes.pop(iid, None)

        for idx, (name, serial, status, account_text, group_text) in enumerate(rows):
            runtime = self._device_runtime_state.get(name) or {}
            runtime_progress = runtime.get("progress")
            if status == "Running":
                task_text = {
                    "scroll": "Scroll Feed",
                    "reels": "Watch Reels",
                    "reg_account": "Register Account",
                    "login": "Login Account",
                    "test_feature": "Test Feature",
                }.get(self.task_type_var.get(), self.task_type_var.get().title())
                progress_text = f"{int(runtime_progress)}%" if isinstance(runtime_progress, (int, float)) else "—"
            elif status == "Active":
                task_text = "Starting"
                progress_text = f"{int(runtime_progress)}%" if isinstance(runtime_progress, (int, float)) else "—"
            elif status == "Inactive":
                task_text = "—"
                progress_text = "0%"
            else:
                task_text = "—"
                progress_text = "0%"
            zebra_tag = "odd_row" if idx % 2 == 0 else "even_row"
            is_checked = name in checked_names
            values = (
                name,
                serial,
                self._status_text(status),
                task_text,
                progress_text,
                account_text,
                group_text,
            )
            text_val = "☑" if is_checked else "☐"
            # Order matters: ttk.Treeview gives later tags higher precedence
            # for shared options (e.g. background). Status tag MUST come last
            # so device state drives row color, not selection state.
            base_tags = [zebra_tag]
            if is_checked:
                base_tags.append("checked")
            base_tags.append(self._status_tag(status))
            tags_tup = tuple(base_tags)

            if name in existing_set:
                self.ld_table.item(name, text=text_val, values=values, tags=tags_tup)
                if self.ld_table.index(name) != idx:
                    self.ld_table.move(name, "", idx)
            else:
                self.ld_table.insert("", idx, iid=name, text=text_val, values=values, tags=tags_tup)
            self.ld_table.checkboxes[name] = is_checked

        self._last_table_signature = render_signature
        self._update_fleet_summary(rows)
        self.update_selection_info()

    def _sync_fleet_state_view(self, rows=None):
        if not hasattr(self, "ld_table_state_view"):
            return
        rows = rows if rows is not None else self._filtered_snapshot_rows()
        state = getattr(self, "_fleet_load_state", "ready")
        error_message = getattr(self, "_fleet_error_message", "")

        if state == "loading":
            self.ld_table_state_view.set(
                kind="loading",
                title="Scanning emulator fleet...",
                message="Looking for LDPlayer instances and current ADB state.",
                actions=[
                    {"text": "Tools", "command": self.show_tools_center, "bootstyle": "outline-secondary"},
                ],
            )
            self.ld_table_state_view.pack(fill="x", pady=(0, 10))
            return

        if state == "error":
            self.ld_table_state_view.set(
                kind="error",
                title="Failed to refresh emulator list",
                message=error_message or "The emulator service could not return the current LDPlayer fleet.",
                actions=[
                    {"text": "Retry", "command": self.refresh_emulator_list, "bootstyle": "outline-danger"},
                    {"text": "Tools", "command": self.show_tools_center, "bootstyle": "outline-secondary"},
                ],
            )
            self.ld_table_state_view.pack(fill="x", pady=(0, 10))
            return

        if not self._ld_snapshot:
            self.ld_table_state_view.set(
                kind="empty",
                title="No LDPlayer instances found",
                message="Create or start LDPlayer instances, then refresh the fleet list.",
                actions=[
                    {"text": "Refresh", "command": self.refresh_emulator_list, "bootstyle": "outline-info"},
                    {"text": "Tools", "command": self.show_tools_center, "bootstyle": "outline-secondary"},
                ],
            )
            self.ld_table_state_view.pack(fill="x", pady=(0, 10))
            return

        if not rows:
            self.ld_table_state_view.set(
                kind="empty",
                title="No devices match the current filters",
                message="Clear search, status, account, or group filters to see the full fleet.",
                actions=[
                    {
                        "text": "Clear Filters",
                        "command": self.clear_ld_filters,
                        "bootstyle": "outline-secondary",
                    },
                ],
            )
            self.ld_table_state_view.pack(fill="x", pady=(0, 10))
            return

        self.ld_table_state_view.pack_forget()

    def _sync_emulator_table(self, snapshot, status_cache=None, account_cache=None, force=False):
        changed = force or snapshot != self._ld_snapshot
        if status_cache is not None and status_cache != self._ld_status_cache:
            changed = True
        old_snapshot = dict(self._ld_snapshot)
        if hasattr(self, "_db_sync_snapshot_changes"):
            try:
                if self._db_sync_snapshot_changes(old_snapshot, snapshot):
                    changed = True
            except Exception as exc:
                try:
                    self.log(f"Failed to sync dashboard LD data: {exc}", "ERROR")
                except Exception:
                    pass

        if account_cache is not None:
            account_cache = self._apply_dashboard_account_cache(snapshot, account_cache)
            if account_cache != self._ld_account_cache:
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
        if hasattr(self, "_refresh_log_filter_options"):
            self._refresh_log_filter_options()

    def _dashboard_account_lookup(self):
        try:
            path = self.paths.config_dir / "dashboard_instances.json"
            if not path.exists():
                return {}
            data = json.loads(path.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}

        lookup = {}
        for instance in data.get("instances") or []:
            name = str(instance.get("name") or "").strip()
            if not name:
                continue
            display = self._dashboard_account_display(instance.get("account") or {})
            if display:
                lookup[name] = display
        return lookup

    def _dashboard_account_display(self, account):
        if not isinstance(account, dict):
            return ""
        for key in ("name", "uid", "mail"):
            value = str(account.get(key) or "").strip()
            if value:
                return value
        return ""

    def _build_ld_account_cache(self, snapshot):
        cache = {}
        for name in snapshot:
            account = self.account_manager.get_device_account(name)
            cache[name] = account.get("username", "No account") if account else "No account"
        return self._apply_dashboard_account_cache(snapshot, cache)

    def _apply_dashboard_account_cache(self, snapshot, account_cache):
        merged = dict(account_cache or {})
        dashboard_accounts = self._dashboard_account_lookup()
        for name in snapshot:
            dashboard_account = dashboard_accounts.get(name)
            if dashboard_account:
                merged[name] = dashboard_account
            else:
                merged.setdefault(name, "No account")
        return merged

    def _on_ld_drag_toggle_start(self, event):
        try:
            item = self.ld_table.identify_row(event.y)
            self._ld_drag_toggle_active = False
            self._ld_drag_toggle_anchor = item
            self._ld_drag_toggle_last = item
            self._ld_drag_toggle_target = None
            self._ld_drag_toggle_visited = set()

            if not item:
                self._clear_ld_table_selection()
                self.update_selection_info()
                self._update_device_focus_card()
                return

            currently_selected = bool(self.ld_table.checkboxes.get(item, False))
            self._ld_drag_toggle_active = True
            self._ld_drag_toggle_target = not currently_selected
            self.ld_table.select_item(item)
            self._set_context_from_ld_item(item)
        except Exception as exc:
            self.log(f"LD drag selection start failed: {exc}", "ERROR")

    def _on_ld_drag_toggle_motion(self, event):
        try:
            if not getattr(self, "_ld_drag_toggle_active", False):
                return
            self._scroll_ld_table_during_drag(event)
            item = self.ld_table.identify_row(event.y)
            if not item:
                return
            previous = getattr(self, "_ld_drag_toggle_last", None) or getattr(
                self, "_ld_drag_toggle_anchor", None
            )
            for row in self._ld_table_items_between(previous, item):
                self._toggle_ld_row_selection(row, self._ld_drag_toggle_target)
            self._ld_drag_toggle_last = item
            self.ld_table.select_item(item)
            self._set_context_from_ld_item(item)
            self.update_selection_info()
            self._update_device_focus_card()
        except Exception as exc:
            self.log(f"LD drag selection motion failed: {exc}", "ERROR")

    def _on_ld_drag_toggle_end(self, _event):
        try:
            self._ld_drag_toggle_active = False
            self._ld_drag_toggle_anchor = None
            self._ld_drag_toggle_last = None
            self._ld_drag_toggle_target = None
            self._ld_drag_toggle_visited = set()
            self.update_selection_info()
            self._update_device_focus_card()
        except Exception as exc:
            self.log(f"LD drag selection end failed: {exc}", "ERROR")

    def _toggle_ld_row_selection(self, item, selected):
        if not item:
            return False
        visited = getattr(self, "_ld_drag_toggle_visited", None)
        if visited is None:
            visited = set()
            self._ld_drag_toggle_visited = visited
        if item in visited:
            return False
        visited.add(item)

        current = bool(self.ld_table.checkboxes.get(item, False))
        desired = bool(selected)
        if current != desired:
            self.ld_table.toggle_checkbox(item)
        return True

    def _ld_table_items_between(self, start_item, end_item):
        if not start_item or not end_item:
            return []
        items = list(self.ld_table.get_children())
        if start_item not in items or end_item not in items:
            return [end_item] if end_item in items else []
        start = items.index(start_item)
        end = items.index(end_item)
        if start > end:
            start, end = end, start
        return items[start : end + 1]

    def _clear_ld_table_selection(self):
        try:
            for item in self.ld_table.get_children():
                if self.ld_table.checkboxes.get(item, False):
                    self.ld_table.toggle_checkbox(item)
            self.ld_table.select_item(None)
            self._context_ld_name = None
            self._context_ld_serial = None
        except Exception as exc:
            self.log(f"Failed to clear LD selection: {exc}", "ERROR")

    def _scroll_ld_table_during_drag(self, event):
        try:
            height = self.ld_table.winfo_height()
        except Exception as exc:
            self.log(f"LD drag auto-scroll failed: {exc}", "ERROR")
            return
        margin = 18
        if event.y < margin:
            self.ld_table.yview_scroll(-1, "units")
        elif event.y > max(margin, height - margin):
            self.ld_table.yview_scroll(1, "units")

    def _on_ld_table_right_press(self, event):
        try:
            item = self.ld_table.identify_row(event.y)
            self._cancel_ld_right_hold()
            self._ld_right_hold_item = item
            self._ld_right_hold_triggered = False
            if not item:
                return "break"

            self.ld_table.select_item(item)
            self._set_context_from_ld_item(item)
            self._ld_right_hold_job = self.root.after(
                getattr(self, "_ld_right_hold_delay_ms", 550),
                lambda target=item: self._trigger_ld_right_hold_select(target),
            )
            return "break"
        except Exception as exc:
            self.log(f"LD right-click press failed: {exc}", "ERROR")
            return "break"

    def _on_ld_table_right_release(self, event):
        try:
            item = self.ld_table.identify_row(event.y) or getattr(self, "_ld_right_hold_item", None)
            hold_triggered = bool(getattr(self, "_ld_right_hold_triggered", False))
            self._cancel_ld_right_hold()

            if not item:
                return "break"
            self.ld_table.select_item(item)
            self._set_context_from_ld_item(item)

            if hold_triggered:
                self.update_selection_info()
                self._update_device_focus_card()
                return "break"

            self._prepare_ld_context_selection(item)
            self._show_instance_context_menu(event, item=item)
            return "break"
        except Exception as exc:
            self.log(f"LD right-click release failed: {exc}", "ERROR")
            return "break"

    def _cancel_ld_right_hold(self):
        job = getattr(self, "_ld_right_hold_job", None)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
        self._ld_right_hold_job = None

    def _trigger_ld_right_hold_select(self, item):
        try:
            self._ld_right_hold_job = None
            if not item or not hasattr(self, "ld_table") or not self.ld_table.exists(item):
                return
            self._ld_right_hold_triggered = True
            self.ld_table.select_item(item)
            self._set_context_from_ld_item(item)
            self._prepare_ld_context_selection(item)
            self.update_selection_info()
            self._update_device_focus_card()
        except Exception as exc:
            self.log(f"LD right-hold selection failed: {exc}", "ERROR")

    def _prepare_ld_context_selection(self, item):
        if not item:
            return
        if self.ld_table.checkboxes.get(item, False):
            return
        for row in self.ld_table.get_children():
            if self.ld_table.checkboxes.get(row, False):
                self.ld_table.toggle_checkbox(row)
        self.ld_table.toggle_checkbox(item)
        self.update_selection_info()

    def _set_context_from_ld_item(self, item):
        values = self.ld_table.item(item, "values")
        if not values:
            return False
        self._context_ld_name = values[0]
        self._context_ld_serial = values[1] if len(values) > 1 else None
        return True

    def _show_instance_context_menu(self, event, item=None):
        item = item or self.ld_table.identify_row(event.y)
        if not item:
            return "break"
        if not self._set_context_from_ld_item(item):
            return "break"
        self.ld_table.select_item(item)
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
                prefix = (
                    "Remove from" if len(target_names) == 1 and group_name in current_groups else "Assign to"
                )
                self.instance_group_menu.add_command(
                    label=f"{prefix} {group_name}",
                    command=lambda group=group_name: self._toggle_context_group(group),
                )
        self.instance_group_menu.add_separator()
        self.instance_group_menu.add_command(
            label="Remove From All Groups", command=self._remove_context_ld_from_groups
        )

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
        self.log(
            f"{action} {len(target_names)} LD(s) {'from' if action == 'Removed' else 'to'} group: {group_name}",
            "INFO",
        )

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
        threading.Thread(
            target=lambda: self._run_single_instance_action(name, "restart"), daemon=True
        ).start()

    def _context_rename_instance(self):
        old_name = self._context_ld_name
        if not old_name:
            return

        new_name = simpledialog.askstring(
            "Rename LD Instance",
            f"New name for '{old_name}':",
            initialvalue=old_name,
            parent=self.root,
        )
        if new_name is None:
            return
        new_name = new_name.strip()
        if not new_name or new_name == old_name:
            return

        # Reject characters that LDPlayer titles cannot contain.
        forbidden = set('\\/:*?"<>|')
        if any(ch in forbidden for ch in new_name):
            MessageBox.showwarning(
                "Rename LD Instance",
                'Name cannot contain any of: \\ / : * ? " < > |',
                parent=self.root,
            )
            return

        if new_name in self.emulator.name_to_serial:
            MessageBox.showwarning(
                "Rename LD Instance",
                f"An instance named '{new_name}' already exists.",
                parent=self.root,
            )
            return

        def worker():
            try:
                if not self.emulator.rename_ld(old_name, new_name):
                    self.log(f"Failed to rename LD '{old_name}' to '{new_name}'", "ERROR")
                    return
                self.log(f"Renamed LD '{old_name}' to '{new_name}'", "SUCCESS")
                # Refresh the device table so the row reflects the new name.
                try:
                    self.root.after(0, self.populate_ld_table)
                except Exception:
                    pass
            except Exception as exc:
                self.log(f"Rename error for '{old_name}': {exc}", "ERROR")

        threading.Thread(target=worker, daemon=True).start()

    def _context_health_check(self):
        """Run a VBox-log scan and (if needed) recovery on the targeted LD(s).

        Surfaces the 'uCountStat < 100' / assertion family of wedges that
        LDPlayer hits after long runs or driver upgrades. Per-instance
        recovery is best-effort: quit → kill orphan VBox/dnplayer procs →
        relaunch → wait for ADB-ready.
        """
        target_names = self._context_target_ld_names()
        if not target_names:
            return

        def worker():
            for name in target_names:
                try:
                    issues = []
                    diagnose = getattr(self.emulator, "diagnose_ld", None)
                    if callable(diagnose):
                        try:
                            issues = diagnose(name) or []
                        except Exception as exc:
                            self.log(f"Diagnose failed for '{name}': {exc}", "ERROR")
                            issues = []

                    if issues:
                        sigs = sorted({i.signature for i in issues})
                        self.log(
                            f"'{name}' VBox log shows: {', '.join(sigs)} — attempting recovery",
                            "WARNING",
                        )
                    else:
                        self.log(
                            f"'{name}' shows no known wedging signature — running recovery anyway",
                            "INFO",
                        )

                    recover = getattr(self.emulator, "recover_ld", None)
                    if not callable(recover):
                        self.log(f"Recovery API unavailable for '{name}'", "ERROR")
                        continue

                    try:
                        boot_timeout = max(90, int(self.boot_delay.get()) * 6)
                    except Exception:
                        boot_timeout = 120

                    result = recover(
                        name,
                        attempts=2,
                        log=self.log,
                        boot_timeout=boot_timeout,
                    )

                    if result and getattr(result, "recovered", False):
                        self.log(
                            f"Recovered LD '{name}' in {result.attempts} attempt(s)",
                            "SUCCESS",
                        )
                    else:
                        err = getattr(result, "error", None) or "unknown"
                        self.log(
                            f"Could not recover LD '{name}' ({err}) — "
                            "consider rebooting the host or disabling Hyper-V/Memory Integrity",
                            "ERROR",
                        )
                except Exception as exc:
                    self.log(f"Health check error for '{name}': {exc}", "ERROR")

            try:
                self.root.after(0, self.populate_ld_table)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _context_set_shared_folder(self):
        target_names = self._context_target_ld_names()
        if not target_names:
            return

        primary = target_names[0]
        # Prefill with the LDPlayer default if known, else last user selection.
        initial_dir = getattr(self, "_last_shared_folder_dir", None)
        if not initial_dir:
            try:
                initial_dir = os.path.expanduser("~")
            except Exception:
                initial_dir = None

        if len(target_names) == 1:
            title = f"Shared Folder · {primary}"
        else:
            title = f"Shared Folder · {len(target_names)} LDs"

        folder = filedialog.askdirectory(
            title=title,
            initialdir=initial_dir or None,
            mustexist=True,
            parent=self.root,
        )
        if not folder:
            return

        # Normalize to native Windows separators so dnconsole sees a clean path.
        folder = os.path.normpath(folder)
        self._last_shared_folder_dir = folder

        if len(target_names) > 1:
            preview = ", ".join(target_names[:5])
            if len(target_names) > 5:
                preview += f", ... (+{len(target_names) - 5} more)"
            if not MessageBox.askyesno(
                "Set Shared Folder",
                f"Apply shared folder to {len(target_names)} LDs?\n\n{preview}\n\nFolder: {folder}",
                parent=self.root,
            ):
                return

        def worker():
            updated = []
            failed = []
            for name in target_names:
                try:
                    # LDPlayer 9 rewrites the per-instance config on shutdown.
                    # Stop the LD first so our edit is not clobbered later.
                    try:
                        self.emulator.quit_ld(name)
                    except Exception:
                        pass
                    if self.emulator.set_shared_folder(name, folder):
                        updated.append(name)
                    else:
                        failed.append(name)
                except Exception as exc:
                    failed.append(name)
                    self.log(f"Shared folder error for '{name}': {exc}", "ERROR")

            if updated:
                self.log(
                    f"Set shared folder for {len(updated)} LD(s) → {folder}: {', '.join(updated)}",
                    "SUCCESS",
                )
                self.log(
                    "Restart the affected LD instances to apply the new shared folder.",
                    "INFO",
                )
            if failed:
                self.log(
                    f"Failed to set shared folder for: {', '.join(failed)} "
                    f"(check that the LD index/config exists and the file is writable)",
                    "ERROR",
                )

        threading.Thread(target=worker, daemon=True).start()

    def _context_delete_instance(self):
        target_names = self._context_target_ld_names()
        if not target_names:
            return
        if self.running_event.is_set():
            MessageBox.showwarning(
                "Delete LD Instance",
                "Stop automation before deleting LD instances.",
                parent=self.root,
            )
            return

        if len(target_names) == 1:
            prompt = f"Permanently delete LD instance '{target_names[0]}'?\n\nThis cannot be undone."
        else:
            preview = ", ".join(target_names[:5])
            if len(target_names) > 5:
                preview += f", ... (+{len(target_names) - 5} more)"
            prompt = (
                f"Permanently delete {len(target_names)} LD instances?\n\n{preview}\n\nThis cannot be undone."
            )
        if not MessageBox.askyesno("Delete LD Instance", prompt, parent=self.root):
            return

        def worker():
            removed = []
            failed = []
            for name in target_names:
                try:
                    # Stop first; ignore failures (instance may already be off).
                    try:
                        self.emulator.quit_ld(name)
                    except Exception:
                        pass
                    if self.emulator.remove_ld(name):
                        removed.append(name)
                    else:
                        failed.append(name)
                except Exception as exc:
                    failed.append(name)
                    self.log(f"Delete error for '{name}': {exc}", "ERROR")

            if removed:
                self._purge_ld_references(removed)
                self.log(f"Deleted LD: {', '.join(removed)}", "SUCCESS")
            if failed:
                self.log(f"Failed to delete LD: {', '.join(failed)}", "ERROR")
            try:
                self.root.after(0, self.populate_ld_table)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _purge_ld_references(self, names):
        """Drop deleted LDs from in-memory caches and groups."""
        names_set = set(names)
        try:
            for cache_attr in (
                "_ld_snapshot",
                "_device_runtime_state",
                "_ld_account_cache",
                "_ld_status_cache",
            ):
                cache = getattr(self, cache_attr, None)
                if isinstance(cache, dict):
                    for name in names_set:
                        cache.pop(name, None)
            checked = getattr(self, "_ld_checked_names", None)
            if isinstance(checked, set):
                checked.difference_update(names_set)
            groups = getattr(self, "_ld_groups", None)
            if isinstance(groups, dict):
                for group_name, members in list(groups.items()):
                    pruned = [m for m in members if m not in names_set]
                    if len(pruned) != len(members):
                        groups[group_name] = pruned
            if hasattr(self, "save_settings"):
                try:
                    self.save_settings()
                except Exception:
                    pass
        except Exception as exc:
            self.log(f"Error purging deleted LD references: {exc}", "ERROR")

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
                    self.max_videos.set(max(1, int(task["max_videos"])))
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
        self.facebook_start_delay_seconds.set(settings.facebook_start_delay_seconds)
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
        self.theme_preset.set(settings.theme_preset)
        self.accent_color.set(settings.accent_color)
        self.ui_density.set(settings.ui_density)
        self.ui_scale.set(settings.ui_scale)
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
            facebook_start_delay_seconds=int(self.facebook_start_delay_seconds.get()),
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
            theme_preset=str(self.theme_preset.get()),
            accent_color=str(self.accent_color.get()),
            ui_density=str(self.ui_density.get()),
            ui_scale=str(self.ui_scale.get()),
            ld_groups=self._normalize_ld_groups(),
            blocked_countries=[
                code.strip().upper() for code in self.blocked_countries.get().split(",") if code.strip()
            ],
        )

        self.controller.save_app_settings(settings)

    def load_schedule_settings(self):
        """Load scheduling settings from the configured schedule settings file."""
        try:
            schedule = self.controller.load_schedule_settings()
        except Exception as exc:
            if hasattr(self, "schedule_state_view"):
                self.schedule_state_view.set(
                    kind="error",
                    title="Could not load schedule settings",
                    message=str(exc) or "The schedule configuration could not be read.",
                    actions=[
                        {
                            "text": "Retry",
                            "command": self.load_schedule_settings,
                            "bootstyle": "outline-danger",
                        },
                        {
                            "text": "Settings",
                            "command": self.show_settings_dialog,
                            "bootstyle": "outline-secondary",
                        },
                    ],
                )
            self.log(f"Failed to load schedule settings: {exc}", "ERROR", category="Schedule")
            return

        self.schedule_time.set(schedule.schedule_time)
        self.schedule_daily.set(schedule.schedule_daily)
        self.schedule_weekly.set(schedule.schedule_weekly)
        self.schedule_repeat_hours.set(schedule.schedule_repeat_hours)

        for day_name, day_var in self.schedule_days.items():
            day_var.set(schedule.schedule_days.get(day_name, False))

        if hasattr(self, "schedule_state_view") and not self.schedule_running:
            self.schedule_state_view.set(
                kind="empty",
                title="Schedule is disabled",
                message="Enable scheduling when you want automation to run without manual start.",
                actions=[
                    {"text": "Enable", "command": self.start_schedule, "bootstyle": "outline-success"},
                ],
            )

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
                    snapshot = self._snapshot_with_dashboard_fallback(dict(self.emulator.name_to_serial))
                    try:
                        online_serials = self.emulator.get_online_serials()
                    except Exception:
                        online_serials = set()
                    status_cache = {}
                    for name, serial in snapshot.items():
                        if not serial:
                            status_cache[name] = "Inactive"
                            continue
                        is_online = serial in online_serials
                        if not is_online and ":" in serial:
                            port = serial.split(":")[1]
                            is_online = any(port in s for s in online_serials)
                        status_cache[name] = "Active" if is_online else "Inactive"
                    account_cache = self._build_ld_account_cache(snapshot)
                    self.root.after_idle(
                        lambda data=snapshot, statuses=status_cache, accounts=account_cache: (
                            self._sync_emulator_table(data, statuses, accounts)
                        )
                    )
                except Exception:
                    pass
                self._status_refresh_event.wait(6)

        threading.Thread(target=worker, daemon=True).start()

    def log(self, message, level="INFO", device=None, category=None, **context):
        """Store and render a structured log record."""
        if not self._is_main_thread():
            try:
                self.root.after(
                    0,
                    lambda msg=message, lvl=level, dev=device, cat=category, ctx=context: self.log(
                        msg, lvl, device=dev, category=cat, **ctx
                    ),
                )
            except Exception:
                pass
            return

        message = str(message).strip()
        normalized_level = str(level or "INFO").upper()
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_device = device or self._extract_log_device(message)
        log_category = category or self._infer_log_category(message, normalized_level)
        record = {
            "timestamp": timestamp,
            "level": normalized_level,
            "message": message,
            "device": log_device or "",
            "category": log_category or "General",
            "context": dict(context),
        }

        self.log_records.append(record)
        if len(self.log_records) > self._max_log_records:
            self.log_records = self.log_records[-self._max_log_records :]

        self._record_dashboard_event(timestamp, message, normalized_level)
        # Only refresh the filter dropdown when the device set actually changes.
        device_key = (log_device or "").strip()
        filter_dirty = False
        if device_key:
            if device_key not in self._known_log_devices:
                self._known_log_devices.add(device_key)
                filter_dirty = True
        elif not self._has_general_log_records:
            self._has_general_log_records = True
            filter_dirty = True
        if filter_dirty and hasattr(self, "_refresh_log_filter_options"):
            self._refresh_log_filter_options()
        if hasattr(self, "_render_logs_view"):
            # Debounce rapid log bursts so the Text widget doesn't rebuild per line.
            pending = getattr(self, "_log_render_job", None)
            if pending is not None:
                try:
                    self.root.after_cancel(pending)
                except Exception:
                    pass

            def _do_render():
                self._log_render_job = None
                self._render_logs_view()

            self._log_render_job = self.root.after(80, _do_render)

        # Keep the system pill reserved for mode state; important messages live in logs/events.
        if normalized_level in ["SUCCESS", "ERROR", "WARNING"]:
            mode_text = "Idle"
            if getattr(self, "running_event", None) and self.running_event.is_set():
                mode_text = (
                    "Paused"
                    if getattr(self, "pause_event", None) and not self.pause_event.is_set()
                    else "Running"
                )
            self._update_header_chips(mode_text=mode_text)

        logger_context = dict(context)
        logger_context.setdefault("device", log_device)
        logger_context.setdefault("category", log_category)
        logger_context.setdefault(
            "running", bool(getattr(self, "running_event", None) and self.running_event.is_set())
        )
        logger_context.setdefault("schedule_running", bool(getattr(self, "schedule_running", False)))
        self.app_logger.log(normalized_level, message, **logger_context)

    def _extract_log_device(self, message):
        """Best-effort device association for legacy log calls."""
        text = str(message or "")
        candidates = set(getattr(self, "_ld_snapshot", {}).keys())
        candidates.update(getattr(self, "_device_runtime_state", {}).keys())
        emulator = getattr(self, "emulator", None)
        candidates.update(getattr(emulator, "name_to_serial", {}).keys() if emulator else [])

        lowered = text.lower()
        for name in sorted((name for name in candidates if name), key=len, reverse=True):
            if str(name).lower() in lowered:
                return str(name)

        match = re.search(r"\b(?:LDPlayer|LD)[\s_-]*\d+\b", text, flags=re.IGNORECASE)
        if match:
            return match.group(0).strip()
        return ""

    def _infer_log_category(self, message, level):
        text = str(message or "").lower()
        if "backup" in text or "restore" in text:
            return "Backup"
        if "schedule" in text or "scheduled" in text:
            return "Schedule"
        if "account" in text:
            return "Accounts"
        if "adb" in text or "emulator" in text or "ld" in text:
            return "Devices"
        if "automation" in text or "task" in text:
            return "Automation"
        if level in {"ERROR", "WARNING"}:
            return "Attention"
        return "General"

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
        self.dashboard_events.append(
            {
                "time": timestamp,
                "level": normalized_level,
                "message": normalized_message[:160],
            }
        )
        self.dashboard_events = self.dashboard_events[-80:]
        if hasattr(self, "dashboard_recent_events_frame"):
            # Debounce repaints — bursts of important logs would otherwise rebuild
            # the FeedCards on every line.
            pending = getattr(self, "_events_render_job", None)
            if pending is not None:
                try:
                    self.root.after_cancel(pending)
                except Exception:
                    pass

            def _do_render_events():
                self._events_render_job = None
                self._render_recent_events()

            self._events_render_job = self.root.after(150, _do_render_events)

    def show_time_picker(self):
        """Show time picker dialog"""
        # Simplified time picker
        time_str = simpledialog.askstring(
            "Time Picker", "Enter time (HH:MM):", initialvalue=self.schedule_time.get()
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
Total Items: {stats["total"]}
Available: {stats["available"]}
Used: {stats["used"]}
Queue Size: {stats["queue_size"]}

Recent Items:
-------------
"""
        for item in details[:10]:  # Show first 10 items
            filename = os.path.basename(item["path"])
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
            visible_rows[item] for item in self.ld_table.get_checked_items() if item in visible_rows
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
        errors = sum(
            1
            for status in self._ld_status_cache.values()
            if status not in ("Active", "Running", "Inactive", "Paused", "Completed")
        )
        with_account = sum(
            1 for account in self._ld_account_cache.values() if account and account != "No account"
        )
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
            "queue": str(len(self.content_manager.get_queue_items()))
            if hasattr(self, "content_manager")
            else "0",
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
        self._set_ld_group_filter("All Groups")
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
        self._fleet_load_state = "loading"
        self._fleet_error_message = ""
        self._sync_fleet_state_view([])
        try:
            self.root.update_idletasks()
        except Exception:
            pass
        try:
            self.emulator = EmulatorService()
            self.populate_ld_table()
            self._fleet_load_state = "ready"
            self._fleet_error_message = ""
            self._sync_fleet_state_view()
            self.log("Emulator list refreshed", "SUCCESS")
        except Exception as e:
            self._fleet_load_state = "error"
            self._fleet_error_message = str(e)
            self._sync_fleet_state_view([])
            self.log(f" Error refreshing emulator list: {e}", "ERROR")

    def populate_ld_table(self):
        """Populate LD table with current emulators"""
        try:
            self.emulator._build_serial_mapping()
            snapshot = self._snapshot_with_dashboard_fallback(dict(self.emulator.name_to_serial))
            status_cache = {name: self._ld_status_cache.get(name, "Inactive") for name in snapshot}
            account_cache = self._build_ld_account_cache(snapshot)
            self._fleet_load_state = "ready"
            self._fleet_error_message = ""
            self._sync_emulator_table(snapshot, status_cache, account_cache, force=True)
        except Exception as exc:
            self._fleet_load_state = "error"
            self._fleet_error_message = str(exc)
            self._sync_fleet_state_view([])
            raise

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
            runtime_defaults.update(
                {
                    "task": {
                        "scroll": "Scroll Feed",
                        "reels": "Watch Reels",
                        "reg_account": "Register Account",
                        "login": "Login Account",
                        "test_feature": "Test Feature",
                    }.get(self.task_type_var.get(), self.task_type_var.get().title()),
                    "progress": 72,
                }
            )
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
                        "login": "Login Account",
                        "test_feature": "Test Feature",
                    }.get(self.task_type_var.get(), self.task_type_var.get().title())
                self.ld_table.item(
                    item,
                    values=(
                        values[0],
                        values[1],
                        self._status_text(status),
                        task_text,
                        progress_text,
                        account_text,
                        group_text,
                    ),
                )

                # Update tags
                tags = list(self.ld_table.item(item, "tags"))
                tags = [
                    t
                    for t in tags
                    if t
                    not in ("active", "inactive", "running", "paused", "completed", "queued", "attention")
                ]
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

        accounts_pool = []
        if task_type == "login":
            try:
                accounts_pool = list(self._db_login_accounts() or [])
            except Exception as exc:
                MessageBox.showerror("Login Account", f"Could not load accounts: {exc}")
                return
            if len(accounts_pool) < len(selected_ld_names):
                MessageBox.showerror(
                    "Login Account",
                    f"Need at least {len(selected_ld_names)} accounts; only {len(accounts_pool)} available.\n"
                    "Open 'Manage Accounts' on the Login task panel to import more.",
                )
                return

        handler_context = TaskHandlerContext(
            emulator=self.emulator,
            log=self.log,
            pause_event=self.pause_event,
            running_flag=lambda: self.running_event.is_set(),
            blocked_countries=[
                code.strip().upper() for code in self.blocked_countries.get().split(",") if code.strip()
            ],
            auto_arrange_ld=bool(self.auto_arrange_ld.get()),
            state_callback=self.update_device_runtime_state,
            verify_account=bool(self.verify_account.get()),
            scroll_after_post=bool(self.scroll_after_post.get()),
            random_like=bool(self.random_like.get()),
            clear_cache=bool(self.clear_cache.get()),
            facebook_start_delay_seconds=int(self.facebook_start_delay_seconds.get()),
            reg_contact_mode=self.reg_contact_mode.get(),
            reg_contact_value=self.reg_contact_value.get(),
            reg_phone_prefix=self.reg_phone_prefix.get(),
            content_manager=self.content_manager,
            use_content_queue=bool(self.use_content_queue.get()),
        )

        try:
            task_handler = self.task_handler_factory.create(task_type, handler_context)
        except UnsupportedTaskTypeError:
            MessageBox.showwarning(
                "Task Not Implemented",
                "This task type is UI-only right now. Please use Scroll Feed, Register Account, Watch Reels, or Test Feature.",
            )
            return

        # Start performance monitoring
        self.performance_monitor.start_task_timer(f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}")

        # Start automation. Button/status updates are applied by the
        # state listener registered on the controller.
        self.automation_controller.start()
        if hasattr(self, "status_task_lbl"):
            self.status_task_lbl.set_status("Running", text=f"Tasks: {len(selected_ld_names)} active")

        self.log(f" Starting automation for {len(selected_ld_names)} LDs", "SUCCESS")
        self.log(f"Task type: {task_type}, Duration: {self.task_duration.get()} minutes", "INFO")

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
            accounts_pool=accounts_pool,
            verify_2fa=bool(self.verify_2fa.get()),
        )

        def automation_thread():
            try:
                main_window = self.task_controller.create_runner(
                    request=request,
                    running_flag=lambda: self.running_event.is_set(),
                    log_func=self.log,
                    task_handler=task_handler,
                    progress_callback=self.update_progress,
                    emulator=self.emulator,
                    state_callback=self.update_device_runtime_state,
                    pause_event=self.pause_event,
                )
            except Exception as exc:
                self.log(f" Error in automation: {exc}", "ERROR")
                self.performance_monitor.end_task_timer(False)
                MessageBox.showerror("Error", f"Automation error: {exc}")
                self.stop_automation(confirm=False)
                return

            def _on_error(exc: BaseException) -> None:
                self.log(f" Error in automation: {exc}", "ERROR")
                self.performance_monitor.end_task_timer(False)
                MessageBox.showerror("Error", f"Automation error: {exc}")

            def _on_completed(completed_normally: bool) -> None:
                self.performance_monitor.end_task_timer(True)
                if completed_normally and self.auto_shutdown_pc.get():
                    self.root.after(0, self._schedule_pc_shutdown)

            try:
                self.automation_controller.run_batch(
                    main_window,
                    on_error=_on_error,
                    on_completed=_on_completed,
                )
            finally:
                # GUI-side cleanup (task label, device-state reset, progress
                # bar) that lives on ``stop_automation``. Safe to call after
                # ``run_batch`` already transitioned state — ``controller.stop``
                # is a no-op the second time.
                self.stop_automation(confirm=False)

        threading.Thread(target=automation_thread, daemon=True).start()

    def _schedule_pc_shutdown(self):
        """Delegate to ``utils.system_power.schedule_pc_shutdown``."""
        schedule_pc_shutdown(self.log)

    def toggle_pause(self):
        """Toggle pause state. Delegates state change to AutomationController."""
        new_state = self.automation_controller.toggle_pause()
        if new_state is AutomationState.PAUSED:
            self.log("Automation paused", "WARNING")
        elif new_state is AutomationState.RUNNING:
            self.log("Automation resumed", "SUCCESS")

    def stop_automation(self, confirm=True):
        """Stop automation process. Delegates state change to AutomationController."""
        if (
            confirm
            and self.running_event.is_set()
            and not MessageBox.askyesno("Stop Automation", "Stop current automation run?")
        ):
            return

        self.automation_controller.stop()
        if hasattr(self, "status_task_lbl"):
            self.status_task_lbl.set_status("Idle", text="Tasks: 0 active")
        self.log("Automation stopped", "INFO")
        self.update_progress(0)
        for name in list(self._device_runtime_state.keys()):
            current_state = self._device_runtime_state[name].get("state", "")
            if current_state not in ("Completed", "Idle"):
                self.update_device_runtime_state(
                    name, state="Idle", task="Waiting for next run", progress=0, queue_label="-"
                )

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
        if hasattr(self, "schedule_state_pill"):
            self.schedule_state_pill.set_status("Enabled", text="Schedule: Enabled")
        if hasattr(self, "schedule_state_view"):
            self.schedule_state_view.set(
                kind="success",
                title="Schedule is enabled",
                message="The scheduler is monitoring the configured run window.",
                actions=[
                    {"text": "Disable", "command": self.stop_schedule, "bootstyle": "outline-warning"},
                ],
            )
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
        if hasattr(self, "schedule_state_pill"):
            self.schedule_state_pill.set_status("Disabled", text="Schedule: Disabled")
        if hasattr(self, "schedule_state_view"):
            self.schedule_state_view.set(
                kind="empty",
                title="Schedule is disabled",
                message="Enable scheduling when you want automation to run without manual start.",
                actions=[
                    {"text": "Enable", "command": self.start_schedule, "bootstyle": "outline-success"},
                ],
            )
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
