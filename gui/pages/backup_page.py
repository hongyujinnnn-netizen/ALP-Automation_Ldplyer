import os
import tkinter as tk
import zipfile
from datetime import datetime
from pathlib import Path
from tkinter import filedialog
from tkinter import messagebox as MessageBox

import ttkbootstrap as tb

from gui.components.scrollable_frame import ScrollableFrame
from gui.components.state_views import StateView

# ── Local palette accents (independent of Analytics/Devices look) ──────── #
_VAULT_INDIGO = "#6366F1"
_VAULT_TEAL = "#14B8A6"
_VAULT_AMBER = "#F59E0B"
_VAULT_ROSE = "#F43F5E"
_VAULT_VIOLET = "#A855F7"
_VAULT_SKY = "#38BDF8"


class BackupPageMixin:
    # ─────────────────────────────────────────────────────────────────── #
    # Entry points

    def create_backup_hub_tab(self):
        tab = tb.Frame(self.notebook, style="CardInner.TFrame")
        self.notebook.add(tab, text="Backups")
        self._backup_host = tab
        self._build_backup_surface(tab)
        self._refresh_backup_page()

    def show_backup_manager(self):
        if hasattr(self, "notebook"):
            try:
                self.notebook.select(5)
                self._on_notebook_tab_changed()
                self.request_backup_refresh()
                return
            except Exception:
                pass

    def request_backup_refresh(self):
        if hasattr(self, "_refresh_backup_page"):
            self._refresh_backup_page()

    def create_color_button(
        self,
        parent,
        *,
        text,
        command,
        base_color,
        hover_color,
        active_color=None,
        text_color="#FFFFFF",
        font=None,
        padx=12,
        pady=6,
        cursor="hand2",
    ):
        """Create a reusable colored button with immediate base styling and smooth hover."""
        resolved_font = font or (self.mono_font, 9, "bold")
        pressed_color = active_color or hover_color
        button = tk.Button(
            parent,
            text=text,
            command=command,
            bg=base_color,
            fg=text_color,
            activebackground=pressed_color,
            activeforeground=text_color,
            disabledforeground=text_color,
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=padx,
            pady=pady,
            cursor=cursor,
            font=resolved_font,
        )
        button.configure(bg=base_color, activebackground=pressed_color)

        def _apply_background(color):
            if button.winfo_exists():
                button.configure(bg=color, activebackground=pressed_color)

        button.bind("<Enter>", lambda _event: _apply_background(hover_color), add="+")
        button.bind("<Leave>", lambda _event: _apply_background(base_color), add="+")
        return button

    # ─────────────────────────────────────────────────────────────────── #
    # Layout

    def _build_backup_surface(self, parent):
        self._backup_include_logs = tk.BooleanVar(value=True)
        self._backup_include_content = tk.BooleanVar(value=True)
        self._backup_selected_path = None
        self._backup_timeline_rows = {}

        scroller = ScrollableFrame(parent, bg=self.palette["surface"])
        scroller.pack(fill="both", expand=True, padx=2)
        body = scroller.body

        # Hero banner — custom, no SectionCard
        self._build_hero_banner(body)

        # Two-column middle row: Timeline + Vault meters
        middle = tb.Frame(body, style="CardInner.TFrame")
        middle.pack(fill="both", expand=True, pady=(12, 12))
        middle.columnconfigure(0, weight=6, uniform="vault_mid")
        middle.columnconfigure(1, weight=4, uniform="vault_mid")

        timeline_col = tb.Frame(middle, style="CardInner.TFrame")
        timeline_col.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        meter_col = tb.Frame(middle, style="CardInner.TFrame")
        meter_col.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        self._build_timeline_panel(timeline_col)
        self._build_vault_meters(meter_col)

        # Archive inspector — full-width bottom
        self._build_archive_inspector(body)

    # ─────────────────────────────────────────────────────────────────── #
    # Hero banner

    def _build_hero_banner(self, parent):
        shell = tk.Frame(
            parent,
            bg=self.palette["surface_alt"],
            highlightthickness=0,
            bd=0,
        )
        shell.pack(fill="x")
        # accent stripe on the left edge
        self._hero_accent = tk.Frame(shell, bg=_VAULT_INDIGO, width=5)
        self._hero_accent.pack(side="left", fill="y")

        inner = tk.Frame(shell, bg=self.palette["surface_alt"], padx=22, pady=20)
        inner.pack(side="left", fill="both", expand=True)

        # Left: title + status
        left = tk.Frame(inner, bg=self.palette["surface_alt"])
        left.pack(side="left", fill="x", expand=True)

        title_row = tk.Frame(left, bg=self.palette["surface_alt"])
        title_row.pack(anchor="w")
        tk.Label(
            title_row,
            text="◆ BACKUP VAULT",
            bg=self.palette["surface_alt"],
            fg=_VAULT_INDIGO,
            font=(self.display_font, 11, "bold"),
        ).pack(side="left")
        self._hero_status_chip = tk.Label(
            title_row,
            text="● PROTECTED",
            bg=self.palette["surface_alt"],
            fg=_VAULT_TEAL,
            font=(self.mono_font, 9, "bold"),
            padx=10,
            pady=2,
        )
        self._hero_status_chip.pack(side="left", padx=(12, 0))

        self._hero_subtitle = tk.Label(
            left,
            text="Snapshot and restore your LDPlayer fleet configuration.",
            bg=self.palette["surface_alt"],
            fg=self.palette["muted"],
            font=(self.mono_font, 10),
        )
        self._hero_subtitle.pack(anchor="w", pady=(6, 12))

        # Toggle row
        toggles = tk.Frame(left, bg=self.palette["surface_alt"])
        toggles.pack(anchor="w", pady=(0, 0))
        tb.Checkbutton(
            toggles,
            variable=self._backup_include_logs,
            text="Include Logs",
            bootstyle="success-round-toggle",
            command=self._refresh_backup_page,
        ).pack(side="left", padx=(0, 14))
        tb.Checkbutton(
            toggles,
            variable=self._backup_include_content,
            text="Include Content Queue",
            bootstyle="info-round-toggle",
            command=self._refresh_backup_page,
        ).pack(side="left")

        # Right: primary CTA + secondary bar
        right = tk.Frame(inner, bg=self.palette["surface_alt"])
        right.pack(side="right", anchor="ne")

        cta = self.create_color_button(
            right,
            text="◉  Create Snapshot",
            command=self._backup_create_archive,
            base_color=_VAULT_INDIGO,
            hover_color=_VAULT_VIOLET,
            active_color=_VAULT_VIOLET,
            text_color="#FFFFFF",
            padx=18,
            pady=10,
            font=(self.display_font, 11, "bold"),
        )
        cta.pack(anchor="e")

        tool_row = tk.Frame(right, bg=self.palette["surface_alt"])
        tool_row.pack(anchor="e", pady=(10, 0))
        for label, cmd, bg_color, hover_color in [
            ("Import ZIP", self._backup_restore_from_file, _VAULT_SKY, "#7DD3FC"),
            ("Cleanup", self._backup_cleanup_archives, _VAULT_AMBER, "#FBBF24"),
            ("Open Folder", self._backup_open_folder, _VAULT_TEAL, "#5EEAD4"),
        ]:
            btn = self.create_color_button(
                tool_row,
                text=label,
                command=cmd,
                base_color=bg_color,
                hover_color=hover_color,
                active_color=hover_color,
                text_color="#FFFFFF",
                padx=12,
                pady=5,
                font=(self.mono_font, 9, "bold"),
            )
            btn.pack(side="left", padx=(6, 0))

    # ─────────────────────────────────────────────────────────────────── #
    # Timeline panel

    def _build_timeline_panel(self, parent):
        panel = self._create_card_section(
            parent,
            "Snapshot Timeline",
            "Chronological view of your backup archives — newest at the top.",
            expand=True,
            pady=(0, 0),
        )
        self._timeline_host = panel

        self._timeline_empty_view = StateView(
            panel,
            kind="empty",
            title="Your timeline is empty",
            message="Create your first snapshot to lock in a recovery point.",
            actions=[
                {"text": "Create Snapshot", "command": self._backup_create_archive, "bootstyle": "info"},
            ],
            palette=self.palette,
            display_font=self.display_font,
            mono_font=self.mono_font,
        )

        self._timeline_canvas_host = tb.Frame(panel, style="CardInner.TFrame")
        self._timeline_canvas_host.pack(fill="both", expand=True)

    def _render_timeline(self, backups):
        for child in self._timeline_canvas_host.winfo_children():
            child.destroy()
        self._backup_timeline_rows = {}

        if not backups:
            self._timeline_empty_view.pack(fill="x", pady=(0, 8))
            return
        try:
            self._timeline_empty_view.pack_forget()
        except Exception:
            pass

        current_path = str(self._backup_selected_path) if self._backup_selected_path else ""

        for idx, row in enumerate(backups):
            age_hours = max(0.0, (datetime.now() - row["created"]).total_seconds() / 3600.0)
            if age_hours < 24:
                dot_color = _VAULT_TEAL
            elif age_hours < 72:
                dot_color = _VAULT_AMBER
            else:
                dot_color = _VAULT_ROSE

            is_last = idx == len(backups) - 1
            selected = str(row["path"]) == current_path

            node = self._build_timeline_node(
                self._timeline_canvas_host,
                row=row,
                dot_color=dot_color,
                is_last=is_last,
                selected=selected,
                age_hours=age_hours,
            )
            node.pack(fill="x")
            self._backup_timeline_rows[str(row["path"])] = node

    def _build_timeline_node(self, parent, row, dot_color, is_last, selected, age_hours):
        node = tk.Frame(parent, bg=self.palette["surface"])

        # Rail column: dot + continuation line
        rail = tk.Canvas(
            node,
            width=28,
            height=72,
            bg=self.palette["surface"],
            highlightthickness=0,
            bd=0,
        )
        rail.pack(side="left", fill="y")
        # Top line (hide for the first entry — we don't fade the top)
        rail.create_line(14, 0, 14, 22, fill=self.palette["border"], width=2)
        # Dot (filled)
        rail.create_oval(7, 17, 21, 31, fill=dot_color, outline=dot_color)
        # Inner dot for selected
        if selected:
            rail.create_oval(11, 21, 17, 27, fill="#FFFFFF", outline="#FFFFFF")
        # Bottom line to next node
        if not is_last:
            rail.create_line(14, 31, 14, 120, fill=self.palette["border"], width=2)

        # Card body
        body_bg = self.palette["surface_alt"] if selected else self.palette["surface"]
        card = tk.Frame(
            node,
            bg=body_bg,
            highlightthickness=1,
            highlightbackground=dot_color if selected else self.palette["border"],
        )
        card.pack(side="left", fill="x", expand=True, padx=(6, 0), pady=(10, 10))

        top = tk.Frame(card, bg=body_bg, padx=14, pady=10)
        top.pack(fill="x")

        # Title
        tk.Label(
            top,
            text=row["name"],
            bg=body_bg,
            fg=self.palette["text"],
            font=(self.display_font, 11, "bold"),
        ).pack(side="left")

        # Age chip
        tk.Label(
            top,
            text=self._format_age(age_hours),
            bg=body_bg,
            fg=dot_color,
            font=(self.mono_font, 9, "bold"),
            padx=10,
        ).pack(side="left", padx=(10, 0))

        # Right: action mini-buttons (solid colors)
        actions = tk.Frame(top, bg=body_bg)
        actions.pack(side="right")
        for label, cmd, bg_color, hover_color in [
            ("Restore", lambda p=row["path"]: self._backup_restore_prompt(p), _VAULT_SKY, "#7DD3FC"),
            ("Delete", lambda p=row["path"]: self._backup_delete_path(p), _VAULT_ROSE, "#FB7185"),
        ]:
            btn = self.create_color_button(
                actions,
                text=label,
                command=cmd,
                base_color=bg_color,
                hover_color=hover_color,
                active_color=hover_color,
                text_color="#FFFFFF",
                padx=12,
                pady=4,
                font=(self.mono_font, 9, "bold"),
            )
            btn.pack(side="left", padx=(4, 0))

        # Meta line
        meta = tk.Frame(card, bg=body_bg)
        meta.pack(fill="x", padx=14, pady=(0, 10))

        created = row["created"].strftime("%Y-%m-%d %H:%M")
        parts = [
            ("📁", f"{row['item_count']} files", self.palette["muted"]),
            ("◔", row["size_text"], self.palette["muted"]),
            ("⏱", created, self.palette["muted"]),
        ]
        for icon, text, fg in parts:
            tk.Label(
                meta,
                text=f"{icon} {text}",
                bg=body_bg,
                fg=fg,
                font=(self.mono_font, 9),
            ).pack(side="left", padx=(0, 16))

        # Clicking anywhere on the node selects it
        def _select_and_refresh(_e=None, p=row["path"]):
            self._backup_selected_path = Path(p)
            self._refresh_backup_page()

        for w in (node, card, top, meta):
            w.bind("<Button-1>", _select_and_refresh)
            w.configure(cursor="hand2")

        return node

    # ─────────────────────────────────────────────────────────────────── #
    # Vault meters (ring gauges)

    def _build_vault_meters(self, parent):
        panel = self._create_card_section(
            parent,
            "Vault Meters",
            "Visual at-a-glance health of freshness, retention, and completeness.",
            pady=(0, 12),
        )

        self._meter_host = tb.Frame(panel, style="CardInner.TFrame")
        self._meter_host.pack(fill="x")

        tips = self._create_card_section(
            parent,
            "Operator Tips",
            "Recovery best-practices for this workspace.",
            expand=True,
            pady=(0, 0),
        )
        self._tips_host = tips

    def _render_meters(self, backups):
        for child in self._meter_host.winfo_children():
            child.destroy()

        latest_age_h = None
        if backups:
            latest_age_h = max(0.0, (datetime.now() - backups[0]["created"]).total_seconds() / 3600.0)

        freshness = 0
        if latest_age_h is not None:
            if latest_age_h <= 24:
                freshness = 100
            elif latest_age_h >= 168:  # 7 days
                freshness = 0
            else:
                freshness = int(max(0, min(100, 100 * (1 - (latest_age_h - 24) / (168 - 24)))))

        retention = int(max(0, min(100, (len(backups) / 10) * 100)))

        if backups:
            groups = backups[0]["groups"]
            parts_present = sum(1 for k in ("config", "logs", "content") if groups.get(k, 0) > 0)
            completeness = int((parts_present / 3) * 100)
        else:
            completeness = 0

        rings = [
            ("Freshness", freshness, _VAULT_TEAL, self._freshness_label(latest_age_h)),
            ("Retention", retention, _VAULT_INDIGO, f"{len(backups)} / 10"),
            ("Coverage", completeness, _VAULT_VIOLET, self._coverage_label(backups)),
        ]
        for label, pct, color, subtitle in rings:
            ring = self._make_ring(self._meter_host, label=label, pct=pct, color=color, subtitle=subtitle)
            ring.pack(side="left", fill="both", expand=True, padx=4)

    def _make_ring(self, parent, label, pct, color, subtitle):
        size = 120
        wrap = tk.Frame(parent, bg=self.palette["surface"])
        canvas = tk.Canvas(
            wrap,
            width=size,
            height=size,
            bg=self.palette["surface"],
            highlightthickness=0,
            bd=0,
        )
        canvas.pack()

        pad = 8
        # Track
        canvas.create_arc(
            pad,
            pad,
            size - pad,
            size - pad,
            start=90,
            extent=-359.999,
            style="arc",
            outline=self.palette["surface_alt"],
            width=10,
        )
        # Progress
        if pct > 0:
            extent = -max(1, int(359.999 * (pct / 100)))
            canvas.create_arc(
                pad,
                pad,
                size - pad,
                size - pad,
                start=90,
                extent=extent,
                style="arc",
                outline=color,
                width=10,
            )
        # Center percentage
        canvas.create_text(
            size / 2,
            size / 2 - 6,
            text=f"{pct}%",
            fill=self.palette["text"],
            font=(self.display_font, 16, "bold"),
        )
        canvas.create_text(
            size / 2,
            size / 2 + 14,
            text=label.upper(),
            fill=color,
            font=(self.mono_font, 8, "bold"),
        )

        tk.Label(
            wrap,
            text=subtitle,
            bg=self.palette["surface"],
            fg=self.palette["muted"],
            font=(self.mono_font, 9),
        ).pack(pady=(6, 0))
        return wrap

    def _render_tips(self, backups):
        for child in self._tips_host.winfo_children():
            child.destroy()

        tips = [
            (
                "●",
                "Snapshot before risky ops",
                "Create a backup before bulk imports, queue resets, or schedule edits.",
                _VAULT_INDIGO,
            ),
            (
                "●",
                "Restore scope",
                "Archives replace matching config/log/content files on restore.",
                _VAULT_AMBER,
            ),
            ("●", "Retention", "Keep at least one baseline + one fresh working snapshot.", _VAULT_TEAL),
        ]
        if backups:
            latest = backups[0]
            tips.append(
                (
                    "●",
                    "Latest snapshot",
                    f"{latest['name']} — {latest['item_count']} files, {latest['size_text']}",
                    _VAULT_SKY,
                )
            )

        for dot, title, msg, color in tips:
            row = tk.Frame(self._tips_host, bg=self.palette["surface"])
            row.pack(fill="x", pady=3)
            tk.Label(
                row,
                text=dot,
                bg=self.palette["surface"],
                fg=color,
                font=(self.display_font, 14),
            ).pack(side="left", padx=(0, 8), anchor="n")
            text_col = tk.Frame(row, bg=self.palette["surface"])
            text_col.pack(side="left", fill="x", expand=True)
            tk.Label(
                text_col,
                text=title,
                bg=self.palette["surface"],
                fg=self.palette["text"],
                font=(self.display_font, 10, "bold"),
                anchor="w",
            ).pack(anchor="w")
            tk.Label(
                text_col,
                text=msg,
                bg=self.palette["surface"],
                fg=self.palette["muted"],
                font=(self.mono_font, 9),
                anchor="w",
                justify="left",
                wraplength=300,
            ).pack(anchor="w")

    # ─────────────────────────────────────────────────────────────────── #
    # Archive inspector (bottom)

    def _build_archive_inspector(self, parent):
        panel = self._create_card_section(
            parent,
            "Archive Inspector",
            "Drill into a selected snapshot's composition and file contents.",
            pady=(0, 0),
        )

        self._inspector_empty_view = StateView(
            panel,
            kind="empty",
            title="No archive selected",
            message="Click a timeline entry above to inspect its contents.",
            palette=self.palette,
            display_font=self.display_font,
            mono_font=self.mono_font,
        )
        self._inspector_body = tb.Frame(panel, style="CardInner.TFrame")

        # Title + meta
        self.backup_detail_title = tk.Label(
            self._inspector_body,
            text="—",
            bg=self.palette["surface"],
            fg=self.palette["text"],
            font=(self.display_font, 14, "bold"),
        )
        self.backup_detail_title.pack(anchor="w")

        self.backup_detail_meta = tk.Label(
            self._inspector_body,
            text="",
            bg=self.palette["surface"],
            fg=self.palette["muted"],
            font=(self.mono_font, 9),
            justify="left",
            anchor="w",
        )
        self.backup_detail_meta.pack(anchor="w", pady=(4, 10))

        # Segmented composition bar
        self._inspector_bar_wrap = tk.Frame(self._inspector_body, bg=self.palette["surface"])
        self._inspector_bar_wrap.pack(fill="x", pady=(0, 4))
        self._inspector_bar = tk.Frame(self._inspector_bar_wrap, bg=self.palette["surface_alt"], height=16)
        self._inspector_bar.pack(fill="x")

        self._inspector_legend = tk.Frame(self._inspector_body, bg=self.palette["surface"])
        self._inspector_legend.pack(fill="x", pady=(6, 12))

        # File list
        list_wrap = tk.Frame(
            self._inspector_body,
            bg=self.palette["surface_alt"],
            highlightthickness=1,
            highlightbackground=self.palette["border"],
        )
        list_wrap.pack(fill="both", expand=True)

        self.backup_detail_files = tk.Listbox(
            list_wrap,
            height=10,
            bg=self.palette["surface_alt"],
            fg=_VAULT_SKY,
            selectbackground=self.palette["surface"],
            selectforeground=self.palette["text"],
            relief="flat",
            highlightthickness=0,
            font=(self.mono_font, 10),
            activestyle="none",
        )
        sb = tb.Scrollbar(
            list_wrap, orient="vertical", command=self.backup_detail_files.yview, style="Vertical.TScrollbar"
        )
        sb.pack(side="right", fill="y")
        self.backup_detail_files.configure(yscrollcommand=sb.set)
        self.backup_detail_files.pack(side="left", fill="both", expand=True)

        self._inspector_body.pack_forget()
        self._inspector_empty_view.pack(fill="x")

    def _render_inspector(self, backups):
        path = self._backup_selected_path
        if (not path or not Path(path).exists()) and backups:
            path = backups[0]["path"]
            self._backup_selected_path = Path(path)

        if not path or not Path(path).exists():
            self._inspector_body.pack_forget()
            self._inspector_empty_view.pack(fill="x")
            return

        rows = {str(row["path"]): row for row in backups}
        row = rows.get(str(path))
        if not row:
            self._inspector_body.pack_forget()
            self._inspector_empty_view.pack(fill="x")
            return

        try:
            self._inspector_empty_view.pack_forget()
        except Exception:
            pass
        self._inspector_body.pack(fill="both", expand=True)

        groups = row["groups"]
        self.backup_detail_title.configure(text=row["name"])
        self.backup_detail_meta.configure(
            text=(
                f"Created {row['created'].strftime('%Y-%m-%d %H:%M:%S')}  ·  "
                f"{row['size_text']}  ·  {row['item_count']} files"
            )
        )

        # Segmented composition bar — grid-based weighted layout
        for w in self._inspector_bar.winfo_children():
            w.destroy()
        for w in self._inspector_legend.winfo_children():
            w.destroy()

        segments = [
            ("Config", groups.get("config", 0), _VAULT_INDIGO),
            ("Logs", groups.get("logs", 0), _VAULT_SKY),
            ("Content", groups.get("content", 0), _VAULT_VIOLET),
            ("Other", groups.get("other", 0), self.palette["muted"]),
        ]
        col = 0
        for name, count, color in segments:
            if count <= 0:
                continue
            self._inspector_bar.columnconfigure(col, weight=count)
            seg = tk.Frame(self._inspector_bar, bg=color, height=16)
            seg.grid(row=0, column=col, sticky="nsew")
            col += 1

        for name, count, color in segments:
            chip = tk.Frame(self._inspector_legend, bg=self.palette["surface"])
            chip.pack(side="left", padx=(0, 12))
            tk.Frame(chip, bg=color, width=10, height=10).pack(side="left", padx=(0, 6))
            tk.Label(
                chip,
                text=f"{name}  {count}",
                bg=self.palette["surface"],
                fg=self.palette["muted"] if count == 0 else self.palette["text"],
                font=(self.mono_font, 9, "bold"),
            ).pack(side="left")

        # File list preview
        self.backup_detail_files.delete(0, "end")
        preview = row["members"][:20]
        for member in preview:
            self.backup_detail_files.insert("end", f"  {member}")
        if len(row["members"]) > len(preview):
            self.backup_detail_files.insert("end", f"  + {len(row['members']) - len(preview)} more file(s)")

    # ─────────────────────────────────────────────────────────────────── #
    # Refresh pipeline

    def _refresh_backup_page(self):
        backups = self._get_backup_rows()
        self._update_hero(backups)
        self._render_timeline(backups)
        self._render_meters(backups)
        self._render_tips(backups)
        self._render_inspector(backups)

    def _update_hero(self, backups):
        count = len(backups)
        latest = backups[0] if backups else None
        if count == 0:
            self._hero_accent.configure(bg=_VAULT_ROSE)
            self._hero_status_chip.configure(text="⚠ NO BASELINE", fg=_VAULT_ROSE)
            self._hero_subtitle.configure(
                text="You have no recovery point yet — create a baseline snapshot now."
            )
        else:
            age_h = (datetime.now() - latest["created"]).total_seconds() / 3600.0
            if age_h > 72:
                self._hero_accent.configure(bg=_VAULT_AMBER)
                self._hero_status_chip.configure(text="◐ STALE", fg=_VAULT_AMBER)
                self._hero_subtitle.configure(
                    text=f"{count} archive(s) — newest is about {age_h:.0f}h old. Consider refreshing."
                )
            else:
                self._hero_accent.configure(bg=_VAULT_TEAL)
                self._hero_status_chip.configure(text="● PROTECTED", fg=_VAULT_TEAL)
                self._hero_subtitle.configure(
                    text=f"{count} archive(s) — newest captured {self._format_age(age_h)}."
                )

    # ─────────────────────────────────────────────────────────────────── #
    # Data helpers

    def _get_backup_rows(self):
        rows = []
        for path in self.backup_manager.list_backups():
            info = self._backup_inspect_zip(path)
            stat = path.stat()
            rows.append(
                {
                    "path": path,
                    "name": path.name,
                    "created": datetime.fromtimestamp(stat.st_mtime),
                    "size_bytes": stat.st_size,
                    "size_text": self._backup_size_text(stat.st_size),
                    "item_count": len(info["members"]),
                    "members": info["members"],
                    "groups": info["groups"],
                }
            )
        rows.sort(key=lambda r: r["created"], reverse=True)
        return rows

    def _backup_inspect_zip(self, path):
        members = []
        groups = {"config": 0, "logs": 0, "content": 0, "other": 0}
        try:
            with zipfile.ZipFile(path, "r") as zipf:
                members = zipf.namelist()
        except Exception:
            return {"members": [], "groups": groups}

        for member in members:
            if member.startswith("config/"):
                groups["config"] += 1
            elif member.startswith("logs/"):
                groups["logs"] += 1
            elif member.startswith("content/"):
                groups["content"] += 1
            else:
                groups["other"] += 1
        return {"members": members, "groups": groups}

    @staticmethod
    def _format_age(hours):
        if hours is None:
            return "—"
        if hours < 1:
            minutes = int(hours * 60)
            return f"{minutes}m ago" if minutes else "just now"
        if hours < 24:
            return f"{int(hours)}h ago"
        days = hours / 24
        if days < 7:
            return f"{int(days)}d ago"
        weeks = days / 7
        return f"{int(weeks)}w ago"

    def _freshness_label(self, age_hours):
        if age_hours is None:
            return "No baseline"
        return self._format_age(age_hours)

    def _coverage_label(self, backups):
        if not backups:
            return "—"
        groups = backups[0]["groups"]
        parts = [k.title() for k in ("config", "logs", "content") if groups.get(k, 0) > 0]
        return " + ".join(parts) if parts else "Empty"

    def _backup_size_text(self, size_bytes):
        size = float(size_bytes or 0)
        units = ["B", "KB", "MB", "GB"]
        idx = 0
        while size >= 1024 and idx < len(units) - 1:
            size /= 1024
            idx += 1
        return f"{size:.1f} {units[idx]}"

    # ─────────────────────────────────────────────────────────────────── #
    # Actions

    def _backup_create_archive(self):
        try:
            ok = self.backup_manager.create_backup(
                include_logs=bool(self._backup_include_logs.get()),
                include_content=bool(self._backup_include_content.get()),
            )
        except Exception as exc:
            MessageBox.showerror("Backup", f"Backup failed: {exc}")
            return

        if ok:
            self.log("Backup created from Backup Center", "SUCCESS")
            self._refresh_backup_page()
            MessageBox.showinfo("Backup", "Backup created successfully.")
        else:
            MessageBox.showerror("Backup", "Backup failed. Check logs for details.")

    def _backup_restore_prompt(self, path):
        path = Path(path)
        if not path.exists():
            MessageBox.showinfo("Restore", "Archive is missing on disk.")
            return
        if not MessageBox.askyesno("Restore Backup", f"Restore '{path.name}' into the project now?"):
            return
        self._backup_restore_path(path)

    def _backup_restore_from_file(self):
        backup_dir = self.paths.backup_dir
        initial_dir = str(backup_dir.resolve()) if backup_dir.exists() else str(Path(".").resolve())
        backup_file = filedialog.askopenfilename(
            title="Select a backup file",
            initialdir=initial_dir,
            filetypes=[("Backup ZIP", "*.zip"), ("All Files", "*.*")],
        )
        if not backup_file:
            return
        self._backup_restore_path(Path(backup_file))

    def _backup_restore_path(self, path):
        try:
            ok = self.backup_manager.restore_backup(Path(path))
        except Exception as exc:
            MessageBox.showerror("Restore", f"Restore failed: {exc}")
            return

        if ok:
            self.log(f"Backup restored from {Path(path).name}", "SUCCESS")
            self._refresh_backup_page()
            MessageBox.showinfo("Restore", "Backup restored successfully.")
        else:
            MessageBox.showerror("Restore", "Restore failed. Check logs for details.")

    def _backup_cleanup_archives(self):
        if not MessageBox.askyesno(
            "Clean Old Backups",
            "Delete older backup archives and keep only the most recent 10?",
        ):
            return
        try:
            self.backup_manager.cleanup_old_backups(keep_count=10)
        except Exception as exc:
            MessageBox.showerror("Backup Cleanup", f"Cleanup failed: {exc}")
            return
        self.log("Old backup archives cleaned from Backup Center", "INFO")
        self._refresh_backup_page()
        MessageBox.showinfo(
            "Backup Cleanup", "Old backups cleaned up. The most recent 10 archives were kept."
        )

    def _backup_delete_path(self, path):
        path = Path(path)
        if not path.exists():
            MessageBox.showinfo("Delete Backup", "Archive is missing on disk.")
            return
        if not MessageBox.askyesno("Delete Backup", f"Delete '{path.name}' permanently?"):
            return
        try:
            path.unlink()
        except Exception as exc:
            MessageBox.showerror("Delete Backup", f"Delete failed: {exc}")
            return
        self.log(f"Backup deleted: {path.name}", "INFO")
        if self._backup_selected_path and Path(self._backup_selected_path) == path:
            self._backup_selected_path = None
        self._refresh_backup_page()

    def _backup_open_folder(self):
        backup_dir = self.paths.backup_dir
        backup_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(backup_dir))
        except Exception:
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(str(backup_dir))
                self.log(f"Backup folder copied to clipboard: {backup_dir}", "INFO")
                MessageBox.showinfo("Backups", f"Backup folder path copied:\n{backup_dir}")
            except Exception as exc:
                MessageBox.showerror("Backups", f"Could not open backup folder: {exc}")
