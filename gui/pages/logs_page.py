import tkinter as tk
from tkinter import filedialog, messagebox as MessageBox

import ttkbootstrap as tb

from gui.components.state_views import StateView


def _hex_to_rgb(hex_color):
    h = (hex_color or "#000000").lstrip("#")
    if len(h) != 6:
        return (0, 0, 0)
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return (0, 0, 0)


def _rgb_to_hex(rgb):
    return "#{:02X}{:02X}{:02X}".format(*[max(0, min(255, int(c))) for c in rgb])


def _blend_color(top, base, ratio):
    """Mix ``top`` over ``base`` at ``ratio`` (0..1).  Used for soft tints."""
    tr, tg, tb_ = _hex_to_rgb(top)
    br, bg, bb = _hex_to_rgb(base)
    return _rgb_to_hex((
        br + (tr - br) * ratio,
        bg + (tg - bg) * ratio,
        bb + (tb_ - bb) * ratio,
    ))


class LogsPageMixin:
    LOG_LEVELS = ("All", "INFO", "SUCCESS", "WARNING", "ERROR", "DEBUG", "Warnings & Errors")
    ALL_DEVICES_LABEL = "All Devices"
    GENERAL_LOG_LABEL = "General"

    # Visual mapping for level: (display label, level tag, optional row-tint tag)
    LOG_LEVEL_VISUALS = {
        "INFO":    ("INFO", "LVL_INFO",    None),
        "SUCCESS": ("DONE", "LVL_SUCCESS", None),
        "WARNING": ("WARN", "LVL_WARNING", "ROW_WARN"),
        "ERROR":   ("FAIL", "LVL_ERROR",   "ROW_ERROR"),
        "DEBUG":   ("DBUG", "LVL_DEBUG",   None),
    }

    def create_logs_tab(self):
        """Create a filterable structured log viewer."""
        logs_tab = tb.Frame(self.notebook)
        self.notebook.add(logs_tab, text="Logs")

        logs_card = self._create_card_section(
            logs_tab,
            "Runtime Logs",
            "Searchable operational output with level and device scope.",
            expand=True,
        )

        controls = tb.Frame(logs_card)
        controls.pack(fill="x", padx=10, pady=(10, 8))

        self.log_search_var = tk.StringVar()
        self.log_level_filter_var = tk.StringVar(value="All")
        self.log_device_filter_var = tk.StringVar(value=self.ALL_DEVICES_LABEL)
        self.log_follow_var = tk.BooleanVar(value=True)

        self.log_search_var.trace_add("write", lambda *_: self._render_logs_view())
        self.log_level_filter_var.trace_add("write", lambda *_: self._render_logs_view())
        self.log_device_filter_var.trace_add("write", lambda *_: self._render_logs_view())

        tb.Label(controls, text="Search", style="Subtitle.TLabel").pack(side="left")
        self.log_search_entry = tb.Entry(controls, textvariable=self.log_search_var, width=28)
        self.log_search_entry.pack(side="left", padx=(6, 12))

        tb.Label(controls, text="Level", style="Subtitle.TLabel").pack(side="left")
        self.log_level_combo = tb.Combobox(
            controls,
            textvariable=self.log_level_filter_var,
            values=self.LOG_LEVELS,
            state="readonly",
            width=11,
        )
        self.log_level_combo.pack(side="left", padx=(6, 12))

        tb.Label(controls, text="Device", style="Subtitle.TLabel").pack(side="left")
        self.log_device_combo = tb.Combobox(
            controls,
            textvariable=self.log_device_filter_var,
            values=(self.ALL_DEVICES_LABEL,),
            state="readonly",
            width=22,
        )
        self.log_device_combo.pack(side="left", padx=(6, 12))

        tb.Checkbutton(
            controls,
            text="Follow",
            variable=self.log_follow_var,
            bootstyle="success-round-toggle",
            command=self._render_logs_view,
        ).pack(side="left", padx=(0, 10))

        tb.Button(
            controls,
            text="Clear Filters",
            command=self.clear_log_filters,
            bootstyle="outline-secondary",
            width=12,
        ).pack(side="right", padx=2)
        tb.Button(
            controls,
            text="Export",
            command=self.export_logs,
            bootstyle="outline-secondary",
            width=9,
        ).pack(side="right", padx=2)
        tb.Button(
            controls,
            text="Clear",
            command=self.clear_logs,
            bootstyle="outline-danger",
            width=9,
        ).pack(side="right", padx=2)

        summary = tb.Frame(logs_card)
        summary.pack(fill="x", padx=10, pady=(0, 8))
        self.log_count_label = tb.Label(summary, text="0 of 0 records", style="MetricSub.TLabel")
        self.log_count_label.pack(side="left")
        self.log_scope_label = tb.Label(summary, text="Scope: All levels / All devices", style="MetricSub.TLabel")
        self.log_scope_label.pack(side="right")

        logs_container = tb.Frame(logs_card)
        logs_container.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.logs_state_view = StateView(
            logs_container,
            kind="loading",
            title="Loading log records...",
            message="Preparing the in-memory log viewer.",
            palette=self.palette,
            display_font=self.display_font,
            mono_font=self.mono_font,
        )
        self.logs_state_view.pack(fill="x", pady=(0, 8))

        self.logs_text = tk.Text(
            logs_container,
            wrap="none",
            font=(self.mono_font, 10),
            bg=self.palette["surface"],
            fg=self.palette["text"],
            insertbackground=self.palette["text"],
            selectbackground="#253447",
            padx=14,
            pady=12,
            spacing1=2,
            spacing3=3,
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.palette["border"],
        )
        self._configure_log_text_tags()

        v_scrollbar = tb.Scrollbar(logs_container, style="Vertical.TScrollbar")
        h_scrollbar = tb.Scrollbar(logs_container, orient="horizontal", style="Horizontal.TScrollbar")
        v_scrollbar.pack(side="right", fill="y")
        h_scrollbar.pack(side="bottom", fill="x")
        self.logs_text.config(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        v_scrollbar.config(command=self.logs_text.yview)
        h_scrollbar.config(command=self.logs_text.xview)
        self.logs_text.pack(fill="both", expand=True)
        self.logs_text.config(state="disabled")

        self._refresh_log_filter_options()
        self._render_logs_view()

    def _configure_log_text_tags(self):
        palette = self.palette
        text = self.logs_text
        surface = palette.get("surface", "#0E1118")
        text_fg = palette.get("text", "#E2E8F0")
        muted = palette.get("muted", "#64748B")
        primary = palette.get("primary", "#22D3EE")
        success = palette.get("success", "#10B981")
        warning = palette.get("warning", "#F59E0B")
        danger = palette.get("danger", "#EF4444")
        debug_color = "#A78BFA"
        emu_color = "#60A5FA"

        # ── Row backgrounds (defined first so level/foreground tags win on conflict) ── #
        text.tag_configure("ROW_WARN",  background=_blend_color(warning, surface, 0.10))
        text.tag_configure("ROW_ERROR", background=_blend_color(danger,  surface, 0.14))

        # ── Level badges — tinted background pill with bold colored text ── #
        badge_font = (self.mono_font, 9, "bold")
        for tag, color in (
            ("LVL_INFO",    primary),
            ("LVL_SUCCESS", success),
            ("LVL_WARNING", warning),
            ("LVL_ERROR",   danger),
            ("LVL_DEBUG",   debug_color),
            ("LVL_EMU",     emu_color),
        ):
            text.tag_configure(
                tag,
                foreground=color,
                background=_blend_color(color, surface, 0.22),
                font=badge_font,
            )

        # ── Field accents ── #
        text.tag_configure("TIMESTAMP", foreground=_blend_color(text_fg, surface, 0.45))
        text.tag_configure("DEVICE",    foreground=primary, font=(self.mono_font, 10, "bold"))
        text.tag_configure("CATEGORY",  foreground=muted)
        text.tag_configure("MESSAGE",   foreground=text_fg)
        text.tag_configure("MESSAGE_WARN",  foreground=_blend_color(warning, text_fg, 0.65))
        text.tag_configure("MESSAGE_ERROR", foreground=_blend_color(danger,  text_fg, 0.55))
        text.tag_configure("SEPARATOR", foreground=_blend_color(muted, surface, 0.55))
        text.tag_configure("GUTTER",    foreground=_blend_color(muted, surface, 0.45))
        text.tag_configure("EMPTY",     foreground=muted, justify="center")

        # Make level badges win the background-color conflict over row tints.
        for tag in ("LVL_INFO", "LVL_SUCCESS", "LVL_WARNING", "LVL_ERROR", "LVL_DEBUG", "LVL_EMU"):
            text.tag_raise(tag)

        # ── Legacy tag aliases (kept for any external callers / older records) ── #
        text.tag_configure("INFO",           foreground=primary)
        text.tag_configure("SUCCESS",        foreground=success)
        text.tag_configure("WARNING",        foreground=warning)
        text.tag_configure("ERROR",          foreground=danger)
        text.tag_configure("DEBUG",          foreground=debug_color)
        text.tag_configure("EMULATOR_COUNT", foreground=emu_color)

    def _refresh_log_filter_options(self):
        if not hasattr(self, "log_device_combo"):
            return
        current = self.log_device_filter_var.get() if hasattr(self, "log_device_filter_var") else self.ALL_DEVICES_LABEL
        devices = set(getattr(self, "_ld_snapshot", {}).keys())
        devices.update(getattr(self, "_device_runtime_state", {}).keys())
        for record in getattr(self, "log_records", []):
            device = str(record.get("device") or "").strip()
            if device:
                devices.add(device)

        values = [self.ALL_DEVICES_LABEL]
        if any(not str(record.get("device") or "").strip() for record in getattr(self, "log_records", [])):
            values.append(self.GENERAL_LOG_LABEL)
        values.extend(sorted(devices, key=str.lower))
        self.log_device_combo.configure(values=tuple(values))
        if current not in values:
            self.log_device_filter_var.set(self.ALL_DEVICES_LABEL)

    def _filter_log_records(self):
        records = list(getattr(self, "log_records", []))
        query = self.log_search_var.get().strip().lower() if hasattr(self, "log_search_var") else ""
        level_filter = self.log_level_filter_var.get().strip().upper() if hasattr(self, "log_level_filter_var") else "ALL"
        device_filter = self.log_device_filter_var.get().strip() if hasattr(self, "log_device_filter_var") else self.ALL_DEVICES_LABEL

        filtered = []
        for record in records:
            level = str(record.get("level") or "INFO").upper()
            device = str(record.get("device") or "").strip()
            category = str(record.get("category") or "General")
            message = str(record.get("message") or "")

            if level_filter == "WARNINGS & ERRORS":
                if level not in {"WARNING", "ERROR"}:
                    continue
            elif level_filter != "ALL" and level != level_filter:
                continue
            if device_filter == self.GENERAL_LOG_LABEL and device:
                continue
            if device_filter not in ("", self.ALL_DEVICES_LABEL, self.GENERAL_LOG_LABEL) and device != device_filter:
                continue
            if query:
                haystack = f"{level} {device} {category} {message}".lower()
                if query not in haystack:
                    continue
            filtered.append(record)
        return filtered

    def _render_logs_view(self):
        if not hasattr(self, "logs_text"):
            return

        filtered = self._filter_log_records()
        total = len(getattr(self, "log_records", []))
        level_scope = self.log_level_filter_var.get() if hasattr(self, "log_level_filter_var") else "All"
        device_scope = self.log_device_filter_var.get() if hasattr(self, "log_device_filter_var") else self.ALL_DEVICES_LABEL

        self.logs_text.config(state="normal")
        self.logs_text.delete("1.0", "end")

        if not filtered:
            has_records = bool(getattr(self, "log_records", []))
            has_filters = any([
                self.log_search_var.get().strip() if hasattr(self, "log_search_var") else "",
                (self.log_level_filter_var.get() if hasattr(self, "log_level_filter_var") else "All") != "All",
                (self.log_device_filter_var.get() if hasattr(self, "log_device_filter_var") else self.ALL_DEVICES_LABEL) != self.ALL_DEVICES_LABEL,
            ])
            if hasattr(self, "logs_state_view"):
                if has_records and has_filters:
                    self.logs_state_view.set(
                        kind="empty",
                        title="No logs match the current filters",
                        message="Try a broader search, a different level, or All Devices.",
                        actions=[
                            {"text": "Clear Filters", "command": self.clear_log_filters, "bootstyle": "outline-secondary"},
                        ],
                    )
                else:
                    self.logs_state_view.set(
                        kind="empty",
                        title="No logs yet",
                        message="Runtime events will appear here as the app discovers devices, runs tasks, or handles errors.",
                        actions=[],
                    )
                self.logs_state_view.pack(fill="x", pady=(0, 8))
            self.logs_text.insert("end", "No log records to display.\n", "EMPTY")
        else:
            if hasattr(self, "logs_state_view"):
                self.logs_state_view.pack_forget()
            for record in filtered[-1000:]:
                self._insert_log_record(record)

        self.logs_text.config(state="disabled")
        if self.log_follow_var.get():
            self.logs_text.see("end")

        if hasattr(self, "log_count_label"):
            shown = len(filtered)
            capped = " (showing latest 1000)" if shown > 1000 else ""
            self.log_count_label.config(text=f"{min(shown, 1000)} of {total} records{capped}")
        if hasattr(self, "log_scope_label"):
            self.log_scope_label.config(text=f"Scope: {level_scope} / {device_scope}")

    def _insert_log_record(self, record):
        timestamp = str(record.get("timestamp") or "--:--:--")
        level = str(record.get("level") or "INFO").upper()
        device = str(record.get("device") or self.GENERAL_LOG_LABEL)
        category = str(record.get("category") or "General")
        message = str(record.get("message") or "")

        label, level_tag, row_tag = self.LOG_LEVEL_VISUALS.get(
            level,
            (level[:4].ljust(4), "LVL_INFO", None),
        )
        if message.startswith("Available emulators:"):
            level_tag = "LVL_EMU"
            label = "EMUL"

        message_tag = "MESSAGE"
        if level == "ERROR":
            message_tag = "MESSAGE_ERROR"
        elif level == "WARNING":
            message_tag = "MESSAGE_WARN"

        line_start = self.logs_text.index("end - 1c")

        # Layout:  ▏ HH:MM:SS  [ INFO ]  Device              ·  Category        │  message
        self.logs_text.insert("end", " ", "GUTTER")
        self.logs_text.insert("end", f"{timestamp} ", "TIMESTAMP")
        self.logs_text.insert("end", f" {label} ", level_tag)
        self.logs_text.insert("end", "  ")
        self.logs_text.insert("end", f"{device:<18.18}", "DEVICE")
        self.logs_text.insert("end", "  ·  ", "SEPARATOR")
        self.logs_text.insert("end", f"{category:<14.14}", "CATEGORY")
        self.logs_text.insert("end", "  │  ", "SEPARATOR")
        self.logs_text.insert("end", f"{message}\n", message_tag)

        if row_tag:
            line_end = self.logs_text.index("end - 1c")
            self.logs_text.tag_add(row_tag, line_start, line_end)

    def clear_log_filters(self):
        if hasattr(self, "log_search_var"):
            self.log_search_var.set("")
        if hasattr(self, "log_level_filter_var"):
            self.log_level_filter_var.set("All")
        if hasattr(self, "log_device_filter_var"):
            self.log_device_filter_var.set(self.ALL_DEVICES_LABEL)
        self._render_logs_view()

    def export_logs(self):
        """Export the currently filtered log view."""
        filename = filedialog.asksaveasfilename(
            defaultextension=".log",
            filetypes=[("Log files", "*.log"), ("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not filename:
            return

        try:
            records = self._filter_log_records()
            with open(filename, "w", encoding="utf-8") as f:
                for record in records:
                    timestamp = str(record.get("timestamp") or "--:--:--")
                    level = str(record.get("level") or "INFO").upper()
                    device = str(record.get("device") or self.GENERAL_LOG_LABEL)
                    category = str(record.get("category") or "General")
                    message = str(record.get("message") or "")
                    f.write(f"[{timestamp}] {level:<7} {device:<18.18} {category:<12.12} {message}\n")
            self.log(f"Logs exported to {filename}", "SUCCESS", category="Logs")
        except Exception as exc:
            self.log(f"Failed to export logs: {exc}", "ERROR", category="Logs")

    def clear_logs(self):
        """Clear in-memory UI logs with confirmation."""
        if not MessageBox.askyesno("Clear Logs", "Clear the in-app log viewer? This does not delete app.jsonl."):
            return

        self.log_records.clear()
        if hasattr(self, "dashboard_events"):
            self.dashboard_events.clear()
        if hasattr(self, "dashboard_recent_events_frame"):
            self._render_recent_events()
        self._refresh_log_filter_options()
        self._render_logs_view()
        self.log("Logs cleared", "INFO", category="Logs")
