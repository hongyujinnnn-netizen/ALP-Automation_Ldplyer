import tkinter as tk
import ttkbootstrap as tb
from core.managers import TaskTemplates
from gui.components.scrollable_frame import ScrollableFrame
from gui.gradient_progress import GradientProgressBar

class TasksPageMixin:
    def create_tasks_tab(self):
        """Create Tasks tab with settings"""
        tasks_tab = tb.Frame(self.notebook)
        self.notebook.add(tasks_tab, text="Tasks")

        scroller = ScrollableFrame(tasks_tab, bg=self.palette["surface"])
        scroller.pack(fill="both", expand=True)

        self.create_enhanced_settings(scroller.body)
        self.create_control_buttons(scroller.body)

    def create_control_buttons(self, parent):
        """Create main automation control buttons."""
        control_frame = self._create_card_section(
            parent,
            "Automation Control",
            "Start, pause, stop and maintenance actions."
        )

        button_grid = tb.Frame(control_frame)
        button_grid.pack(fill="x", padx=6, pady=6)

        self.start_button = tb.Button(
            button_grid,
            text="Run Automation",
            command=self.start_automation,
            style="Primary.TButton",
            width=20
        )
        self.start_button.grid(row=0, column=0, padx=5, pady=5)

        self.pause_button = tb.Button(
            button_grid,
            text="Pause",
            command=self.toggle_pause,
            style="Ctrl.TButton",
            width=20,
            state="disabled"
        )
        self.pause_button.grid(row=0, column=1, padx=5, pady=5)

        self.stop_button = tb.Button(
            button_grid,
            text="Stop Run",
            command=self.stop_automation,
            style="Ctrl.TButton",
            width=20,
            state="disabled"
        )
        self.stop_button.grid(row=0, column=2, padx=5, pady=5)

        self.backup_button = tb.Button(
            button_grid,
            text="Create Backup",
            command=self.create_backup,
            style="Ghost.TButton",
            width=20
        )
        self.backup_button.grid(row=1, column=0, padx=5, pady=5)

        tb.Button(
            button_grid,
            text="Restore Backup",
            command=self.restore_backup,
            style="Ghost.TButton",
            width=20
        ).grid(row=1, column=1, padx=5, pady=5)

        tb.Button(
            button_grid,
            text="Settings",
            command=self.show_settings_dialog,
            style="Ghost.TButton",
            width=20
        ).grid(row=1, column=2, padx=5, pady=5)


    def create_enhanced_settings(self, parent):
        """Create enhanced settings section"""
        settings_frame = self._create_card_section(
            parent,
            "Task Configuration",
            "Tune core automation behavior and reusable templates.",
        )

        # fill="x" — height is determined by tab content, not the viewport.
        settings_notebook = tb.Notebook(settings_frame)
        settings_notebook.pack(fill="x", padx=4, pady=4)
        
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

        tb.Label(main_grid, text="Post Pages:", bootstyle="secondary").grid(
            row=2, column=0, padx=10, pady=10, sticky="w")

        tb.Spinbox(main_grid, from_=1, to=20, textvariable=self.page_per_account,
                   width=8).grid(row=2, column=1, padx=10, pady=10, sticky="w")

        tb.Label(main_grid, text="Accounts per LD:", bootstyle="secondary").grid(
            row=2, column=2, padx=10, pady=10, sticky="w")

        tb.Spinbox(main_grid, from_=1, to=20, textvariable=self.accounts_per_ld,
                   width=8).grid(row=2, column=3, padx=10, pady=10, sticky="w")
        
        # Row 3 - Checkboxes
        tb.Checkbutton(main_grid, text="Start Devices Simultaneously",
                      variable=self.start_same_time,
                      bootstyle="primary-round-toggle").grid(
            row=3, column=0, columnspan=2, padx=10, pady=10, sticky="w")
        
        tb.Checkbutton(main_grid, text="Use Content Queue",
                      variable=self.use_content_queue,
                      bootstyle="primary-round-toggle").grid(
            row=3, column=2, columnspan=2, padx=10, pady=10, sticky="w")
        tb.Checkbutton(
            main_grid,
            text="Auto Arrange LD",
            variable=self.auto_arrange_ld,
            bootstyle="primary-round-toggle",
        ).grid(row=4, column=0, columnspan=2, padx=10, pady=10, sticky="w")
        tb.Checkbutton(
            main_grid,
            text="Verify Account",
            variable=self.verify_account,
            bootstyle="primary-round-toggle",
        ).grid(row=4, column=2, columnspan=2, padx=10, pady=10, sticky="w")
        tb.Checkbutton(
            main_grid,
            text="Auto Shutdown PC After Task Completion",
            variable=self.auto_shutdown_pc,
            bootstyle="danger-round-toggle",
        ).grid(row=5, column=0, columnspan=4, padx=10, pady=10, sticky="w")
        tb.Label(
            main_grid,
            text="Tip: 'Accounts per LD' is used by Register Account tasks and will loop on the same emulator.",
            style="Subtitle.TLabel"
        ).grid(row=6, column=0, columnspan=4, padx=10, pady=(4, 0), sticky="w")


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
            ("Register Account", "reg_account"),
            ("Post Reels", "reels"),
            ("Test Feature", "test_feature"),
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
        tb.Checkbutton(
            main_grid,
            text="Scroll Reels After Post",
            variable=self.scroll_after_post,
            bootstyle="primary-round-toggle",
        ).grid(row=2, column=0, columnspan=2, padx=10, pady=(10, 10), sticky="w")
        tb.Checkbutton(
            main_grid,
            text="Clear Facebook Cache After Task",
            variable=self.clear_cache,
            bootstyle="primary-round-toggle",
        ).grid(row=2, column=2, columnspan=2, padx=10, pady=(10, 10), sticky="w")
        tb.Label(
            main_grid,
            text="Template applies validated defaults to reduce setup mistakes.",
            style="Subtitle.TLabel"
        ).grid(row=3, column=0, columnspan=4, padx=10, pady=(2, 0), sticky="w")

