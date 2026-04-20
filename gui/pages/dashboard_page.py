import tkinter as tk
from datetime import datetime, timedelta

import ttkbootstrap as tb

from gui.components.cards import AlertCard, FeedCard, MetricCard
from gui.components.status import StatusPill, status_bootstyle, status_color, status_label, status_sort_key
from gui.gradient_progress import GradientProgressBar


class DashboardPageMixin:
    def create_dashboard_tab(self):
        """Create the command-center dashboard tab."""
        dashboard_tab = tb.Frame(self.notebook, style="CardInner.TFrame")
        self.notebook.add(dashboard_tab, text="Analytics")

        dashboard = tb.Frame(dashboard_tab, style="CardInner.TFrame", padding=(2, 0, 2, 0))
        dashboard.pack(fill="both", expand=True)

        self.create_analytics_dashboard(dashboard)
        self.create_dashboard_alerts_section(dashboard)

        middle = tb.Frame(dashboard, style="CardInner.TFrame")
        middle.pack(fill="both", expand=True, pady=(0, 14))
        middle.columnconfigure(0, weight=5, uniform="dashboard_mid")
        middle.columnconfigure(1, weight=4, uniform="dashboard_mid")
        middle.rowconfigure(0, weight=1)

        fleet_col = tb.Frame(middle, style="CardInner.TFrame", padding=(0, 0, 7, 0))
        activity_col = tb.Frame(middle, style="CardInner.TFrame", padding=(7, 0, 0, 0))
        fleet_col.grid(row=0, column=0, sticky="nsew")
        activity_col.grid(row=0, column=1, sticky="nsew")
        self.create_fleet_health_panel(fleet_col)
        self.create_live_activity_panel(activity_col)

        bottom = tb.Frame(dashboard, style="CardInner.TFrame")
        bottom.pack(fill="both", expand=True)
        bottom.columnconfigure(0, weight=4, uniform="dashboard_bottom")
        bottom.columnconfigure(1, weight=5, uniform="dashboard_bottom")
        bottom.rowconfigure(0, weight=1)

        schedule_col = tb.Frame(bottom, style="CardInner.TFrame", padding=(0, 0, 7, 0))
        events_col = tb.Frame(bottom, style="CardInner.TFrame", padding=(7, 0, 0, 0))
        schedule_col.grid(row=0, column=0, sticky="nsew")
        events_col.grid(row=0, column=1, sticky="nsew")
        self.create_schedule_overview_panel(schedule_col)
        self.create_recent_events_panel(events_col)

        self._refresh_dashboard()

    def create_analytics_dashboard(self, parent):
        """Create top-level KPI cards for the operations dashboard."""
        panel = self._create_card_section(
            parent,
            "Command Center",
            "Current fleet posture, queue readiness, and failure pressure.",
            pady=(0, 12),
        )

        self.dashboard_kpi_labels = {}
        self.dashboard_kpi_sub_labels = {}
        self.dashboard_kpi_cards = {}
        grid = tb.Frame(panel, style="CardInner.TFrame")
        grid.pack(fill="x")

        kpis = [
            ("total_devices", "Total Devices", self.palette["primary"]),
            ("running", "Running", self.palette["success"]),
            ("active", "Active", "#38BDF8"),
            ("inactive", "Offline", self.palette["muted"]),
            ("failures", "Failures", self.palette["danger"]),
            ("queue", "Queue", self.palette["warning"]),
        ]
        for col, (key, title, accent) in enumerate(kpis):
            grid.columnconfigure(col, weight=1, uniform="dashboard_kpis")
            self._build_kpi_card(grid, key, title, accent, col)

    def _build_kpi_card(self, parent, key, title, accent, column):
        card = MetricCard(parent, title, "0", "-", accent=accent, palette=self.palette)
        card.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 5, 0 if column == 5 else 5))
        self.dashboard_kpi_cards[key] = card
        self.dashboard_kpi_labels[key] = card.value_label
        self.dashboard_kpi_sub_labels[key] = card.subtitle_label

    def create_dashboard_alerts_section(self, parent):
        """Create actionable dashboard alerts."""
        panel = self._create_card_section(
            parent,
            "Alerts / Incidents",
            "Operator priorities based on current fleet, queue, schedule, and runtime state.",
            pady=(0, 12),
        )
        self.dashboard_alerts_frame = panel

    def create_fleet_health_panel(self, parent):
        panel = self._create_card_section(
            parent,
            "Fleet Health",
            "Distribution of emulator states across the current fleet.",
            expand=True,
        )
        self.dashboard_fleet_health_frame = panel

    def create_live_activity_panel(self, parent):
        panel = self._create_card_section(
            parent,
            "Live Activity",
            "Devices with active, queued, or recently completed work.",
            expand=True,
        )
        self.dashboard_live_activity_frame = panel

    def create_schedule_overview_panel(self, parent):
        panel = self._create_card_section(
            parent,
            "Schedule Summary",
            "Run window, cadence, and next configured trigger.",
            expand=True,
        )

        header = tb.Frame(panel, style="CardInner.TFrame")
        header.pack(fill="x", pady=(0, 8))
        self.dashboard_schedule_state = StatusPill(
            header,
            "Disabled",
            palette=self.palette,
            font=(self.display_font, 9),
            padx=10,
            pady=4,
        )
        self.dashboard_schedule_state.pack(side="left")

        tb.Label(header, text="Enabled", style="MetricSub.TLabel").pack(side="right")
        self.schedule_enabled_ui = tk.BooleanVar(value=self.schedule_running)
        tb.Checkbutton(
            header,
            variable=self.schedule_enabled_ui,
            command=self._toggle_schedule_from_dashboard,
            bootstyle="success-round-toggle",
        ).pack(side="right", padx=(0, 6))

        self.dashboard_schedule_labels = {}
        rows = tb.Frame(panel, style="CardInner.TFrame")
        rows.pack(fill="x")
        for key, label in (
            ("next_run", "Next Run"),
            ("mode", "Mode"),
            ("repeat", "Repeat"),
            ("days", "Days"),
        ):
            self._build_schedule_summary_row(rows, key, label)

    def _build_schedule_summary_row(self, parent, key, label):
        row = tb.Frame(parent, style="CardInner.TFrame")
        row.pack(fill="x", pady=5)
        tb.Label(row, text=label.upper(), style="MetricLabel.TLabel").pack(side="left")
        value = tb.Label(row, text="-", style="MetricSub.TLabel", anchor="e")
        value.pack(side="right")
        self.dashboard_schedule_labels[key] = value

    def _toggle_schedule_from_dashboard(self):
        if self.schedule_enabled_ui.get() and not self.schedule_running:
            self.start_schedule()
        elif not self.schedule_enabled_ui.get() and self.schedule_running:
            self.stop_schedule()
        self._refresh_dashboard()

    def create_recent_events_panel(self, parent):
        panel = self._create_card_section(
            parent,
            "Recent Important Events",
            "High-signal successes, warnings, failures, and lifecycle changes.",
            expand=True,
        )
        self.dashboard_recent_events_frame = panel

    def _refresh_dashboard(self):
        if not hasattr(self, "dashboard_kpi_labels"):
            return
        self._update_dashboard_kpis()
        self._render_dashboard_alerts(self._compute_dashboard_alerts())
        self._render_fleet_health()
        self._render_live_activity()
        self._render_schedule_summary()
        self._render_recent_events()

    def _update_dashboard_kpis(self):
        kpis = self._compute_dashboard_kpis()
        for key, data in kpis.items():
            card = self.dashboard_kpi_cards.get(key)
            if card:
                card.set(data["value"], data["subtitle"])

    def _compute_dashboard_kpis(self):
        counts = self._get_dashboard_status_counts()
        queue_stats = self._get_dashboard_queue_stats()
        perf = self._get_dashboard_performance_stats()
        total = len(self._ld_snapshot)
        selected = len(self._ld_checked_names)
        known_online = counts["Running"] + counts["Active"]
        success_rate = perf.get("success_rate", 0)
        total_tasks = perf.get("total_tasks", 0)
        failed_samples = perf.get("failed", 0)

        failure_subtitle = "No current attention states"
        if failed_samples:
            failure_subtitle = f"{failed_samples} failed task sample(s)"
        if total_tasks:
            failure_subtitle = f"{success_rate:.0f}% success across {total_tasks} run(s)"

        return {
            "total_devices": {
                "value": total,
                "subtitle": f"{selected} selected / {known_online} online",
            },
            "running": {
                "value": counts["Running"],
                "subtitle": "Executing automation now",
            },
            "active": {
                "value": counts["Active"],
                "subtitle": "ADB online and ready",
            },
            "inactive": {
                "value": counts["Inactive"],
                "subtitle": "Offline or not booted",
            },
            "failures": {
                "value": counts["Failed"],
                "subtitle": failure_subtitle,
            },
            "queue": {
                "value": queue_stats.get("available", 0),
                "subtitle": f"{queue_stats.get('used', 0)} used / {queue_stats.get('total', 0)} total",
            },
        }

    def _get_dashboard_status_counts(self):
        counts = {
            "Running": 0,
            "Active": 0,
            "Inactive": 0,
            "Paused": 0,
            "Completed": 0,
            "Failed": 0,
        }
        known = set(counts) - {"Failed"}
        for name in self._ld_snapshot:
            runtime = self._device_runtime_state.get(name, {})
            runtime_state = str(runtime.get("state", "")).strip().lower()
            status = self._ld_status_cache.get(name, "Inactive")
            if runtime_state in ("attention", "error", "failed"):
                counts["Failed"] += 1
            elif status in known:
                counts[status] += 1
            else:
                counts["Failed"] += 1
        return counts

    def _get_dashboard_queue_stats(self):
        if not hasattr(self, "content_manager"):
            return {"total": 0, "used": 0, "available": 0, "queue_size": 0}
        try:
            stats = self.content_manager.get_queue_stats()
            return {
                "total": int(stats.get("total", 0)),
                "used": int(stats.get("used", 0)),
                "available": int(stats.get("available", 0)),
                "queue_size": int(stats.get("queue_size", stats.get("total", 0))),
            }
        except Exception:
            items = self.content_manager.get_queue_items() if hasattr(self.content_manager, "get_queue_items") else []
            total = len(items)
            used = sum(1 for item in items if item.get("used"))
            return {"total": total, "used": used, "available": total - used, "queue_size": total}

    def _get_dashboard_performance_stats(self):
        if not hasattr(self, "performance_monitor"):
            return {"total_tasks": 0, "success_rate": 0, "completed": 0, "failed": 0}
        try:
            return self.performance_monitor.get_stats()
        except Exception:
            return {"total_tasks": 0, "success_rate": 0, "completed": 0, "failed": 0}

    def _compute_dashboard_alerts(self):
        alerts = []
        counts = self._get_dashboard_status_counts()
        queue_stats = self._get_dashboard_queue_stats()
        running = bool(getattr(self, "running_event", None) and self.running_event.is_set())
        total = len(self._ld_snapshot)

        failure_names = []
        otp_waiting = []
        now = datetime.now()
        for name in self._ld_snapshot:
            status = self._ld_status_cache.get(name, "Inactive")
            runtime = self._device_runtime_state.get(name, {})
            runtime_state = str(runtime.get("state", "")).lower()
            task = str(runtime.get("task", "")).lower()
            if runtime_state in ("attention", "error", "failed") or status not in ("Running", "Active", "Inactive", "Paused", "Completed"):
                failure_names.append(name)
            if "otp" in task or "verification code" in task:
                updated = self._parse_dashboard_timestamp(runtime.get("updated_at") or runtime.get("started_at"))
                if updated and now - updated > timedelta(minutes=6):
                    otp_waiting.append(name)

        if failure_names:
            alerts.append({
                "severity": "critical",
                "title": "Devices need attention",
                "detail": self._format_device_list(failure_names, "runtime issue"),
            })
        if otp_waiting:
            alerts.append({
                "severity": "critical",
                "title": "OTP flow may be stuck",
                "detail": self._format_device_list(otp_waiting, "waiting over 6 min"),
            })
        if running and counts["Inactive"]:
            alerts.append({
                "severity": "warning",
                "title": "Offline devices during active run",
                "detail": f"{counts['Inactive']} inactive device(s) may reduce throughput.",
            })

        no_account = [
            name for name in self._ld_snapshot
            if not self._ld_account_cache.get(name) or self._ld_account_cache.get(name) == "No account"
        ]
        if no_account:
            alerts.append({
                "severity": "warning",
                "title": "Accounts missing",
                "detail": self._format_device_list(no_account, "without assigned account"),
            })

        if bool(getattr(self, "use_content_queue", None) and self.use_content_queue.get()) and queue_stats.get("available", 0) == 0:
            alerts.append({
                "severity": "warning",
                "title": "Content queue empty",
                "detail": "Queue-backed tasks have no available content to consume.",
            })

        if total and not self.schedule_running and not running:
            alerts.append({
                "severity": "info",
                "title": "Schedule is disabled",
                "detail": "Automation will only run manually until scheduling is enabled.",
            })
        elif self.schedule_running:
            summary = self._get_dashboard_schedule_summary()
            alerts.append({
                "severity": "info",
                "title": "Next scheduled run",
                "detail": summary["next_run"],
            })

        return alerts[:5]

    def _parse_dashboard_timestamp(self, value):
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    def _format_device_list(self, names, suffix):
        names = list(names)
        preview = ", ".join(names[:4])
        if len(names) > 4:
            preview = f"{preview} +{len(names) - 4} more"
        return f"{preview} {suffix}."

    def _render_dashboard_alerts(self, alerts):
        self._clear_frame(self.dashboard_alerts_frame)
        if not alerts:
            self._build_empty_state(
                self.dashboard_alerts_frame,
                "All systems normal",
                "No current incidents were detected from fleet, queue, schedule, or runtime state.",
                self.palette["success"],
            )
            return

        for alert in alerts:
            card = AlertCard(
                self.dashboard_alerts_frame,
                alert["severity"],
                alert["title"],
                alert["detail"],
                palette=self.palette,
            )
            card.pack(fill="x", pady=4)

    def _render_fleet_health(self):
        self._clear_frame(self.dashboard_fleet_health_frame)
        counts = self._get_dashboard_status_counts()
        total = max(1, len(self._ld_snapshot))
        rows = [
            ("Running", counts["Running"]),
            ("Active", counts["Active"]),
            ("Inactive", counts["Inactive"]),
            ("Paused", counts["Paused"]),
            ("Completed", counts["Completed"]),
            ("Failed", counts["Failed"]),
        ]

        for status, count in rows:
            label = status_label(status)
            color = status_color(status, self.palette)
            percent = count / total * 100
            row = tb.Frame(self.dashboard_fleet_health_frame, style="CardInner.TFrame")
            row.pack(fill="x", pady=5)
            header = tb.Frame(row, style="CardInner.TFrame")
            header.pack(fill="x")
            tb.Label(header, text=label, style="MetricSub.TLabel").pack(side="left")
            tb.Label(header, text=str(count), style="MetricSub.TLabel", foreground=color).pack(side="right")
            bar = GradientProgressBar(row, bg=self.palette["surface_alt"], color_start=color, color_end=color, height=5)
            bar.pack(fill="x", pady=(3, 0))
            bar.set(percent)

    def _render_live_activity(self):
        self._clear_frame(self.dashboard_live_activity_frame)
        activity = self._get_dashboard_live_activity()
        if not activity:
            self._build_empty_state(
                self.dashboard_live_activity_frame,
                "No active device work",
                "Start automation or select devices to see live runtime state here.",
                self.palette["muted"],
            )
            return

        for item in activity:
            detail = f"{item['task']}  |  {item['progress']}%"
            if item["queue"]:
                detail = f"{item['queue']}  |  {detail}"
            card = FeedCard(
                self.dashboard_live_activity_frame,
                item["name"],
                detail,
                accent=item["accent"],
                palette=self.palette,
            )
            card.pack(fill="x", pady=4)
            StatusPill(
                card.header,
                item["state"],
                palette=self.palette,
                font=(self.display_font, 9),
                padx=8,
                pady=2,
            ).pack(side="right")
            bar = GradientProgressBar(card.body, bg=self.palette["surface_alt"], color_start=item["accent"], color_end=item["accent"], height=4)
            bar.pack(fill="x", pady=(5, 0))
            bar.set(item["progress"])

    def _get_dashboard_live_activity(self):
        priority = {
            "attention": 0,
            "error": 0,
            "failed": 0,
            "running": 1,
            "queued": 2,
            "starting": 3,
            "preparing": 3,
            "waiting": 3,
            "ready": 4,
            "active": 4,
            "completed": 5,
            "idle": 6,
        }
        rows = []
        for name in self._ld_snapshot:
            runtime = self._device_runtime_state.get(name, {})
            state = str(runtime.get("state") or self._ld_status_cache.get(name, "Inactive"))
            task = str(runtime.get("task") or "Waiting for selection")
            if not runtime and state in ("Inactive", "Idle"):
                continue
            if not runtime and state == "Active":
                task = "Device online"
            elif not runtime and state == "Running":
                task = "Automation running"
            if state == "Inactive" and task in ("Waiting for selection", "Waiting for next run"):
                continue
            if state == "Idle" and task in ("Waiting for selection", "Waiting for next run"):
                continue
            progress = self._coerce_progress(runtime.get("progress", 0))
            queue = str(runtime.get("queue_label") or "")
            queue = "" if queue == "-" else queue
            state_key = state.lower()
            rows.append({
                "name": name,
                "state": status_label(state),
                "task": task,
                "progress": progress,
                "queue": queue,
                "accent": status_color(state_key, self.palette),
                "bootstyle": status_bootstyle(state_key),
                "sort": min(priority.get(state_key, 7), status_sort_key(state_key)),
            })
        rows.sort(key=lambda item: (item["sort"], item["name"].lower()))
        return rows[:6]

    def _coerce_progress(self, value):
        try:
            return max(0, min(100, int(float(value))))
        except (TypeError, ValueError):
            return 0

    def _render_schedule_summary(self):
        summary = self._get_dashboard_schedule_summary()
        if hasattr(self, "schedule_enabled_ui"):
            self.schedule_enabled_ui.set(bool(self.schedule_running))
        state_label = getattr(self, "dashboard_schedule_state", None)
        if state_label:
            if self.schedule_running:
                state_label.set_status("Enabled")
            else:
                state_label.set_status("Disabled")
        for key, value in summary.items():
            label = self.dashboard_schedule_labels.get(key)
            if label:
                label.config(text=value)

    def _get_dashboard_schedule_summary(self):
        mode = "Daily" if self.schedule_daily.get() else "Weekly"
        repeat_hours = int(self.schedule_repeat_hours.get())
        repeat = f"Every {repeat_hours}h" if repeat_hours > 0 else "No repeat"
        days = "Every day" if self.schedule_daily.get() else self._format_schedule_days()
        next_run = self._format_next_schedule_run()
        if not self.schedule_running:
            next_run = f"Disabled / {self.schedule_time.get()} configured"
        return {
            "next_run": next_run,
            "mode": mode,
            "repeat": repeat,
            "days": days,
        }

    def _format_schedule_days(self):
        selected = [day[:3] for day, var in self.schedule_days.items() if var.get()]
        return ", ".join(selected) if selected else "No days selected"

    def _format_next_schedule_run(self):
        next_run = self._get_next_schedule_datetime()
        if not next_run:
            return self.schedule_time.get()
        now = datetime.now()
        if next_run.date() == now.date():
            prefix = "Today"
        elif next_run.date() == (now + timedelta(days=1)).date():
            prefix = "Tomorrow"
        else:
            prefix = next_run.strftime("%a")
        return f"{prefix} {next_run.strftime('%H:%M')}"

    def _get_next_schedule_datetime(self):
        try:
            run_time = datetime.strptime(self.schedule_time.get(), "%H:%M").time()
        except ValueError:
            return None

        now = datetime.now()
        if self.schedule_daily.get():
            candidate = datetime.combine(now.date(), run_time)
            if candidate <= now:
                candidate += timedelta(days=1)
            return candidate

        selected_days = {day for day, var in self.schedule_days.items() if var.get()}
        for offset in range(8):
            day = now + timedelta(days=offset)
            if day.strftime("%A") not in selected_days:
                continue
            candidate = datetime.combine(day.date(), run_time)
            if candidate > now:
                return candidate
        return None

    def _render_recent_events(self):
        self._clear_frame(self.dashboard_recent_events_frame)
        events = self._get_dashboard_recent_events()
        if not events:
            self._build_empty_state(
                self.dashboard_recent_events_frame,
                "No important events yet",
                "Warnings, failures, successes, and lifecycle events will appear here.",
                self.palette["muted"],
            )
            return

        for event in events:
            color = self._event_color(event["level"])
            card = FeedCard(
                self.dashboard_recent_events_frame,
                event["time"],
                event["message"],
                accent=color,
                chip_text=event["level"],
                chip_style=self._event_bootstyle(event["level"]),
                palette=self.palette,
                padding=(10, 6),
            )
            card.pack(fill="x", pady=3)

    def _get_dashboard_recent_events(self):
        events = getattr(self, "dashboard_events", [])
        return list(reversed(events[-7:]))

    def _event_color(self, level):
        return {
            "SUCCESS": self.palette["success"],
            "WARNING": self.palette["warning"],
            "ERROR": self.palette["danger"],
            "INFO": self.palette["primary"],
        }.get(level, self.palette["muted"])

    def _event_bootstyle(self, level):
        return {
            "SUCCESS": "success",
            "WARNING": "warning",
            "ERROR": "danger",
            "INFO": "info",
        }.get(level, "secondary")

    def _build_empty_state(self, parent, title, detail, accent):
        severity = "success" if accent == self.palette["success"] else "neutral"
        card = AlertCard(parent, severity, title, detail, palette=self.palette)
        card.pack(fill="x", pady=4)

    def _clear_frame(self, frame):
        for child in frame.winfo_children():
            child.destroy()
