"""
gui/dialogs/account_dialog.py
Account Manager dialog — table with status badges, search, summary pills.
Author: Bunhong
"""

import tkinter as tk
import ttkbootstrap as tb


class AccountDialogMixin:

    def show_account_manager(self):
        if hasattr(self, "_account_dialog") and self._account_dialog.winfo_exists():
            self._account_dialog.focus()
            return

        P = self.palette
        win = tk.Toplevel(self.root)
        win.title("Account Manager")
        win.resizable(False, False)
        win.geometry("560x480")
        win.transient(self.root)
        win.grab_set()
        win.configure(bg=P["surface"])
        self._account_dialog = win

        # ── header ────────────────────────────────────────────────────── #
        hdr = tk.Frame(win, bg=P["surface_alt"],
                       highlightthickness=1,
                       highlightbackground=P["border_alt"])
        hdr.pack(fill="x")

        tk.Label(hdr, text="👤", bg="#0D0A1F",
                 fg="#A78BFA", font=(self.display_font, 14),
                 width=4, pady=14).pack(side="left")
        tk.Label(hdr, text="Account Manager", bg=P["surface_alt"],
                 fg=P["text"], font=(self.display_font, 14)).pack(side="left", padx=(4, 0))
        tk.Label(hdr, text="Linked Facebook accounts per emulator",
                 bg=P["surface_alt"], fg=P["muted"],
                 font=(self.mono_font, 9)).pack(side="left", padx=(8, 0))

        # ── body ──────────────────────────────────────────────────────── #
        body = tk.Frame(win, bg=P["surface"], padx=16, pady=14)
        body.pack(fill="both", expand=True)

        # summary pills
        pill_row = tk.Frame(body, bg=P["surface"])
        pill_row.pack(fill="x", pady=(0, 10))

        self._acct_pill_active = self._pill(pill_row, "0 Active",  "#34D399", P)
        self._acct_pill_idle   = self._pill(pill_row, "0 Idle",    P["muted"], P)
        self._acct_pill_error  = self._pill(pill_row, "0 Error",   "#F87171", P)
        self._acct_pill_total  = self._pill(pill_row, "0 Total",   P["primary"], P, right=True)

        # search bar
        sb = tk.Frame(body, bg=P["surface_alt"],
                      highlightthickness=1, highlightbackground=P["border_alt"])
        sb.pack(fill="x", pady=(0, 10))

        tk.Label(sb, text="⌕", bg=P["surface_alt"],
                 fg=P["muted"], font=(self.display_font, 12),
                 padx=8).pack(side="left")
        self._acct_search_var = tk.StringVar()
        self._acct_search_var.trace_add("write", lambda *_: self._refresh_account_tree())
        tk.Entry(sb, textvariable=self._acct_search_var,
                 bg=P["surface_alt"], fg=P["text"],
                 insertbackground=P["primary"],
                 relief="flat", font=(self.mono_font, 11),
                 highlightthickness=0).pack(side="left", fill="x",
                                            expand=True, pady=8)

        # treeview
        cols = ("num", "name", "instance", "status")
        tree = tb.Treeview(body, columns=cols, show="headings",
                           height=10, style="Custom.Treeview")
        self._account_tree = tree

        widths = {"num": 36, "name": 180, "instance": 130, "status": 90}
        heads  = {"num": "#", "name": "Account Name",
                  "instance": "LD Instance", "status": "Status"}
        for c in cols:
            tree.heading(c, text=heads[c], anchor="w")
            tree.column(c, width=widths[c], anchor="w")

        tree.tag_configure("active",   foreground="#34D399", background="#050E0A")
        tree.tag_configure("idle",     foreground=P["muted"], background=P["surface"])
        tree.tag_configure("error",    foreground="#F87171", background="#0E0505")
        tree.tag_configure("odd_row",  background="#0C1016")
        tree.tag_configure("even_row", background=P["surface"])

        vsb = tb.Scrollbar(body, orient="vertical", command=tree.yview,
                           style="Vertical.TScrollbar")
        vsb.pack(side="right", fill="y")
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(fill="both", expand=True)

        self._refresh_account_tree()

        # ── footer ────────────────────────────────────────────────────── #
        foot = tk.Frame(win, bg=P["surface_alt"],
                        highlightthickness=1, highlightbackground=P["border"])
        foot.pack(fill="x", side="bottom")
        fp = tk.Frame(foot, bg=P["surface_alt"], padx=16, pady=12)
        fp.pack(fill="x")

        self._acct_btn(fp, "Close",       P["muted"],   P["border"],               win.destroy,          "left")
        self._acct_btn(fp, "Remove",      "#F87171",    "rgba(239,68,68,0.4)",     self._remove_account, "right")
        self._acct_btn(fp, "+ Add Account", "#A78BFA",  "rgba(124,58,237,0.4)",   self._add_account,    "right")
        self._acct_btn(fp, "↺ Refresh",   P["primary"], P["primary"],             self._refresh_account_tree, "right")

    # ── helpers ───────────────────────────────────────────────────────── #

    def _pill(self, parent, text, fg, P, right=False):
        f = tk.Frame(parent, bg=P["surface_alt"],
                     highlightthickness=1, highlightbackground=P["border"])
        side = "right" if right else "left"
        f.pack(side=side, padx=(0 if right else 0, 4))
        dot = tk.Canvas(f, width=10, height=10, bg=P["surface_alt"],
                        highlightthickness=0)
        dot.pack(side="left", padx=(6, 0), pady=6)
        dot.create_oval(2, 2, 9, 9, fill=fg, outline="")
        lbl = tk.Label(f, text=text, bg=P["surface_alt"],
                       fg=fg, font=(self.mono_font, 9), padx=4, pady=5)
        lbl.pack(side="left", padx=(0, 6))
        return lbl

    def _acct_btn(self, parent, text, fg, border_col, command, side):
        # border_col may be a hex string
        try:
            border_hex = border_col
        except Exception:
            border_hex = self.palette["border"]
        f = tk.Frame(parent, bg=self.palette["border_alt"], padx=1, pady=1)
        f.pack(side=side, padx=4)
        tk.Button(f, text=text, bg=self.palette["surface_alt"], fg=fg,
                  activebackground=self.palette["surface"],
                  activeforeground=fg, relief="flat",
                  font=(self.mono_font, 10), padx=12, pady=5,
                  cursor="hand2", command=command).pack()

    def _remove_account(self):
        tree = getattr(self, "_account_tree", None)
        if not tree:
            return
        sel = tree.selection()
        if not sel:
            self.log("No account selected", "WARNING")
            return
        item = sel[0]
        name = tree.item(item, "values")[1]
        if tb.Messagebox.yesno(f"Remove account '{name}'?", "Confirm"):
            tree.delete(item)
            self.log(f"Account removed: {name}", "INFO")

    def _add_account(self):
        self.log("Add account — not yet implemented", "INFO")

    def _refresh_account_tree(self):
        tree = getattr(self, "_account_tree", None)
        if not tree:
            return
        for item in tree.get_children():
            tree.delete(item)

        query = getattr(self, "_acct_search_var",
                        tk.StringVar()).get().lower()

        try:
            accounts = self.account_manager.list_accounts()
        except Exception as exc:
            self.log(f"Failed to load accounts: {exc}", "ERROR")
            accounts = []

        active = idle = error = 0
        for i, acc in enumerate(accounts):
            name   = acc.get("name", f"account_{i}")
            status = acc.get("status", "active").lower()
            inst   = acc.get("instance", f"LDPlayer-{i}")

            if query and query not in name.lower() and query not in inst.lower():
                continue

            tag = status if status in ("active", "idle", "error") else "odd_row"
            alt = "odd_row" if i % 2 else "even_row"
            tree.insert("", "end",
                        values=(f"{i+1:02d}", name, inst, status.title()),
                        tags=(tag,))

            if status == "active": active += 1
            elif status == "idle": idle += 1
            elif status == "error": error += 1

        total = active + idle + error
        if hasattr(self, "_acct_pill_active"):
            self._acct_pill_active.config(text=f"{active} Active")
            self._acct_pill_idle.config(text=f"{idle} Idle")
            self._acct_pill_error.config(text=f"{error} Error")
            self._acct_pill_total.config(text=f"{total} Total")
