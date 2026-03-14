"""
gui/dialogs/tools_dialog.py
Tools Center dialog — Quick / Diagnostics / ADB Console tabs.
Author: Bunhong
"""

import tkinter as tk
import ttkbootstrap as tb


class ToolsDialogMixin:

    def show_tools_center(self, section="quick"):
        if hasattr(self, "_tools_center_window") and \
                self._tools_center_window.winfo_exists():
            self._tools_center_window.focus()
            return

        P = self.palette
        win = tk.Toplevel(self.root)
        win.title("Automation Tools Center")
        win.resizable(False, False)
        win.geometry("680x520")
        win.transient(self.root)
        win.grab_set()
        win.configure(bg=P["surface"])
        self._tools_center_window = win

        # ── header ────────────────────────────────────────────────────── #
        hdr = tk.Frame(win, bg=P["surface_alt"],
                       highlightthickness=1,
                       highlightbackground=P["border_alt"])
        hdr.pack(fill="x")

        tk.Label(hdr, text="🔌", bg="#100D04",
                 fg=P["warning"], font=(self.display_font, 14),
                 width=4, pady=14).pack(side="left")
        tk.Label(hdr, text="Tools Center", bg=P["surface_alt"],
                 fg=P["text"], font=(self.display_font, 14)).pack(side="left", padx=(4, 0))
        tk.Label(hdr, text="Quick actions · diagnostics · ADB console",
                 bg=P["surface_alt"], fg=P["muted"],
                 font=(self.mono_font, 9)).pack(side="left", padx=(8, 0))

        # ── tab bar ───────────────────────────────────────────────────── #
        tab_bar = tk.Frame(win, bg=P["surface_alt"],
                           highlightthickness=1, highlightbackground=P["border"])
        tab_bar.pack(fill="x")

        self._tools_panels = {}
        self._tools_tab_btns = {}
        tabs = [("quick", "Quick Actions"), ("diag", "Diagnostics"), ("adb", "ADB Console")]

        tab_btn_frame = tk.Frame(tab_bar, bg=P["surface_alt"])
        tab_btn_frame.pack(fill="x", padx=12)

        for key, label in tabs:
            btn = tk.Button(
                tab_btn_frame, text=label,
                bg=P["surface_alt"], fg=P["muted"],
                activebackground=P["surface_alt"], activeforeground=P["primary"],
                relief="flat", font=(self.display_font, 10),
                padx=16, pady=8, cursor="hand2",
                command=lambda k=key: self._open_tools_tab(k),
            )
            btn.pack(side="left")
            self._tools_tab_btns[key] = btn

        # ── content frame ─────────────────────────────────────────────── #
        content = tk.Frame(win, bg=P["surface"])
        content.pack(fill="both", expand=True)

        # Quick tab
        q = tk.Frame(content, bg=P["surface"], padx=18, pady=16)
        self._tools_panels["quick"] = q

        quick_tools = [
            ("💾", "Create Backup",      "Snapshot current settings and account data",
             P["primary"], self.create_backup),
            ("🔄", "Restore Backup",     "Load a previous configuration snapshot",
             "#A78BFA",   self.restore_backup),
            ("📊", "Performance Report", "Open live metrics & session statistics",
             P["success"], self.show_performance_report),
            ("👤", "Account Manager",   "View and manage linked Facebook accounts",
             P["warning"], self.show_account_manager),
        ]
        for icon, name, desc, color, cmd in quick_tools:
            self._tool_card(q, icon, name, desc, color, cmd)

        # Diagnostics tab
        d = tk.Frame(content, bg=P["surface"], padx=18, pady=16)
        self._tools_panels["diag"] = d

        tk.Label(d, text="SYSTEM INFORMATION", bg=P["surface"],
                 fg=P["muted"], font=(self.display_font, 9)).pack(anchor="w", pady=(0, 8))

        out_frame = tk.Frame(d, bg="#030508",
                             highlightthickness=1, highlightbackground=P["border"])
        out_frame.pack(fill="both", expand=True, pady=(0, 10))

        self.system_info_text = tk.Text(
            out_frame, wrap="word", height=14,
            bg="#030508", fg="#7dd3fc",
            font=(self.mono_font, 10), relief="flat",
            insertbackground=P["primary"], highlightthickness=0,
            padx=12, pady=10,
        )
        self.system_info_text.pack(fill="both", expand=True)

        self._tool_row_btn(d, "↺ Refresh System Info", P["primary"],
                           self._refresh_system_info_tree)

        # ADB tab
        a = tk.Frame(content, bg=P["surface"], padx=18, pady=16)
        self._tools_panels["adb"] = a

        tk.Label(a, text="ADB COMMAND CONSOLE", bg=P["surface"],
                 fg=P["muted"], font=(self.display_font, 9)).pack(anchor="w", pady=(0, 8))

        cmd_row = tk.Frame(a, bg=P["surface"])
        cmd_row.pack(fill="x", pady=(0, 8))

        self.adb_command_var = tk.StringVar(value="adb devices")
        inp_frame = tk.Frame(cmd_row, bg=P["surface_alt"],
                             highlightthickness=1, highlightbackground=P["border_alt"])
        inp_frame.pack(side="left", fill="x", expand=True, padx=(0, 8))
        tk.Entry(inp_frame, textvariable=self.adb_command_var,
                 bg=P["surface_alt"], fg=P["text"],
                 insertbackground=P["primary"], relief="flat",
                 font=(self.mono_font, 11), highlightthickness=0,
                 pady=7, padx=10).pack(fill="x")

        run_f = tk.Frame(cmd_row, bg=P["primary"], padx=1, pady=1)
        run_f.pack(side="right")
        tk.Button(run_f, text="Run ›", bg=P["surface_alt"], fg=P["primary"],
                  activebackground=P["surface"], activeforeground=P["primary"],
                  relief="flat", font=(self.mono_font, 11), padx=14, pady=5,
                  cursor="hand2",
                  command=self._run_custom_adb_command).pack()

        # quick-fire preset buttons
        preset_row = tk.Frame(a, bg=P["surface"])
        preset_row.pack(fill="x", pady=(0, 8))
        for preset in ("adb devices", "adb shell getprop ro.build.version.release",
                       "adb kill-server"):
            short = preset.split()[-1]
            f = tk.Frame(preset_row, bg=P["border"], padx=1, pady=1)
            f.pack(side="left", padx=(0, 6))
            tk.Button(f, text=short, bg=P["surface_alt"], fg=P["muted"],
                      activebackground=P["surface"], activeforeground=P["text"],
                      relief="flat", font=(self.mono_font, 9),
                      padx=8, pady=4, cursor="hand2",
                      command=lambda p=preset: self.adb_command_var.set(p)).pack()

        out_frame2 = tk.Frame(a, bg="#030508",
                              highlightthickness=1, highlightbackground=P["border"])
        out_frame2.pack(fill="both", expand=True)

        self.adb_output = tk.Text(
            out_frame2, wrap="word", height=10,
            bg="#030508", fg="#7dd3fc",
            font=(self.mono_font, 10), relief="flat",
            insertbackground=P["primary"], highlightthickness=0,
            padx=12, pady=10,
        )
        self.adb_output.insert("end", "// output will appear here\n")
        self.adb_output.pack(fill="both", expand=True)

        # ── footer ────────────────────────────────────────────────────── #
        foot = tk.Frame(win, bg=P["surface_alt"],
                        highlightthickness=1, highlightbackground=P["border"])
        foot.pack(fill="x", side="bottom")
        fp = tk.Frame(foot, bg=P["surface_alt"], padx=16, pady=12)
        fp.pack(fill="x")

        f = tk.Frame(fp, bg=P["border"], padx=1, pady=1)
        f.pack(side="left", padx=4)
        tk.Button(f, text="Close", bg=P["surface_alt"], fg=P["muted"],
                  activebackground=P["surface"], activeforeground=P["text"],
                  relief="flat", font=(self.mono_font, 10),
                  padx=14, pady=5, cursor="hand2",
                  command=win.destroy).pack()

        self._open_tools_tab(section)

    # ── helpers ───────────────────────────────────────────────────────── #

    def _tool_card(self, parent, icon, name, desc, color, command):
        P = self.palette
        card = tk.Frame(parent, bg=P["surface_alt"],
                        highlightthickness=1, highlightbackground=P["border"],
                        cursor="hand2")
        card.pack(fill="x", pady=5)

        def on_enter(e):  card.config(highlightbackground=P["border_alt"])
        def on_leave(e):  card.config(highlightbackground=P["border"])
        card.bind("<Enter>", on_enter)
        card.bind("<Leave>", on_leave)
        card.bind("<Button-1>", lambda e: command())

        inner = tk.Frame(card, bg=P["surface_alt"], padx=14, pady=12)
        inner.pack(fill="x")
        inner.bind("<Button-1>", lambda e: command())

        # icon pill
        ico_bg = tk.Frame(inner, bg=P["surface3"] if hasattr(P, "surface3")
                          else P["surface_alt"])
        ico_bg.pack(side="left", padx=(0, 12))
        tk.Label(ico_bg, text=icon, bg=P["surface_alt"],
                 fg=color, font=(self.display_font, 18),
                 width=3, pady=4).pack()

        info = tk.Frame(inner, bg=P["surface_alt"])
        info.pack(side="left", fill="x", expand=True)
        info.bind("<Button-1>", lambda e: command())

        tk.Label(info, text=name, bg=P["surface_alt"],
                 fg=P["text"], font=(self.display_font, 11),
                 anchor="w").pack(fill="x")
        tk.Label(info, text=desc, bg=P["surface_alt"],
                 fg=P["muted"], font=(self.mono_font, 9),
                 anchor="w").pack(fill="x")

        tk.Label(inner, text="›", bg=P["surface_alt"],
                 fg=P["border_alt"], font=(self.display_font, 16)).pack(side="right")

    def _tool_row_btn(self, parent, text, color, command):
        P = self.palette
        f = tk.Frame(parent, bg=color, padx=1, pady=1)
        f.pack(fill="x", pady=(0, 4))
        tk.Button(f, text=text, bg=P["surface_alt"], fg=color,
                  activebackground=P["surface"], activeforeground=color,
                  relief="flat", font=(self.mono_font, 10),
                  pady=7, cursor="hand2", command=command).pack(fill="x")

    def _open_tools_tab(self, key):
        P = self.palette
        for k, panel in self._tools_panels.items():
            panel.pack_forget()
        self._tools_panels[key].pack(fill="both", expand=True)
        for k, btn in self._tools_tab_btns.items():
            if k == key:
                btn.config(fg=P["primary"],
                           highlightthickness=1, highlightbackground=P["primary"],
                           highlightcolor=P["primary"])
            else:
                btn.config(fg=P["muted"], highlightthickness=0)

    def _refresh_system_info_tree(self):
        if not hasattr(self, "system_info_text"):
            return
        try:
            import platform, sys, psutil
            info = {
                "platform":    platform.system() + " " + platform.release(),
                "python":      sys.version.split()[0],
                "cpu_cores":   psutil.cpu_count(logical=False),
                "cpu_threads": psutil.cpu_count(logical=True),
                "ram_total":   f"{psutil.virtual_memory().total / 1e9:.1f} GB",
                "ram_avail":   f"{psutil.virtual_memory().available / 1e9:.1f} GB",
                "disk_free":   f"{psutil.disk_usage('/').free / 1e9:.1f} GB",
            }
            try:
                extra = self.performance_monitor.get_stats()
                info.update(extra)
            except Exception:
                pass

            self.system_info_text.config(state="normal")
            self.system_info_text.delete("1.0", "end")
            for k, v in info.items():
                self.system_info_text.insert("end", f"{k:<16} {v}\n")
            self.system_info_text.config(state="disabled")
        except Exception as exc:
            self.log(f"System info refresh failed: {exc}", "ERROR")

    def _run_custom_adb_command(self):
        cmd_str = getattr(self, "adb_command_var", None)
        if cmd_str is None:
            return
        try:
            output = self.emulator.run_adb_command(cmd_str.get())
        except Exception as exc:
            output = f"ADB error: {exc}"
        self._append_adb_output(f"$ {cmd_str.get()}\n{output}")

    def _append_adb_output(self, text):
        if not hasattr(self, "adb_output"):
            return
        self.adb_output.config(state="normal")
        self.adb_output.insert("end", text + "\n")
        self.adb_output.see("end")
        self.adb_output.config(state="disabled")

    # compat stubs
    def _build_tools_quick_tab(self, parent):      pass
    def _build_tools_diagnostics_tab(self, parent): pass
    def _build_tools_adb_tab(self, parent):        pass
    def _create_tool_card(self, parent, title, desc, command,
                          icon="", style="info"):
        return self._tool_card(parent, icon, title, desc,
                               self.palette["primary"], command)

    def show_system_info(self):
        self.show_tools_center("diag")
        self._refresh_system_info_tree()
