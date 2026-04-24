"""
gui/pages/dashboard_page.py
Dashboard hub — KPI overview, LD instance list, account + page insights.
Styled to match Analytics/Devices design language.
Persists to config/dashboard_instances.json.
"""

import json
import tkinter as tk
from tkinter import messagebox as MessageBox

import ttkbootstrap as tb

from core.paths import get_app_paths
from gui.components.cards import FeedCard, MetricCard
from gui.components.scrollable_frame import ScrollableFrame
from gui.components.state_views import StateView
from gui.components.status import StatusPill
from gui.gradient_progress import GradientProgressBar


_NONE_TOKEN = "None"


def _v(value):
    if value is None:
        return _NONE_TOKEN
    text = str(value).strip()
    return text if text else _NONE_TOKEN


class DashboardDialogMixin:
    # ─────────────────────────────────────────────────────────────────── #
    # Entry points

    def create_dashboard_hub_tab(self):
        tab = tb.Frame(self.notebook, style="CardInner.TFrame")
        self.notebook.add(tab, text="Dashboard")

        self._dashboard_load_data()
        self._db_clear_widget_refs()
        self._dashboard_selected = None
        self._dashboard_dirty = False
        self._db_sync_from_devices()
        self._db_build_surface(tab, embedded=True)
        self._db_render_all()

    def show_dashboard(self):
        if hasattr(self, "notebook"):
            try:
                self.notebook.select(1)
                self._on_notebook_tab_changed()
                self.request_embedded_dashboard_refresh()
                return
            except Exception:
                pass

        win = getattr(self, "_dashboard_dialog", None)
        if self._db_widget_exists(win):
            win.focus()
            return

        self._dashboard_host = None
        self._dashboard_embedded = False
        self._dashboard_load_data()
        self._db_clear_widget_refs()

        win = tk.Toplevel(self.root)
        win.title("Dashboard")
        win.geometry("1360x820")
        win.minsize(1120, 680)
        win.transient(self.root)
        win.configure(bg=self.palette["surface"])
        self._dashboard_dialog = win
        self._dashboard_selected = None
        self._dashboard_dirty = False

        self._db_sync_from_devices()
        self._db_build_surface(win, embedded=False)
        self._db_render_all()
        win.protocol("WM_DELETE_WINDOW", self._db_on_close)

    def request_embedded_dashboard_refresh(self):
        host = getattr(self, "_dashboard_host", None)
        if not self._db_widget_exists(host):
            return
        self._dashboard_load_data()
        self._db_sync_from_devices()
        self._db_render_all()

    # ─────────────────────────────────────────────────────────────────── #
    # Layout

    def _db_build_surface(self, parent, embedded=False):
        self._dashboard_embedded = embedded
        self._dashboard_host = parent if embedded else None
        self._dashboard_dialog = None if embedded else parent

        scroller = ScrollableFrame(parent, bg=self.palette["surface"])
        scroller.pack(fill="both", expand=True, padx=2)
        body = scroller.body

        # KPI hero row
        hero = self._create_card_section(
            body,
            "Fleet Overview",
            "LD instances, linked accounts, pages, and active reels pipelines.",
            pady=(0, 12),
        )
        self._db_build_kpis(hero)

        # Two-column layout: instance list | detail
        grid = tb.Frame(body, style="CardInner.TFrame")
        grid.pack(fill="both", expand=True)
        grid.columnconfigure(0, weight=3, uniform="dashboard_hub")
        grid.columnconfigure(1, weight=5, uniform="dashboard_hub")

        left_col = tb.Frame(grid, style="CardInner.TFrame")
        right_col = tb.Frame(grid, style="CardInner.TFrame")
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        right_col.grid(row=0, column=1, sticky="nsew", padx=(7, 0))

        self._db_build_instance_panel(left_col)
        self._db_build_detail_panel(right_col)

        # Footer
        footer = self._create_card_section(
            body,
            "Persistence",
            "Sync with the current device fleet or save account and reels configuration.",
            pady=(12, 0),
        )
        self._db_build_footer(footer)

    # ─────────────────────────────────────────────────────────────────── #
    # KPI cards

    def _db_build_kpis(self, parent):
        row = tb.Frame(parent, style="CardInner.TFrame")
        row.pack(fill="x")
        self._db_kpi_cards = {}
        specs = [
            ("instances", "LD Instances", self.palette["primary"], "Total registered"),
            ("accounts", "Accounts", "#38BDF8", "With credentials"),
            ("pages", "Facebook Pages", self.palette["warning"], "Configured for reels"),
            ("reels_on", "Reels Automation", self.palette["success"], "Active pipelines"),
        ]
        for idx, (key, label, accent, subtitle) in enumerate(specs):
            card = MetricCard(row, label, "0", subtitle, accent=accent, palette=self.palette)
            card.pack(
                side="left",
                fill="both",
                expand=True,
                padx=(0, 8 if idx < len(specs) - 1 else 0),
            )
            self._db_kpi_cards[key] = card

    def _db_update_kpis(self):
        if not getattr(self, "_db_kpi_cards", None):
            return
        device_names = self._db_device_names()
        by_name = {str(i.get("name") or ""): i for i in self._db_instances()}
        visible = [by_name.get(n, {"name": n, "account": {}}) for n in device_names]

        total_inst = len(device_names)
        total_acc = sum(
            1 for i in visible
            if (i.get("account") or {}).get("uid") or (i.get("account") or {}).get("mail")
        )
        total_pages = sum(len(self._db_account_pages(i.get("account") or {})) for i in visible)
        total_reels_on = sum(
            1
            for i in visible
            for p in self._db_account_pages(i.get("account") or {})
            if (p.get("reels") or {}).get("enabled")
        )

        self._db_kpi_cards["instances"].set(total_inst, subtitle="Total registered")
        self._db_kpi_cards["accounts"].set(total_acc, subtitle=f"{total_acc} / {max(1, total_inst)} linked")
        self._db_kpi_cards["pages"].set(total_pages, subtitle=f"across {total_inst} instance(s)")
        self._db_kpi_cards["reels_on"].set(
            total_reels_on, subtitle=f"{total_reels_on} / {max(1, total_pages)} pages ON"
        )

    # ─────────────────────────────────────────────────────────────────── #
    # Instance list panel

    def _db_build_instance_panel(self, parent):
        card = self._create_card_section(
            parent,
            "LD Instances",
            "Pick an instance to inspect its Facebook account and reels pipeline.",
            expand=True,
            pady=(0, 0),
        )

        header = tb.Frame(card, style="CardInner.TFrame")
        header.pack(fill="x", pady=(0, 8))
        self._db_list_count = StatusPill(
            header,
            "info",
            palette=self.palette,
            text="0 instances",
            font=(self.mono_font, 9),
            padx=10,
            pady=3,
        )
        self._db_list_count.pack(side="left")
        tb.Button(
            header,
            text="Sync Devices",
            bootstyle="info-outline",
            command=self._db_refresh_from_devices,
            width=14,
        ).pack(side="right")

        search_row = tb.Frame(card, style="CardInner.TFrame")
        search_row.pack(fill="x", pady=(0, 8))
        tb.Label(search_row, text="SEARCH", style="MetricLabel.TLabel").pack(side="left", padx=(0, 8))
        self._db_search_var = tk.StringVar()
        self._db_search_var.trace_add("write", lambda *_: self._db_refresh_instance_list())
        tb.Entry(
            search_row,
            textvariable=self._db_search_var,
            bootstyle="secondary",
        ).pack(side="left", fill="x", expand=True)

        columns = ("name", "status", "pages")
        tree = tb.Treeview(
            card,
            columns=columns,
            show="headings",
            height=14,
            style="Custom.Treeview",
            selectmode="browse",
        )
        tree.heading("name", text="Instance", anchor="w")
        tree.heading("status", text="State", anchor="w")
        tree.heading("pages", text="Pages", anchor="e")
        tree.column("name", width=180, anchor="w")
        tree.column("status", width=100, anchor="w")
        tree.column("pages", width=60, anchor="e")

        scroll = tb.Scrollbar(card, orient="vertical", command=tree.yview, style="Vertical.TScrollbar")
        scroll.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(fill="both", expand=True)
        tree.bind("<<TreeviewSelect>>", self._db_on_select_instance)
        self._db_tree = tree

    # ─────────────────────────────────────────────────────────────────── #
    # Detail panel

    def _db_build_detail_panel(self, parent):
        card = self._create_card_section(
            parent,
            "Instance Detail",
            "Account credentials health and all configured Facebook pages for this LD.",
            expand=True,
            pady=(0, 0),
        )
        self._db_detail_host = card

    def _db_render_empty_detail(self):
        self._clear_frame(self._db_detail_host)
        view = StateView(
            self._db_detail_host,
            kind="empty",
            title="Select an LD instance",
            message="Pick one from the list on the left to inspect its account and page analytics.",
            palette=self.palette,
            display_font=self.display_font,
            mono_font=self.mono_font,
        )
        view.pack(fill="x", pady=(0, 4))

    def _db_render_instance(self, instance):
        self._clear_frame(self._db_detail_host)
        acc = instance.get("account") or {}
        pages = self._db_account_pages(acc)

        # ── Account profile row ─────────────────────────────────────── #
        profile = tb.Frame(self._db_detail_host, style="CardInner.TFrame")
        profile.pack(fill="x", pady=(0, 12))

        avatar = tk.Label(
            profile,
            text=(acc.get("name") or instance.get("name") or "?")[:1].upper(),
            bg=self.palette["primary"],
            fg="#0B0F17",
            font=(self.display_font, 22, "bold"),
            width=3,
            height=1,
        )
        avatar.pack(side="left")

        meta = tb.Frame(profile, style="CardInner.TFrame")
        meta.pack(side="left", fill="x", expand=True, padx=14)

        name_row = tb.Frame(meta, style="CardInner.TFrame")
        name_row.pack(anchor="w", fill="x")
        tk.Label(
            name_row,
            text=acc.get("name") or instance.get("name") or "Unnamed",
            bg=self.palette["surface"],
            fg=self.palette["text"],
            font=(self.display_font, 16, "bold"),
        ).pack(side="left")
        has_2fa = bool((acc.get("twofa") or "").strip())
        StatusPill(
            name_row,
            "success" if has_2fa else "muted",
            palette=self.palette,
            text="2FA ON" if has_2fa else "2FA OFF",
            font=(self.mono_font, 8),
            padx=8,
            pady=3,
        ).pack(side="left", padx=10)

        tb.Label(
            meta,
            text="LD Instance · Facebook Account",
            style="MetricSub.TLabel",
        ).pack(anchor="w", pady=(4, 8))

        # Credential presence chips
        chip_row = tb.Frame(meta, style="CardInner.TFrame")
        chip_row.pack(anchor="w")
        for lbl, val in [
            ("UID", acc.get("uid")),
            ("Password", acc.get("password")),
            ("2FA", acc.get("twofa")),
            ("Mail", acc.get("mail")),
        ]:
            present = bool((val or "") if not isinstance(val, str) else val.strip())
            StatusPill(
                chip_row,
                "success" if present else "muted",
                palette=self.palette,
                text=f"● {lbl}" if present else f"○ {lbl}",
                font=(self.mono_font, 8),
                padx=8,
                pady=3,
            ).pack(side="left", padx=(0, 6))

        tb.Button(
            profile,
            text="Edit Account",
            bootstyle="primary",
            command=self._db_edit_account,
            width=14,
        ).pack(side="right", anchor="n")

        # ── Mini summary metrics ────────────────────────────────────── #
        mini = tb.Frame(self._db_detail_host, style="CardInner.TFrame")
        mini.pack(fill="x", pady=(0, 12))

        reels_on = sum(1 for p in pages if (p.get("reels") or {}).get("enabled"))
        total_tags = sum(len((p.get("reels") or {}).get("hashtags") or []) for p in pages)
        auto_pct = (reels_on / len(pages) * 100) if pages else 0

        for idx, (label, value, accent, subtitle) in enumerate([
            ("Pages", str(len(pages)), self.palette["primary"], "Configured on this LD"),
            ("Automation", f"{auto_pct:.0f}%", self.palette["success"], f"{reels_on} of {len(pages)} ON"),
            ("Hashtags", str(total_tags), self.palette["warning"], "across all pages"),
        ]):
            card = MetricCard(mini, label, value, subtitle, accent=accent, palette=self.palette)
            card.pack(side="left", fill="both", expand=True, padx=(0, 8 if idx < 2 else 0))

        # ── Pages section ───────────────────────────────────────────── #
        sec_head = tb.Frame(self._db_detail_host, style="CardInner.TFrame")
        sec_head.pack(fill="x", pady=(0, 8))
        tb.Label(
            sec_head,
            text="FACEBOOK PAGES · REELS PIPELINE",
            style="MetricLabel.TLabel",
        ).pack(side="left")
        tb.Button(
            sec_head,
            text="+ Add Page",
            bootstyle="success-outline",
            command=self._db_add_page,
            width=12,
        ).pack(side="right")

        if not pages:
            view = StateView(
                self._db_detail_host,
                kind="empty",
                title="No pages yet",
                message="Add a Facebook page to enable the reels pipeline for this LD instance.",
                palette=self.palette,
                display_font=self.display_font,
                mono_font=self.mono_font,
                actions=[
                    {"text": "Add Page", "command": self._db_add_page, "bootstyle": "outline-success"},
                ],
            )
            view.pack(fill="x")
        else:
            for idx, page in enumerate(pages):
                self._db_render_page_card(self._db_detail_host, idx, page)

    def _db_render_page_card(self, parent, idx, page):
        reels = page.get("reels") or {}
        enabled = bool(reels.get("enabled"))
        accent = self.palette["success"] if enabled else self.palette["muted"]

        detail_bits = [
            f"Schedule: {reels.get('schedule') or 'Manual'}",
            f"Every {reels.get('interval_min', 30)} min",
            f"{len(reels.get('hashtags') or [])} hashtags",
            "Source set" if reels.get("source_folder") else "No source",
        ]
        message = "  |  ".join(detail_bits)

        card = FeedCard(
            parent,
            f"{page.get('name') or f'Page {idx + 1}'}  ·  ID {_v(page.get('page_id'))}",
            message,
            accent=accent,
            chip_text="REELS ON" if enabled else "REELS OFF",
            chip_status="success" if enabled else "muted",
            palette=self.palette,
        )
        card.pack(fill="x", pady=4)

        actions = tb.Frame(card.body, style="CardInner.TFrame")
        actions.pack(fill="x", pady=(6, 0))
        tb.Button(
            actions,
            text="Reels Config",
            bootstyle="info",
            command=lambda i=idx: self._db_configure_reels(i),
            width=12,
        ).pack(side="left", padx=(0, 6))
        tb.Button(
            actions,
            text="Edit",
            bootstyle="secondary-outline",
            command=lambda i=idx: self._db_edit_page(i),
            width=8,
        ).pack(side="left", padx=(0, 6))
        tb.Button(
            actions,
            text="Remove",
            bootstyle="danger-outline",
            command=lambda i=idx: self._db_remove_page(i),
            width=8,
        ).pack(side="left")

    # ─────────────────────────────────────────────────────────────────── #
    # Footer

    def _db_build_footer(self, parent):
        bar = tb.Frame(parent, style="CardInner.TFrame")
        bar.pack(fill="x")

        self._db_status_label = tb.Label(bar, text="Ready", style="MetricSub.TLabel")
        self._db_status_label.pack(side="left")

        tb.Button(
            bar,
            text="Save All",
            bootstyle="success",
            command=self._db_save_all,
            width=12,
        ).pack(side="right", padx=(6, 0))
        tb.Button(
            bar,
            text="Sync Devices",
            bootstyle="info-outline",
            command=self._db_refresh_from_devices,
            width=14,
        ).pack(side="right", padx=(6, 0))
        if not getattr(self, "_dashboard_embedded", False):
            tb.Button(
                bar,
                text="Close",
                bootstyle="secondary-outline",
                command=self._db_on_close,
                width=10,
            ).pack(side="right")

    # ─────────────────────────────────────────────────────────────────── #
    # Shared helpers

    def _clear_frame(self, frame):
        for child in frame.winfo_children():
            child.destroy()

    def _db_status(self, text, color=None):
        label = getattr(self, "_db_status_label", None)
        if not self._db_widget_exists(label):
            self._db_status_label = None
            return
        try:
            if color:
                label.configure(text=text, foreground=color)
            else:
                label.configure(text=text)
        except tk.TclError:
            self._db_status_label = None

    def _db_widget_exists(self, widget):
        if widget is None:
            return False
        try:
            return bool(widget.winfo_exists())
        except tk.TclError:
            return False

    def _db_clear_widget_refs(self):
        self._db_status_label = None
        self._db_kpi_cards = {}
        self._db_list_count = None
        self._db_tree = None
        self._db_detail_host = None

    def _db_message_parent(self):
        parent = getattr(self, "_dashboard_dialog", None)
        if self._db_widget_exists(parent):
            return parent
        host = getattr(self, "_dashboard_host", None)
        if self._db_widget_exists(host):
            try:
                return host.winfo_toplevel()
            except Exception:
                return host
        return getattr(self, "root", None)

    # ─────────────────────────────────────────────────────────────────── #
    # Data

    def _db_data_path(self):
        paths = get_app_paths()
        paths.ensure_runtime_dirs()
        return paths.config_dir / "dashboard_instances.json"

    def _dashboard_load_data(self):
        path = self._db_data_path()
        if not path.exists():
            self._dashboard_data = {"instances": []}
            return
        try:
            loaded = json.loads(path.read_text(encoding="utf-8")) or {}
            if "instances" not in loaded:
                loaded = {"instances": []}
            self._dashboard_data = loaded
        except Exception as exc:
            self._dashboard_data = {"instances": []}
            try:
                self.log(f"Failed to load dashboard data: {exc}", "ERROR")
            except Exception:
                pass

    def _db_save_all(self):
        try:
            path = self._db_write_data()
        except Exception as exc:
            MessageBox.showerror("Save Failed", str(exc), parent=self._db_message_parent())
            return
        self._dashboard_dirty = False
        self._db_status(f"Saved → {path.name}", self.palette["success"])

    def _db_mark_dirty(self):
        self._dashboard_dirty = True
        self._db_status("Unsaved changes", self.palette["warning"])

    def _db_write_data(self):
        path = self._db_data_path()
        path.write_text(
            json.dumps(self._dashboard_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def _db_instances(self):
        return self._dashboard_data.setdefault("instances", [])

    def _db_blank_instance(self, name):
        return {
            "name": name,
            "account": {
                "name": None,
                "uid": None,
                "password": None,
                "twofa": None,
                "mail": None,
                "pages": [],
            },
        }

    def _db_device_names(self):
        snapshot = getattr(self, "_ld_snapshot", None) or {}
        try:
            return list(snapshot.keys())
        except Exception:
            return []

    def _db_sync_from_devices(self):
        insts = self._db_instances()
        by_name = {str(i.get("name") or ""): i for i in insts if i.get("name")}
        changed = False
        for name in self._db_device_names():
            if name not in by_name:
                entry = self._db_blank_instance(name)
                insts.append(entry)
                by_name[name] = entry
                changed = True
        if changed:
            self._db_mark_dirty()
            self._db_write_data()
            self._dashboard_dirty = False

    def _db_sync_snapshot_changes(self, old_snapshot, new_snapshot):
        old_snapshot = dict(old_snapshot or {})
        new_snapshot = dict(new_snapshot or {})

        self._dashboard_load_data()
        insts = self._db_instances()
        by_name = {str(i.get("name") or ""): i for i in insts if i.get("name")}
        changed = False

        removed_names = set(old_snapshot) - set(new_snapshot)
        added_names = set(new_snapshot) - set(old_snapshot)

        for old_name in sorted(removed_names):
            old_serial = old_snapshot.get(old_name)
            if not old_serial:
                continue
            matching_new = next(
                (
                    new_name for new_name in sorted(added_names)
                    if new_snapshot.get(new_name) == old_serial
                ),
                None,
            )
            if not matching_new:
                continue

            entry = by_name.pop(old_name, None)
            if entry is None:
                entry = self._db_blank_instance(matching_new)
                insts.append(entry)
            entry["name"] = matching_new
            by_name[matching_new] = entry
            added_names.discard(matching_new)
            changed = True
            if getattr(self, "_dashboard_selected", None) == old_name:
                self._dashboard_selected = matching_new

        for name in sorted(new_snapshot):
            if name not in by_name:
                entry = self._db_blank_instance(name)
                insts.append(entry)
                by_name[name] = entry
                changed = True

        if changed:
            self._dashboard_dirty = False
            self._db_write_data()
            try:
                self._db_status("Dashboard synced from LD instances", self.palette["success"])
            except Exception:
                pass
        return changed

    def _db_refresh_from_devices(self):
        self._db_sync_from_devices()
        if self._dashboard_dirty:
            self._db_save_all()
        self._db_render_all()
        self._db_status("Synced from Devices", self.palette["success"])

    def _db_device_status(self, name):
        cache = getattr(self, "_ld_status_cache", None) or {}
        return str(cache.get(name) or "Inactive")

    def _db_selected_instance(self):
        name = self._dashboard_selected
        if not name:
            return None
        for inst in self._db_instances():
            if inst.get("name") == name:
                return inst
        return None

    def _db_default_reels_config(self):
        return {
            "enabled": False,
            "schedule": "Manual",
            "interval_min": 30,
            "hashtags": [],
            "caption_template": "",
            "source_folder": "",
        }

    def _db_normalize_page_record(self, page):
        if isinstance(page, dict):
            payload = dict(page)
            name = str(payload.get("name") or "").strip()
        else:
            payload = {}
            name = str(page or "").strip()
        if not name:
            return None
        payload["name"] = name
        payload.setdefault("page_id", None)
        payload.setdefault("reels", self._db_default_reels_config())
        return payload

    def _db_account_pages(self, account):
        if not isinstance(account, dict):
            return []
        pages = account.setdefault("pages", [])
        normalized = []
        seen = set()
        for page in pages:
            payload = self._db_normalize_page_record(page)
            if not payload:
                continue
            name = payload.get("name")
            if name in seen:
                continue
            seen.add(name)
            normalized.append(payload)
        account["pages"] = normalized
        return normalized

    # ─────────────────────────────────────────────────────────────────── #
    # Rendering

    def _db_render_all(self):
        if not (
            self._db_widget_exists(getattr(self, "_dashboard_dialog", None))
            or self._db_widget_exists(getattr(self, "_dashboard_host", None))
        ):
            return
        self._db_refresh_instance_list()
        self._db_update_kpis()
        inst = self._db_selected_instance()
        if inst:
            self._db_render_instance(inst)
        else:
            self._db_render_empty_detail()

    def _db_refresh_instance_list(self):
        tree = getattr(self, "_db_tree", None)
        if not self._db_widget_exists(tree):
            self._db_tree = None
            return

        try:
            for item in tree.get_children():
                tree.delete(item)
        except tk.TclError:
            self._db_tree = None
            return

        query = (self._db_search_var.get() or "").strip().lower() if hasattr(self, "_db_search_var") else ""
        device_names = self._db_device_names()
        by_name = {str(i.get("name") or ""): i for i in self._db_instances()}

        for name in device_names:
            if query and query not in name.lower():
                continue
            inst = by_name.get(name) or {}
            pages = self._db_account_pages(inst.get("account") or {})
            status = self._db_device_status(name)
            tree.insert(
                "",
                "end",
                iid=name,
                values=(name, status, str(len(pages))),
            )

        if self._db_widget_exists(getattr(self, "_db_list_count", None)):
            count = len(device_names)
            self._db_list_count.set_status(
                "info",
                text=f"{count} instance{'s' if count != 1 else ''}",
            )

        if self._dashboard_selected and tree.exists(self._dashboard_selected):
            tree.selection_set(self._dashboard_selected)

    def _db_on_select_instance(self, _event=None):
        tree = self._db_tree
        sel = tree.selection()
        if not sel:
            self._dashboard_selected = None
            self._db_render_empty_detail()
            return
        self._dashboard_selected = str(sel[0])
        inst = self._db_selected_instance()
        if inst:
            self._db_render_instance(inst)
        else:
            self._db_render_empty_detail()

    # ─────────────────────────────────────────────────────────────────── #
    # Editors

    def _db_edit_account(self):
        inst = self._db_selected_instance()
        if not inst:
            MessageBox.showinfo("Edit", "Select an instance first.", parent=self._db_message_parent())
            return
        self._db_open_instance_editor(inst)

    def _db_open_instance_editor(self, instance):
        data = instance
        acc = data.get("account") or {}
        pages = self._db_account_pages(acc)

        win = self._db_modal(f"Account · {data.get('name')}", 540, 500)

        form = tb.Frame(win, style="Card.TFrame", padding=22)
        form.pack(fill="both", expand=True)

        tb.Label(form, text="Edit Account", style="SectionTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        tb.Label(
            form,
            text=f"LD Instance · {data.get('name')}  (from Devices)",
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 14))

        vars_map = {
            "name": tk.StringVar(value=str(acc.get("name") or "")),
            "uid": tk.StringVar(value=str(acc.get("uid") or "")),
            "password": tk.StringVar(value=str(acc.get("password") or "")),
            "twofa": tk.StringVar(value=str(acc.get("twofa") or "")),
            "mail": tk.StringVar(value=str(acc.get("mail") or "")),
        }
        fields = [
            ("Facebook Name", "name", False),
            ("UID", "uid", False),
            ("Password", "password", True),
            ("2FA Secret", "twofa", True),
            ("Mail", "mail", False),
        ]
        for i, (lbl, key, secret) in enumerate(fields, start=2):
            tb.Label(form, text=lbl.upper(), style="MetricLabel.TLabel").grid(
                row=i, column=0, sticky="w", pady=8, padx=(0, 16)
            )
            tb.Entry(
                form,
                textvariable=vars_map[key],
                bootstyle="secondary",
                show="•" if secret else "",
            ).grid(row=i, column=1, sticky="ew", pady=8, ipady=4)
        form.columnconfigure(1, weight=1)

        def commit():
            data["account"] = {
                "name": vars_map["name"].get().strip() or None,
                "uid": vars_map["uid"].get().strip() or None,
                "password": vars_map["password"].get().strip() or None,
                "twofa": vars_map["twofa"].get().strip() or None,
                "mail": vars_map["mail"].get().strip() or None,
                "pages": pages,
            }
            self._db_mark_dirty()
            self._db_save_all()
            self._db_render_all()
            win.destroy()

        footer = tb.Frame(win, style="CardInner.TFrame", padding=(18, 12))
        footer.pack(fill="x", side="bottom")
        tb.Button(footer, text="Cancel", bootstyle="secondary-outline", command=win.destroy, width=10).pack(side="left")
        tb.Button(footer, text="Save", bootstyle="primary", command=commit, width=10).pack(side="right")

    def _db_add_page(self):
        self._db_open_page_editor(None)

    def _db_edit_page(self, idx):
        inst = self._db_selected_instance()
        if not inst:
            return
        pages = self._db_account_pages(inst.setdefault("account", {}))
        if 0 <= idx < len(pages):
            self._db_open_page_editor(idx)

    def _db_remove_page(self, idx):
        inst = self._db_selected_instance()
        if not inst:
            return
        pages = self._db_account_pages(inst.setdefault("account", {}))
        if not (0 <= idx < len(pages)):
            return
        name = pages[idx].get("name") or f"Page {idx + 1}"
        if not MessageBox.askyesno("Remove Page", f"Remove '{name}'?", parent=self._db_message_parent()):
            return
        del pages[idx]
        self._db_mark_dirty()
        self._db_save_all()
        self._db_render_all()

    def _db_open_page_editor(self, idx):
        inst = self._db_selected_instance()
        if not inst:
            return
        pages = self._db_account_pages(inst.setdefault("account", {}))
        is_new = idx is None
        page = {} if is_new else pages[idx]

        win = self._db_modal("Add Page" if is_new else "Edit Page", 500, 320)

        form = tb.Frame(win, style="Card.TFrame", padding=22)
        form.pack(fill="both", expand=True)

        tb.Label(
            form,
            text="Add Page" if is_new else "Edit Page",
            style="SectionTitle.TLabel",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 16))

        name_var = tk.StringVar(value=str(page.get("name") or ""))
        pid_var = tk.StringVar(value=str(page.get("page_id") or ""))

        for i, (lbl, var) in enumerate([("Page Name", name_var), ("Page ID", pid_var)], start=1):
            tb.Label(form, text=lbl.upper(), style="MetricLabel.TLabel").grid(
                row=i, column=0, sticky="w", pady=8, padx=(0, 16)
            )
            tb.Entry(form, textvariable=var, bootstyle="secondary").grid(
                row=i, column=1, sticky="ew", pady=8, ipady=4
            )
        form.columnconfigure(1, weight=1)

        def commit():
            name = name_var.get().strip()
            if not name:
                MessageBox.showwarning("Missing", "Page name is required.", parent=win)
                return
            payload = {
                "name": name,
                "page_id": pid_var.get().strip() or None,
                "reels": page.get("reels") or self._db_default_reels_config(),
            }
            if is_new:
                pages.append(payload)
            else:
                page.update(payload)
            self._db_mark_dirty()
            self._db_save_all()
            self._db_render_all()
            win.destroy()

        footer = tb.Frame(win, style="CardInner.TFrame", padding=(18, 12))
        footer.pack(fill="x", side="bottom")
        tb.Button(footer, text="Cancel", bootstyle="secondary-outline", command=win.destroy, width=10).pack(side="left")
        tb.Button(footer, text="Save", bootstyle="primary", command=commit, width=10).pack(side="right")

    # ─────────────────────────────────────────────────────────────────── #
    # Reels config

    def _db_configure_reels(self, page_idx):
        inst = self._db_selected_instance()
        if not inst:
            return
        pages = self._db_account_pages(inst.setdefault("account", {}))
        if not (0 <= page_idx < len(pages)):
            return
        page = pages[page_idx]
        reels = page.setdefault(
            "reels",
            self._db_default_reels_config(),
        )

        win = self._db_modal(f"Reels · {page.get('name')}", 580, 620)

        head = tb.Frame(win, style="Card.TFrame", padding=(22, 16))
        head.pack(fill="x")
        tb.Label(head, text="Reels Configuration", style="SectionTitle.TLabel").pack(anchor="w")
        tb.Label(
            head,
            text=f"Page · {page.get('name')}  ·  {_v(page.get('page_id'))}",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        body = tb.Frame(win, style="Card.TFrame", padding=22)
        body.pack(fill="both", expand=True)

        enabled_var = tk.BooleanVar(value=bool(reels.get("enabled")))
        schedule_var = tk.StringVar(value=str(reels.get("schedule") or "Manual"))
        interval_var = tk.StringVar(value=str(reels.get("interval_min") or 30))
        hashtags_var = tk.StringVar(value=", ".join(reels.get("hashtags") or []))
        source_var = tk.StringVar(value=str(reels.get("source_folder") or ""))

        toggle_row = tb.Frame(body, style="CardInner.TFrame")
        toggle_row.pack(fill="x", pady=(0, 14))
        tb.Label(toggle_row, text="Enable Reels Posting", style="CardItemTitle.TLabel").pack(side="left")
        tb.Label(
            toggle_row,
            text="Automates video upload to this page.",
            style="MetricSub.TLabel",
        ).pack(side="left", padx=10)
        tb.Checkbutton(toggle_row, variable=enabled_var, bootstyle="success-round-toggle").pack(side="right")

        row = tb.Frame(body, style="CardInner.TFrame")
        row.pack(fill="x", pady=(0, 12))
        lcol = tb.Frame(row, style="CardInner.TFrame")
        lcol.pack(side="left", fill="x", expand=True, padx=(0, 8))
        tb.Label(lcol, text="SCHEDULE", style="MetricLabel.TLabel").pack(anchor="w", pady=(0, 4))
        tb.Combobox(
            lcol,
            textvariable=schedule_var,
            values=("Manual", "Hourly", "Daily", "Custom Interval"),
            state="readonly",
            bootstyle="secondary",
        ).pack(fill="x")

        rcol = tb.Frame(row, style="CardInner.TFrame")
        rcol.pack(side="left", fill="x", expand=True, padx=(8, 0))
        tb.Label(rcol, text="INTERVAL (MIN)", style="MetricLabel.TLabel").pack(anchor="w", pady=(0, 4))
        tb.Entry(rcol, textvariable=interval_var, bootstyle="secondary").pack(fill="x", ipady=3)

        tb.Label(body, text="HASHTAGS (COMMA SEPARATED)", style="MetricLabel.TLabel").pack(anchor="w", pady=(0, 4))
        tb.Entry(body, textvariable=hashtags_var, bootstyle="secondary").pack(fill="x", pady=(0, 12), ipady=3)

        tb.Label(body, text="SOURCE FOLDER / PATH", style="MetricLabel.TLabel").pack(anchor="w", pady=(0, 4))
        tb.Entry(body, textvariable=source_var, bootstyle="secondary").pack(fill="x", pady=(0, 12), ipady=3)

        tb.Label(body, text="CAPTION TEMPLATE", style="MetricLabel.TLabel").pack(anchor="w", pady=(0, 4))
        caption_text = tk.Text(
            body,
            height=5,
            bg=self.palette["surface_alt"],
            fg=self.palette["text"],
            insertbackground=self.palette["primary"],
            relief="flat",
            font=(self.mono_font, 10),
            wrap="word",
            highlightthickness=1,
            highlightbackground=self.palette["border"],
        )
        caption_text.pack(fill="both", expand=True)
        caption_text.insert("1.0", str(reels.get("caption_template") or ""))

        def commit():
            try:
                interval = max(1, int(interval_var.get().strip() or 30))
            except ValueError:
                MessageBox.showwarning("Invalid", "Interval must be a number.", parent=win)
                return
            tags = [t.strip().lstrip("#") for t in hashtags_var.get().split(",") if t.strip()]
            reels.update(
                {
                    "enabled": bool(enabled_var.get()),
                    "schedule": schedule_var.get().strip() or "Manual",
                    "interval_min": interval,
                    "hashtags": tags,
                    "source_folder": source_var.get().strip(),
                    "caption_template": caption_text.get("1.0", "end").strip(),
                }
            )
            self._db_mark_dirty()
            self._db_save_all()
            self._db_render_all()
            win.destroy()

        footer = tb.Frame(win, style="CardInner.TFrame", padding=(18, 12))
        footer.pack(fill="x", side="bottom")
        tb.Button(footer, text="Cancel", bootstyle="secondary-outline", command=win.destroy, width=10).pack(side="left")
        tb.Button(footer, text="Save Reels", bootstyle="success", command=commit, width=12).pack(side="right")

    # ─────────────────────────────────────────────────────────────────── #
    # Modal + close

    def _db_modal(self, title, w, h):
        parent = self._db_message_parent()
        win = tk.Toplevel(parent)
        win.title(title)
        win.geometry(f"{w}x{h}")
        win.resizable(False, False)
        if parent is not None:
            win.transient(parent)
        win.grab_set()
        win.configure(bg=self.palette["surface"])
        return win

    def _db_on_close(self):
        if getattr(self, "_dashboard_embedded", False):
            return
        win = getattr(self, "_dashboard_dialog", None)
        if self._dashboard_dirty:
            choice = MessageBox.askyesnocancel("Unsaved changes", "Save before closing?", parent=win)
            if choice is None:
                return
            if choice:
                self._db_save_all()
        if self._db_widget_exists(win):
            win.destroy()
        self._dashboard_dialog = None
        self._db_clear_widget_refs()
