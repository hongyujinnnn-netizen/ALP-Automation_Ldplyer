import tkinter as tk
from tkinter import filedialog, messagebox as MessageBox

import ttkbootstrap as tb

from gui.components.scrollable_frame import ScrollableFrame
from gui.components.state_views import StateView
from gui.components.status import (
    StatusPill,
    configure_status_tree_tags,
    normalize_status,
    status_color,
    status_count_text,
    status_label,
    status_table_text,
    status_tag,
)


class _AccountOverviewItem:
    """Tiny shim that mimics MetricCard.set(value, subtitle=...) for the
    compact overview strip — only the value is displayed; subtitle is ignored.

    Stores the accent color so it can be re-asserted on every refresh; some
    ttk themes try to repaint tk widgets on theme changes and we want the
    colored count to stay visible regardless.
    """

    __slots__ = ("_label", "_color")

    def __init__(self, label, color):
        self._label = label
        self._color = color

    def set(self, value, subtitle=None):
        if self._label.winfo_exists():
            self._label.configure(text=str(value), foreground=self._color)


class AccountDialogMixin:
    def create_account_hub_tab(self):
        tab = tb.Frame(self.notebook, style="CardInner.TFrame")
        self.notebook.add(tab, text="Account")
        self._account_host = tab
        self._account_dialog = None
        self._build_account_surface(tab, embedded=True)
        self._refresh_account_tree()

    def show_account_manager(self):
        if hasattr(self, "notebook"):
            try:
                self.notebook.select(4)
                self._on_notebook_tab_changed()
                self.request_embedded_account_refresh()
                return
            except Exception:
                pass

        win = getattr(self, "_account_dialog", None)
        if win is not None and win.winfo_exists():
            win.focus()
            return

        win = tk.Toplevel(self.root)
        win.title("Account Manager")
        win.geometry("1280x860")
        win.minsize(980, 620)
        win.transient(self.root)
        win.grab_set()
        win.configure(bg=self.palette["surface"])
        self._account_host = None
        self._account_dialog = win
        self._build_account_surface(win, embedded=False)
        self._refresh_account_tree()

    # ─────────────────────────────────────────────────────────────────── #
    # Layout

    def _build_account_surface(self, parent, embedded=False):
        self._account_embedded = embedded
        self._acct_sort_by_var = tk.StringVar(value="Created")
        self._acct_sort_order_var = tk.StringVar(value="Descending")
        self._acct_status_filter_var = tk.StringVar(value="All")
        self._acct_search_var = tk.StringVar()

        scroller = ScrollableFrame(parent, bg=self.palette["surface"])
        scroller.pack(fill="both", expand=True, padx=2)
        body = scroller.body

        # Filters
        filters = self._create_card_section(
            body,
            "Filters",
            "Search, narrow by status, and control the sort order of the account list.",
            pady=(0, 12),
        )
        self._build_account_filters(filters)

        # Accounts table
        list_card = self._create_card_section(
            body,
            "Accounts",
            "Right click a row for quick edit, delete, and info actions.",
            expand=True,
            pady=(0, 8),
        )
        self._build_account_table(list_card)

        # Compact overview strip — right-aligned beneath the account list
        self._build_account_overview_strip(body)

        # Actions footer
        actions = self._create_card_section(
            body,
            "Actions",
            "Refresh, import, or export the accounts visible in the list.",
            pady=(0, 0),
        )
        self._build_account_actions(actions, embedded=embedded)

    # ─────────────────────────────────────────────────────────────────── #
    # Compact overview strip

    def _build_account_overview_strip(self, parent):
        """Tiny right-aligned summary line beneath the account list.

        Replaces the old Account Overview metric-card hero. Each entry is a
        colored dot + label + count, separated by thin dividers.
        """
        strip = tb.Frame(parent, style="CardInner.TFrame")
        strip.pack(fill="x", pady=(0, 8))

        right = tb.Frame(strip, style="CardInner.TFrame")
        right.pack(side="right")

        # (key, label, accent hex from palette, bootstyle for tb.Label fallback)
        specs = [
            ("active", "Live",      self.palette["success"],                    "success"),
            ("idle",   "Idle",      self.palette.get("muted", "#64748B"),       "secondary"),
            ("novery", "No Verify", self.palette["warning"],                    "warning"),
            ("dead",   "Dead",      self.palette["danger"],                     "danger"),
            ("total",  "Total",     self.palette["primary"],                    "info"),
        ]

        bg_color = self.palette["surface"]
        muted = self.palette.get("muted", "#64748B")

        self._acct_metric_cards = {}
        for idx, (key, label, accent, _bootstyle) in enumerate(specs):
            if idx > 0:
                divider = tk.Label(
                    right,
                    text="·",
                    font=(self.mono_font, 9),
                )
                divider.configure(bg=bg_color, fg=muted)
                divider.pack(side="left", padx=4)

            item = tk.Frame(right, bg=bg_color)
            item.pack(side="left")

            dot = tk.Label(item, text="●", font=(self.mono_font, 9))
            dot.configure(bg=bg_color, fg=accent)
            dot.pack(side="left")

            name_lbl = tk.Label(item, text=label, font=(self.mono_font, 9, "bold"))
            name_lbl.configure(bg=bg_color, fg=accent)
            name_lbl.pack(side="left", padx=(4, 4))

            value_lbl = tk.Label(item, text="0", font=(self.mono_font, 10, "bold"))
            value_lbl.configure(bg=bg_color, fg=accent)
            value_lbl.pack(side="left")

            self._acct_metric_cards[key] = _AccountOverviewItem(value_lbl, accent)

    # ─────────────────────────────────────────────────────────────────── #
    # Filters

    def _build_account_filters(self, parent):
        row = tb.Frame(parent, style="CardInner.TFrame")
        row.pack(fill="x")

        tb.Label(row, text="SEARCH", style="MetricLabel.TLabel").pack(side="left", padx=(0, 8))
        self._acct_search_var.trace_add("write", lambda *_: self._refresh_account_tree())
        tb.Entry(
            row,
            textvariable=self._acct_search_var,
            bootstyle="secondary",
        ).pack(side="left", fill="x", expand=True)

        tb.Label(row, text="STATUS", style="MetricLabel.TLabel").pack(side="left", padx=(14, 6))
        tb.Combobox(
            row,
            textvariable=self._acct_status_filter_var,
            values=("All", "Live", "Idle", status_label("novery"), "Dead", "Unknown"),
            state="readonly",
            width=12,
            bootstyle="secondary",
        ).pack(side="left")
        self._acct_status_filter_var.trace_add("write", lambda *_: self._refresh_account_tree())

        tb.Label(row, text="SORT", style="MetricLabel.TLabel").pack(side="left", padx=(14, 6))
        tb.Combobox(
            row,
            textvariable=self._acct_sort_by_var,
            values=("Created", "Updated", "Name", "Status", "Instance"),
            state="readonly",
            width=12,
            bootstyle="secondary",
        ).pack(side="left")
        self._acct_sort_by_var.trace_add("write", lambda *_: self._refresh_account_tree())

        tb.Combobox(
            row,
            textvariable=self._acct_sort_order_var,
            values=("Descending", "Ascending"),
            state="readonly",
            width=12,
            bootstyle="secondary",
        ).pack(side="left", padx=(6, 0))
        self._acct_sort_order_var.trace_add("write", lambda *_: self._refresh_account_tree())

    # ─────────────────────────────────────────────────────────────────── #
    # Accounts table

    def _build_account_table(self, parent):
        self._account_empty_view = StateView(
            parent,
            kind="empty",
            title="No accounts yet",
            message="Create a new account or import from a JSON/CSV file to populate the list.",
            palette=self.palette,
            display_font=self.display_font,
            mono_font=self.mono_font,
            actions=[
                {"text": "New Account", "command": self._create_new_account, "bootstyle": "outline-success"},
                {"text": "Import", "command": self._import_accounts, "bootstyle": "outline-info"},
            ],
        )
        self._account_empty_view.pack(fill="x", pady=(0, 10))

        cols = ("num", "uid", "name", "gender", "contact", "instance", "status", "created")
        tree = tb.Treeview(parent, columns=cols, show="headings", height=16, style="Custom.Treeview")
        self._account_tree = tree
        for col, width, title in (
            ("num", 42, "#"),
            ("uid", 170, "UID"),
            ("name", 160, "Account"),
            ("gender", 80, "Gender"),
            ("contact", 170, "Phone / Email"),
            ("instance", 150, "LD Instance"),
            ("status", 90, "Status"),
            ("created", 140, "Created"),
        ):
            tree.heading(col, text=title, anchor="w")
            tree.column(col, width=width, anchor="w")

        configure_status_tree_tags(tree, self.palette, include_zebra=False)
        # Account list uses foreground-only highlighting: clear any backgrounds
        # set by the shared helper and disable zebra striping on this tree.
        # Multiple specs share the same tag (e.g. both "live" and "active" map
        # to tag "active"); skip duplicates so earlier specs win — matching the
        # de-dup behavior in configure_status_tree_tags.
        from gui.components.status import STATUS_SPECS
        configured_tags = set()
        for spec in STATUS_SPECS.values():
            if spec.tag in configured_tags:
                continue
            configured_tags.add(spec.tag)
            tree.tag_configure(spec.tag, background="", foreground=status_color(spec.key, self.palette))
        tree.tag_configure("odd_row", background="")
        tree.tag_configure("even_row", background="")
        # Extra tags not covered by the shared helper.
        for key in ("live", "idle", "novery", "dead", "unknown"):
            tree.tag_configure(key, background="", foreground=status_color(key, self.palette))

        scrollbar = tb.Scrollbar(parent, orient="vertical", command=tree.yview, style="Vertical.TScrollbar")
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(fill="both", expand=True)
        tree.bind("<<TreeviewSelect>>", self._on_account_selection_changed)
        tree.bind("<Button-3>", self._show_account_context_menu)

        self._account_context_menu = tk.Menu(parent, tearoff=0)
        self._account_context_menu.add_command(label="Edit", command=self._edit_selected_account)
        self._account_context_menu.add_command(label="Delete", command=self._delete_selected_account)
        self._account_context_menu.add_separator()
        self._account_context_menu.add_command(label="Info", command=self._view_selected_account_info)

    # ─────────────────────────────────────────────────────────────────── #
    # Actions footer

    def _build_account_actions(self, parent, embedded=False):
        row = tb.Frame(parent, style="CardInner.TFrame")
        row.pack(fill="x")

        tb.Button(
            row,
            text="New",
            bootstyle="success",
            command=self._create_new_account,
            width=10,
        ).pack(side="left", padx=(0, 6))
        tb.Button(
            row,
            text="Import",
            bootstyle="info-outline",
            command=self._import_accounts,
            width=10,
        ).pack(side="left", padx=(0, 6))
        tb.Button(
            row,
            text="Export",
            bootstyle="secondary-outline",
            command=self._export_accounts,
            width=10,
        ).pack(side="left")

        tb.Button(
            row,
            text="Refresh",
            bootstyle="primary-outline",
            command=self._refresh_accounts,
            width=10,
        ).pack(side="right")
        if not embedded:
            tb.Button(
                row,
                text="Close",
                bootstyle="danger-outline",
                command=self._close_account_dialog,
                width=10,
            ).pack(side="right", padx=(0, 6))

    # ─────────────────────────────────────────────────────────────────── #
    # Status helpers

    def _account_status_key(self, status):
        key = normalize_status(status)
        if key == "live":
            return "active"
        return "unknown" if key == "error" else key

    def _account_display_status_key(self, status):
        key = self._account_status_key(status)
        return "live" if key == "active" else key

    def _account_filter_status_key(self, status):
        key = normalize_status(status)
        return "active" if key == "live" else key

    # ─────────────────────────────────────────────────────────────────── #
    # Dialog lifecycle

    def _close_account_dialog(self):
        win = getattr(self, "_account_dialog", None)
        if win is not None and win.winfo_exists():
            win.destroy()
        self._account_dialog = None

    def _on_account_selection_changed(self, _event=None):
        return

    def _refresh_accounts(self):
        try:
            if hasattr(self.account_manager, "load_accounts"):
                self.account_manager.accounts = self.account_manager.load_accounts()
        except Exception as exc:
            self.log(f"Failed to refresh accounts: {exc}", "ERROR")
            return

        self._refresh_account_tree()
        self.log("Account Manager refreshed", "INFO")

    def _get_tree_selected_uid(self):
        tree = getattr(self, "_account_tree", None)
        if not tree:
            return ""
        selection = tree.selection()
        return str(selection[0]) if selection else ""

    def _show_account_context_menu(self, event):
        tree = getattr(self, "_account_tree", None)
        menu = getattr(self, "_account_context_menu", None)
        if not tree or not menu:
            return
        item = tree.identify_row(event.y)
        if not item:
            return
        tree.selection_set(item)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _create_new_account(self):
        self._open_account_editor({})

    def _edit_selected_account(self):
        uid = self._get_tree_selected_uid()
        if not uid:
            self.log("Select an account first.", "WARNING")
            return
        account = self.account_manager.get_account(uid)
        if not account:
            self.log("Account not found.", "WARNING")
            return
        self._open_account_editor(account)

    def _view_selected_account_info(self):
        uid = self._get_tree_selected_uid()
        if not uid:
            self.log("Select an account first.", "WARNING")
            return
        account = self.account_manager.get_account(uid)
        if not account:
            self.log("Account not found.", "WARNING")
            return
        self._open_account_info_dialog(account)

    def _delete_selected_account(self):
        uid = self._get_tree_selected_uid()
        if not uid:
            self.log("Select an account to delete first.", "WARNING")
            return

        account = self.account_manager.get_account(uid)
        name = str(account.get("name") or account.get("email") or account.get("phone") or uid)
        instance = str(account.get("instance") or account.get("device_name") or account.get("ld_name") or "")
        if not MessageBox.askyesno(
            "Confirm Delete",
            f"Delete account '{name}' from '{instance or 'unassigned'}'?",
            parent=self._account_message_parent(),
        ):
            return

        try:
            self.account_manager.remove_account(uid)
        except Exception as exc:
            self.log(f"Failed to delete account: {exc}", "ERROR")
            return

        self.log(f"Account deleted: {name}", "INFO")
        self._refresh_account_tree()

    # ─────────────────────────────────────────────────────────────────── #
    # Info dialog

    def _open_account_info_dialog(self, account):
        win = tk.Toplevel(self.root)
        win.title("Account Info")
        win.geometry("480x420")
        win.resizable(False, False)
        win.transient(self._account_message_parent())
        win.grab_set()
        win.configure(bg=self.palette["surface"])

        card = tb.Frame(win, style="Card.TFrame", padding=20)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        tb.Label(card, text="Account Info", style="SectionTitle.TLabel").pack(anchor="w")
        tb.Label(
            card,
            text=account.get("name") or account.get("facebook_uid") or "—",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 12))

        status_key = self._account_display_status_key(account.get("status") or "idle")
        StatusPill(
            card,
            status_key,
            palette=self.palette,
            text=status_label(status_key),
            font=(self.mono_font, 9, "bold"),
            padx=10,
            pady=4,
        ).pack(anchor="w", pady=(0, 12))

        rows = [
            ("Name", account.get("name")),
            ("Gender", account.get("gender")),
            ("Phone", account.get("phone")),
            ("Email", account.get("email")),
            ("LD Instance", account.get("instance") or account.get("device_name") or account.get("ld_name")),
            ("ADB Serial", account.get("ld_adb")),
            ("Created", account.get("created_at")),
            ("Updated", account.get("updated_at")),
            ("Notes", account.get("notes")),
        ]
        for label, value in rows:
            row = tb.Frame(card, style="CardInner.TFrame")
            row.pack(fill="x", pady=3)
            tb.Label(row, text=label.upper(), style="MetricLabel.TLabel").pack(side="left")
            tb.Label(
                row,
                text=str(value) if value else "—",
                style="MetricSub.TLabel",
                anchor="e",
            ).pack(side="right")

        footer = tb.Frame(card, style="CardInner.TFrame")
        footer.pack(fill="x", pady=(14, 0))
        tb.Button(footer, text="Close", bootstyle="secondary-outline", command=win.destroy, width=10).pack(side="right")

    # ─────────────────────────────────────────────────────────────────── #
    # Editor

    def _open_account_editor(self, account):
        is_edit = bool(account.get("account_id"))
        win = tk.Toplevel(self.root)
        win.title("Edit Account" if is_edit else "New Account")
        win.geometry("560x620")
        win.resizable(False, False)
        win.transient(self._account_message_parent())
        win.grab_set()
        win.configure(bg=self.palette["surface"])

        vars_map = {
            "name": tk.StringVar(value=str(account.get("name") or "")),
            "gender": tk.StringVar(value=str(account.get("gender") or "")),
            "phone": tk.StringVar(value=str(account.get("phone") or "")),
            "email": tk.StringVar(value=str(account.get("email") or "")),
            "password": tk.StringVar(value=str(account.get("password") or "")),
            "instance": tk.StringVar(
                value=str(account.get("instance") or account.get("device_name") or account.get("ld_name") or "")
            ),
            "ld_adb": tk.StringVar(value=str(account.get("ld_adb") or "")),
            "status": tk.StringVar(value=status_label(self._account_display_status_key(account.get("status") or "idle"))),
        }

        card = tb.Frame(win, style="Card.TFrame", padding=22)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        tb.Label(
            card,
            text="Edit Account" if is_edit else "New Account",
            style="SectionTitle.TLabel",
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        tb.Label(
            card,
            text="Update credentials, status, and linked LD instance for this account.",
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 14))

        fields = [
            ("Name", "name"),
            ("Gender", "gender"),
            ("Phone", "phone"),
            ("Email", "email"),
            ("Password", "password"),
            ("LD Instance", "instance"),
            ("ADB Serial", "ld_adb"),
            ("Status", "status"),
        ]
        for row, (label, key) in enumerate(fields, start=2):
            tb.Label(card, text=label.upper(), style="MetricLabel.TLabel").grid(
                row=row, column=0, sticky="w", padx=(0, 16), pady=8
            )
            if key == "gender":
                widget = tb.Combobox(
                    card,
                    textvariable=vars_map[key],
                    values=("", "Female", "Male"),
                    state="readonly",
                    bootstyle="secondary",
                )
            elif key == "status":
                widget = tb.Combobox(
                    card,
                    textvariable=vars_map[key],
                    values=("Live", "Idle", status_label("novery"), "Dead", "Unknown"),
                    state="readonly",
                    bootstyle="secondary",
                )
            else:
                widget = tb.Entry(
                    card,
                    textvariable=vars_map[key],
                    bootstyle="secondary",
                    show="*" if key == "password" else "",
                )
            widget.grid(row=row, column=1, sticky="ew", pady=8, ipady=3)

        notes_row = len(fields) + 2
        tb.Label(card, text="NOTES", style="MetricLabel.TLabel").grid(
            row=notes_row, column=0, sticky="nw", padx=(0, 16), pady=8
        )
        notes_text = tk.Text(
            card,
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
        notes_text.grid(row=notes_row, column=1, sticky="nsew", pady=8)
        notes_text.insert("1.0", str(account.get("notes") or ""))

        card.columnconfigure(1, weight=1)
        card.rowconfigure(notes_row, weight=1)

        footer = tb.Frame(card, style="CardInner.TFrame")
        footer.grid(row=notes_row + 1, column=0, columnspan=2, sticky="ew", pady=(14, 0))

        def save_account():
            payload = {key: var.get().strip() for key, var in vars_map.items()}
            payload["status"] = self._account_filter_status_key(payload.get("status") or "idle")
            payload["notes"] = notes_text.get("1.0", "end").strip()
            if not payload["name"] and not payload["email"] and not payload["phone"]:
                self.log("Name, phone, or email is required.", "WARNING")
                return
            if not payload["phone"] and not payload["email"]:
                self.log("At least one contact field is required.", "WARNING")
                return

            try:
                if is_edit:
                    saved = self.account_manager.update_account(str(account["account_id"]), payload)
                    self.log(f"Account updated: {saved.get('name') or saved.get('facebook_uid')}", "SUCCESS")
                else:
                    saved = self.account_manager.create_account(payload)
                    self.log(f"Account added: {saved.get('name') or saved.get('facebook_uid')}", "SUCCESS")
            except Exception as exc:
                self.log(f"Failed to save account: {exc}", "ERROR")
                return

            self._refresh_account_tree(select_uid=str(saved.get("account_id") or saved.get("facebook_uid") or ""))
            win.destroy()

        tb.Button(footer, text="Cancel", bootstyle="secondary-outline", command=win.destroy, width=10).pack(side="left")
        tb.Button(footer, text="Save", bootstyle="primary", command=save_account, width=10).pack(side="right")

    # ─────────────────────────────────────────────────────────────────── #
    # Import / export

    def _import_accounts(self):
        file_path = filedialog.askopenfilename(
            parent=self._account_message_parent(),
            title="Import Accounts",
            filetypes=[
                ("Account Files", "*.json *.csv"),
                ("JSON Files", "*.json"),
                ("CSV Files", "*.csv"),
                ("All Files", "*.*"),
            ],
        )
        if not file_path:
            return

        try:
            imported = self.account_manager.import_accounts(file_path)
        except Exception as exc:
            self.log(f"Failed to import accounts: {exc}", "ERROR")
            return

        self.log(f"Imported {imported} account(s) from {file_path}", "SUCCESS")
        self._refresh_account_tree()

    def _export_accounts(self):
        file_path = filedialog.asksaveasfilename(
            parent=self._account_message_parent(),
            title="Export Accounts",
            defaultextension=".csv",
            filetypes=[
                ("CSV Files", "*.csv"),
                ("Text Files", "*.txt"),
                ("PDF Files", "*.pdf"),
                ("JSON Files", "*.json"),
            ],
        )
        if not file_path:
            return

        try:
            exported = self.account_manager.export_accounts(file_path, rows=self._get_visible_accounts())
        except Exception as exc:
            self.log(f"Failed to export accounts: {exc}", "ERROR")
            return

        self.log(f"Accounts exported to {exported}", "SUCCESS")

    # ─────────────────────────────────────────────────────────────────── #
    # Data

    def _get_visible_accounts(self):
        query = getattr(self, "_acct_search_var", tk.StringVar()).get().strip().lower()
        status_filter_raw = getattr(self, "_acct_status_filter_var", tk.StringVar(value="All")).get().strip()
        status_filter = "all" if status_filter_raw.lower() == "all" else self._account_filter_status_key(status_filter_raw)
        sort_by = getattr(self, "_acct_sort_by_var", tk.StringVar(value="Created")).get().strip().lower()
        descending = getattr(self, "_acct_sort_order_var", tk.StringVar(value="Descending")).get().strip().lower() != "ascending"
        try:
            accounts = self.account_manager.list_accounts()
        except Exception as exc:
            self.log(f"Failed to load accounts: {exc}", "ERROR")
            return []

        visible_accounts = []
        for acc in accounts:
            uid = str(acc.get("facebook_uid") or "")
            name = str(acc.get("name") or acc.get("username") or acc.get("email") or "account")
            gender = str(acc.get("gender") or "")
            instance = str(acc.get("instance") or acc.get("device_name") or acc.get("ld_name") or "")
            contact = str(acc.get("phone") or acc.get("email") or "")
            haystack = f"{uid} {name} {gender} {instance} {contact} {acc.get('notes', '')}".lower()
            status = self._account_status_key(acc.get("status") or "idle")
            if query and query not in haystack:
                continue
            if status_filter != "all" and self._account_status_key(status) != status_filter:
                continue
            visible_accounts.append(acc)

        key_map = {
            "created": lambda row: str(row.get("created_at") or ""),
            "updated": lambda row: str(row.get("updated_at") or ""),
            "name": lambda row: str(row.get("name") or row.get("username") or "").lower(),
            "status": lambda row: str(row.get("status") or "").lower(),
            "instance": lambda row: str(row.get("instance") or row.get("device_name") or "").lower(),
        }
        sort_key = key_map.get(sort_by, key_map["created"])
        visible_accounts.sort(key=sort_key, reverse=descending)
        return visible_accounts

    def _refresh_account_tree(self, select_uid=None):
        tree = getattr(self, "_account_tree", None)
        if not tree:
            return

        for item in tree.get_children():
            tree.delete(item)

        try:
            accounts = self._get_visible_accounts()
            summary = self.account_manager.get_account_summary()
        except Exception as exc:
            self.log(f"Failed to load accounts: {exc}", "ERROR")
            accounts = []
            summary = {"active": 0, "idle": 0, "novery": 0, "dead": 0, "unknown": 0, "total": 0}

        visible_index = 0
        selected_uid = None
        for acc in accounts:
            account_id = str(acc.get("account_id") or "")
            uid = str(acc.get("facebook_uid") or "")
            name = str(acc.get("name") or acc.get("username") or acc.get("email") or "account")
            gender = str(acc.get("gender") or "")
            status = self._account_status_key(acc.get("status") or "idle")
            display_status = self._account_display_status_key(status)
            instance = str(acc.get("instance") or acc.get("device_name") or acc.get("ld_name") or "")
            contact = str(acc.get("phone") or acc.get("email") or "")
            created = str(acc.get("created_at") or "").replace("T", " ")

            visible_index += 1
            tags = [status_tag(display_status), display_status]
            tags.append("even" if visible_index % 2 == 0 else "odd")
            tree.insert(
                "",
                "end",
                iid=account_id,
                values=(
                    f"{visible_index:02d}",
                    uid,
                    name,
                    gender,
                    contact,
                    instance,
                    status_table_text(display_status),
                    created,
                ),
                tags=tuple(tags),
            )
            if select_uid and (uid == select_uid or account_id == select_uid):
                selected_uid = account_id

        # Update metric cards
        cards = getattr(self, "_acct_metric_cards", {}) or {}
        if cards:
            cards["active"].set(summary.get("active", 0), subtitle=status_count_text("live", summary.get("active", 0)))
            cards["idle"].set(summary.get("idle", 0), subtitle=status_count_text("idle", summary.get("idle", 0)))
            cards["novery"].set(summary.get("novery", 0), subtitle=status_count_text("novery", summary.get("novery", 0)))
            cards["dead"].set(summary.get("dead", 0), subtitle=status_count_text("dead", summary.get("dead", 0)))
            cards["total"].set(summary.get("total", 0), subtitle="All accounts tracked")

        # Empty-state visibility
        empty_view = getattr(self, "_account_empty_view", None)
        if empty_view is not None:
            if visible_index == 0:
                empty_view.pack(fill="x", pady=(0, 10))
            else:
                empty_view.pack_forget()

        if selected_uid and tree.exists(selected_uid):
            tree.selection_set(selected_uid)
            tree.focus(selected_uid)

    def _account_message_parent(self):
        win = getattr(self, "_account_dialog", None)
        if win is not None and win.winfo_exists():
            return win
        host = getattr(self, "_account_host", None)
        if host is not None and host.winfo_exists():
            try:
                return host.winfo_toplevel()
            except Exception:
                return host
        return self.root

    def request_embedded_account_refresh(self):
        host = getattr(self, "_account_host", None)
        if host is None or not host.winfo_exists():
            return
        self._refresh_account_tree()
