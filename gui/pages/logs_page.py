import tkinter as tk
from tkinter import messagebox as MessageBox
import ttkbootstrap as tb
from gui.gradient_progress import GradientProgressBar

class LogsPageMixin:
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

