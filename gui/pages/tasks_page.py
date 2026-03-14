import tkinter as tk
import ttkbootstrap as tb
from core.managers import TaskTemplates
from gui.gradient_progress import GradientProgressBar

class TasksPageMixin:
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

