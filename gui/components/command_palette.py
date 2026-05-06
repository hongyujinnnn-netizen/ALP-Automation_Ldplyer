import tkinter as tk
from dataclasses import dataclass, field
from tkinter import ttk
from typing import Callable


@dataclass(frozen=True)
class Command:
    id: str
    label: str
    category: str
    action: Callable[[], None]
    keywords: tuple[str, ...] = field(default_factory=tuple)
    hint: str = ""


class CommandPalette(tk.Toplevel):
    """Searchable command launcher for app-level actions."""

    MAX_RESULTS = 8

    def __init__(self, master, commands, palette=None, display_font="Segoe UI", mono_font="Consolas"):
        super().__init__(master)
        self.master = master
        self.commands = [self._coerce_command(command) for command in commands]
        self.palette = palette or {}
        self.display_font = display_font
        self.mono_font = mono_font
        self.filtered_commands = []
        self.selected_index = 0
        self.row_widgets = []

        self._configure_window()
        try:
            self._build_ui()
            self._bind_events()
            self._filter_commands()
        finally:
            self._show_window()
        self.after(20, self._focus_search)

    @staticmethod
    def _coerce_command(command):
        if isinstance(command, Command):
            return command
        return Command(
            id=command["id"],
            label=command["label"],
            category=command.get("category", "Command"),
            keywords=tuple(command.get("keywords", ())),
            action=command["action"],
            hint=command.get("hint", ""),
        )

    def _color(self, key, fallback):
        return self.palette.get(key, fallback)

    def _configure_window(self):
        self.title("Command Palette")
        self.transient(self.master)
        self.resizable(False, False)
        self.configure(bg=self._color("app_bg", "#080B10"))
        self.withdraw()

        self._width = 680
        self._height = 520

    def _show_window(self):
        self.update_idletasks()
        master_x = self.master.winfo_rootx()
        master_y = self.master.winfo_rooty()
        master_w = max(self.master.winfo_width(), 1)
        master_h = max(self.master.winfo_height(), 1)
        x = master_x + (master_w - self._width) // 2
        y = master_y + max(80, (master_h - self._height) // 4)
        self.geometry(f"{self._width}x{self._height}+{max(x, 0)}+{max(y, 0)}")
        self.deiconify()
        self.lift()
        self.grab_set()

    def _build_ui(self):
        surface = self._color("surface", "#0E1118")
        border = self._color("border_alt", "#222B3A")

        outer = tk.Frame(self, bg=border, padx=1, pady=1)
        outer.pack(fill="both", expand=True, padx=18, pady=18)

        self.shell = tk.Frame(outer, bg=surface)
        self.shell.pack(fill="both", expand=True)

        header = tk.Frame(self.shell, bg=self._color("surface_alt", "#141820"), padx=18, pady=14)
        header.pack(fill="x")

        tk.Label(
            header,
            text="Command Palette",
            bg=self._color("surface_alt", "#141820"),
            fg=self._color("text", "#E2E8F0"),
            font=(self.display_font, 14),
        ).pack(side="left")
        tk.Label(
            header,
            text="Ctrl+K",
            bg=self._color("surface_alt_2", "#1A1F2C"),
            fg=self._color("muted", "#64748B"),
            font=(self.mono_font, 9),
            padx=8,
            pady=2,
        ).pack(side="right")

        search_wrap = tk.Frame(self.shell, bg=surface)
        search_wrap.pack(fill="x", pady=(16, 10))
        self.query_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_wrap, textvariable=self.query_var, font=(self.display_font, 13))
        self.search_entry.pack(fill="x", ipady=7, padx=18)

        self.results_container = tk.Frame(self.shell, bg=surface)
        self.results_container.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        self.empty_label = tk.Label(
            self.results_container,
            text="No commands found",
            bg=surface,
            fg=self._color("muted", "#64748B"),
            font=(self.display_font, 11),
        )

        footer = tk.Frame(self.shell, bg=self._color("surface_alt", "#141820"), padx=18, pady=10)
        footer.pack(fill="x", side="bottom")
        tk.Label(
            footer,
            text="Use Up/Down to move, Enter to run, Escape to close",
            bg=self._color("surface_alt", "#141820"),
            fg=self._color("muted", "#64748B"),
            font=(self.mono_font, 9),
        ).pack(side="left")

    def _bind_events(self):
        self.query_var.trace_add("write", lambda *_: self._filter_commands())
        self.bind("<Escape>", self.close)
        self.bind("<Return>", self._run_selected)
        self.bind("<KP_Enter>", self._run_selected)
        self.bind("<Up>", self._select_previous)
        self.bind("<Down>", self._select_next)
        self.search_entry.bind("<Escape>", self.close)
        self.search_entry.bind("<Return>", self._run_selected)
        self.search_entry.bind("<KP_Enter>", self._run_selected)
        self.search_entry.bind("<Up>", self._select_previous)
        self.search_entry.bind("<Down>", self._select_next)
        self.protocol("WM_DELETE_WINDOW", self.close)

    def _focus_search(self):
        if self.winfo_exists():
            self.search_entry.focus_set()
            self.search_entry.selection_range(0, "end")

    def focus_search(self):
        self.lift()
        self._focus_search()

    def _filter_commands(self):
        query = self.query_var.get().strip().lower()
        scored = []

        for index, command in enumerate(self.commands):
            haystack = " ".join([command.label, command.category, command.hint, *command.keywords]).lower()
            label = command.label.lower()
            category = command.category.lower()
            keywords = " ".join(command.keywords).lower()

            if not query:
                score = (3, index)
            elif label.startswith(query):
                score = (0, index)
            elif query in label:
                score = (1, index)
            elif query in keywords or query in category or query in haystack:
                score = (2, index)
            else:
                continue
            scored.append((score, command))

        scored.sort(key=lambda item: item[0])
        self.filtered_commands = [command for _, command in scored[: self.MAX_RESULTS]]
        self.selected_index = 0
        self._render_results()

    def _render_results(self):
        for widget in self.row_widgets:
            widget.destroy()
        self.row_widgets = []
        self.empty_label.pack_forget()

        if not self.filtered_commands:
            self.empty_label.pack(fill="both", expand=True, pady=80)
            return

        for index, command in enumerate(self.filtered_commands):
            row = tk.Frame(self.results_container, bg=self._row_bg(index), padx=12, pady=9)
            row.pack(fill="x", padx=8, pady=2)

            text_frame = tk.Frame(row, bg=self._row_bg(index))
            text_frame.pack(side="left", fill="x", expand=True)

            label = tk.Label(
                text_frame,
                text=command.label,
                bg=self._row_bg(index),
                fg=self._row_fg(index),
                font=(self.display_font, 11),
                anchor="w",
            )
            label.pack(fill="x", anchor="w")

            secondary_text = command.hint or ", ".join(command.keywords[:4])
            meta = tk.Label(
                text_frame,
                text=secondary_text,
                bg=self._row_bg(index),
                fg=self._color("muted", "#64748B"),
                font=(self.mono_font, 8),
                anchor="w",
            )
            meta.pack(fill="x", anchor="w", pady=(2, 0))

            category = tk.Label(
                row,
                text=command.category.upper(),
                bg=self._row_bg(index),
                fg=self._color("primary", "#00E5FF")
                if index == self.selected_index
                else self._color("muted", "#64748B"),
                font=(self.mono_font, 8),
                padx=8,
            )
            category.pack(side="right")

            for widget in (row, text_frame, label, meta, category):
                widget.bind("<Button-1>", lambda _event, idx=index: self._run_index(idx))
                widget.bind("<Enter>", lambda _event, idx=index: self._set_selected(idx))

            self.row_widgets.append(row)

    def _row_bg(self, index):
        if index == self.selected_index:
            return self._color("surface_alt_2", "#1A1F2C")
        return self._color("surface", "#0E1118")

    def _row_fg(self, index):
        if index == self.selected_index:
            return self._color("text", "#E2E8F0")
        return self._color("text", "#E2E8F0")

    def _set_selected(self, index):
        if not self.filtered_commands:
            return
        self.selected_index = max(0, min(index, len(self.filtered_commands) - 1))
        self._render_results()

    def _select_previous(self, _event=None):
        if self.filtered_commands:
            self.selected_index = (self.selected_index - 1) % len(self.filtered_commands)
            self._render_results()
        return "break"

    def _select_next(self, _event=None):
        if self.filtered_commands:
            self.selected_index = (self.selected_index + 1) % len(self.filtered_commands)
            self._render_results()
        return "break"

    def _run_selected(self, _event=None):
        return self._run_index(self.selected_index)

    def _run_index(self, index):
        if not self.filtered_commands:
            return "break"
        command = self.filtered_commands[max(0, min(index, len(self.filtered_commands) - 1))]
        action = command.action
        self.close()
        self.master.after(10, action)
        return "break"

    def close(self, _event=None):
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
        return "break"
