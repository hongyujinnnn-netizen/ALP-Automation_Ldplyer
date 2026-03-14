import tkinter as tk


class MenuBarMixin:
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
