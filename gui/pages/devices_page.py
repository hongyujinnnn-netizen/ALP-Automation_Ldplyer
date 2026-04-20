import tkinter as tk
import ttkbootstrap as tb

from gui.components.cards import MetricCard
from gui.components.status import StatusPill, status_color, status_label, status_table_text, status_tag
from gui.gradient_progress import GradientProgressBar


class DevicesPageMixin:
    def create_devices_tab(self):
        devices_tab = tb.Frame(self.notebook)
        self.notebook.add(devices_tab, text="Devices")

        shell = tb.Frame(devices_tab, style="CardInner.TFrame", padding=(0, 0, 0, 0))
        shell.pack(fill="both", expand=True)

        top = self._create_card_section(
            shell,
            "Device Fleet",
            "All LD instances, group controls, runtime state, and quick actions in one place.",
            pady=(0, 12),
        )
        self._build_devices_hero(top)

        lower = tk.PanedWindow(shell, orient=tk.HORIZONTAL, sashwidth=6, bg=self.palette["surface"])
        lower.pack(fill="both", expand=True)

        left = tb.Frame(lower, style="CardInner.TFrame", padding=(0, 0, 8, 0))
        right = tb.Frame(lower, style="CardInner.TFrame", padding=(8, 0, 0, 0))
        lower.add(left, stretch="always", minsize=540)
        lower.add(right, minsize=320)

        self.create_ld_table_panel(left)
        self._build_devices_table_panel(left)
        self._build_device_group_panel(right)
        self._build_devices_side_panel(right)
        self._render_devices_page()

    def _build_devices_hero(self, parent):
        row = tb.Frame(parent, style="CardInner.TFrame")
        row.pack(fill="x")
        self.device_metric_cards = {}
        metrics = [
            ("selected", "Selected", self.palette["primary"], "Queued for the next run"),
            ("waiting", "Waiting", self.palette["warning"], "Ready but not yet running"),
            ("running", "Running", self.palette["success"], "Devices executing live tasks"),
            ("completed", "Completed", "#38BDF8", "Finished in the current session"),
        ]
        for idx, (key, label, accent, subtitle) in enumerate(metrics):
            card = MetricCard(
                row,
                label,
                "0",
                subtitle,
                accent=accent,
                palette=self.palette,
            )
            card.pack(side="left", fill="both", expand=True, padx=(0, 8 if idx < len(metrics) - 1 else 0))
            self.device_metric_cards[key] = card.value_label

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

        tree.tag_configure("idle", background=self.palette["surface"], foreground=status_color("Idle", self.palette))
        tree.tag_configure("inactive", background=self.palette["surface"], foreground=status_color("Inactive", self.palette))
        tree.tag_configure("active", background="#0A1A20", foreground=status_color("Active", self.palette))
        tree.tag_configure("queued", background="#111827", foreground=status_color("Queued", self.palette))
        tree.tag_configure("running", background="#081C14", foreground=status_color("Running", self.palette))
        tree.tag_configure("attention", background="#1F1720", foreground=status_color("Attention", self.palette))
        tree.tag_configure("completed", background="#0A1420", foreground=status_color("Completed", self.palette))
        tree.tag_configure("paused", background="#160F22", foreground=status_color("Paused", self.palette))

        scroll = tb.Scrollbar(card, orient="vertical", command=tree.yview, style="Vertical.TScrollbar")
        scroll.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(fill="both", expand=True)
        tree.bind("<<TreeviewSelect>>", lambda _e: self._update_device_focus_card())

    def _build_devices_side_panel(self, parent):
        focus = self._create_card_section(
            parent,
            "Focus Device",
            "Detailed view for the clicked or currently active LD.",
            pady=(0, 12),
        )
        self.device_focus_name = tk.Label(focus, text="No device selected", bg=self.palette["surface"], fg=self.palette["text"], font=(self.display_font, 15))
        self.device_focus_name.pack(anchor="w")
        self.device_focus_state = StatusPill(
            focus,
            "Idle",
            palette=self.palette,
            font=(self.mono_font, 9),
            padx=8,
            pady=2,
        )
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

    def _build_device_group_panel(self, parent):
        card = self._create_card_section(
            parent,
            "LD Groups",
            "Create reusable device groups for quick selection and batch actions.",
            pady=(0, 12),
        )

        self.device_group_summary = tk.Label(
            card,
            text="0 groups  |  0 assigned",
            bg=self.palette["surface"],
            fg=self.palette["muted"],
            font=(self.mono_font, 9),
        )
        self.device_group_summary.pack(anchor="w", pady=(0, 8))

        self.device_group_list = tk.Listbox(
            card,
            height=7,
            bg="#030508",
            fg="#c4b5fd",
            selectbackground=self.palette["surface_alt"],
            selectforeground=self.palette["text"],
            relief="flat",
            highlightthickness=0,
            font=(self.mono_font, 10),
            activestyle="none",
        )
        self.device_group_list.pack(fill="x", expand=False)
        self.device_group_list.bind("<<ListboxSelect>>", lambda _e: self._sync_group_filter_from_list())

        actions = tb.Frame(card, style="CardInner.TFrame")
        actions.pack(fill="x", pady=(10, 0))
        tb.Button(actions, text="Create", bootstyle="outline-primary", command=self.create_ld_group, width=10).pack(side="left", padx=(0, 6))
        tb.Button(actions, text="Rename", bootstyle="outline-secondary", command=self.rename_selected_ld_group, width=10).pack(side="left", padx=(0, 6))
        tb.Button(actions, text="Delete", bootstyle="outline-danger", command=self.delete_selected_ld_group, width=10).pack(side="left")

        actions2 = tb.Frame(card, style="CardInner.TFrame")
        actions2.pack(fill="x", pady=(8, 0))
        tb.Button(actions2, text="Assign Selected", bootstyle="info", command=self.assign_selected_to_group, width=16).pack(side="left", padx=(0, 6))
        tb.Button(actions2, text="Select Group", bootstyle="success", command=self.select_active_group_devices, width=14).pack(side="left")

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
            tag = status_tag(row["state"])
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
                values=(row["name"], status_table_text(row["state"]), row["task"], row["timer"], row["target"], row["queue"], row["account"]),
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
        if hasattr(self, "ld_table"):
            selected_item = self.ld_table.get_selected_item()
            if selected_item:
                values = self.ld_table.item(selected_item, "values")
                if values:
                    selected_name = values[0]
        if hasattr(self, "devices_tree"):
            current = self.devices_tree.selection()
            if current and not selected_name:
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
            self.device_focus_state.set_status("Idle")
            self.device_focus_task.config(text="Select LDs from the fleet table to queue them here.")
            self.device_focus_progress.set(0)
            self.device_focus_meta.config(text="Runtime: 00:00  |  Queue: -")
            self.device_focus_ip.config(text="IP: -")
            return

        self.device_focus_name.config(text=focus_row["name"])
        self.device_focus_state.set_status(focus_row["state"], text=status_label(focus_row["state"]))
        self.device_focus_task.config(text=focus_row["task"])
        self.device_focus_progress.set(focus_row["progress"])
        self.device_focus_meta.config(text=f"Runtime: {focus_row['timer']}  |  Queue: {focus_row['queue']}")
        ip_text = focus_row["public_ip"]
        country = focus_row["public_ip_country"]
        if country:
            ip_text = f"{ip_text} ({country})"
        self.device_focus_ip.config(text=f"IP: {ip_text}")
