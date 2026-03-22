import tkinter as tk
from tkinter import filedialog

import ttkbootstrap as tb


class AccountDialogMixin:
    def show_account_manager(self):
        win = getattr(self, "_account_dialog", None)
        if win is not None and win.winfo_exists():
            win.focus()
            return

        palette = self.palette
        win = tk.Toplevel(self.root)
        win.title("Account Manager")
        win.resizable(False, False)
        win.geometry("620x500")
        win.transient(self.root)
        win.grab_set()
        win.configure(bg=palette["surface"])
        self._account_dialog = win

        header = tk.Frame(
            win,
            bg=palette["surface_alt"],
            highlightthickness=1,
            highlightbackground=palette["border_alt"],
        )
        header.pack(fill="x")
        tk.Label(
            header,
            text="Account Manager",
            bg=palette["surface_alt"],
            fg=palette["text"],
            font=(self.display_font, 14),
            pady=14,
        ).pack(side="left", padx=16)
        tk.Label(
            header,
            text="Manage linked Facebook accounts and import account files",
            bg=palette["surface_alt"],
            fg=palette["muted"],
            font=(self.mono_font, 9),
        ).pack(side="left", padx=(0, 8))

        body = tk.Frame(win, bg=palette["surface"], padx=16, pady=14)
        body.pack(fill="both", expand=True)

        pill_row = tk.Frame(body, bg=palette["surface"])
        pill_row.pack(fill="x", pady=(0, 10))
        self._acct_pill_active = self._pill(pill_row, "0 Active", "#34D399", palette)
        self._acct_pill_idle = self._pill(pill_row, "0 Idle", palette["muted"], palette)
        self._acct_pill_error = self._pill(pill_row, "0 Error", "#F87171", palette)
        self._acct_pill_total = self._pill(pill_row, "0 Total", palette["primary"], palette, right=True)

        search_bar = tk.Frame(
            body,
            bg=palette["surface_alt"],
            highlightthickness=1,
            highlightbackground=palette["border_alt"],
        )
        search_bar.pack(fill="x", pady=(0, 10))
        self._acct_search_var = tk.StringVar()
        self._acct_search_var.trace_add("write", lambda *_: self._refresh_account_tree())
        tk.Label(
            search_bar,
            text="Search",
            bg=palette["surface_alt"],
            fg=palette["muted"],
            font=(self.mono_font, 10),
            padx=10,
        ).pack(side="left")
        tk.Entry(
            search_bar,
            textvariable=self._acct_search_var,
            bg=palette["surface_alt"],
            fg=palette["text"],
            insertbackground=palette["primary"],
            relief="flat",
            font=(self.mono_font, 11),
            highlightthickness=0,
        ).pack(side="left", fill="x", expand=True, pady=8, padx=(0, 8))

        cols = ("num", "name", "instance", "status")
        tree = tb.Treeview(body, columns=cols, show="headings", height=11, style="Custom.Treeview")
        self._account_tree = tree
        for col, width, title in (
            ("num", 36, "#"),
            ("name", 220, "Account"),
            ("instance", 180, "LD Instance"),
            ("status", 110, "Status"),
        ):
            tree.heading(col, text=title, anchor="w")
            tree.column(col, width=width, anchor="w")

        tree.tag_configure("active", foreground="#34D399", background="#050E0A")
        tree.tag_configure("idle", foreground=palette["muted"], background=palette["surface"])
        tree.tag_configure("error", foreground="#F87171", background="#0E0505")
        scrollbar = tb.Scrollbar(body, orient="vertical", command=tree.yview, style="Vertical.TScrollbar")
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(fill="both", expand=True)
        tree.bind("<<TreeviewSelect>>", self._on_account_selection_changed)

        self._refresh_account_tree()

        footer = tk.Frame(
            win,
            bg=palette["surface_alt"],
            highlightthickness=1,
            highlightbackground=palette["border"],
        )
        footer.pack(fill="x", side="bottom")
        actions = tk.Frame(footer, bg=palette["surface_alt"], padx=16, pady=12)
        actions.pack(fill="x")
        self._acct_btn(actions, "Close", palette["muted"], palette["border"], win.destroy, "left")
        self._acct_remove_btn = self._acct_btn(
            actions, "Remove", "#F87171", "#F87171", self._remove_account, "right"
        )
        self._acct_add_btn = self._acct_btn(
            actions, "Add Account", "#A78BFA", "#A78BFA", self._add_account, "right"
        )
        self._acct_import_btn = self._acct_btn(
            actions, "Import CSV/JSON", palette["warning"], palette["warning"], self._import_accounts, "right"
        )
        self._acct_refresh_btn = self._acct_btn(
            actions, "Refresh", palette["primary"], palette["primary"], self._refresh_account_tree, "right"
        )
        self._acct_remove_btn.configure(state="disabled")

    def _pill(self, parent, text, fg, palette, right=False):
        frame = tk.Frame(parent, bg=palette["surface_alt"], highlightthickness=1, highlightbackground=palette["border"])
        frame.pack(side="right" if right else "left", padx=(0, 4))
        dot = tk.Canvas(frame, width=10, height=10, bg=palette["surface_alt"], highlightthickness=0)
        dot.pack(side="left", padx=(6, 0), pady=6)
        dot.create_oval(2, 2, 9, 9, fill=fg, outline="")
        label = tk.Label(frame, text=text, bg=palette["surface_alt"], fg=fg, font=(self.mono_font, 9), padx=4, pady=5)
        label.pack(side="left", padx=(0, 6))
        return label

    def _acct_btn(self, parent, text, fg, border_color, command, side):
        frame = tk.Frame(parent, bg=self.palette["border_alt"], padx=1, pady=1)
        frame.pack(side=side, padx=4)
        button = tk.Button(
            frame,
            text=text,
            bg=self.palette["surface_alt"],
            fg=fg,
            activebackground=self.palette["surface"],
            activeforeground=fg,
            relief="flat",
            font=(self.mono_font, 10),
            padx=12,
            pady=5,
            cursor="hand2",
            command=command,
        )
        button.pack()
        return button

    def _on_account_selection_changed(self, _event=None):
        tree = getattr(self, "_account_tree", None)
        button = getattr(self, "_acct_remove_btn", None)
        if not tree or not button:
            return
        button.configure(state="normal" if tree.selection() else "disabled")

    def _remove_account(self):
        tree = getattr(self, "_account_tree", None)
        if not tree:
            return
        selected = tree.selection()
        if not selected:
            self.log("Select an account to remove first.", "WARNING")
            return

        item = selected[0]
        _, name, instance, _status = tree.item(item, "values")
        if not tb.Messagebox.yesno(
            f"Remove account '{name}' from instance '{instance}'?",
            "Confirm Removal",
        ):
            return

        try:
            self.account_manager.remove_account(instance)
        except Exception as exc:
            self.log(f"Failed to remove account: {exc}", "ERROR")
            return

        self.log(f"Account removed: {name} ({instance})", "INFO")
        self._refresh_account_tree()

    def _add_account(self):
        palette = self.palette
        win = tk.Toplevel(self.root)
        win.title("Add Account")
        win.resizable(False, False)
        win.geometry("430x330")
        win.transient(self.root)
        win.grab_set()
        win.configure(bg=palette["surface"])

        form = tk.Frame(win, bg=palette["surface"], padx=18, pady=16)
        form.pack(fill="both", expand=True)
        fields = {}
        rows = [
            ("LD Instance", "instance"),
            ("Name", "name"),
            ("Email", "email"),
            ("Password", "password"),
            ("Status", "status"),
        ]
        for row_index, (label, key) in enumerate(rows):
            tk.Label(
                form,
                text=label,
                bg=palette["surface"],
                fg=palette["text"],
                font=(self.mono_font, 10),
            ).grid(row=row_index, column=0, sticky="w", pady=8)
            var = tk.StringVar(value="active" if key == "status" else "")
            entry = tk.Entry(
                form,
                textvariable=var,
                bg=palette["surface_alt"],
                fg=palette["text"],
                insertbackground=palette["primary"],
                relief="flat",
                font=(self.mono_font, 10),
                width=28,
                show="*" if key == "password" else "",
            )
            entry.grid(row=row_index, column=1, sticky="ew", padx=(12, 0), pady=8)
            fields[key] = var
        form.columnconfigure(1, weight=1)

        footer = tk.Frame(win, bg=palette["surface_alt"], padx=16, pady=12)
        footer.pack(fill="x", side="bottom")

        def save_account():
            instance = fields["instance"].get().strip()
            if not instance:
                self.log("LD Instance is required.", "WARNING")
                return

            payload = {
                "name": fields["name"].get().strip(),
                "email": fields["email"].get().strip(),
                "password": fields["password"].get().strip(),
                "status": fields["status"].get().strip() or "active",
            }
            try:
                self.account_manager.assign_account_to_device(instance, payload)
            except Exception as exc:
                self.log(f"Failed to save account: {exc}", "ERROR")
                return

            self.log(f"Account saved for {instance}", "SUCCESS")
            win.destroy()
            self._refresh_account_tree()

        self._acct_btn(footer, "Cancel", palette["muted"], palette["border"], win.destroy, "left")
        self._acct_btn(footer, "Save", palette["primary"], palette["primary"], save_account, "right")

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

    def _refresh_account_tree(self):
        tree = getattr(self, "_account_tree", None)
        if not tree:
            return

        for item in tree.get_children():
            tree.delete(item)

        query = getattr(self, "_acct_search_var", tk.StringVar()).get().strip().lower()
        try:
            accounts = self.account_manager.list_accounts()
        except Exception as exc:
            self.log(f"Failed to load accounts: {exc}", "ERROR")
            accounts = []

        active = idle = error = 0
        visible_index = 0
        for acc in accounts:
            name = str(acc.get("name") or acc.get("username") or acc.get("email") or "account")
            status = str(acc.get("status") or "active").lower()
            instance = str(acc.get("instance") or acc.get("device_name") or "")

            haystack = f"{name} {instance} {acc.get('email', '')}".lower()
            if query and query not in haystack:
                continue

            visible_index += 1
            tag = status if status in {"active", "idle", "error"} else "idle"
            tree.insert(
                "",
                "end",
                values=(f"{visible_index:02d}", name, instance, status.title()),
                tags=(tag,),
            )
            if status == "active":
                active += 1
            elif status == "idle":
                idle += 1
            else:
                error += 1

        total = active + idle + error
        self._acct_pill_active.config(text=f"{active} Active")
        self._acct_pill_idle.config(text=f"{idle} Idle")
        self._acct_pill_error.config(text=f"{error} Error")
        self._acct_pill_total.config(text=f"{total} Total")
        self._on_account_selection_changed()
