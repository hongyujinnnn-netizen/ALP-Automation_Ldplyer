import tkinter as tk
from tkinter import filedialog

import ttkbootstrap as tb


class AccountDialogMixin:
    _ACCOUNT_ACCENT = "#F97316"
    _ACCOUNT_ACCENT_SOFT = "#FDBA74"
    _ACCOUNT_SUCCESS = "#22C55E"
    _ACCOUNT_DANGER = "#EF4444"
    _ACCOUNT_WARNING = "#F59E0B"
    _ACCOUNT_INFO = "#38BDF8"
    _ACCOUNT_BG = "#0F172A"
    _ACCOUNT_CARD = "#111827"
    _ACCOUNT_CARD_ALT = "#172033"
    _ACCOUNT_TEXT = "#F8FAFC"
    _ACCOUNT_MUTED = "#94A3B8"
    _ACCOUNT_HOVER = "#24324A"
    _ACCOUNT_ROW_ALT = "#0B1220"

    def show_account_manager(self):
        win = getattr(self, "_account_dialog", None)
        if win is not None and win.winfo_exists():
            win.focus()
            return

        win = tk.Toplevel(self.root)
        win.title("Account Manager")
        win.geometry("1280x980")
        win.minsize(820, 520)
        win.transient(self.root)
        win.grab_set()
        win.configure(bg=self._ACCOUNT_BG)
        self._account_dialog = win
        self._acct_sort_by_var = tk.StringVar(value="Created")
        self._acct_sort_order_var = tk.StringVar(value="Descending")

        self._configure_account_tree_style()

        header = tk.Frame(
            win,
            bg=self._ACCOUNT_CARD,
            highlightthickness=1,
            highlightbackground=self._ACCOUNT_ACCENT,
        )
        header.pack(fill="x")
        accent_bar = tk.Frame(header, bg=self._ACCOUNT_ACCENT, height=4)
        accent_bar.pack(fill="x", side="top")
        header_body = tk.Frame(header, bg=self._ACCOUNT_CARD, padx=18, pady=16)
        header_body.pack(fill="x")
        header_left = tk.Frame(header_body, bg=self._ACCOUNT_CARD)
        header_left.pack(side="left", fill="x", expand=True)
        tk.Label(
            header_left,
            text="Account Studio",
            bg=self._ACCOUNT_CARD,
            fg=self._ACCOUNT_TEXT,
            font=(self.display_font, 18, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header_left,
            text="Search, sort, edit, and export account inventory from one place.",
            bg=self._ACCOUNT_CARD,
            fg=self._ACCOUNT_MUTED,
            font=(self.mono_font, 10),
        ).pack(anchor="w", pady=(4, 0))
        hero_badge = tk.Label(
            header_body,
            text="Right click rows for quick actions",
            bg=self._ACCOUNT_ACCENT,
            fg=self._ACCOUNT_BG,
            font=(self.mono_font, 10, "bold"),
            padx=12,
            pady=8,
        )
        hero_badge.pack(side="right", padx=(12, 0))

        body = tk.Frame(win, bg=self._ACCOUNT_BG, padx=16, pady=12)
        body.pack(fill="both", expand=True)

        pill_row = tk.Frame(body, bg=self._ACCOUNT_BG)
        pill_row.pack(fill="x", pady=(0, 12))
        self._acct_pill_active = self._pill(pill_row, "0 Active", self._ACCOUNT_SUCCESS)
        self._acct_pill_idle = self._pill(pill_row, "0 Idle", self._ACCOUNT_MUTED)
        self._acct_pill_error = self._pill(pill_row, "0 Error", self._ACCOUNT_DANGER)
        self._acct_pill_novery = self._pill(pill_row, "0 Novery", self._ACCOUNT_WARNING)
        self._acct_pill_dead = self._pill(pill_row, "0 Dead", self._ACCOUNT_INFO)
        self._acct_pill_total = self._pill(pill_row, "0 Total", self._ACCOUNT_ACCENT, right=True)

        controls = tk.Frame(
            body,
            bg=self._ACCOUNT_CARD_ALT,
            highlightthickness=1,
            highlightbackground=self._ACCOUNT_HOVER,
            padx=14,
            pady=14,
        )
        controls.pack(fill="x", pady=(0, 12))
        search_bar = tk.Frame(
            controls,
            bg=self._ACCOUNT_BG,
            highlightthickness=1,
            highlightbackground=self._ACCOUNT_ACCENT,
        )
        search_bar.pack(side="left", fill="x", expand=True)
        self._acct_search_var = tk.StringVar()
        self._acct_search_var.trace_add("write", lambda *_: self._refresh_account_tree())
        tk.Label(
            search_bar,
            text="Search",
            bg=self._ACCOUNT_CARD,
            fg=self._ACCOUNT_MUTED,
            font=(self.mono_font, 10),
            padx=12,
        ).pack(side="left")
        tk.Entry(
            search_bar,
            textvariable=self._acct_search_var,
            bg=self._ACCOUNT_CARD,
            fg=self._ACCOUNT_TEXT,
            insertbackground=self._ACCOUNT_ACCENT,
            relief="flat",
            font=(self.mono_font, 11),
            highlightthickness=1,
            highlightbackground=self._ACCOUNT_ACCENT,
            highlightcolor=self._ACCOUNT_ACCENT,
        ).pack(side="left", fill="x", expand=True, pady=12, padx=(0, 12))

        self._acct_status_filter_var = tk.StringVar(value="All")
        tb.Combobox(
            controls,
            textvariable=self._acct_status_filter_var,
            values=("All", "Active", "Idle", "Error", "Novery", "Dead", "Unknown"),
            state="readonly",
            width=12,
        ).pack(side="left", padx=(10, 0))
        self._acct_status_filter_var.trace_add("write", lambda *_: self._refresh_account_tree())
        tk.Label(
            controls,
            text="Sort",
            bg=self._ACCOUNT_CARD_ALT,
            fg=self._ACCOUNT_MUTED,
            font=(self.mono_font, 10),
            padx=10,
        ).pack(side="left")
        tb.Combobox(
            controls,
            textvariable=self._acct_sort_by_var,
            values=("Created", "Updated", "Name", "Status", "Instance"),
            state="readonly",
            width=12,
        ).pack(side="left")
        self._acct_sort_by_var.trace_add("write", lambda *_: self._refresh_account_tree())
        tb.Combobox(
            controls,
            textvariable=self._acct_sort_order_var,
            values=("Descending", "Ascending"),
            state="readonly",
            width=12,
        ).pack(side="left", padx=(10, 0))
        self._acct_sort_order_var.trace_add("write", lambda *_: self._refresh_account_tree())

        list_frame = tk.Frame(
            body,
            bg=self._ACCOUNT_CARD,
            highlightthickness=1,
            highlightbackground=self._ACCOUNT_ACCENT,
            padx=12,
            pady=12,
        )
        list_frame.pack(fill="both", expand=True)

        cols = ("num", "uid", "name", "gender", "contact", "instance", "status", "created")
        tree = tb.Treeview(list_frame, columns=cols, show="headings", height=18, style="Custom.Treeview")
        self._account_tree = tree
        for col, width, title in (
            ("num", 42, "#"),
            ("uid", 180, "UID"),
            ("name", 170, "Account"),
            ("gender", 90, "Gender"),
            ("contact", 180, "Phone / Email"),
            ("instance", 160, "LD Instance"),
            ("status", 90, "Status"),
            ("created", 150, "Created"),
        ):
            tree.heading(col, text=title, anchor="w")
            tree.column(col, width=width, anchor="w")

        tree.tag_configure("active", foreground=self._ACCOUNT_SUCCESS)
        tree.tag_configure("idle", foreground=self._ACCOUNT_MUTED)
        tree.tag_configure("error", foreground=self._ACCOUNT_DANGER)
        tree.tag_configure("novery", foreground=self._ACCOUNT_WARNING)
        tree.tag_configure("dead", foreground=self._ACCOUNT_INFO)
        tree.tag_configure("even", background=self._ACCOUNT_CARD)
        tree.tag_configure("odd", background=self._ACCOUNT_ROW_ALT)
        scrollbar = tb.Scrollbar(list_frame, orient="vertical", command=tree.yview, style="Vertical.TScrollbar")
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(fill="both", expand=True)
        tree.bind("<<TreeviewSelect>>", self._on_account_selection_changed)
        tree.bind("<Button-3>", self._show_account_context_menu)

        self._account_context_menu = tk.Menu(win, tearoff=0)
        self._account_context_menu.add_command(label="Edit", command=self._edit_selected_account)
        self._account_context_menu.add_command(label="Delete", command=self._delete_selected_account)
        self._account_context_menu.add_separator()
        self._account_context_menu.add_command(label="Info", command=self._view_selected_account_info)

        footer = tk.Frame(
            win,
            bg=self._ACCOUNT_CARD,
            highlightthickness=1,
            highlightbackground=self._ACCOUNT_HOVER,
        )
        footer.pack(fill="x", side="bottom")
        actions = tk.Frame(footer, bg=self._ACCOUNT_CARD, padx=16, pady=12)
        actions.pack(fill="x")
        self._acct_btn(actions, "Close", self._close_account_dialog, "left")
        self._acct_refresh_btn = self._acct_btn(actions, "Refresh", self._refresh_accounts, "left")
        self._acct_export_btn = self._acct_btn(actions, "Export", self._export_accounts, "right")
        self._acct_import_btn = self._acct_btn(actions, "Import", self._import_accounts, "right")
        self._acct_new_btn = self._acct_btn(actions, "New", self._create_new_account, "right")

        self._refresh_account_tree()

    def _configure_account_tree_style(self):
        self.style.configure(
            "Custom.Treeview",
            rowheight=32,
            background=self._ACCOUNT_CARD,
            fieldbackground=self._ACCOUNT_CARD,
            foreground=self._ACCOUNT_TEXT,
            borderwidth=0,
        )
        self.style.configure(
            "Custom.Treeview.Heading",
            background=self._ACCOUNT_CARD_ALT,
            foreground=self._ACCOUNT_TEXT,
            relief="flat",
            borderwidth=0,
            font=(self.mono_font, 10, "bold"),
        )
        self.style.map(
            "Custom.Treeview",
            background=[("selected", self._ACCOUNT_HOVER)],
            foreground=[("selected", self._ACCOUNT_TEXT)],
        )

    def _pill(self, parent, text, fg, right=False):
        frame = tk.Frame(parent, bg=self._ACCOUNT_CARD_ALT, highlightthickness=1, highlightbackground=self._ACCOUNT_HOVER)
        frame.pack(side="right" if right else "left", padx=(0, 4))
        dot = tk.Canvas(frame, width=10, height=10, bg=self._ACCOUNT_CARD_ALT, highlightthickness=0)
        dot.pack(side="left", padx=(6, 0), pady=6)
        dot.create_oval(2, 2, 9, 9, fill=fg, outline="")
        label = tk.Label(frame, text=text, bg=self._ACCOUNT_CARD_ALT, fg=fg, font=(self.mono_font, 9, "bold"), padx=8, pady=6)
        label.pack(side="left", padx=(0, 6))
        return label

    def _acct_btn(self, parent, text, command, side):
        button = tk.Button(
            parent,
            text=text,
            bg=self._ACCOUNT_CARD_ALT,
            fg=self._ACCOUNT_TEXT,
            activebackground=self._ACCOUNT_HOVER,
            activeforeground=self._ACCOUNT_TEXT,
            relief="flat",
            bd=0,
            font=("Segoe UI", 10, "bold"),
            padx=14,
            pady=8,
            cursor="hand2",
            command=command,
        )
        button.pack(side=side, padx=4)
        button.bind("<Enter>", lambda e: e.widget.configure(bg=self._ACCOUNT_HOVER))
        button.bind("<Leave>", lambda e: e.widget.configure(bg=self._ACCOUNT_CARD_ALT))
        return button

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
        if not tb.Messagebox.yesno(
            f"Delete account '{name}' from '{instance or 'unassigned'}'?",
            "Confirm Delete",
        ):
            return

        try:
            self.account_manager.remove_account(uid)
        except Exception as exc:
            self.log(f"Failed to delete account: {exc}", "ERROR")
            return

        self.log(f"Account deleted: {name}", "INFO")
        self._refresh_account_tree()

    def _open_account_info_dialog(self, account):
        win = tk.Toplevel(self.root)
        win.title("Account Info")
        win.geometry("460x360")
        win.resizable(False, False)
        win.transient(self._account_dialog)
        win.grab_set()
        win.configure(bg=self._ACCOUNT_BG)

        card = tk.Frame(
            win,
            bg=self._ACCOUNT_CARD,
            highlightthickness=1,
            highlightbackground=self._ACCOUNT_HOVER,
            padx=16,
            pady=16,
        )
        card.pack(fill="both", expand=True, padx=16, pady=16)

        tk.Label(
            card,
            text="Account Info",
            bg=self._ACCOUNT_CARD,
            fg=self._ACCOUNT_TEXT,
            font=(self.display_font, 14, "bold"),
        ).pack(anchor="w", pady=(0, 12))

        rows = [
            ("Name", account.get("name")),
            ("Gender", account.get("gender")),
            ("Phone", account.get("phone")),
            ("Email", account.get("email")),
            ("LD Instance", account.get("instance") or account.get("device_name") or account.get("ld_name")),
            ("ADB Serial", account.get("ld_adb")),
            ("Status", account.get("status")),
            ("Created", account.get("created_at")),
            ("Updated", account.get("updated_at")),
            ("Notes", account.get("notes")),
        ]
        for label, value in rows:
            tk.Label(
                card,
                text=f"{label}: {value or ''}",
                bg=self._ACCOUNT_CARD,
                fg=self._ACCOUNT_MUTED if not value else self._ACCOUNT_TEXT,
                font=(self.mono_font, 10),
                anchor="w",
                justify="left",
            ).pack(fill="x", pady=4)

        footer = tk.Frame(card, bg=self._ACCOUNT_CARD)
        footer.pack(fill="x", pady=(12, 0))
        self._acct_btn(footer, "Close", win.destroy, "right")

    def _open_account_editor(self, account):
        win = tk.Toplevel(self.root)
        win.title("Edit Account" if account.get("account_id") else "New Account")
        win.geometry("520x560")
        win.resizable(False, False)
        win.transient(self._account_dialog)
        win.grab_set()
        win.configure(bg=self._ACCOUNT_BG)

        vars_map = {
            "name": tk.StringVar(value=str(account.get("name") or "")),
            "gender": tk.StringVar(value=str(account.get("gender") or "")),
            "phone": tk.StringVar(value=str(account.get("phone") or "")),
            "email": tk.StringVar(value=str(account.get("email") or "")),
            "password": tk.StringVar(value=str(account.get("password") or "")),
            "instance": tk.StringVar(value=str(account.get("instance") or account.get("device_name") or account.get("ld_name") or "")),
            "ld_adb": tk.StringVar(value=str(account.get("ld_adb") or "")),
            "status": tk.StringVar(value=str(account.get("status") or "idle")),
        }

        card = tk.Frame(
            win,
            bg=self._ACCOUNT_CARD,
            highlightthickness=1,
            highlightbackground=self._ACCOUNT_HOVER,
            padx=16,
            pady=16,
        )
        card.pack(fill="both", expand=True, padx=16, pady=16)

        tk.Label(
            card,
            text="Edit Account" if account.get("account_id") else "New Account",
            bg=self._ACCOUNT_CARD,
            fg=self._ACCOUNT_TEXT,
            font=(self.display_font, 14, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

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
        for row, (label, key) in enumerate(fields, start=1):
            tk.Label(
                card,
                text=label,
                bg=self._ACCOUNT_CARD,
                fg=self._ACCOUNT_MUTED,
                font=(self.mono_font, 10),
            ).grid(row=row, column=0, sticky="w", padx=(0, 16), pady=10)

            if key == "gender":
                widget = tb.Combobox(
                    card,
                    textvariable=vars_map[key],
                    values=("", "Female", "Male"),
                    state="readonly",
                    width=28,
                )
            elif key == "status":
                widget = tb.Combobox(
                    card,
                    textvariable=vars_map[key],
                    values=("active", "idle", "error", "Novery", "Dead","Unknown"),
                    state="readonly",
                    width=28,
                )
            else:
                widget = tk.Entry(
                    card,
                    textvariable=vars_map[key],
                    bg=self._ACCOUNT_BG,
                    fg=self._ACCOUNT_TEXT,
                    insertbackground=self._ACCOUNT_ACCENT,
                    relief="flat",
                    font=(self.mono_font, 10),
                    width=30,
                    show="*" if key == "password" else "",
                    highlightthickness=1,
                    highlightbackground=self._ACCOUNT_ACCENT,
                    highlightcolor=self._ACCOUNT_ACCENT,
                )
            widget.grid(row=row, column=1, sticky="ew", pady=10)

        tk.Label(
            card,
            text="Notes",
            bg=self._ACCOUNT_CARD,
            fg=self._ACCOUNT_MUTED,
            font=(self.mono_font, 10),
        ).grid(row=len(fields) + 1, column=0, sticky="nw", padx=(0, 16), pady=10)
        notes_text = tk.Text(
            card,
            height=5,
            bg=self._ACCOUNT_BG,
            fg=self._ACCOUNT_TEXT,
            insertbackground=self._ACCOUNT_ACCENT,
            relief="flat",
            font=(self.mono_font, 10),
            wrap="word",
            highlightthickness=1,
            highlightbackground=self._ACCOUNT_ACCENT,
            highlightcolor=self._ACCOUNT_ACCENT,
        )
        notes_text.grid(row=len(fields) + 1, column=1, sticky="nsew", pady=10)
        notes_text.insert("1.0", str(account.get("notes") or ""))

        card.columnconfigure(1, weight=1)
        card.rowconfigure(len(fields) + 1, weight=1)

        footer = tk.Frame(card, bg=self._ACCOUNT_CARD)
        footer.grid(row=len(fields) + 2, column=0, columnspan=2, sticky="ew", pady=(12, 0))

        def save_account():
            payload = {key: var.get().strip() for key, var in vars_map.items()}
            payload["notes"] = notes_text.get("1.0", "end").strip()
            if not payload["name"] and not payload["email"] and not payload["phone"]:
                self.log("Name, phone, or email is required.", "WARNING")
                return
            if not payload["phone"] and not payload["email"]:
                self.log("At least one contact field is required.", "WARNING")
                return

            try:
                if account.get("account_id"):
                    saved = self.account_manager.update_account(str(account["account_id"]), payload)
                    self.log(f"Account updated: {saved.get('name') or saved.get('facebook_uid')}", "SUCCESS")
                else:
                    saved = self.account_manager.create_account(payload)
                    self.log(f"Account added: {saved.get('name') or saved.get('facebook_uid')}", "SUCCESS")
            except Exception as exc:
                self.log(f"Failed to save account: {exc}", "ERROR")
                return

            self._refresh_account_tree(select_uid=str(saved.get("facebook_uid") or saved.get("account_id") or ""))
            win.destroy()

        self._acct_btn(footer, "Cancel", win.destroy, "left")
        self._acct_btn(footer, "Save", save_account, "right")

    def _import_accounts(self):
        file_path = filedialog.askopenfilename(
            parent=self.root,
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
            parent=self.root,
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

    def _get_visible_accounts(self):
        query = getattr(self, "_acct_search_var", tk.StringVar()).get().strip().lower()
        status_filter = getattr(self, "_acct_status_filter_var", tk.StringVar(value="All")).get().strip().lower()
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
            status = str(acc.get("status") or "idle").lower()
            if query and query not in haystack:
                continue
            if status_filter != "all" and status != status_filter:
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
            summary = {"active": 0, "idle": 0, "error": 0, "novery": 0, "dead": 0, "unknown": 0, "total": 0}

        visible_index = 0
        selected_uid = None
        for acc in accounts:
            account_id = str(acc.get("account_id") or "")
            uid = str(acc.get("facebook_uid") or "")
            name = str(acc.get("name") or acc.get("username") or acc.get("email") or "account")
            gender = str(acc.get("gender") or "")
            status = str(acc.get("status") or "idle").lower()
            instance = str(acc.get("instance") or acc.get("device_name") or acc.get("ld_name") or "")
            contact = str(acc.get("phone") or acc.get("email") or "")
            created = str(acc.get("created_at") or "").replace("T", " ")

            visible_index += 1
            tags = [status if status in {"active", "idle", "error", "novery", "dead"} else "idle"]
            tags.append("even" if visible_index % 2 == 0 else "odd")
            tree.insert(
                "",
                "end",
                iid=account_id,
                values=(f"{visible_index:02d}", uid, name, gender, contact, instance, status.title(), created),
                tags=tuple(tags),
            )
            if select_uid and (uid == select_uid or account_id == select_uid):
                selected_uid = account_id

        self._acct_pill_active.config(text=f"{summary.get('active', 0)} Active")
        self._acct_pill_idle.config(text=f"{summary.get('idle', 0)} Idle")
        self._acct_pill_error.config(text=f"{summary.get('error', 0)} Error")
        self._acct_pill_novery.config(text=f"{summary.get('novery', 0)} Novery")
        self._acct_pill_dead.config(text=f"{summary.get('dead', 0)} Dead")
        self._acct_pill_total.config(text=f"{summary.get('total', 0)} Total")

        if selected_uid and tree.exists(selected_uid):
            tree.selection_set(selected_uid)
            tree.focus(selected_uid)
