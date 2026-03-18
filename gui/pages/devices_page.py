import tkinter as tk
import ttkbootstrap as tb

from gui.gradient_progress import GradientProgressBar


class DevicesPageMixin:
    def create_devices_tab(self):
        devices_tab = tb.Frame(self.notebook)
        self.notebook.add(devices_tab, text="Devices")

        shell = tb.Frame(devices_tab, style="CardInner.TFrame", padding=(0, 0, 0, 0))
        shell.pack(fill="both", expand=True)

        top = self._create_card_section(
            shell,
            "Device Operations",
            "Live task state, selected queue, and focus detail for every LD in the current run.",
            pady=(0, 12),
        )
        self._build_devices_hero(top)

        lower = tk.PanedWindow(shell, orient=tk.HORIZONTAL, sashwidth=6, bg=self.palette["surface"])
        lower.pack(fill="both", expand=True)

        left = tb.Frame(lower, style="CardInner.TFrame", padding=(0, 0, 8, 0))
        right = tb.Frame(lower, style="CardInner.TFrame", padding=(8, 0, 0, 0))
        lower.add(left, stretch="always", minsize=540)
        lower.add(right, minsize=320)

        self._build_devices_table_panel(left)
        self._build_devices_side_panel(right)
        self._render_devices_page()

    def _build_devices_hero(self, parent):
        row = tk.Frame(parent, bg=self.palette["surface"])
        row.pack(fill="x")
        self.device_metric_cards = {}
        metrics = [
            ("selected", "Selected", self.palette["primary"], "Queued for the next run"),
            ("waiting", "Waiting", self.palette["warning"], "Ready but not yet running"),
            ("running", "Running", self.palette["success"], "Devices executing live tasks"),
            ("completed", "Completed", "#38BDF8", "Finished in the current session"),
        ]
        for idx, (key, label, accent, subtitle) in enumerate(metrics):
            card = tk.Frame(
                row,
                bg=self.palette["surface_alt"],
                highlightthickness=1,
                highlightbackground=self.palette["border"],
                padx=14,
                pady=12,
            )
            card.pack(side="left", fill="both", expand=True, padx=(0, 8 if idx < len(metrics) - 1 else 0))
            tk.Frame(card, bg=accent, height=3).pack(fill="x", pady=(0, 10))
            tk.Label(card, text=label.upper(), bg=self.palette["surface_alt"], fg=self.palette["muted"], font=(self.mono_font, 8)).pack(anchor="w")
            value = tk.Label(card, text="0", bg=self.palette["surface_alt"], fg=accent, font=(self.display_font, 20))
            value.pack(anchor="w", pady=(4, 0))
            tk.Label(card, text=subtitle, bg=self.palette["surface_alt"], fg=self.palette["muted"], font=(self.mono_font, 8)).pack(anchor="w", pady=(2, 0))
            self.device_metric_cards[key] = value

    def _build_devices_table_panel(self, parent):
        card = self._create_card_section(
            parent,
            "Fleet Timeline",
            "Each LD shows current task, timer, target session, and queue position.",
            expand=True,
            pady=(0, 0),
        )

        columns = ("device", "state", "task", "timer", "target", "queue", "account")
        tree = tb.Treeview(card, columns=columns, show="headings", height=14, style="Custom.Treeview")
        self.devices_tree = tree

        config = {
            "device": ("LD Device", 130),
            "state": ("State", 90),
            "task": ("Current Task", 170),
            "timer": ("Run Time", 90),
            "target": ("Target", 90),
            "queue": ("Queue", 70),
            "account": ("Account", 150),
        }
        for key, (title, width) in config.items():
            tree.heading(key, text=title, anchor="w")
            tree.column(key, width=width, anchor="w")

        tree.tag_configure("idle", background=self.palette["surface"], foreground=self.palette["muted"])
        tree.tag_configure("queued", background="#111827", foreground="#FCD34D")
        tree.tag_configure("running", background="#081C14", foreground="#6EE7B7")
        tree.tag_configure("attention", background="#1F1720", foreground="#FCA5A5")
        tree.tag_configure("completed", background="#0A1420", foreground="#93C5FD")

        scroll = tb.Scrollbar(card, orient="vertical", command=tree.yview, style="Vertical.TScrollbar")
        scroll.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(fill="both", expand=True)
        tree.bind("<<TreeviewSelect>>", lambda _e: self._update_device_focus_card())

    def _build_devices_side_panel(self, parent):
        focus = self._create_card_section(
            parent,
            "Focus Device",
            "Detailed view for the currently active or selected LD.",
            pady=(0, 12),
        )
        self.device_focus_name = tk.Label(focus, text="No device selected", bg=self.palette["surface"], fg=self.palette["text"], font=(self.display_font, 15))
        self.device_focus_name.pack(anchor="w")
        self.device_focus_state = tk.Label(focus, text="Idle", bg=self.palette["surface"], fg=self.palette["muted"], font=(self.mono_font, 9))
        self.device_focus_state.pack(anchor="w", pady=(4, 0))
        self.device_focus_task = tk.Label(focus, text="Waiting for selection", bg=self.palette["surface"], fg=self.palette["text"], font=(self.mono_font, 10), wraplength=280, justify="left")
        self.device_focus_task.pack(anchor="w", pady=(12, 8))
        self.device_focus_progress = GradientProgressBar(
            focus,
            bg=self.palette["surface_alt"],
            color_start=self.palette["primary"],
            color_end=self.palette["secondary"],
            height=7,
        )
        self.device_focus_progress.pack(fill="x", pady=(0, 8))
        self.device_focus_meta = tk.Label(focus, text="Runtime: 00:00  |  Queue: -", bg=self.palette["surface"], fg=self.palette["muted"], font=(self.mono_font, 9))
        self.device_focus_meta.pack(anchor="w")
        self.device_focus_ip = tk.Label(focus, text="IP: -", bg=self.palette["surface"], fg=self.palette["muted"], font=(self.mono_font, 9))
        self.device_focus_ip.pack(anchor="w", pady=(6, 0))

        queue_card = self._create_card_section(
            parent,
            "Selected Queue",
            "LDs selected in the main fleet table and waiting for the next automation batch.",
            expand=True,
            pady=(0, 0),
        )
        self.devices_waiting_list = tk.Listbox(
            queue_card,
            bg="#030508",
            fg="#7dd3fc",
            selectbackground=self.palette["surface_alt"],
            selectforeground=self.palette["text"],
            relief="flat",
            highlightthickness=0,
            font=(self.mono_font, 10),
            activestyle="none",
        )
        self.devices_waiting_list.pack(fill="both", expand=True)

    def _device_page_rows(self):
        names = set(getattr(self, "_ld_snapshot", {}).keys())
        names.update(getattr(self, "_device_runtime_state", {}).keys())
        rows = []
        for name in sorted(names):
            runtime = self._device_runtime_state.get(name, {})
            account = self._ld_account_cache.get(name, "No account")
            selected = name in getattr(self, "_ld_checked_names", set())
            state = runtime.get("state") or ("Queued" if selected and not self.running_event.is_set() else self._ld_status_cache.get(name, "Idle"))
            task = runtime.get("task") or ("Waiting for batch" if selected else "Idle")
            timer = self._device_elapsed_text(name)
            target = f"{self.task_duration.get()} min"
            queue = runtime.get("queue_label") or ("Selected" if selected else "-")
            rows.append({
                "name": name,
                "state": state,
                "task": task,
                "timer": timer,
                "target": target,
                "queue": queue,
                "account": account,
                "selected": selected,
                "progress": runtime.get("progress", 0),
                "public_ip": runtime.get("public_ip") or "-",
                "public_ip_country": runtime.get("public_ip_country") or "",
            })
        return rows

    def _device_elapsed_text(self, name):
        runtime = self._device_runtime_state.get(name, {})
        started_at = runtime.get("started_task_at") or runtime.get("started_at")
        if not started_at:
            return "00:00"
        try:
            from datetime import datetime
            started = datetime.fromisoformat(started_at)
            elapsed = max(0, int((datetime.now() - started).total_seconds()))
            minutes, seconds = divmod(elapsed, 60)
            hours, minutes = divmod(minutes, 60)
            return f"{hours:02}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"
        except Exception:
            return "00:00"

    def _render_devices_page(self):
        if not hasattr(self, "devices_tree"):
            return
        rows = self._device_page_rows()
        for item in self.devices_tree.get_children():
            self.devices_tree.delete(item)
        selected_count = waiting_count = running_count = completed_count = 0
        for row in rows:
            state_lower = row["state"].lower()
            tag = "idle"
            if "running" in state_lower:
                tag = "running"
                running_count += 1
            elif "queued" in state_lower or "waiting" in state_lower or row["selected"]:
                tag = "queued"
                waiting_count += 1
            elif "completed" in state_lower or "idle" in state_lower:
                tag = "completed" if "completed" in state_lower else "idle"
                if "completed" in state_lower:
                    completed_count += 1
            elif "attention" in state_lower or "timeout" in state_lower:
                tag = "attention"
            if row["selected"]:
                selected_count += 1
            self.devices_tree.insert(
                "",
                "end",
                values=(row["name"], row["state"], row["task"], row["timer"], row["target"], row["queue"], row["account"]),
                tags=(tag,),
            )

        if hasattr(self, "device_metric_cards"):
            self.device_metric_cards["selected"].config(text=str(selected_count))
            self.device_metric_cards["waiting"].config(text=str(waiting_count))
            self.device_metric_cards["running"].config(text=str(running_count))
            self.device_metric_cards["completed"].config(text=str(completed_count))

        if hasattr(self, "devices_waiting_list"):
            self.devices_waiting_list.delete(0, "end")
            waiting_rows = [row for row in rows if row["selected"] and row["state"].lower() not in ("running",)]
            if waiting_rows:
                for row in waiting_rows:
                    self.devices_waiting_list.insert("end", f"{row['name']}  |  {row['task']}")
            else:
                self.devices_waiting_list.insert("end", "No selected LD waiting for a task.")

        self._update_device_focus_card(rows)

    def _update_device_focus_card(self, rows=None):
        if not hasattr(self, "device_focus_name"):
            return
        rows = rows or self._device_page_rows()
        selected_name = None
        if hasattr(self, "devices_tree"):
            current = self.devices_tree.selection()
            if current:
                values = self.devices_tree.item(current[0], "values")
                if values:
                    selected_name = values[0]
        focus_row = None
        if selected_name:
            focus_row = next((row for row in rows if row["name"] == selected_name), None)
        if focus_row is None:
            focus_row = next((row for row in rows if row["state"].lower() == "running"), None)
        if focus_row is None and rows:
            focus_row = rows[0]
        if focus_row is None:
            self.device_focus_name.config(text="No device selected")
            self.device_focus_state.config(text="Idle", fg=self.palette["muted"])
            self.device_focus_task.config(text="Select LDs from the fleet table to queue them here.")
            self.device_focus_progress.set(0)
            self.device_focus_meta.config(text="Runtime: 00:00  |  Queue: -")
            self.device_focus_ip.config(text="IP: -")
            return

        accent = self.palette["primary"]
        state_lower = focus_row["state"].lower()
        if "running" in state_lower:
            accent = self.palette["success"]
        elif "queued" in state_lower or "waiting" in state_lower:
            accent = self.palette["warning"]
        elif "attention" in state_lower:
            accent = self.palette["danger"]
        self.device_focus_name.config(text=focus_row["name"])
        self.device_focus_state.config(text=focus_row["state"], fg=accent)
        self.device_focus_task.config(text=focus_row["task"])
        self.device_focus_progress.set(focus_row["progress"])
        self.device_focus_meta.config(text=f"Runtime: {focus_row['timer']}  |  Queue: {focus_row['queue']}")
        ip_text = focus_row["public_ip"]
        country = focus_row["public_ip_country"]
        if country:
            ip_text = f"{ip_text} ({country})"
        self.device_focus_ip.config(text=f"IP: {ip_text}")
