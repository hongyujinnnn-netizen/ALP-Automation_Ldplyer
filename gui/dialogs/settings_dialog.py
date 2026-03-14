"""
gui/dialogs/settings_dialog.py
Settings dialog — cyber dark aesthetic with spinboxes and toggle rows.
Author: Bunhong
"""

import tkinter as tk
import ttkbootstrap as tb


class SettingsDialogMixin:

    def show_settings_dialog(self):
        if hasattr(self, "_settings_dialog") and self._settings_dialog.winfo_exists():
            self._settings_dialog.focus()
            return

        P = self.palette
        dialog = tk.Toplevel(self.root)
        dialog.title("Settings")
        dialog.resizable(False, False)
        dialog.geometry("580x500")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg=P["surface"])
        self._settings_dialog = dialog

        # local copies so Cancel discards changes
        parallel_var       = tk.IntVar(value=self.parallel_ld.get())
        boot_delay_var     = tk.IntVar(value=self.boot_delay.get())
        task_duration_var  = tk.IntVar(value=self.task_duration.get())
        max_videos_var     = tk.IntVar(value=self.max_videos.get())
        start_same_var     = tk.BooleanVar(value=self.start_same_time.get())
        use_queue_var      = tk.BooleanVar(value=self.use_content_queue.get())

        # ── header ────────────────────────────────────────────────────── #
        hdr = tk.Frame(dialog, bg=P["surface_alt"],
                       highlightthickness=1,
                       highlightbackground=P["border_alt"])
        hdr.pack(fill="x")

        icon_lbl = tk.Label(hdr, text="⚙", bg="#071820",
                            fg=P["primary"], font=(self.display_font, 14),
                            width=4, pady=14)
        icon_lbl.pack(side="left")

        tk.Label(hdr, text="Settings", bg=P["surface_alt"],
                 fg=P["text"], font=(self.display_font, 14)).pack(side="left", padx=(4, 0))
        tk.Label(hdr, text="Automation configuration & persistence",
                 bg=P["surface_alt"], fg=P["muted"],
                 font=(self.mono_font, 9)).pack(side="left", padx=(8, 0))

        # ── body ──────────────────────────────────────────────────────── #
        body = tk.Frame(dialog, bg=P["surface"], padx=20, pady=16)
        body.pack(fill="both", expand=True)

        # section label
        def sec_label(parent, text):
            tk.Label(parent, text=text, bg=P["surface"],
                     fg=P["muted"], font=(self.display_font, 9)).pack(
                anchor="w", pady=(0, 8))

        # spinbox group helper
        def spin_group(parent, label, var, from_, to, row, col):
            cell = tk.Frame(parent, bg=P["surface"])
            cell.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")

            tk.Label(cell, text=label.upper(), bg=P["surface"],
                     fg=P["muted"], font=(self.mono_font, 8)).pack(anchor="w")

            wrap = tk.Frame(cell, bg=P["surface_alt"],
                            highlightthickness=1,
                            highlightbackground=P["border_alt"])
            wrap.pack(fill="x", pady=(4, 0))

            def dec():
                v = var.get()
                if v > from_: var.set(v - 1)
            def inc():
                v = var.get()
                if v < to: var.set(v + 1)

            tk.Button(wrap, text="−", bg=P["surface_alt"], fg=P["muted"],
                      relief="flat", font=(self.display_font, 13),
                      activebackground=P["border"], activeforeground=P["primary"],
                      command=dec, width=2, cursor="hand2").pack(side="left")

            tk.Label(wrap, textvariable=var, bg=P["surface_alt"],
                     fg=P["text"], font=(self.mono_font, 11),
                     width=4, anchor="center").pack(side="left", fill="x", expand=True)

            tk.Button(wrap, text="+", bg=P["surface_alt"], fg=P["muted"],
                      relief="flat", font=(self.display_font, 13),
                      activebackground=P["border"], activeforeground=P["primary"],
                      command=inc, width=2, cursor="hand2").pack(side="right")

        sec_label(body, "CORE PARAMETERS")

        grid = tk.Frame(body, bg=P["surface"])
        grid.pack(fill="x", pady=(0, 16))
        for i in range(2):
            grid.columnconfigure(i, weight=1)

        spin_group(grid, "Parallel LDs",      parallel_var,      1, 10,  0, 0)
        spin_group(grid, "Boot Delay (s)",    boot_delay_var,    0, 60,  0, 1)
        spin_group(grid, "Task Duration (min)", task_duration_var, 1, 240, 1, 0)
        spin_group(grid, "Max Reels",         max_videos_var,    1, 50,  1, 1)

        # divider
        tk.Frame(body, bg=P["border"], height=1).pack(fill="x", pady=(0, 14))

        sec_label(body, "BEHAVIOR FLAGS")

        def toggle_row(parent, text, sub, var):
            row = tk.Frame(parent, bg=P["surface_alt"],
                           highlightthickness=1, highlightbackground=P["border"])
            row.pack(fill="x", pady=4)
            row.configure(cursor="hand2")

            info = tk.Frame(row, bg=P["surface_alt"], padx=12, pady=10)
            info.pack(side="left", fill="both", expand=True)
            tk.Label(info, text=text, bg=P["surface_alt"],
                     fg=P["text"], font=(self.display_font, 10)).pack(anchor="w")
            tk.Label(info, text=sub, bg=P["surface_alt"],
                     fg=P["muted"], font=(self.mono_font, 8)).pack(anchor="w")

            # pill canvas
            pill_c = tk.Canvas(row, width=40, height=22, bg=P["surface_alt"],
                               highlightthickness=0)
            pill_c.pack(side="right", padx=12)

            def redraw(*_):
                pill_c.delete("all")
                on = var.get()
                bg_col = P["primary"] if on else P["border"]
                pill_c.create_rounded_rect = None  # workaround
                pill_c.create_oval(0, 2, 22, 20, fill=bg_col, outline="")
                pill_c.create_oval(18, 2, 40, 20, fill=bg_col, outline="")
                pill_c.create_rectangle(11, 2, 29, 20, fill=bg_col, outline="")
                thumb_x = 26 if on else 10
                thumb_col = "#030608" if on else P["muted"]
                pill_c.create_oval(thumb_x-8, 3, thumb_x+8, 19,
                                   fill=thumb_col, outline="")

            var.trace_add("write", redraw)
            redraw()

            def toggle(e=None):
                var.set(not var.get())

            for w in (row, info, pill_c):
                w.bind("<Button-1>", toggle)

        toggle_row(body, "Start all devices simultaneously",
                   "Launch all selected LDs at the same moment", start_same_var)
        toggle_row(body, "Use content queue",
                   "Feed videos from managed queue list", use_queue_var)

        # ── footer ────────────────────────────────────────────────────── #
        foot = tk.Frame(dialog, bg=P["surface_alt"],
                        highlightthickness=1, highlightbackground=P["border"])
        foot.pack(fill="x", side="bottom")

        fp = tk.Frame(foot, bg=P["surface_alt"], padx=16, pady=12)
        fp.pack(fill="x")

        def save_and_close():
            try:
                self.parallel_ld.set(parallel_var.get())
                self.boot_delay.set(boot_delay_var.get())
                self.task_duration.set(task_duration_var.get())
                self.max_videos.set(max_videos_var.get())
                self.start_same_time.set(start_same_var.get())
                self.use_content_queue.set(use_queue_var.get())
                self.save_settings()
                self.log("Settings saved", "SUCCESS")
                dialog.destroy()
            except Exception as exc:
                self.log(f"Failed to save settings: {exc}", "ERROR")
                tb.Messagebox.show_error(f"Error: {exc}", "Save Failed")

        def _btn(parent, text, fg, border_col, command, side="right"):
            f = tk.Frame(parent, bg=border_col, padx=1, pady=1)
            f.pack(side=side, padx=4)
            b = tk.Button(f, text=text, bg=P["surface_alt"], fg=fg,
                          activebackground=P["surface"],
                          activeforeground=fg,
                          relief="flat", font=(self.mono_font, 10),
                          padx=14, pady=6, cursor="hand2",
                          command=command)
            b.pack()

        _btn(fp, "Save Settings", P["primary"], P["primary"], save_and_close)
        _btn(fp, "Cancel", P["muted"], P["border"], dialog.destroy)
