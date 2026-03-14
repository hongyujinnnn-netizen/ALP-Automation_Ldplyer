import tkinter as tk
from tkinter import ttk
import ttkbootstrap as tb
from gui.gradient_progress import GradientProgressBar

class DashboardPageMixin:
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

