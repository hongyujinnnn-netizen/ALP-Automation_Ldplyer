"""
gui/pages/dashboard_page.py
Dashboard hub — KPI overview, LD instance list, account + page insights.
Styled to match Analytics/Devices design language.
Persists to config/dashboard_instances.json.
"""

import json
import logging
import re
import threading
import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox as MessageBox

import ttkbootstrap as tb

from core.account_secrets import (
    SECRET_ACCOUNT_FIELDS,
    delete_secrets,
    derive_dashboard_account_id,
    has_plaintext_secrets,
    hydrate_secrets,
    migrate_legacy_plaintext,
    persist_secrets,
    redacted_copy,
)
from core.paths import get_app_paths

_logger = logging.getLogger(__name__)
from gui.checkbox_treeview import build_checkbox_image_set
from gui.components.cards import FeedCard, MetricCard
from gui.components.scrollable_frame import ScrollableFrame
from gui.components.state_views import StateView
from gui.components.status import (
    StatusPill,
    configure_status_tree_tags,
    status_table_text,
    status_tag,
)

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
        self._dashboard_checked = set()
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
        self._dashboard_checked = set()
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
            1 for i in visible if (i.get("account") or {}).get("uid") or (i.get("account") or {}).get("mail")
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
        self._db_checked_count = StatusPill(
            header,
            "muted",
            palette=self.palette,
            text="0 selected",
            font=(self.mono_font, 9),
            padx=10,
            pady=3,
        )
        self._db_checked_count.pack(side="left", padx=(6, 0))
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

        columns = ("name", "status", "account", "pages")
        tree = tb.Treeview(
            card,
            columns=columns,
            show="tree headings",
            height=14,
            style="Custom.Treeview",
            selectmode="browse",
        )
        tree.heading("#0", text="", anchor="center")
        tree.heading("name", text="LD Instance", anchor="w")
        tree.heading("status", text="State", anchor="w")
        tree.heading("account", text="Account", anchor="w")
        tree.heading("pages", text="Pages", anchor="e")
        tree.column("#0", width=42, minwidth=42, stretch=False, anchor="center")
        tree.column("name", width=170, anchor="w")
        tree.column("status", width=120, anchor="w")
        tree.column("account", width=150, anchor="w")
        tree.column("pages", width=60, anchor="e")

        configure_status_tree_tags(tree, self.palette, include_zebra=True)
        tree.tag_configure(
            "hover",
            background=self.palette.get("hover_bg", self.palette["surface_alt"]),
        )

        scroll = tb.Scrollbar(card, orient="vertical", command=tree.yview, style="Vertical.TScrollbar")
        scroll.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(fill="both", expand=True)
        self._db_tree_hover_item = None
        tree.bind("<Button-1>", self._db_on_tree_click, add="+")
        tree.bind("<B1-Motion>", self._db_on_tree_drag, add="+")
        tree.bind("<ButtonRelease-1>", self._db_end_tree_drag, add="+")
        tree.bind("<Motion>", self._db_on_tree_hover, add="+")
        tree.bind("<Leave>", self._db_on_tree_leave, add="+")
        tree.bind("<Button-3>", self._db_show_instance_context_menu, add="+")
        tree.bind("<Control-a>", self._db_select_all_visible_instances)
        tree.bind("<Control-A>", self._db_select_all_visible_instances)
        tree.bind("<<TreeviewSelect>>", self._db_on_select_instance)
        self._db_tree = tree
        self._db_context_menu = self._db_build_instance_context_menu(tree)

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

        ld_name = instance.get("name") or "Unnamed"
        fb_name = (acc.get("name") or "").strip() or "— Not set"

        name_row = tb.Frame(meta, style="CardInner.TFrame")
        name_row.pack(anchor="w", fill="x")
        tk.Label(
            name_row,
            text=ld_name,
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

        fb_row = tb.Frame(meta, style="CardInner.TFrame")
        fb_row.pack(anchor="w", fill="x", pady=(4, 0))
        tb.Label(
            fb_row,
            text="FACEBOOK",
            style="MetricLabel.TLabel",
        ).pack(side="left")
        tk.Label(
            fb_row,
            text=fb_name,
            bg=self.palette["surface"],
            fg=self.palette["primary"],
            font=(self.display_font, 11, "bold"),
        ).pack(side="left", padx=(8, 0))

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

        for idx, (label, value, accent, subtitle) in enumerate(
            [
                ("Pages", str(len(pages)), self.palette["primary"], "Configured on this LD"),
                ("Automation", f"{auto_pct:.0f}%", self.palette["success"], f"{reels_on} of {len(pages)} ON"),
                ("Hashtags", str(total_tags), self.palette["warning"], "across all pages"),
            ]
        ):
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
        except AttributeError:
            return True
        except tk.TclError:
            return False

    def _db_get_checkbox_images(self):
        """Lazily build (and cache) the shared checkbox PhotoImage set."""
        images = getattr(self, "_db_checkbox_images", None)
        if not images:
            images = build_checkbox_image_set(getattr(self, "palette", None))
            self._db_checkbox_images = images
        return images

    def _db_apply_check_visual(self, tree, item, checked):
        """Render a tree row's checkbox column using the shared image set.

        Also applies a subtle ``row_checked`` tag tint so checked rows pop the
        same way the Devices fleet table does. Falls back to Unicode glyphs
        when PhotoImage construction is unavailable.
        """
        if not self._db_widget_exists(tree) or not tree.exists(item):
            return
        self._db_ensure_check_row_tag(tree)
        images = self._db_get_checkbox_images()
        image = images.get("checked" if checked else "unchecked")
        if image is not None:
            tree.item(item, image=image, text="")
        else:
            tree.item(item, image="", text="☑" if checked else "☐")
        try:
            current_tags = tree.item(item, "tags")
        except TypeError:
            current_tags = tree.item(item).get("tags", ())
        tags = [t for t in current_tags if t != "row_checked"]
        if checked:
            tags.append("row_checked")
        tree.item(item, tags=tags)

    def _db_ensure_check_row_tag(self, tree):
        if getattr(tree, "_db_row_checked_configured", False):
            return
        try:
            from gui.checkbox_treeview import _blend  # local import keeps top-level imports tidy

            tint = _blend(
                self.palette.get("success", "#10B981"),
                self.palette.get("surface", "#0E1118"),
                0.12,
            )
            tree.tag_configure("row_checked", background=tint, foreground=self.palette.get("text", "#E2E8F0"))
            tree._db_row_checked_configured = True
        except Exception:
            pass

    def _db_clear_widget_refs(self):
        self._db_status_label = None
        self._db_kpi_cards = {}
        self._db_list_count = None
        self._db_checked_count = None
        self._db_tree = None
        self._db_context_menu = None
        self._db_login_checked_account_id = None
        self._db_login_checked_account_ids = set()
        self._db_instance_drag_select = None
        self._db_login_drag_select = None
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

    def _db_login_accounts_path(self):
        paths = get_app_paths()
        paths.ensure_runtime_dirs()
        return paths.config_dir / "accounts_login.json"

    def _dashboard_load_data(self):
        path = self._db_data_path()
        if not path.exists():
            self._dashboard_data = {"instances": []}
            return
        try:
            loaded = json.loads(path.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, list):
                loaded = {"instances": loaded}
            if not isinstance(loaded, dict):
                loaded = {"instances": []}

            normalized = []
            for raw in loaded.get("instances") or []:
                if isinstance(raw, dict):
                    item = dict(raw)
                    name = str(item.get("name") or "").strip()
                else:
                    item = {}
                    name = str(raw or "").strip()
                if not name:
                    continue

                account = item.get("account") if isinstance(item.get("account"), dict) else {}
                account = dict(account or {})
                account.setdefault("name", None)
                account.setdefault("uid", None)
                account.setdefault("password", None)
                account.setdefault("twofa", None)
                account.setdefault("mail", None)
                account.setdefault("pages", [])

                item["name"] = name
                item["account"] = account
                if "serial" in item:
                    item["serial"] = str(item.get("serial") or "").strip()
                normalized.append(item)

            loaded["instances"] = normalized
            self._dashboard_data = loaded
            if self._dashboard_migrate_and_hydrate_secrets(normalized):
                try:
                    self._db_write_data()
                except Exception as exc:
                    _logger.warning(
                        "[credential-migration] could not rewrite dashboard data: %s",
                        exc,
                    )
        except Exception as exc:
            self._dashboard_data = {"instances": []}
            try:
                self.log(f"Failed to load dashboard data: {exc}", "ERROR")
            except Exception:
                pass

    def _dashboard_migrate_and_hydrate_secrets(self, instances) -> bool:
        """Migrate plaintext secrets in dashboard instance account blocks; hydrate from keyring.

        Returns True if any plaintext was migrated and the file should be rewritten.
        """

        accounts = []
        for item in instances or []:
            if isinstance(item, dict):
                acc = item.get("account")
                if isinstance(acc, dict):
                    accounts.append(acc)
        plaintext_present = has_plaintext_secrets(accounts)
        needs_rewrite = False
        for account in accounts:
            account_id = derive_dashboard_account_id(account)
            if not account_id:
                continue
            if plaintext_present:
                migrated = migrate_legacy_plaintext(account_id, account)
                if migrated:
                    needs_rewrite = True
                    _logger.info(
                        "[credential-migration] moved %s for dashboard account %s into the OS credential vault",
                        ", ".join(migrated.keys()),
                        account_id,
                    )
            hydrate_secrets(account_id, account)
        return needs_rewrite

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
        # Build a deep copy with secrets persisted to keyring + redacted from JSON.
        data_copy = json.loads(json.dumps(self._dashboard_data))
        for item in data_copy.get("instances") or []:
            if not isinstance(item, dict):
                continue
            account = item.get("account")
            if not isinstance(account, dict):
                continue
            account_id = derive_dashboard_account_id(account)
            if not account_id:
                continue
            persisted = persist_secrets(account_id, account)
            for field, ok in persisted.items():
                if ok:
                    account[field] = ""
        path.write_text(
            json.dumps(data_copy, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def _db_instances(self):
        return self._dashboard_data.setdefault("instances", [])

    def _db_blank_instance(self, name, serial=""):
        return {
            "name": name,
            "serial": str(serial or "").strip(),
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
            names = list(snapshot.keys())
            if names:
                return names
        except Exception:
            pass
        return [str(i.get("name") or "") for i in self._db_instances() if i.get("name")]

    def _db_sync_from_devices(self):
        insts = self._db_instances()
        by_name = {str(i.get("name") or ""): i for i in insts if i.get("name")}
        snapshot = getattr(self, "_ld_snapshot", None) or {}
        changed = False
        for name in self._db_device_names():
            if name not in by_name:
                entry = self._db_blank_instance(name, snapshot.get(name, ""))
                insts.append(entry)
                by_name[name] = entry
                changed = True
            elif snapshot.get(name) and by_name[name].get("serial") != snapshot.get(name):
                by_name[name]["serial"] = snapshot.get(name)
                changed = True
        if changed:
            self._db_mark_dirty()
            self._db_write_data()
            self._dashboard_dirty = False

    def _db_sync_snapshot_changes(self, old_snapshot, new_snapshot):
        old_snapshot = dict(old_snapshot or {})
        new_snapshot = dict(new_snapshot or {})

        # Do not reload from disk here — it replaces _dashboard_data with new
        # dict objects and invalidates references captured by open editors,
        # which silently discards pending Edit Account / Edit Page changes.
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
                (new_name for new_name in sorted(added_names) if new_snapshot.get(new_name) == old_serial),
                None,
            )
            if not matching_new:
                continue

            entry = by_name.pop(old_name, None)
            if entry is None:
                entry = self._db_blank_instance(matching_new, new_snapshot.get(matching_new, ""))
                insts.append(entry)
            entry["name"] = matching_new
            entry["serial"] = new_snapshot.get(matching_new, "")
            by_name[matching_new] = entry
            added_names.discard(matching_new)
            changed = True
            if getattr(self, "_dashboard_selected", None) == old_name:
                self._dashboard_selected = matching_new

        if old_snapshot or new_snapshot:
            stale_names = set(by_name) - set(new_snapshot)
            if stale_names:
                self._dashboard_data["instances"] = [
                    inst for inst in insts if str(inst.get("name") or "") not in stale_names
                ]
                insts = self._db_instances()
                by_name = {str(i.get("name") or ""): i for i in insts if i.get("name")}
                changed = True
                if getattr(self, "_dashboard_selected", None) in stale_names:
                    self._dashboard_selected = None
                if hasattr(self, "_dashboard_checked"):
                    self._dashboard_checked = set(getattr(self, "_dashboard_checked", set())) - stale_names

        for name in sorted(new_snapshot):
            if name not in by_name:
                entry = self._db_blank_instance(name, new_snapshot.get(name, ""))
                insts.append(entry)
                by_name[name] = entry
                changed = True
            elif by_name[name].get("serial") != new_snapshot.get(name, ""):
                by_name[name]["serial"] = new_snapshot.get(name, "")
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

    def _db_instances_by_name(self):
        return {str(i.get("name") or ""): i for i in self._db_instances() if i.get("name")}

    def _db_checked_names(self):
        checked = getattr(self, "_dashboard_checked", set())
        device_names = set(self._db_device_names())
        return [name for name in self._db_device_names() if name in checked and name in device_names]

    def _db_checked_instances(self):
        by_name = self._db_instances_by_name()
        return [by_name[name] for name in self._db_checked_names() if name in by_name]

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
        self._dashboard_checked = set(getattr(self, "_dashboard_checked", set())) & set(device_names)
        by_name = self._db_instances_by_name()

        row_idx = 0
        for name in device_names:
            if query and query not in name.lower():
                continue
            inst = by_name.get(name) or {}
            acc = inst.get("account") or {}
            pages = self._db_account_pages(acc)
            status = self._db_device_status(name)
            account_label = (
                str(acc.get("name") or acc.get("uid") or acc.get("mail") or "").strip() or "— No account"
            )
            zebra = "even_row" if row_idx % 2 == 0 else "odd_row"
            tree.insert(
                "",
                "end",
                iid=name,
                values=(
                    name,
                    status_table_text(status),
                    account_label,
                    str(len(pages)),
                ),
                tags=(status_tag(status), zebra),
            )
            self._db_apply_check_visual(tree, name, name in self._dashboard_checked)
            row_idx += 1

        if self._db_widget_exists(getattr(self, "_db_list_count", None)):
            count = len(tree.get_children())
            self._db_list_count.set_status(
                "info",
                text=f"{count} instance{'s' if count != 1 else ''}",
            )
        self._db_update_checked_count()

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

    def _db_update_checked_count(self):
        pill = getattr(self, "_db_checked_count", None)
        if not self._db_widget_exists(pill):
            return
        count = len(self._db_checked_names())
        pill.set_status(
            "success" if count else "muted",
            text=f"{count} selected",
        )

    def _db_on_tree_click(self, event):
        tree = getattr(self, "_db_tree", None)
        if not self._db_widget_exists(tree):
            return None
        item = tree.identify_row(event.y)
        region = tree.identify_region(event.x, event.y)
        column = tree.identify_column(event.x)
        if not item:
            return None
        self._db_begin_tree_drag(item)
        if region == "tree" or column == "#0":
            self._db_toggle_instance_checked(item)
            tree.selection_set(item)
            self._dashboard_selected = str(item)
            self._db_on_select_instance()
            return "break"
        return None

    def _db_begin_tree_drag(self, item):
        checked_names = getattr(self, "_dashboard_checked", set())
        self._db_instance_drag_select = {
            "checked": item not in checked_names,
            "visited": {str(item)},
            "start": str(item),
            "last": str(item),
        }

    def _db_tree_items_between(self, tree, start_item, end_item):
        if not self._db_widget_exists(tree) or not start_item or not end_item:
            return []
        items = list(tree.get_children())
        start_item = str(start_item)
        end_item = str(end_item)
        if end_item not in items:
            return []
        if start_item not in items:
            return [end_item]
        s = items.index(start_item)
        e = items.index(end_item)
        if s > e:
            s, e = e, s
        return items[s : e + 1]

    def _db_autoscroll_tree(self, tree, event, margin=18):
        try:
            height = tree.winfo_height()
        except Exception:
            return
        if event.y < margin:
            tree.yview_scroll(-1, "units")
        elif event.y > max(margin, height - margin):
            tree.yview_scroll(1, "units")

    def _db_on_tree_drag(self, event):
        tree = getattr(self, "_db_tree", None)
        drag = getattr(self, "_db_instance_drag_select", None)
        if not self._db_widget_exists(tree) or not drag:
            return None
        self._db_autoscroll_tree(tree, event)
        item = tree.identify_row(event.y)
        if not item:
            return None
        visited = drag.setdefault("visited", set())
        checked = bool(drag.get("checked"))
        last = drag.get("last") or drag.get("start")
        for row_id in self._db_tree_items_between(tree, last, str(item)):
            if row_id and row_id not in visited and tree.exists(row_id):
                self._db_toggle_instance_checked(row_id, checked)
                visited.add(row_id)
        drag["last"] = str(item)
        tree.selection_set(item)
        self._dashboard_selected = str(item)
        self._db_on_select_instance()
        return "break"

    def _db_end_tree_drag(self, _event=None):
        self._db_instance_drag_select = None
        return None

    def _db_on_generic_tree_hover(self, event, tree, attr):
        if not self._db_widget_exists(tree):
            return None
        item = tree.identify_row(event.y)
        previous = getattr(self, attr, None)
        if item == previous:
            return None
        if previous and tree.exists(previous):
            tags = [t for t in tree.item(previous, "tags") if t != "hover"]
            tree.item(previous, tags=tags)
        if item and tree.exists(item):
            tags = list(tree.item(item, "tags"))
            if "hover" not in tags:
                tags.append("hover")
            tree.item(item, tags=tags)
        setattr(self, attr, item if item else None)
        return None

    def _db_on_generic_tree_leave(self, tree, attr):
        previous = getattr(self, attr, None)
        if self._db_widget_exists(tree) and previous and tree.exists(previous):
            tags = [t for t in tree.item(previous, "tags") if t != "hover"]
            tree.item(previous, tags=tags)
        setattr(self, attr, None)
        return None

    def _db_on_tree_hover(self, event):
        return self._db_on_generic_tree_hover(event, getattr(self, "_db_tree", None), "_db_tree_hover_item")

    def _db_on_tree_leave(self, _event=None):
        return self._db_on_generic_tree_leave(getattr(self, "_db_tree", None), "_db_tree_hover_item")

    def _db_toggle_instance_checked(self, name, checked=None):
        checked_names = getattr(self, "_dashboard_checked", set())
        if checked is None:
            checked = name not in checked_names
        if checked:
            checked_names.add(name)
        else:
            checked_names.discard(name)
        self._dashboard_checked = checked_names
        tree = getattr(self, "_db_tree", None)
        if self._db_widget_exists(tree) and tree.exists(name):
            self._db_apply_check_visual(tree, name, checked)
        self._db_update_checked_count()

    def _db_set_checked_instances(self, names):
        self._dashboard_checked = set(names or []) & set(self._db_device_names())
        tree = getattr(self, "_db_tree", None)
        if self._db_widget_exists(tree):
            for item in tree.get_children():
                self._db_apply_check_visual(tree, item, item in self._dashboard_checked)
        self._db_update_checked_count()

    def _db_select_all_visible_instances(self, _event=None):
        tree = getattr(self, "_db_tree", None)
        if not self._db_widget_exists(tree):
            return "break"
        self._db_set_checked_instances(
            set(getattr(self, "_dashboard_checked", set())) | set(tree.get_children())
        )
        return "break"

    def _db_clear_checked_instances(self):
        self._db_set_checked_instances(set())

    def _db_prepare_context_selection(self, item):
        if not item:
            return
        if item not in getattr(self, "_dashboard_checked", set()):
            self._db_set_checked_instances({item})
        tree = getattr(self, "_db_tree", None)
        if self._db_widget_exists(tree) and tree.exists(item):
            tree.selection_set(item)
            self._dashboard_selected = str(item)
            self._db_on_select_instance()

    def _db_build_instance_context_menu(self, parent):
        menu = tk.Menu(
            parent,
            tearoff=0,
            bg=self.palette.get("context_bg", "#343A40"),
            fg=self.palette.get("context_fg", "white"),
        )
        menu.add_command(label="Edit Account", command=self._db_edit_checked_account)
        menu.add_command(label="Add Page", command=self._db_add_page_to_checked)
        menu.add_command(label="Login", command=self._db_open_login_account_dialog)
        menu.add_command(label="Create Page", command=self._db_open_create_page_dialog)
        menu.add_separator()
        menu.add_command(label="Clear Account Data", command=self._db_clear_checked_account_data)
        menu.add_command(label="Remove Dashboard Data", command=self._db_delete_checked_dashboard_data)
        menu.add_separator()
        menu.add_command(label="Copy Instance Names", command=self._db_copy_checked_names)
        menu.add_command(label="Select All Visible", command=self._db_select_all_visible_instances)
        menu.add_command(label="Clear Selection", command=self._db_clear_checked_instances)
        return menu

    def _db_show_instance_context_menu(self, event):
        tree = getattr(self, "_db_tree", None)
        menu = getattr(self, "_db_context_menu", None)
        if not self._db_widget_exists(tree) or menu is None:
            return "break"
        item = tree.identify_row(event.y)
        if item:
            self._db_prepare_context_selection(item)
        if self._db_checked_names():
            menu.post(event.x_root, event.y_root)
        return "break"

    def _db_edit_checked_account(self):
        names = self._db_checked_names()
        if len(names) > 1:
            MessageBox.showinfo(
                "Edit Account",
                "Edit works on one LD instance at a time. Keep only one checkbox selected.",
                parent=self._db_message_parent(),
            )
            return
        if names:
            self._dashboard_selected = names[0]
        self._db_edit_account()

    def _db_add_page_to_checked(self):
        names = self._db_checked_names()
        if len(names) > 1:
            MessageBox.showinfo(
                "Add Page",
                "Add Page works on one LD instance at a time. Keep only one checkbox selected.",
                parent=self._db_message_parent(),
            )
            return
        if names:
            self._dashboard_selected = names[0]
        self._db_add_page()

    # ------------------------------------------------------------------
    # Create Page (Facebook Page automation)
    # ------------------------------------------------------------------

    _CREATE_PAGE_RANDOM_WORDS = (
        "Aurora",
        "Vertex",
        "Lumen",
        "Nimbus",
        "Cobalt",
        "Quartz",
        "Onyx",
        "Echo",
        "Atlas",
        "Pixel",
        "Nova",
        "Drift",
        "Hatch",
        "Spark",
        "Mango",
        "Harbor",
        "Summit",
        "Orbit",
        "Glow",
        "Ember",
        "Maple",
        "Lumio",
        "Forge",
        "Loop",
        "Tide",
        "Cipher",
        "Halo",
        "Brisk",
        "Solace",
        "Vibe",
    )

    _CREATE_PAGE_RANDOM_SUFFIXES = (
        "Studio",
        "Lab",
        "Hub",
        "House",
        "Co",
        "Works",
        "Daily",
        "Club",
        "Media",
        "World",
        "Spot",
        "Press",
        "Notes",
        "Society",
        "Stories",
    )

    def _db_random_page_name(self):
        import random

        word = random.choice(self._CREATE_PAGE_RANDOM_WORDS)
        suffix = random.choice(self._CREATE_PAGE_RANDOM_SUFFIXES)
        # Occasional numeric suffix to reduce collisions.
        if random.random() < 0.35:
            return f"{word} {suffix} {random.randint(10, 9999)}"
        return f"{word} {suffix}"

    def _db_open_create_page_dialog(self):
        names = self._db_checked_names()
        if not names:
            MessageBox.showinfo(
                "Create Page",
                "Select one or more instances first.",
                parent=self._db_message_parent(),
            )
            return

        multi_mode = len(names) > 1
        title_suffix = f"{len(names)} instances" if multi_mode else names[0]
        win = self._db_modal(f"Create Page · {title_suffix}", 640, 520 if multi_mode else 280)

        shell = tb.Frame(win, style="Card.TFrame", padding=18)
        shell.pack(fill="both", expand=True)

        head = tb.Frame(shell, style="CardInner.TFrame")
        head.pack(fill="x", pady=(0, 12))
        tb.Label(head, text="Create Facebook Page", style="SectionTitle.TLabel").pack(anchor="w")
        if multi_mode:
            subtitle = (
                f"Enter a page name for each of the {len(names)} selected LD instances. "
                "Use Random to fill any blank rows automatically."
            )
        else:
            subtitle = f"Set the page name for LD Instance · {names[0]}"
        tb.Label(head, text=subtitle, style="Subtitle.TLabel").pack(anchor="w", pady=(2, 0))

        # Optional shared category field.
        category_var = tk.StringVar(value="")
        cat_row = tb.Frame(shell, style="CardInner.TFrame")
        cat_row.pack(fill="x", pady=(0, 10))
        tb.Label(cat_row, text="Category (optional, applied to all):").pack(side="left")
        tb.Entry(cat_row, textvariable=category_var, width=32).pack(side="left", padx=(8, 0))

        name_vars: dict[str, tk.StringVar] = {}

        if multi_mode:
            list_frame = tb.Frame(shell, style="CardInner.TFrame")
            list_frame.pack(fill="both", expand=True)

            canvas = tk.Canvas(list_frame, bg=self.palette["surface"], highlightthickness=0)
            scroll_y = tb.Scrollbar(
                list_frame, orient="vertical", command=canvas.yview, style="Vertical.TScrollbar"
            )
            inner = tb.Frame(canvas, style="CardInner.TFrame")
            inner.bind(
                "<Configure>",
                lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
            )
            canvas.create_window((0, 0), window=inner, anchor="nw")
            canvas.configure(yscrollcommand=scroll_y.set)
            canvas.pack(side="left", fill="both", expand=True)
            scroll_y.pack(side="right", fill="y")

            header = tb.Frame(inner, style="CardInner.TFrame")
            header.pack(fill="x", pady=(0, 4))
            tb.Label(header, text="LD Instance", width=24, style="SectionTitle.TLabel").pack(side="left")
            tb.Label(header, text="Page Name", style="SectionTitle.TLabel").pack(side="left", padx=(8, 0))

            for ld_name in names:
                row = tb.Frame(inner, style="CardInner.TFrame")
                row.pack(fill="x", pady=2)
                tb.Label(row, text=ld_name, width=24).pack(side="left")
                var = tk.StringVar(value="")
                name_vars[ld_name] = var
                tb.Entry(row, textvariable=var, width=32).pack(side="left", padx=(8, 0))
                tb.Button(
                    row,
                    text="🎲",
                    width=3,
                    bootstyle="secondary-outline",
                    command=lambda v=var: v.set(self._db_random_page_name()),
                ).pack(side="left", padx=(6, 0))
        else:
            single_var = tk.StringVar(value="")
            name_vars[names[0]] = single_var
            row = tb.Frame(shell, style="CardInner.TFrame")
            row.pack(fill="x", pady=(0, 12))
            tb.Label(row, text="Page Name:", width=12).pack(side="left")
            tb.Entry(row, textvariable=single_var, width=36).pack(side="left", padx=(8, 0))
            tb.Button(
                row,
                text="🎲 Random",
                bootstyle="secondary-outline",
                command=lambda: single_var.set(self._db_random_page_name()),
            ).pack(side="left", padx=(6, 0))

        # Footer buttons
        footer = tb.Frame(shell, style="CardInner.TFrame")
        footer.pack(fill="x", pady=(12, 0))

        def fill_random_blanks():
            for var in name_vars.values():
                if not var.get().strip():
                    var.set(self._db_random_page_name())

        if multi_mode:
            tb.Button(
                footer,
                text="Random All Blanks",
                bootstyle="info-outline",
                command=fill_random_blanks,
            ).pack(side="left")

        def on_cancel():
            win.destroy()

        def on_create():
            assignments = []
            missing = []
            for ld_name in names:
                page_name = name_vars[ld_name].get().strip()
                if not page_name:
                    missing.append(ld_name)
                else:
                    assignments.append((ld_name, page_name))

            if missing:
                MessageBox.showwarning(
                    "Create Page",
                    f"Missing page name for: {', '.join(missing)}.\n\n"
                    "Type a name or click Random to fill blanks.",
                    parent=win,
                )
                return

            win.destroy()
            self._db_start_create_page_batch(assignments, category=category_var.get().strip())

        tb.Button(footer, text="Cancel", bootstyle="secondary", command=on_cancel).pack(
            side="right", padx=(6, 0)
        )
        tb.Button(footer, text="Create", bootstyle="primary", command=on_create).pack(side="right")

    def _db_start_create_page_batch(self, assignments, category=""):
        """Run the create_page task on each (ld_name, page_name) pair.

        For a single assignment we run inline in a thread (mirrors single-login).
        For multiple assignments we use the task_handler_factory + task_controller
        batch runner, same as multi-login.
        """
        assignments = [(str(n).strip(), str(p).strip()) for n, p in assignments if str(n or "").strip()]
        if not assignments:
            return

        if getattr(self, "running_event", None) is not None and self.running_event.is_set():
            MessageBox.showwarning(
                "Create Page",
                "Automation is already running. Stop it before starting a create-page task.",
                parent=self._db_message_parent(),
            )
            return

        if len(assignments) == 1:
            ld_name, page_name = assignments[0]
            self._db_start_single_create_page(ld_name, page_name, category)
            return

        self._db_start_multi_create_page(assignments, category)

    def _db_start_single_create_page(self, ld_name, page_name, category=""):
        try:
            from core.tasks.create_page import CreatePageTaskHandler
        except Exception as exc:
            MessageBox.showerror(
                "Create Page",
                f"Create-page task is not available: {exc}",
                parent=self._db_message_parent(),
            )
            return

        try:
            if hasattr(self, "automation_controller"):
                self.automation_controller.start()
            elif getattr(self, "running_event", None) is not None:
                self.running_event.set()
            if hasattr(self, "status_task_lbl"):
                self.status_task_lbl.set_status("Running", text="Tasks: 1 active")
            self.update_device_runtime_state(
                ld_name,
                {
                    "phase": "create_page",
                    "state": "Running",
                    "task": "Create Facebook Page",
                    "progress": 5,
                },
            )
        except Exception:
            pass

        handler = CreatePageTaskHandler(
            self.emulator,
            self.log,
            self.pause_event,
            lambda: self.running_event.is_set(),
        )
        handler.blocked_countries = [
            code.strip().upper()
            for code in self._db_var_value("blocked_countries", "").split(",")
            if code.strip()
        ]
        handler.auto_arrange_ld = bool(self._db_var_value("auto_arrange_ld", False))
        handler.state_callback = self.update_device_runtime_state

        payload = {"page_name": page_name, "category": category}

        def worker():
            success = False
            try:
                self.log(f"Starting create-page task for {ld_name} → '{page_name}'", "INFO")
                duration = int(self._db_var_value("task_duration", 5)) * 60
                success = bool(handler.execute(ld_name, duration=duration, **payload))
                self.log(
                    f"Create-page task {'completed' if success else 'failed'} for {ld_name}",
                    "SUCCESS" if success else "ERROR",
                )
                self.update_device_runtime_state(
                    ld_name,
                    {
                        "phase": "create_page",
                        "state": "Completed" if success else "Attention",
                        "task": "Create Facebook Page",
                        "progress": 100 if success else 0,
                    },
                )
            except Exception as exc:
                self.log(f"Create-page task error for {ld_name}: {exc}", "ERROR")
            finally:
                try:
                    self.stop_automation(confirm=False)
                except Exception:
                    if getattr(self, "running_event", None) is not None:
                        self.running_event.clear()

        threading.Thread(target=worker, daemon=True).start()

    def _db_start_multi_create_page(self, assignments, category=""):
        from services.task_handler_factory import TaskHandlerContext, UnsupportedTaskTypeError

        ld_names = [n for n, _ in assignments]
        page_name_by_ld = {n: p for n, p in assignments}

        try:
            blocked_countries = [
                code.strip().upper()
                for code in self._db_var_value("blocked_countries", "").split(",")
                if code.strip()
            ]
        except Exception:
            blocked_countries = []

        handler_context = TaskHandlerContext(
            emulator=self.emulator,
            log=self.log,
            pause_event=self.pause_event,
            running_flag=lambda: self.running_event.is_set(),
            blocked_countries=blocked_countries,
            auto_arrange_ld=bool(self._db_var_value("auto_arrange_ld", False)),
            state_callback=self.update_device_runtime_state,
        )

        try:
            task_handler = self.task_handler_factory.create("create_page", handler_context)
        except UnsupportedTaskTypeError as exc:
            MessageBox.showerror(
                "Create Page",
                f"Create-page handler is not registered: {exc}",
                parent=self._db_message_parent(),
            )
            return

        # Inject the per-LD page name lookup so the runner can pass each LD
        # its own page name when execute() is invoked.
        original_execute = task_handler.execute

        def execute_with_per_ld_name(name, duration=300, **kwargs):
            kwargs.setdefault("page_name", page_name_by_ld.get(name, ""))
            kwargs.setdefault("category", category)
            return original_execute(name, duration=duration, **kwargs)

        task_handler.execute = execute_with_per_ld_name

        parallel_ld = max(1, int(self._db_var_value("parallel_ld", 1) or 1))
        boot_delay = max(1, int(self._db_var_value("boot_delay", 20) or 20))
        task_duration_seconds = int(self._db_var_value("task_duration", 5) or 5) * 60

        request = self.task_controller.build_request(
            selected_ld_names=list(ld_names),
            task_type="create_page",
            task_template=str(self._db_var_value("task_template_var", "custom") or "custom"),
            parallel_ld=parallel_ld,
            start_same_time=bool(self._db_var_value("start_same_time", False)),
            auto_arrange_ld=bool(self._db_var_value("auto_arrange_ld", False)),
            boot_delay=boot_delay,
            task_duration_seconds=task_duration_seconds,
            max_videos=int(self._db_var_value("max_videos", 2) or 2),
            page_per_account=int(self._db_var_value("page_per_account", 2) or 2),
            accounts_per_ld=1,
            scroll_after_post=bool(self._db_var_value("scroll_after_post", True)),
            clear_cache=bool(self._db_var_value("clear_cache", True)),
            verify_account=bool(self._db_var_value("verify_account", True)),
            verify_2fa=bool(self._db_var_value("verify_2fa", True)),
        )

        try:
            self.automation_controller.start()
        except Exception:
            self.running_event.set()
        if hasattr(self, "status_task_lbl"):
            self.status_task_lbl.set_status("Running", text=f"Tasks: {len(ld_names)} active")
        self.log(f"Starting multi create-page on {len(ld_names)} LD(s)", "INFO")

        def worker():
            try:
                runner = self.task_controller.create_runner(
                    request=request,
                    running_flag=lambda: self.running_event.is_set(),
                    log_func=self.log,
                    task_handler=task_handler,
                    progress_callback=self.update_progress if hasattr(self, "update_progress") else None,
                    emulator=self.emulator,
                    state_callback=self.update_device_runtime_state,
                )
            except Exception as exc:
                self.log(f"Multi create-page setup error: {exc}", "ERROR")
                self.stop_automation(confirm=False)
                return

            def _on_error(exc):
                self.log(f"Multi create-page error: {exc}", "ERROR")

            def _on_completed(_completed):
                pass

            try:
                self.automation_controller.run_batch(runner, on_error=_on_error, on_completed=_on_completed)
            finally:
                try:
                    self.stop_automation(confirm=False)
                except Exception:
                    if getattr(self, "running_event", None) is not None:
                        self.running_event.clear()

        threading.Thread(target=worker, daemon=True).start()

    def _db_open_login_account_dialog(self):
        names = self._db_checked_names()
        if not names:
            MessageBox.showinfo(
                "Login", "Select one or more instances first.", parent=self._db_message_parent()
            )
            return
        if len(names) == 1:
            self._dashboard_selected = names[0]
        inst = self._db_selected_instance() if len(names) == 1 else None
        multi_mode = len(names) > 1

        title_suffix = f"{len(names)} instances" if multi_mode else (inst.get("name") if inst else "")
        win = self._db_modal(f"Login Account · {title_suffix}", 920, 640)
        shell = tb.Frame(win, style="Card.TFrame", padding=18)
        shell.pack(fill="both", expand=True)

        head = tb.Frame(shell, style="CardInner.TFrame")
        head.pack(fill="x", pady=(0, 12))
        tb.Label(head, text="Login Account", style="SectionTitle.TLabel").pack(anchor="w")
        if multi_mode:
            subtitle = (
                f"Multi-login on {len(names)} LDs. Check at least {len(names)} accounts; "
                "each LD will consume one account. Common settings (Parallel Devices, "
                "Auto Arrange, Clear Cache) apply."
            )
        else:
            subtitle = f"Choose or import credentials for LD Instance · {inst.get('name')}"
        tb.Label(head, text=subtitle, style="Subtitle.TLabel").pack(anchor="w", pady=(2, 0))

        cols = ("name", "uid", "email", "password", "twofa")
        self._db_login_checked_account_id = None
        self._db_login_checked_account_ids = set()
        tree = tb.Treeview(
            shell,
            columns=cols,
            show="tree headings",
            height=13,
            style="Custom.Treeview",
            selectmode="extended",
        )
        tree.heading("#0", text="", anchor="center")
        tree.column("#0", width=42, minwidth=42, stretch=False, anchor="center")
        for col, width, title in (
            ("name", 160, "Name"),
            ("uid", 180, "UID"),
            ("email", 220, "Email"),
            ("password", 150, "Password"),
            ("twofa", 260, "2FA"),
        ):
            tree.heading(col, text=title, anchor="w")
            tree.column(col, width=width, anchor="w")
        configure_status_tree_tags(tree, self.palette, include_zebra=True)
        tree.tag_configure(
            "hover",
            background=self.palette.get("hover_bg", self.palette["surface_alt"]),
        )

        scroll = tb.Scrollbar(shell, orient="vertical", command=tree.yview, style="Vertical.TScrollbar")
        scroll.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(fill="both", expand=True)
        self._db_login_hover_item = None
        tree.bind("<Button-1>", lambda event: self._db_on_login_account_click(event, tree), add="+")
        tree.bind("<B1-Motion>", lambda event: self._db_on_login_account_drag(event, tree), add="+")
        tree.bind("<ButtonRelease-1>", lambda event: self._db_end_login_account_drag(event), add="+")
        tree.bind(
            "<Motion>",
            lambda event: self._db_on_generic_tree_hover(event, tree, "_db_login_hover_item"),
            add="+",
        )
        tree.bind(
            "<Leave>", lambda event: self._db_on_generic_tree_leave(tree, "_db_login_hover_item"), add="+"
        )

        def refresh(select_id=None):
            for item in tree.get_children():
                tree.delete(item)
            for idx, account in enumerate(self._db_login_accounts()):
                account_id = str(account.get("account_id") or self._db_account_row_id(account))
                tree.insert(
                    "",
                    "end",
                    iid=account_id,
                    values=(
                        str(account.get("name") or ""),
                        str(account.get("uid") or ""),
                        str(account.get("email") or ""),
                        "••••••••" if account.get("password") else "",
                        str(account.get("twofa") or ""),
                    ),
                    tags=("even_row" if idx % 2 == 0 else "odd_row",),
                )
                self._db_apply_check_visual(
                    tree, account_id, account_id in self._db_login_checked_account_ids
                )
            if select_id and tree.exists(select_id):
                tree.selection_set(select_id)
                tree.focus(select_id)
                self._db_set_login_account_checked(tree, select_id)

        def selected_account():
            account_id = self._db_first_checked_login_account_id(tree)
            if not account_id:
                MessageBox.showinfo("Login Account", "Check an account first.", parent=win)
                return None
            return self._db_get_login_account(str(account_id))

        def delete_selected():
            account_ids = self._db_checked_login_account_ids(tree)
            if not account_ids:
                MessageBox.showinfo("Delete Accounts", "Check one or more accounts first.", parent=win)
                return
            if not MessageBox.askyesno(
                "Delete Accounts",
                f"Delete {len(account_ids)} selected account(s) from the login list?",
                parent=win,
            ):
                return
            removed = self._db_delete_login_accounts(account_ids)
            self._db_login_checked_account_ids.difference_update(account_ids)
            self._db_sync_login_account_primary_id(tree)
            refresh()
            self._db_status(f"Deleted {removed} login account(s)", self.palette["success"])

        def use_selected():
            account = selected_account()
            if not account:
                return
            self._db_assign_login_account_to_instance(inst, account)
            self._db_mark_dirty()
            self._db_save_all()
            self._db_render_all()
            self._db_status(f"Login account assigned to {inst.get('name')}", self.palette["success"])
            win.destroy()
            self._db_start_login_account_task(inst, account)

        def run_multi():
            checked_ids = self._db_checked_login_account_ids(tree)
            if len(checked_ids) < len(names):
                MessageBox.showwarning(
                    "Login Account",
                    f"Need at least {len(names)} checked accounts; only {len(checked_ids)} selected.",
                    parent=win,
                )
                return
            accounts = [self._db_get_login_account(str(account_id)) for account_id in checked_ids]
            accounts = [a for a in accounts if a]
            if len(accounts) < len(names):
                MessageBox.showwarning(
                    "Login Account",
                    "Some checked accounts could not be loaded.",
                    parent=win,
                )
                return
            win.destroy()
            self._db_start_multi_login_batch(list(names), accounts[: len(names)])

        footer = tb.Frame(win, style="CardInner.TFrame", padding=(18, 12))
        footer.pack(fill="x", side="bottom")
        tb.Button(
            footer,
            text="Import Text",
            bootstyle="info-outline",
            command=lambda: self._db_import_login_accounts_text(refresh, win),
            width=13,
        ).pack(side="left")
        tb.Button(
            footer,
            text="Import File",
            bootstyle="info-outline",
            command=lambda: self._db_import_login_accounts_file(refresh, win),
            width=12,
        ).pack(side="left", padx=(6, 0))
        tb.Button(
            footer,
            text="Add Account",
            bootstyle="success-outline",
            command=lambda: self._db_add_login_account(refresh, win),
            width=13,
        ).pack(side="left", padx=(6, 0))
        tb.Button(
            footer, text="Delete Selected", bootstyle="danger-outline", command=delete_selected, width=15
        ).pack(side="left", padx=(6, 0))
        tb.Button(footer, text="Cancel", bootstyle="secondary-outline", command=win.destroy, width=10).pack(
            side="right"
        )
        if multi_mode:
            tb.Button(
                footer,
                text=f"Run Login on {len(names)} LDs",
                bootstyle="primary",
                command=run_multi,
                width=22,
            ).pack(side="right", padx=(0, 6))
        else:
            tb.Button(footer, text="Use Account", bootstyle="primary", command=use_selected, width=12).pack(
                side="right", padx=(0, 6)
            )

        refresh()

    def _db_login_accounts(self):
        try:
            path = self._db_login_accounts_path()
            if not path.exists():
                return []
            loaded = json.loads(path.read_text(encoding="utf-8")) or []
            if not isinstance(loaded, list):
                return []
            records = [self._db_normalize_login_account(row) for row in loaded if isinstance(row, dict)]

            plaintext_present = has_plaintext_secrets(records)
            needs_rewrite = False
            for record in records:
                account_id = str(record.get("account_id") or "").strip()
                if not account_id:
                    continue
                if plaintext_present:
                    migrated = migrate_legacy_plaintext(account_id, record)
                    if migrated:
                        needs_rewrite = True
                        _logger.info(
                            "[credential-migration] moved %s for login account %s into the OS credential vault",
                            ", ".join(migrated.keys()),
                            account_id,
                        )
                hydrate_secrets(account_id, record)

            if needs_rewrite:
                try:
                    self._db_write_login_accounts_redacted(records)
                except OSError as exc:
                    _logger.warning(
                        "[credential-migration] could not rewrite %s: %s",
                        path,
                        exc,
                    )
            return records
        except Exception as exc:
            try:
                self.log(f"Failed to load login accounts: {exc}", "ERROR")
            except Exception:
                pass
            return []

    def _db_write_login_accounts_redacted(self, records):
        rows = []
        for record in records or []:
            account_id = str(record.get("account_id") or "").strip()
            if account_id:
                # On rewrite-after-migration, keyring holds the truth — redact everything.
                rows.append(redacted_copy(record, persisted_fields={f: True for f in SECRET_ACCOUNT_FIELDS}))
            else:
                rows.append(dict(record))
        self._db_login_accounts_path().write_text(
            json.dumps(rows, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _db_account_row_id(self, account):
        return str(account.get("account_id") or account.get("uid") or account.get("email") or "account")

    def _db_get_login_account(self, account_id):
        for account in self._db_login_accounts():
            if self._db_account_row_id(account) == account_id:
                return account
        return {}

    def _db_set_login_account_checked(self, tree, account_id):
        if isinstance(account_id, (set, list, tuple)):
            checked_ids = {str(item) for item in account_id if str(item or "")}
        else:
            account_id = str(account_id or "")
            checked_ids = {account_id} if account_id else set()
        self._db_login_checked_account_ids = checked_ids
        self._db_sync_login_account_primary_id(tree)
        for item in tree.get_children():
            self._db_apply_check_visual(tree, item, item in self._db_login_checked_account_ids)
        first_id = getattr(self, "_db_login_checked_account_id", None)
        if first_id and tree.exists(first_id):
            try:
                tree.selection_set(tuple(self._db_checked_login_account_ids(tree)))
            except Exception:
                tree.selection_set(first_id)
            tree.focus(first_id)

    def _db_toggle_login_account_checked(self, tree, account_id):
        account_id = str(account_id or "")
        checked_ids = set(getattr(self, "_db_login_checked_account_ids", set()))
        if account_id in checked_ids:
            checked_ids.remove(account_id)
        else:
            checked_ids.add(account_id)
        self._db_set_login_account_checked(tree, checked_ids)

    def _db_set_login_account_item_checked(self, tree, account_id, checked):
        account_id = str(account_id or "")
        if not account_id:
            return
        checked_ids = set(getattr(self, "_db_login_checked_account_ids", set()))
        if checked:
            checked_ids.add(account_id)
        else:
            checked_ids.discard(account_id)
        self._db_login_checked_account_ids = checked_ids
        if self._db_widget_exists(tree) and tree.exists(account_id):
            self._db_apply_check_visual(tree, account_id, checked)
        self._db_sync_login_account_primary_id(tree)

    def _db_checked_login_account_ids(self, tree=None):
        checked_ids = set(getattr(self, "_db_login_checked_account_ids", set()))
        if tree is not None:
            return [item for item in tree.get_children() if item in checked_ids]
        return sorted(checked_ids)

    def _db_first_checked_login_account_id(self, tree=None):
        checked_ids = self._db_checked_login_account_ids(tree)
        return checked_ids[0] if checked_ids else None

    def _db_sync_login_account_primary_id(self, tree=None):
        self._db_login_checked_account_id = self._db_first_checked_login_account_id(tree)
        return self._db_login_checked_account_id

    def _db_on_login_account_click(self, event, tree):
        item = tree.identify_row(event.y)
        if not item:
            return None
        self._db_begin_login_account_drag(item)
        region = tree.identify_region(event.x, event.y)
        column = tree.identify_column(event.x)
        if region == "tree" or column == "#0":
            self._db_toggle_login_account_checked(tree, item)
            return "break"
        return None

    def _db_begin_login_account_drag(self, item):
        checked_ids = set(getattr(self, "_db_login_checked_account_ids", set()))
        self._db_login_drag_select = {
            "checked": str(item) not in checked_ids,
            "visited": {str(item)},
            "start": str(item),
            "last": str(item),
        }

    def _db_on_login_account_drag(self, event, tree):
        drag = getattr(self, "_db_login_drag_select", None)
        if not self._db_widget_exists(tree) or not drag:
            return None
        self._db_autoscroll_tree(tree, event)
        item = tree.identify_row(event.y)
        if not item:
            return None
        visited = drag.setdefault("visited", set())
        checked = bool(drag.get("checked"))
        last = drag.get("last") or drag.get("start")
        for row_id in self._db_tree_items_between(tree, last, str(item)):
            if row_id and row_id not in visited and tree.exists(row_id):
                self._db_set_login_account_item_checked(tree, row_id, checked)
                visited.add(row_id)
        drag["last"] = str(item)
        tree.selection_set(tuple(self._db_checked_login_account_ids(tree)))
        tree.focus(item)
        return "break"

    def _db_end_login_account_drag(self, _event=None):
        self._db_login_drag_select = None
        return None

    def _db_delete_login_accounts(self, account_ids):
        account_ids = {str(account_id) for account_id in account_ids if str(account_id or "")}
        if not account_ids:
            return 0
        accounts = self._db_login_accounts()
        kept: list[dict] = []
        deleted_account_ids: list[str] = []
        for account in accounts:
            row_id = str(account.get("account_id") or self._db_account_row_id(account))
            if row_id in account_ids:
                actual_id = str(account.get("account_id") or "").strip()
                if actual_id:
                    deleted_account_ids.append(actual_id)
            else:
                kept.append(account)
        removed = len(accounts) - len(kept)

        # Persist + redact remaining accounts via the same path as save.
        rows_to_write: list[dict] = []
        for record in kept:
            account_id = str(record.get("account_id") or "").strip()
            if not account_id:
                rows_to_write.append(dict(record))
                continue
            persisted = persist_secrets(account_id, record)
            rows_to_write.append(redacted_copy(record, persisted_fields=persisted))
        self._db_login_accounts_path().write_text(
            json.dumps(rows_to_write, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        for account_id in deleted_account_ids:
            delete_secrets(account_id)
        return removed

    def _db_assign_login_account_to_instance(self, instance, account):
        acc = instance.setdefault("account", {})
        pages = self._db_account_pages(acc)
        # Prefer the Facebook display name (e.g. "Christopher M. Luu") so the
        # dashboard surfaces the human name; fall back to email/uid only if
        # the display name is missing on the source record.
        acc.update(
            {
                "name": (
                    str(account.get("name") or "").strip()
                    or str(account.get("email") or account.get("uid") or "").strip()
                    or None
                ),
                "uid": str(account.get("uid") or "").strip() or None,
                "password": str(account.get("password") or "").strip() or None,
                "twofa": str(account.get("twofa") or account.get("2fa") or "").strip() or None,
                "mail": str(account.get("email") or "").strip() or None,
                "pages": pages,
            }
        )

    def _db_start_login_account_task(self, instance, account):
        ld_name = str((instance or {}).get("name") or "").strip()
        if not ld_name:
            MessageBox.showwarning(
                "Login Account", "LD instance name is missing.", parent=self._db_message_parent()
            )
            return

        if getattr(self, "running_event", None) is not None and self.running_event.is_set():
            MessageBox.showwarning(
                "Login Account",
                "Automation is already running. Stop it before starting a login task.",
                parent=self._db_message_parent(),
            )
            return

        uid = str(account.get("uid") or "").strip()
        email = str(account.get("email") or "").strip()
        identifier = uid or email
        password = str(account.get("password") or "").strip()
        if not identifier or not password:
            MessageBox.showwarning(
                "Login Account",
                "Selected account needs UID/email and password.",
                parent=self._db_message_parent(),
            )
            return

        try:
            from core.tasks.login_account import LoginAccountTaskHandler
        except Exception as exc:
            MessageBox.showerror(
                "Login Account", f"Login task is not available: {exc}", parent=self._db_message_parent()
            )
            return

        try:
            if hasattr(self, "automation_controller"):
                self.automation_controller.start()
            elif getattr(self, "running_event", None) is not None:
                self.running_event.set()
            if hasattr(self, "status_task_lbl"):
                self.status_task_lbl.set_status("Running", text="Tasks: 1 active")
            self.update_device_runtime_state(
                ld_name,
                {
                    "phase": "login",
                    "state": "Running",
                    "task": "Facebook login",
                    "progress": 10,
                },
            )
        except Exception:
            pass

        handler = LoginAccountTaskHandler(
            self.emulator,
            self.log,
            self.pause_event,
            lambda: self.running_event.is_set(),
        )
        handler.blocked_countries = [
            code.strip().upper()
            for code in self._db_var_value("blocked_countries", "").split(",")
            if code.strip()
        ]
        handler.auto_arrange_ld = bool(self._db_var_value("auto_arrange_ld", False))
        handler.state_callback = self.update_device_runtime_state

        payload = {
            "identifier": identifier,
            "identifier_label": "uid" if uid else "email",
            "account_name": str(account.get("name") or "").strip(),
            "email": email,
            "password": password,
            "twofa": str(account.get("twofa") or "").strip(),
            "twofa_secret": str(account.get("twofa") or "").strip(),
            "clear_before_login": True,
            "verify_2fa": bool(account.get("twofa")) or bool(self._db_var_value("verify_account", True)),
        }

        def worker():
            success = False
            try:
                self.log(f"Starting login task for {ld_name}", "INFO")
                duration = int(self._db_var_value("task_duration", 5)) * 60
                success = bool(handler.execute(ld_name, duration=duration, **payload))
                self.log(
                    f"Login task {'completed' if success else 'failed'} for {ld_name}",
                    "SUCCESS" if success else "ERROR",
                )

                # If the handler renamed the LD instance to the Facebook
                # display name, sync the dashboard JSON so the persisted
                # instance entry matches what dnconsole now reports.
                new_ld_name = getattr(handler, "last_renamed_to", "") or ""
                if success and new_ld_name and new_ld_name != ld_name:
                    try:
                        instance["name"] = new_ld_name
                        self._db_write_data()
                        self._db_status(
                            f"Renamed instance → {new_ld_name}",
                            self.palette["success"],
                        )
                    except Exception as exc:
                        self.log(
                            f"Failed to persist renamed instance for {ld_name}: {exc}",
                            "WARNING",
                        )

                self.update_device_runtime_state(
                    new_ld_name or ld_name,
                    {
                        "phase": "login",
                        "state": "Completed" if success else "Attention",
                        "task": "Facebook login",
                        "progress": 100 if success else 0,
                    },
                )
            except Exception as exc:
                self.log(f"Login task error for {ld_name}: {exc}", "ERROR")
                self.update_device_runtime_state(
                    ld_name,
                    {
                        "phase": "login",
                        "state": "Attention",
                        "task": "Login error",
                        "progress": 0,
                    },
                )
            finally:
                try:
                    if hasattr(self, "performance_monitor"):
                        self.performance_monitor.end_task_timer(success)
                except Exception:
                    pass
                try:
                    self.stop_automation(confirm=False)
                except Exception:
                    if getattr(self, "running_event", None) is not None:
                        self.running_event.clear()

        try:
            if hasattr(self, "performance_monitor"):
                self.performance_monitor.start_task_timer("dashboard_login_account")
        except Exception:
            pass
        threading.Thread(target=worker, daemon=True).start()

    def _db_start_multi_login_batch(self, ld_names, accounts):
        if not ld_names or not accounts:
            return
        if getattr(self, "running_event", None) is not None and self.running_event.is_set():
            MessageBox.showwarning(
                "Login Account",
                "Automation is already running. Stop it before starting a login batch.",
                parent=self._db_message_parent(),
            )
            return

        from services.task_handler_factory import TaskHandlerContext, UnsupportedTaskTypeError

        try:
            blocked_countries = [
                code.strip().upper()
                for code in self._db_var_value("blocked_countries", "").split(",")
                if code.strip()
            ]
        except Exception:
            blocked_countries = []

        handler_context = TaskHandlerContext(
            emulator=self.emulator,
            log=self.log,
            pause_event=self.pause_event,
            running_flag=lambda: self.running_event.is_set(),
            blocked_countries=blocked_countries,
            auto_arrange_ld=bool(self._db_var_value("auto_arrange_ld", False)),
            state_callback=self.update_device_runtime_state,
            verify_account=bool(self._db_var_value("verify_account", True)),
            scroll_after_post=bool(self._db_var_value("scroll_after_post", True)),
            clear_cache=bool(self._db_var_value("clear_cache", True)),
        )

        try:
            task_handler = self.task_handler_factory.create("login", handler_context)
        except UnsupportedTaskTypeError as exc:
            MessageBox.showerror(
                "Login Account", f"Login handler is not registered: {exc}", parent=self._db_message_parent()
            )
            return

        parallel_ld = max(1, int(self._db_var_value("parallel_ld", 1) or 1))
        boot_delay = max(1, int(self._db_var_value("boot_delay", 20) or 20))
        task_duration_seconds = int(self._db_var_value("task_duration", 5) or 5) * 60

        request = self.task_controller.build_request(
            selected_ld_names=list(ld_names),
            task_type="login",
            task_template=str(self._db_var_value("task_template_var", "custom") or "custom"),
            parallel_ld=parallel_ld,
            start_same_time=bool(self._db_var_value("start_same_time", False)),
            auto_arrange_ld=bool(self._db_var_value("auto_arrange_ld", False)),
            boot_delay=boot_delay,
            task_duration_seconds=task_duration_seconds,
            max_videos=int(self._db_var_value("max_videos", 2) or 2),
            page_per_account=int(self._db_var_value("page_per_account", 2) or 2),
            accounts_per_ld=1,
            scroll_after_post=bool(self._db_var_value("scroll_after_post", True)),
            clear_cache=bool(self._db_var_value("clear_cache", True)),
            verify_account=bool(self._db_var_value("verify_account", True)),
            accounts_pool=list(accounts),
            verify_2fa=bool(self._db_var_value("verify_2fa", True)),
        )

        try:
            self.automation_controller.start()
        except Exception:
            self.running_event.set()
        if hasattr(self, "status_task_lbl"):
            self.status_task_lbl.set_status("Running", text=f"Tasks: {len(ld_names)} active")
        self.log(f"Starting multi-login on {len(ld_names)} LD(s) with {len(accounts)} account(s)", "INFO")

        def worker():
            try:
                runner = self.task_controller.create_runner(
                    request=request,
                    running_flag=lambda: self.running_event.is_set(),
                    log_func=self.log,
                    task_handler=task_handler,
                    progress_callback=self.update_progress if hasattr(self, "update_progress") else None,
                    emulator=self.emulator,
                    state_callback=self.update_device_runtime_state,
                )
            except Exception as exc:
                self.log(f"Multi-login setup error: {exc}", "ERROR")
                self.stop_automation(confirm=False)
                return

            def _on_error(exc):
                self.log(f"Multi-login error: {exc}", "ERROR")

            def _on_completed(_completed):
                pass

            try:
                self.automation_controller.run_batch(runner, on_error=_on_error, on_completed=_on_completed)
            finally:
                try:
                    self.stop_automation(confirm=False)
                except Exception:
                    if getattr(self, "running_event", None) is not None:
                        self.running_event.clear()

        threading.Thread(target=worker, daemon=True).start()

    def _db_var_value(self, attr_name, default=None):
        value = getattr(self, attr_name, default)
        if hasattr(value, "get"):
            try:
                return value.get()
            except Exception:
                return default
        return value

    def _db_parse_login_account_lines(self, text):
        accounts = []
        for raw_line in str(text or "").splitlines():
            line = raw_line.rstrip("\r\n").strip()
            if not line:
                continue
            lower = line.lower()
            if (
                lower.startswith("name,")
                or lower.startswith("name\t")
                or lower.startswith("uid,")
                or lower.startswith("uid\t")
                or lower.startswith("facebook_uid,")
                or lower.startswith("facebook_uid\t")
            ):
                continue
            if "\t" in line:
                parts = [part.strip() for part in line.split("\t")]
            elif "," in line:
                parts = [part.strip() for part in line.split(",")]
            else:
                parts = [part.strip() for part in re.split(r"\s{2,}", line)]
            if len(parts) < 4:
                continue
            if len(parts) == 4:
                name = ""
                uid, password, email, twofa = parts
            else:
                name, uid, password, email = parts[:4]
                twofa = parts[4]
            if not (uid or email) or not password:
                continue
            accounts.append(
                self._db_normalize_login_account(
                    {
                        "name": name,
                        "uid": uid,
                        "password": password,
                        "email": email,
                        "twofa": twofa,
                    }
                )
            )
        return accounts

    def _db_normalize_login_account(self, account):
        uid = str(account.get("uid") or account.get("facebook_uid") or "").strip()
        email = str(account.get("email") or account.get("mail") or "").strip()
        password = str(account.get("password") or "").strip()
        twofa = str(account.get("twofa") or account.get("2fa") or "").strip()
        name = str(account.get("name") or "").strip()
        account_id = str(account.get("account_id") or uid or email).strip()
        normalized = {
            "account_id": account_id,
            "uid": uid,
            "password": password,
            "email": email,
            "twofa": twofa,
        }
        if name:
            normalized["name"] = name
        return normalized

    def _db_save_login_accounts(self, accounts):
        existing_accounts = self._db_login_accounts()
        by_key = {}
        for account in existing_accounts:
            key = self._db_login_account_key(account)
            if key:
                by_key[key] = account

        saved = []
        for account in accounts:
            clean = self._db_normalize_login_account(account)
            if not (clean["uid"] or clean["email"]) or not clean["password"]:
                continue
            key = self._db_login_account_key(clean)
            by_key[key] = clean
            saved.append(clean)

        records = sorted(by_key.values(), key=lambda row: (row.get("email") or "", row.get("uid") or ""))
        rows_to_write: list[dict] = []
        for record in records:
            account_id = str(record.get("account_id") or "").strip()
            if not account_id:
                rows_to_write.append(dict(record))
                continue
            persisted = persist_secrets(account_id, record)
            if any(not ok for ok in persisted.values()):
                _logger.warning(
                    "[credential-migration] keyring write failed for some fields of login account %s; "
                    "they remain as plaintext in accounts_login.json",
                    account_id,
                )
            rows_to_write.append(redacted_copy(record, persisted_fields=persisted))
        self._db_login_accounts_path().write_text(
            json.dumps(rows_to_write, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return saved

    def _db_login_account_key(self, account):
        uid = str(account.get("uid") or "").strip()
        email = str(account.get("email") or "").strip()
        return uid or email

    def _db_import_login_accounts_text(self, refresh, parent):
        win = self._db_modal("Import Login Accounts", 640, 420)
        if parent is not None:
            try:
                win.transient(parent)
            except Exception:
                pass
        body = tb.Frame(win, style="Card.TFrame", padding=18)
        body.pack(fill="both", expand=True)
        tb.Label(body, text="Import Login Accounts", style="SectionTitle.TLabel").pack(anchor="w")
        tb.Label(
            body,
            text="Format per line: Name<TAB or ,>UID<TAB or ,>Password<TAB or ,>email<TAB or ,>2fa",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 10))
        text = tk.Text(
            body,
            height=10,
            bg=self.palette["surface_alt"],
            fg=self.palette["text"],
            insertbackground=self.palette["primary"],
            relief="flat",
            font=(self.mono_font, 10),
            wrap="none",
            highlightthickness=1,
            highlightbackground=self.palette["border"],
        )
        text.pack(fill="both", expand=True)
        text.insert("1.0", "Name,UID,Password,email@example.com,2FA SECRET")

        def commit():
            accounts = self._db_parse_login_account_lines(text.get("1.0", "end"))
            if not accounts:
                MessageBox.showwarning("Import Login Accounts", "No valid account lines found.", parent=win)
                return
            saved = self._db_save_login_accounts(accounts)
            refresh(str(saved[-1].get("account_id") or "") if saved else None)
            self._db_status(f"Imported {len(saved)} login account(s)", self.palette["success"])
            win.destroy()

        footer = tb.Frame(win, style="CardInner.TFrame", padding=(18, 12))
        footer.pack(fill="x", side="bottom")
        tb.Button(footer, text="Cancel", bootstyle="secondary-outline", command=win.destroy, width=10).pack(
            side="left"
        )
        tb.Button(footer, text="Import", bootstyle="primary", command=commit, width=10).pack(side="right")

    def _db_import_login_accounts_file(self, refresh, parent):
        file_path = filedialog.askopenfilename(
            parent=parent,
            title="Import Login Accounts",
            filetypes=[("Text / CSV", "*.txt *.csv"), ("All Files", "*.*")],
        )
        if not file_path:
            return
        try:
            text = open(file_path, "r", encoding="utf-8-sig").read()
        except OSError as exc:
            MessageBox.showerror("Import Login Accounts", str(exc), parent=parent)
            return
        accounts = self._db_parse_login_account_lines(text)
        if not accounts:
            MessageBox.showwarning("Import Login Accounts", "No valid account lines found.", parent=parent)
            return
        saved = self._db_save_login_accounts(accounts)
        refresh(str(saved[-1].get("account_id") or "") if saved else None)
        self._db_status(f"Imported {len(saved)} login account(s)", self.palette["success"])

    def _db_add_login_account(self, refresh, parent):
        win = self._db_modal("Add Login Account", 540, 420)
        if parent is not None:
            try:
                win.transient(parent)
            except Exception:
                pass
        form = tb.Frame(win, style="Card.TFrame", padding=22)
        form.pack(fill="both", expand=True)
        tb.Label(form, text="Add Login Account", style="SectionTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        tb.Label(form, text="Credentials used by the Login task.", style="Subtitle.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(2, 14)
        )

        vars_map = {
            "uid": tk.StringVar(),
            "password": tk.StringVar(),
            "email": tk.StringVar(),
            "twofa": tk.StringVar(),
            "name": tk.StringVar(),
        }
        fields = [
            ("UID", "uid", False),
            ("Password", "password", True),
            ("Email", "email", False),
            ("2FA", "twofa", False),
            ("Name", "name", False),
        ]
        for row, (label, key, secret) in enumerate(fields, start=2):
            tb.Label(form, text=label.upper(), style="MetricLabel.TLabel").grid(
                row=row, column=0, sticky="w", padx=(0, 16), pady=8
            )
            tb.Entry(
                form, textvariable=vars_map[key], bootstyle="secondary", show="*" if secret else ""
            ).grid(row=row, column=1, sticky="ew", pady=8, ipady=3)
        form.columnconfigure(1, weight=1)

        def commit():
            payload = {key: var.get().strip() for key, var in vars_map.items()}
            if not (payload["uid"] or payload["email"]) or not payload["password"]:
                MessageBox.showwarning(
                    "Add Login Account", "UID or email plus password is required.", parent=win
                )
                return
            saved = self._db_save_login_accounts([payload])
            refresh(str(saved[-1].get("account_id") or "") if saved else None)
            self._db_status("Login account added", self.palette["success"])
            win.destroy()

        footer = tb.Frame(win, style="CardInner.TFrame", padding=(18, 12))
        footer.pack(fill="x", side="bottom")
        tb.Button(footer, text="Cancel", bootstyle="secondary-outline", command=win.destroy, width=10).pack(
            side="left"
        )
        tb.Button(footer, text="Save", bootstyle="primary", command=commit, width=10).pack(side="right")

    def _db_clear_checked_account_data(self):
        instances = self._db_checked_instances()
        if not instances:
            MessageBox.showinfo(
                "Clear Account Data", "Select one or more instances first.", parent=self._db_message_parent()
            )
            return
        label = f"{len(instances)} selected instance{'s' if len(instances) != 1 else ''}"
        if not MessageBox.askyesno(
            "Clear Account Data",
            f"Clear Facebook account and page data for {label}?",
            parent=self._db_message_parent(),
        ):
            return
        for inst in instances:
            inst["account"] = self._db_blank_instance(inst.get("name") or "")["account"]
        self._db_mark_dirty()
        self._db_save_all()
        self._db_render_all()

    def _db_delete_checked_dashboard_data(self):
        names = set(self._db_checked_names())
        if not names:
            MessageBox.showinfo(
                "Remove Dashboard Data",
                "Select one or more instances first.",
                parent=self._db_message_parent(),
            )
            return
        if not MessageBox.askyesno(
            "Remove Dashboard Data",
            f"Remove saved dashboard data for {len(names)} selected instance(s)?\n\nThe LDPlayer instances are not deleted.",
            parent=self._db_message_parent(),
        ):
            return
        self._dashboard_data["instances"] = [
            inst for inst in self._db_instances() if inst.get("name") not in names
        ]
        if self._dashboard_selected in names:
            self._dashboard_selected = None
        self._db_clear_checked_instances()
        self._db_mark_dirty()
        self._db_save_all()
        self._db_sync_from_devices()
        self._db_render_all()

    def _db_copy_checked_names(self):
        names = self._db_checked_names()
        if not names:
            return
        parent = self._db_message_parent()
        if parent is None:
            return
        parent.clipboard_clear()
        parent.clipboard_append("\n".join(names))
        self._db_status(f"Copied {len(names)} instance name(s)", self.palette["success"])

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
            live = self._db_instances_by_name().get(str(data.get("name") or ""))
            target = live if live is not None else data
            target["account"] = {
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
        tb.Button(footer, text="Cancel", bootstyle="secondary-outline", command=win.destroy, width=10).pack(
            side="left"
        )
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
            live_inst = self._db_instances_by_name().get(str(inst.get("name") or ""))
            target_pages = (
                self._db_account_pages(live_inst.setdefault("account", {}))
                if live_inst is not None
                else pages
            )
            if is_new:
                target_pages.append(payload)
            else:
                if 0 <= idx < len(target_pages):
                    target_pages[idx].update(payload)
                else:
                    target_pages.append(payload)
            self._db_mark_dirty()
            self._db_save_all()
            self._db_render_all()
            win.destroy()

        footer = tb.Frame(win, style="CardInner.TFrame", padding=(18, 12))
        footer.pack(fill="x", side="bottom")
        tb.Button(footer, text="Cancel", bootstyle="secondary-outline", command=win.destroy, width=10).pack(
            side="left"
        )
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

        tb.Label(body, text="HASHTAGS (COMMA SEPARATED)", style="MetricLabel.TLabel").pack(
            anchor="w", pady=(0, 4)
        )
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
        tb.Button(footer, text="Cancel", bootstyle="secondary-outline", command=win.destroy, width=10).pack(
            side="left"
        )
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
