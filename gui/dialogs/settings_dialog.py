import re
import tkinter as tk
from tkinter import filedialog
import ttkbootstrap as tb

from gui.appearance import (
    ACCENT_COLORS,
    DEFAULT_APPEARANCE_SETTINGS,
    THEME_PRESETS,
    UI_DENSITIES,
    UI_SCALES,
    label_for,
    resolve_appearance,
)
from gui.components.status import StatusPill
from gui.dialogs.email_settings_dialog import EmailSettingsDialogMixin


class SettingsDialogMixin(EmailSettingsDialogMixin):
    def _import_fixed_contacts_from_text(self, mode_var, value_var):
        mode = str(mode_var.get() or "").strip().lower()
        if mode not in {"fixed_phone", "fixed_email"}:
            self.log("Import TXT only works with fixed_phone or fixed_email mode.", "WARNING")
            return

        file_path = filedialog.askopenfilename(
            parent=getattr(self, "root", None),
            title="Import Fixed Contacts From Text",
            filetypes=[
                ("Text Files", "*.txt"),
                ("All Files", "*.*"),
            ],
        )
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8") as handle:
                content = handle.read()
        except UnicodeDecodeError:
            with open(file_path, "r", encoding="utf-8-sig") as handle:
                content = handle.read()
        except OSError as exc:
            self.log(f"Failed to read text file: {exc}", "ERROR")
            return

        items = (
            self._extract_phone_candidates(content)
            if mode == "fixed_phone"
            else self._extract_email_candidates(content)
        )
        if not items:
            target = "phone numbers" if mode == "fixed_phone" else "emails"
            self.log(f"No valid {target} found in {file_path}", "WARNING")
            return

        value_var.set(",".join(items))
        self.log(f"Imported {len(items)} {'phone numbers' if mode == 'fixed_phone' else 'emails'} from {file_path}", "SUCCESS")

    def _extract_phone_candidates(self, content):
        seen = set()
        phones = []
        for match in re.finditer(r"\+?\d[\d\s().-]{6,}\d", str(content or "")):
            raw = match.group(0).strip()
            has_plus = raw.startswith("+")
            normalized = re.sub(r"[^\d]", "", raw)
            if len(normalized) < 7:
                continue
            phone = f"+{normalized}" if has_plus else normalized
            if phone in seen:
                continue
            seen.add(phone)
            phones.append(phone)
        return phones

    def _extract_email_candidates(self, content):
        seen = set()
        emails = []
        for match in re.finditer(r"(?i)\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b", str(content or "")):
            email = match.group(0).strip()
            key = email.lower()
            if key in seen:
                continue
            seen.add(key)
            emails.append(email)
        return emails

    def _bind_settings_mousewheel(self, widget, canvas):
        def _on_mousewheel(event):
            delta = 0
            if getattr(event, "delta", 0):
                delta = -1 * int(event.delta / 120)
            elif getattr(event, "num", None) == 4:
                delta = -1
            elif getattr(event, "num", None) == 5:
                delta = 1
            if delta:
                canvas.yview_scroll(delta, "units")

        widget.bind("<MouseWheel>", _on_mousewheel, add="+")
        widget.bind("<Button-4>", _on_mousewheel, add="+")
        widget.bind("<Button-5>", _on_mousewheel, add="+")

    def _create_scrollable_settings_page(self, parent, palette):
        page = tk.Frame(parent, bg=palette["surface"])
        page.place(relx=0, rely=0, relwidth=1, relheight=1)

        canvas = tk.Canvas(
            page,
            bg=palette["surface"],
            highlightthickness=0,
            bd=0,
        )
        scrollbar = tb.Scrollbar(
            page,
            orient="vertical",
            command=canvas.yview,
            style="Vertical.TScrollbar",
        )
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        body = tk.Frame(canvas, bg=palette["surface"])
        window_id = canvas.create_window((0, 0), window=body, anchor="nw")

        def _sync_scrollregion(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _sync_width(event):
            canvas.itemconfigure(window_id, width=event.width)

        body.bind("<Configure>", _sync_scrollregion)
        canvas.bind("<Configure>", _sync_width)

        for target in (page, canvas, body):
            self._bind_settings_mousewheel(target, canvas)

        return page, body

    def show_settings_dialog(self):
        dialog = getattr(self, "_settings_dialog", None)
        if dialog is not None and dialog.winfo_exists():
            dialog.focus()
            return

        P = self.palette
        dialog = tk.Toplevel(self.root)
        dialog.title("Control Settings")
        dialog.geometry("1040x700")
        dialog.minsize(1040, 700)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg=P["surface"])
        dialog.protocol("WM_DELETE_WINDOW", lambda: self._close_settings_dialog(dialog))
        self._settings_dialog = dialog

        parallel_var = tk.IntVar(value=self.parallel_ld.get())
        boot_delay_var = tk.IntVar(value=self.boot_delay.get())
        task_duration_var = tk.IntVar(value=self.task_duration.get())
        max_videos_var = tk.IntVar(value=self.max_videos.get())
        accounts_per_ld_var = tk.IntVar(value=self.accounts_per_ld.get())
        start_same_var = tk.BooleanVar(value=self.start_same_time.get())
        use_queue_var = tk.BooleanVar(value=self.use_content_queue.get())
        auto_arrange_var = tk.BooleanVar(value=self.auto_arrange_ld.get())
        auto_shutdown_var = tk.BooleanVar(value=self.auto_shutdown_pc.get())
        verify_account_var = tk.BooleanVar(value=self.verify_account.get())
        reg_contact_mode_var = tk.StringVar(value=self.reg_contact_mode.get())
        reg_contact_value_var = tk.StringVar(value=self.reg_contact_value.get())
        reg_phone_prefix_var = tk.StringVar(value=self.reg_phone_prefix.get())
        email_provider_var = tk.StringVar(value=self.email_provider.get())
        email_address_var = tk.StringVar(value=self.email_address.get())
        email_app_password_var = tk.StringVar(value=self.email_app_password.get())
        email_imap_server_var = tk.StringVar(value=self.email_imap_server.get())
        email_imap_port_var = tk.IntVar(value=self.email_imap_port.get())
        email_mailbox_var = tk.StringVar(value=self.email_mailbox.get())
        email_use_ssl_var = tk.BooleanVar(value=self.email_use_ssl.get())
        email_unread_only_var = tk.BooleanVar(value=self.email_unread_only.get())
        email_sender_filter_var = tk.StringVar(value=self.email_sender_filter.get())
        email_subject_filter_var = tk.StringVar(value=self.email_subject_filter.get())
        email_timeout_var = tk.IntVar(value=self.email_timeout_seconds.get())
        email_poll_interval_var = tk.IntVar(value=self.email_poll_interval_seconds.get())
        email_mark_as_seen_var = tk.BooleanVar(value=self.email_mark_as_seen.get())
        appearance_vars = {
            "theme_preset": tk.StringVar(value=self.theme_preset.get()),
            "accent_color": tk.StringVar(value=self.accent_color.get()),
            "ui_density": tk.StringVar(value=self.ui_density.get()),
            "ui_scale": tk.StringVar(value=self.ui_scale.get()),
        }
        # Reuse the main app variable for blocked countries so changes are live.
        blocked_countries_var = getattr(self, "blocked_countries", tk.StringVar(value=""))

        shell = tk.Frame(dialog, bg=P["surface"], padx=18, pady=18)
        shell.pack(fill="both", expand=True)

        self._build_settings_shell(
            shell,
            P,
            dialog,
            parallel_var,
            boot_delay_var,
            task_duration_var,
            max_videos_var,
            accounts_per_ld_var,
            start_same_var,
            use_queue_var,
            auto_arrange_var,
            auto_shutdown_var,
            verify_account_var,
            reg_contact_mode_var,
            reg_contact_value_var,
            reg_phone_prefix_var,
            email_provider_var,
            email_address_var,
            email_app_password_var,
            email_imap_server_var,
            email_imap_port_var,
            email_mailbox_var,
            email_use_ssl_var,
            email_unread_only_var,
            email_sender_filter_var,
            email_subject_filter_var,
            email_timeout_var,
            email_poll_interval_var,
            email_mark_as_seen_var,
            appearance_vars,
        )

    def _build_settings_shell(
        self,
        parent,
        palette,
        dialog,
        parallel_var,
        boot_delay_var,
        task_duration_var,
        max_videos_var,
        accounts_per_ld_var,
        start_same_var,
        use_queue_var,
        auto_arrange_var,
        auto_shutdown_var,
        verify_account_var,
        reg_contact_mode_var,
        reg_contact_value_var,
        reg_phone_prefix_var,
        email_provider_var,
        email_address_var,
        email_app_password_var,
        email_imap_server_var,
        email_imap_port_var,
        email_mailbox_var,
        email_use_ssl_var,
        email_unread_only_var,
        email_sender_filter_var,
        email_subject_filter_var,
        email_timeout_var,
        email_poll_interval_var,
        email_mark_as_seen_var,
        appearance_vars,
    ):
        wrapper = tk.Frame(parent, bg=palette["border_alt"], padx=1, pady=1)
        wrapper.pack(fill="both", expand=True)

        container = tk.Frame(wrapper, bg=palette["surface"])
        container.pack(fill="both", expand=True)

        self._build_premium_header(
            container,
            palette,
            parallel_var,
            task_duration_var,
            use_queue_var,
        )

        body = tk.Frame(container, bg=palette["surface"])
        body.pack(fill="both", expand=True, padx=18, pady=(0, 14))

        sidebar = tk.Frame(body, bg=palette["surface_alt"], width=260)
        sidebar.pack(side="left", fill="y", padx=(0, 16))
        sidebar.pack_propagate(False)

        content = tk.Frame(body, bg=palette["surface"])
        content.pack(side="left", fill="both", expand=True)

        self._settings_nav_buttons = {}
        self._settings_pages = {}
        self._settings_overview_var = tk.StringVar()

        self._build_premium_sidebar(
            sidebar,
            palette,
            parallel_var,
            boot_delay_var,
            task_duration_var,
            max_videos_var,
            start_same_var,
            use_queue_var,
            auto_arrange_var,
        )

        for key in ("general", "appearance", "behavior", "email", "profiles", "summary"):
            page, body = self._create_scrollable_settings_page(content, palette)
            self._settings_pages[key] = page
            self._settings_pages[f"{key}_body"] = body

        self._build_appearance_page(
            self._settings_pages["appearance_body"],
            palette,
            appearance_vars,
        )
        self._build_general_page(
            self._settings_pages["general_body"],
            palette,
            parallel_var,
            boot_delay_var,
            task_duration_var,
            max_videos_var,
            accounts_per_ld_var,
        )
        self._build_behavior_page(
            self._settings_pages["behavior_body"],
            palette,
            start_same_var,
            use_queue_var,
            auto_arrange_var,
            auto_shutdown_var,
            verify_account_var,
            parallel_var,
            boot_delay_var,
            task_duration_var,
            max_videos_var,
            reg_contact_mode_var,
            reg_contact_value_var,
            reg_phone_prefix_var,
        )
        self._build_profiles_page(
            self._settings_pages["profiles_body"],
            palette,
            parallel_var,
            boot_delay_var,
            task_duration_var,
            max_videos_var,
            start_same_var,
            use_queue_var,
            auto_arrange_var,
        )
        self._build_email_settings_page(
            self._settings_pages["email_body"],
            palette,
            email_provider_var,
            email_address_var,
            email_app_password_var,
            email_imap_server_var,
            email_imap_port_var,
            email_mailbox_var,
            email_use_ssl_var,
            email_unread_only_var,
            email_sender_filter_var,
            email_subject_filter_var,
            email_timeout_var,
            email_poll_interval_var,
            email_mark_as_seen_var,
            appearance_vars,
        )
        self._build_summary_page(
            self._settings_pages["summary_body"],
            palette,
            parallel_var,
            boot_delay_var,
            task_duration_var,
            max_videos_var,
            accounts_per_ld_var,
            start_same_var,
            use_queue_var,
            auto_arrange_var,
            auto_shutdown_var,
            verify_account_var,
            reg_contact_mode_var,
            reg_contact_value_var,
            reg_phone_prefix_var,
            email_provider_var,
            email_address_var,
            email_sender_filter_var,
            email_subject_filter_var,
        )

        self._build_premium_footer(
            container,
            palette,
            dialog,
            parallel_var,
            boot_delay_var,
            task_duration_var,
            max_videos_var,
            accounts_per_ld_var,
            start_same_var,
            use_queue_var,
            auto_arrange_var,
            auto_shutdown_var,
            verify_account_var,
            reg_contact_mode_var,
            reg_contact_value_var,
            reg_phone_prefix_var,
            email_provider_var,
            email_address_var,
            email_app_password_var,
            email_imap_server_var,
            email_imap_port_var,
            email_mailbox_var,
            email_use_ssl_var,
            email_unread_only_var,
            email_sender_filter_var,
            email_subject_filter_var,
            email_timeout_var,
            email_poll_interval_var,
            email_mark_as_seen_var,
            appearance_vars,
        )

        self._bind_summary_refresh_with_accounts(
            parallel_var,
            boot_delay_var,
            task_duration_var,
            max_videos_var,
            accounts_per_ld_var,
            start_same_var,
            use_queue_var,
            auto_arrange_var,
            auto_shutdown_var,
            verify_account_var,
            reg_contact_mode_var,
            reg_contact_value_var,
            reg_phone_prefix_var,
            email_provider_var,
            email_address_var,
            email_sender_filter_var,
            email_subject_filter_var,
        )
        self.root.after(0, lambda: self._open_settings_page("appearance"))

    def _build_premium_header(self, parent, palette, parallel_var, task_duration_var, use_queue_var):
        header = tk.Frame(parent, bg=palette["surface"], pady=18, padx=18)
        header.pack(fill="x")

        left = tk.Frame(header, bg=palette["surface"])
        left.pack(side="left", fill="x", expand=True)

        badge_wrap = tk.Frame(left, bg=palette["surface"])
        badge_wrap.pack(anchor="w")

        tip_bg = palette.get("tip_bg", palette["surface_alt"])
        icon = tk.Frame(badge_wrap, bg=tip_bg, width=68, height=68, highlightthickness=1, highlightbackground=palette["border_alt"])
        icon.pack(side="left")
        icon.pack_propagate(False)
        tk.Label(icon, text="CTRL", bg=tip_bg, fg=palette["primary"], font=(self.display_font, 12)).pack(expand=True)

        title_wrap = tk.Frame(badge_wrap, bg=palette["surface"], padx=14)
        title_wrap.pack(side="left", fill="x", expand=True)
        tk.Label(title_wrap, text="Control Settings", bg=palette["surface"], fg=palette["text"], font=(self.display_font, 20)).pack(anchor="w")
        tk.Label(
            title_wrap,
            text="Premium control center for launch pacing, behavior, presets, and review.",
            bg=palette["surface"],
            fg=palette["muted"],
            font=(self.mono_font, 9),
        ).pack(anchor="w", pady=(4, 0))

        status = tk.Frame(header, bg=palette["surface_alt"], padx=14, pady=10, highlightthickness=1, highlightbackground=palette["border"])
        status.pack(side="right")
        tk.Label(status, text="ACTIVE MODE", bg=palette["surface_alt"], fg=palette["muted"], font=(self.mono_font, 8)).pack(anchor="e")
        self._header_status_var = tk.StringVar(value="Balanced")
        tk.Label(status, textvariable=self._header_status_var, bg=palette["surface_alt"], fg=palette["primary"], font=(self.display_font, 12)).pack(anchor="e")
        self._header_meta_var = tk.StringVar(value="Ready • Queue On")
        tk.Label(status, textvariable=self._header_meta_var, bg=palette["surface_alt"], fg=palette["text"], font=(self.mono_font, 8)).pack(anchor="e", pady=(2, 0))

    def _build_premium_sidebar(
        self,
        parent,
        palette,
        parallel_var,
        boot_delay_var,
        task_duration_var,
        max_videos_var,
        start_same_var,
        use_queue_var,
        auto_arrange_var,
    ):
        inner = tk.Frame(parent, bg=palette["surface_alt"], padx=16, pady=18)
        inner.pack(fill="both", expand=True)

        tk.Label(inner, text="SETTINGS MENU", bg=palette["surface_alt"], fg=palette["muted"], font=(self.mono_font, 8)).pack(anchor="w")
        tk.Label(
            inner,
            textvariable=self._settings_overview_var,
            bg=palette["surface_alt"],
            fg=palette["primary"],
            justify="left",
            wraplength=210,
            font=(self.mono_font, 9),
        ).pack(anchor="w", pady=(8, 18))

        menu_items = [
            ("appearance", "*", "Appearance", "Theme, accent, spacing, and scale"),
            ("general", "⚙", "General", "Core launch and session values"),
            ("behavior", "⇄", "Behavior", "Queue and dispatch options"),
            ("email", "@", "Email OTP", "Authorized IMAP inbox reader"),
            ("profiles", "◈", "Profiles", "Fast preset modes"),
            ("summary", "▣", "Summary", "Review current control state"),
        ]

        for key, icon, title, desc in menu_items:
            outer = tk.Frame(inner, bg=palette["surface_alt"])
            outer.pack(fill="x", pady=5)

            accent = tk.Frame(outer, bg=palette["surface_alt"], width=4)
            accent.pack(side="left", fill="y")

            btn = tk.Frame(outer, bg=palette["surface_alt"], padx=12, pady=10, cursor="hand2")
            btn.pack(side="left", fill="x", expand=True)

            top = tk.Frame(btn, bg=palette["surface_alt"])
            top.pack(fill="x")
            tk.Label(top, text=icon, bg=palette["surface_alt"], fg=palette["primary"], font=(self.display_font, 11)).pack(side="left")
            tk.Label(top, text=title, bg=palette["surface_alt"], fg=palette["text"], font=(self.display_font, 11)).pack(side="left", padx=(8, 0))
            tk.Label(btn, text=desc, bg=palette["surface_alt"], fg=palette["muted"], font=(self.mono_font, 8), justify="left").pack(anchor="w", pady=(4, 0))

            for widget in (outer, accent, btn, top):
                widget.bind("<Button-1>", lambda e, page=key: self._open_settings_page(page))
            for child in btn.winfo_children():
                child.bind("<Button-1>", lambda e, page=key: self._open_settings_page(page))
            for child in top.winfo_children():
                child.bind("<Button-1>", lambda e, page=key: self._open_settings_page(page))

            self._settings_nav_buttons[key] = (outer, accent, btn)

        tip_bg = palette.get("tip_bg", palette["surface_alt"])
        tip = tk.Frame(inner, bg=tip_bg, padx=12, pady=12, highlightthickness=1, highlightbackground=palette["border_alt"])
        tip.pack(fill="x", side="bottom", pady=(18, 0))
        tk.Label(tip, text="RECOMMENDATION", bg=tip_bg, fg=palette["primary"], font=(self.mono_font, 8)).pack(anchor="w")
        tk.Label(
            tip,
            text="Use Balanced profile first, then adjust only one or two values.",
            bg=tip_bg,
            fg=palette["text"],
            wraplength=210,
            justify="left",
            font=(self.mono_font, 8),
        ).pack(anchor="w", pady=(6, 0))

    def _page_heading(self, parent, palette, eyebrow, title, subtitle):
        wrap = tk.Frame(parent, bg=palette["surface"])
        wrap.pack(fill="x", pady=(0, 14))
        tk.Label(wrap, text=eyebrow, bg=palette["surface"], fg=palette["primary"], font=(self.mono_font, 8)).pack(anchor="w")
        tk.Label(wrap, text=title, bg=palette["surface"], fg=palette["text"], font=(self.display_font, 18)).pack(anchor="w", pady=(4, 0))
        tk.Label(wrap, text=subtitle, bg=palette["surface"], fg=palette["muted"], font=(self.mono_font, 9)).pack(anchor="w", pady=(4, 0))

    def _premium_card(self, parent, palette, title, subtitle=None, padding=16):
        if padding == 16:
            padding = int(getattr(getattr(self, "appearance", None), "spacing", {}).get("card_padding", padding))
        outer = tk.Frame(parent, bg=palette["border"], padx=1, pady=1)
        card = tk.Frame(outer, bg=palette["surface_alt"], padx=padding, pady=padding)
        card.pack(fill="both", expand=True)
        if title:
            tk.Label(card, text=title, bg=palette["surface_alt"], fg=palette["text"], font=(self.display_font, 12)).pack(anchor="w")
        if subtitle:
            tk.Label(card, text=subtitle, bg=palette["surface_alt"], fg=palette["muted"], font=(self.mono_font, 8)).pack(anchor="w", pady=(4, 10))
        return outer, card

    def _metric_card(self, parent, palette, title, variable, unit, help_text, step=1, min_value=0):
        outer, card = self._premium_card(parent, palette, title, help_text)
        outer.pack(side="left", fill="both", expand=True, padx=6)

        value_row = tk.Frame(card, bg=palette["surface_alt"])
        value_row.pack(fill="x", pady=(6, 0))

        minus = tk.Button(value_row, text="−", relief="flat", bg=palette["surface"], fg=palette["text"], activebackground=palette["border_alt"], activeforeground=palette["text"], font=(self.display_font, 14), width=3, cursor="hand2", command=lambda: variable.set(max(min_value, variable.get() - step)))
        minus.pack(side="left")

        center = tk.Frame(value_row, bg=palette["surface_alt"])
        center.pack(side="left", fill="both", expand=True)
        tk.Label(center, textvariable=variable, bg=palette["surface_alt"], fg=palette["primary"], font=(self.display_font, 24)).pack()
        tk.Label(center, text=unit, bg=palette["surface_alt"], fg=palette["muted"], font=(self.mono_font, 8)).pack()

        plus = tk.Button(value_row, text="+", relief="flat", bg=palette["surface"], fg=palette["text"], activebackground=palette["border_alt"], activeforeground=palette["text"], font=(self.display_font, 13), width=3, cursor="hand2", command=lambda: variable.set(variable.get() + step))
        plus.pack(side="right")

        return outer

    def _build_appearance_page(self, parent, palette, appearance_vars):
        self._page_heading(
            parent,
            palette,
            "APPEARANCE",
            "Product Look & Feel",
            "Choose a focused visual preset, accent, spacing density, and readable scale.",
        )

        preview_state = {"refresh": None}

        self._appearance_choice_group(
            parent,
            palette,
            "Theme",
            "A curated app shell preset mapped to ttkbootstrap.",
            appearance_vars["theme_preset"],
            THEME_PRESETS,
            lambda: preview_state["refresh"]() if preview_state["refresh"] else None,
        )
        self._appearance_choice_group(
            parent,
            palette,
            "Accent Color",
            "Controls primary buttons, active navigation, highlights, and status emphasis.",
            appearance_vars["accent_color"],
            ACCENT_COLORS,
            lambda: preview_state["refresh"]() if preview_state["refresh"] else None,
            swatches=True,
        )
        self._appearance_choice_group(
            parent,
            palette,
            "Layout Density",
            "Adjusts shared padding, card rhythm, navigation spacing, and table row height.",
            appearance_vars["ui_density"],
            UI_DENSITIES,
            lambda: preview_state["refresh"]() if preview_state["refresh"] else None,
        )
        self._appearance_choice_group(
            parent,
            palette,
            "Typography Scale",
            "Adjusts shared font sizes used by headings, controls, tables, and badges.",
            appearance_vars["ui_scale"],
            UI_SCALES,
            lambda: preview_state["refresh"]() if preview_state["refresh"] else None,
        )

        preview_outer, preview = self._premium_card(
            parent,
            palette,
            "Preview",
            "A miniature sample of the active appearance selection.",
        )
        preview_outer.pack(fill="x", pady=(6, 12))

        sample = tk.Frame(preview, bg=palette["surface"], padx=14, pady=14, highlightthickness=1, highlightbackground=palette["border"])
        sample.pack(fill="x")
        title = tk.Label(sample, text="Automation Control", bg=palette["surface"], fg=palette["text"], font=(self.display_font, 13))
        title.pack(anchor="w")
        subtitle = tk.Label(
            sample,
            text="Fleet status, primary action, secondary action, and a status badge.",
            bg=palette["surface"],
            fg=palette["muted"],
            font=(self.mono_font, 9),
        )
        subtitle.pack(anchor="w", pady=(3, 10))
        actions = tk.Frame(sample, bg=palette["surface"])
        actions.pack(fill="x")
        primary = tk.Button(actions, text="Start Automation", relief="flat", padx=12, pady=7, cursor="hand2")
        primary.pack(side="left", padx=(0, 8))
        secondary = tk.Button(actions, text="Review Queue", relief="flat", padx=12, pady=7, cursor="hand2")
        secondary.pack(side="left", padx=(0, 8))
        pill = StatusPill(actions, "Active", palette=palette, text="READY", font=(self.display_font, 9), padx=8, pady=3)
        pill.pack(side="left")
        meta = tk.Label(sample, text="", bg=palette["surface"], fg=palette["muted"], font=(self.mono_font, 8))
        meta.pack(anchor="w", pady=(12, 0))

        controls = tk.Frame(parent, bg=palette["surface"])
        controls.pack(fill="x", pady=(0, 12))
        tk.Button(
            controls,
            text="Apply Appearance Now",
            relief="flat",
            bg=palette["primary"],
            fg=palette["primary_fg"],
            activebackground=palette["primary_active"],
            activeforeground=palette["primary_fg"],
            font=(self.mono_font, 9, "bold"),
            padx=14,
            pady=7,
            cursor="hand2",
            command=lambda: self._apply_appearance_from_dialog(appearance_vars, save=False),
        ).pack(side="left")
        tk.Button(
            controls,
            text="Reset Appearance",
            relief="flat",
            bg=palette["surface_alt"],
            fg=palette["warning"],
            activebackground=palette["border_alt"],
            activeforeground=palette["warning"],
            font=(self.mono_font, 9),
            padx=14,
            pady=7,
            cursor="hand2",
            command=lambda: self._reset_appearance_vars(appearance_vars),
        ).pack(side="left", padx=(8, 0))

        outer, notes = self._premium_card(parent, palette, "Apply Flow", "How appearance changes behave.")
        outer.pack(fill="x")
        self._info_row(notes, palette, "Preview", "Changing a control updates the miniature preview immediately.")
        self._info_row(notes, palette, "Apply now", "Updates the active window colors and ttk styles without closing settings.")
        self._info_row(notes, palette, "Save", "Save & Apply persists appearance and automation settings to disk.")

        def refresh_preview(*_):
            resolved = resolve_appearance(
                theme_preset=appearance_vars["theme_preset"].get(),
                accent_color=appearance_vars["accent_color"].get(),
                ui_density=appearance_vars["ui_density"].get(),
                ui_scale=appearance_vars["ui_scale"].get(),
            )
            p = resolved.palette
            body_size = resolved.font_sizes["body"]
            meta_size = resolved.font_sizes["meta"]
            card_size = resolved.font_sizes["card_title"]
            button_pad = resolved.spacing["button_pad"]
            sample.configure(bg=p["surface"], padx=resolved.spacing["card_padding"], pady=resolved.spacing["card_padding"], highlightbackground=p["border"])
            actions.configure(bg=p["surface"])
            title.configure(bg=p["surface"], fg=p["text"], font=(self.display_font, card_size + 2))
            subtitle.configure(bg=p["surface"], fg=p["muted"], font=(self.mono_font, meta_size))
            primary.configure(
                bg=p["primary"],
                fg=p["primary_fg"],
                activebackground=p["primary_active"],
                activeforeground=p["primary_fg"],
                font=(self.display_font, body_size),
                padx=button_pad[0],
                pady=button_pad[1],
            )
            secondary.configure(
                bg=p["surface_alt"],
                fg=p["text"],
                activebackground=p["border_alt"],
                activeforeground=p["text"],
                font=(self.display_font, body_size),
                padx=button_pad[0],
                pady=button_pad[1],
            )
            pill.update_palette(p)
            pill.label.configure(font=(self.display_font, meta_size))
            meta.configure(
                text=(
                    f"{label_for(THEME_PRESETS, resolved.theme_preset)} theme | "
                    f"{label_for(ACCENT_COLORS, resolved.accent_color)} accent | "
                    f"{label_for(UI_DENSITIES, resolved.ui_density)} density | "
                    f"{label_for(UI_SCALES, resolved.ui_scale)} scale"
                ),
                bg=p["surface"],
                fg=p["muted"],
                font=(self.mono_font, max(7, meta_size - 1)),
            )

        preview_state["refresh"] = refresh_preview
        for var in appearance_vars.values():
            var.trace_add("write", refresh_preview)
        refresh_preview()

    def _appearance_choice_group(self, parent, palette, title, description, variable, options, refresh, swatches=False):
        outer, card = self._premium_card(parent, palette, title, description)
        outer.pack(fill="x", pady=(0, 12))
        row = tk.Frame(card, bg=palette["surface_alt"])
        row.pack(fill="x", pady=(2, 0))
        buttons = {}

        def select(value):
            variable.set(value)
            refresh()

        def redraw(*_):
            current = variable.get()
            for value, button in buttons.items():
                option_color = options[value].get("color", palette["primary"])
                selected = value == current
                button.configure(
                    bg=option_color if selected and swatches else palette["primary"] if selected else palette["surface"],
                    fg=palette["primary_fg"] if selected else palette["text"],
                    activebackground=palette["primary_active"] if selected else palette["border_alt"],
                    activeforeground=palette["primary_fg"] if selected else palette["text"],
                    highlightbackground=option_color if swatches else palette["border_alt"],
                    highlightcolor=option_color if swatches else palette["border_alt"],
                )

        for value, meta in options.items():
            label = str(meta.get("label", value.title()))
            if swatches:
                label = f"  {label}"
            button = tk.Button(
                row,
                text=label,
                relief="flat",
                bd=0,
                highlightthickness=1,
                font=(self.mono_font, 9),
                padx=12,
                pady=7,
                cursor="hand2",
                command=lambda item=value: select(item),
            )
            button.pack(side="left", padx=(0, 8), pady=(4, 0))
            buttons[value] = button

        variable.trace_add("write", redraw)
        redraw()

    def _apply_appearance_from_dialog(self, appearance_vars, save=False):
        self.theme_preset.set(appearance_vars["theme_preset"].get())
        self.accent_color.set(appearance_vars["accent_color"].get())
        self.ui_density.set(appearance_vars["ui_density"].get())
        self.ui_scale.set(appearance_vars["ui_scale"].get())
        if hasattr(self, "apply_appearance_settings"):
            self.apply_appearance_settings()
        if save and hasattr(self, "save_settings"):
            self.save_settings()
        if hasattr(self, "_footer_state_var"):
            self._footer_state_var.set("Appearance applied. Save & Apply persists the full settings set.")

    def _reset_appearance_vars(self, appearance_vars):
        for key, value in DEFAULT_APPEARANCE_SETTINGS.items():
            if key in appearance_vars:
                appearance_vars[key].set(value)
        if hasattr(self, "_footer_state_var"):
            self._footer_state_var.set("Appearance reset to defaults. Save & Apply to persist.")

    def _build_general_page(self, parent, palette, parallel_var, boot_delay_var, task_duration_var, max_videos_var, accounts_per_ld_var):
        self._page_heading(parent, palette, "GENERAL", "Launch & Session Controls", "Tune your main runtime values with cleaner, more readable controls.")

        grid1 = tk.Frame(parent, bg=palette["surface"])
        grid1.pack(fill="x", pady=(0, 12))
        self._metric_card(grid1, palette, "Parallel LDs", parallel_var, "active devices", "Recommended: 1–2 for mid-range PCs.", min_value=1)
        self._metric_card(grid1, palette, "Boot Delay", boot_delay_var, "seconds", "Increase if emulator startup is unstable.", min_value=1)

        grid2 = tk.Frame(parent, bg=palette["surface"])
        grid2.pack(fill="x", pady=(0, 12))
        self._metric_card(grid2, palette, "Task Duration", task_duration_var, "minutes", "Target session runtime per account.", min_value=1)
        self._metric_card(grid2, palette, "Max Reels", max_videos_var, "per cycle", "Use lower values for a safer behavior pattern.", min_value=1)

        grid3 = tk.Frame(parent, bg=palette["surface"])
        grid3.pack(fill="x", pady=(0, 12))
        self._metric_card(grid3, palette, "Accounts / LD", accounts_per_ld_var, "registration loops", "Register Account will run this many times per emulator.", min_value=1)

        outer, notes = self._premium_card(parent, palette, "Performance Notes", "Quick guidance based on current setup.")
        outer.pack(fill="x", pady=(2, 0))
        self._info_row(notes, palette, "System load", "Higher parallel counts increase CPU, RAM, and ADB contention.")
        self._info_row(notes, palette, "Safer setup", "Balanced pacing usually gives more stable startup and fewer connection issues.")
        self._info_row(notes, palette, "Best practice", "Change one value at a time, then test the workflow before raising throughput.")

    def _build_behavior_page(self, parent, palette, start_same_var, use_queue_var, auto_arrange_var, auto_shutdown_var, verify_account_var, parallel_var, boot_delay_var, task_duration_var, max_videos_var, reg_contact_mode_var, reg_contact_value_var, reg_phone_prefix_var):
        self._page_heading(parent, palette, "BEHAVIOR", "Dispatch & Queue Logic", "Configure how sessions start and how content is delivered during execution.")

        self._toggle_feature_card(parent, palette, "Start at Same Time", "Launch all selected instances together for faster startup on stronger machines.", start_same_var)
        self._toggle_feature_card(parent, palette, "Use Content Queue", "Enable a safer and more organized content delivery flow during the session.", use_queue_var)
        self._toggle_feature_card(parent, palette, "Auto Arrange LD", "Automatically arrange LD windows after the start stage completes.", auto_arrange_var)
        self._toggle_feature_card(parent, palette, "Auto Shutdown PC", "Shutdown Windows automatically after the current automation run finishes normally.", auto_shutdown_var)
        self._toggle_feature_card(parent, palette, "Verify Account", "When enabled, registration tasks continue into the account verification flow after signup.", verify_account_var)

        # Country / IP guard configuration
        outer, card = self._premium_card(
            parent,
            palette,
            "IP / Country Guard",
            "Block automation when your public IP is detected in selected countries.",
        )
        outer.pack(fill="x", pady=(12, 0))

        row = tk.Frame(card, bg=palette["surface_alt"])
        row.pack(fill="x", pady=(8, 0))

        tk.Label(
            row,
            text="Blocked Countries (ISO codes)",
            bg=palette["surface_alt"],
            fg=palette["text"],
            font=(self.mono_font, 8),
        ).pack(anchor="w")

        hint = (
            "Examples: US, KH, CN, TH, VN, PH, ID, MY, LA, MM\n"
            "Automation will not start if your public IP is in any blocked country."
        )
        tk.Label(
            card,
            text=hint,
            bg=palette["surface_alt"],
            fg=palette["muted"],
            justify="left",
            wraplength=520,
            font=(self.mono_font, 8),
        ).pack(anchor="w", pady=(2, 8))

        # Use the main app's StringVar so changes are saved directly.
        entry = tk.Entry(
            card,
            textvariable=getattr(self, "blocked_countries", None),
            bg=palette["surface"],
            fg=palette["text"],
            insertbackground=palette["text"],
        )
        entry.pack(fill="x")

        outer, reg_card = self._premium_card(
            parent,
            palette,
            "Register Account Contact",
            "Choose whether signup uses phone or email, and whether the value is fixed or generated.",
        )
        outer.pack(fill="x", pady=(12, 0))

        tk.Label(reg_card, text="Contact Type", bg=palette["surface_alt"], fg=palette["text"], font=(self.mono_font, 8)).pack(anchor="w")
        tb.Combobox(
            reg_card,
            textvariable=reg_contact_mode_var,
            values=("random_phone", "fixed_phone", "random_email", "fixed_email"),
            state="readonly",
            width=22,
        ).pack(anchor="w", pady=(4, 10))

        tk.Label(reg_card, text="Fixed Contact", bg=palette["surface_alt"], fg=palette["text"], font=(self.mono_font, 8)).pack(anchor="w")
        tk.Entry(
            reg_card,
            textvariable=reg_contact_value_var,
            bg=palette["surface"],
            fg=palette["text"],
            insertbackground=palette["text"],
        ).pack(fill="x", pady=(4, 10))

        import_row = tk.Frame(reg_card, bg=palette["surface_alt"])
        import_row.pack(fill="x", pady=(0, 10))
        tk.Button(
            import_row,
            text="Import TXT",
            bg=palette["surface"],
            fg=palette["text"],
            activebackground=palette["primary"],
            activeforeground=palette["surface"],
            relief="flat",
            bd=0,
            font=(self.mono_font, 9, "bold"),
            padx=12,
            pady=6,
            cursor="hand2",
            command=lambda: self._import_fixed_contacts_from_text(reg_contact_mode_var, reg_contact_value_var),
        ).pack(side="left")
        tk.Label(
            import_row,
            text="fixed_phone imports only phone numbers, fixed_email imports only emails",
            bg=palette["surface_alt"],
            fg=palette["muted"],
            font=(self.mono_font, 8),
        ).pack(side="left", padx=(10, 0))

        tk.Label(reg_card, text="Phone Prefix", bg=palette["surface_alt"], fg=palette["text"], font=(self.mono_font, 8)).pack(anchor="w")
        tk.Entry(
            reg_card,
            textvariable=reg_phone_prefix_var,
            bg=palette["surface"],
            fg=palette["text"],
            insertbackground=palette["text"],
        ).pack(fill="x")

        tk.Label(
            reg_card,
            text="Modes: random_phone, fixed_phone, random_email, fixed_email",
            bg=palette["surface_alt"],
            fg=palette["muted"],
            justify="left",
            wraplength=520,
            font=(self.mono_font, 8),
        ).pack(anchor="w", pady=(8, 0))

        outer, notes = self._premium_card(parent, palette, "Operational Notes", "Behavior settings should match your hardware and launch pacing.")
        outer.pack(fill="x", pady=(12, 0))
        self._info_row(notes, palette, "Parallel impact", f"Current parallel load: {parallel_var.get()} device(s).")
        self._info_row(notes, palette, "Boot pacing", f"Current startup delay: {boot_delay_var.get()} second(s).")
        self._info_row(notes, palette, "Session target", f"{task_duration_var.get()} min / {max_videos_var.get()} reels configured.")

    def _toggle_feature_card(self, parent, palette, title, description, variable):
        outer = tk.Frame(parent, bg=palette["border"], padx=1, pady=1)
        outer.pack(fill="x", pady=6)
        card = tk.Frame(outer, bg=palette["surface_alt"], padx=16, pady=14)
        card.pack(fill="x")

        left = tk.Frame(card, bg=palette["surface_alt"])
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text=title, bg=palette["surface_alt"], fg=palette["text"], font=(self.display_font, 12)).pack(anchor="w")
        tk.Label(left, text=description, bg=palette["surface_alt"], fg=palette["muted"], justify="left", wraplength=520, font=(self.mono_font, 8)).pack(anchor="w", pady=(5, 0))

        right = tk.Frame(card, bg=palette["surface_alt"])
        right.pack(side="right")

        state_var = tk.StringVar()
        state = tk.Label(right, textvariable=state_var, bg=palette["surface_alt"], fg=palette["primary"], font=(self.mono_font, 8))
        state.pack(anchor="e", pady=(0, 6))

        switch_shell = tk.Frame(right, bg=palette["surface"], width=64, height=30, cursor="hand2")
        switch_shell.pack(anchor="e")
        switch_shell.pack_propagate(False)
        knob = tk.Frame(switch_shell, bg=palette["text"], width=24, height=24)

        def redraw(*_):
            enabled = bool(variable.get())
            active_bg = palette.get("nav_active_bg", palette["surface_alt"])
            state_var.set("ENABLED" if enabled else "DISABLED")
            card.config(bg=active_bg if enabled else palette["surface_alt"])
            left.config(bg=active_bg if enabled else palette["surface_alt"])
            right.config(bg=active_bg if enabled else palette["surface_alt"])
            state.config(bg=active_bg if enabled else palette["surface_alt"], fg=palette["primary"] if enabled else palette["muted"])
            switch_shell.config(bg=palette["primary"] if enabled else palette["surface"])
            knob.place(x=36 if enabled else 4, y=3)

        def toggle(_event=None):
            variable.set(not variable.get())

        for widget in (outer, card, left, right, state, switch_shell, knob):
            widget.bind("<Button-1>", toggle)
        for child in left.winfo_children():
            child.bind("<Button-1>", toggle)

        variable.trace_add("write", redraw)
        redraw()

    def _build_profiles_page(self, parent, palette, parallel_var, boot_delay_var, task_duration_var, max_videos_var, start_same_var, use_queue_var, auto_arrange_var):
        self._page_heading(parent, palette, "PROFILES", "Preset Profiles", "Apply a starter preset, then fine-tune individual values if needed.")

        profiles = [
            ("Safe", "#38BDF8", "Low load and safer startup pacing for weaker hardware.", (1, 12, 10, 1, False, True), "Stable first"),
            ("Balanced", palette["primary"], "Best default profile for most daily usage.", (2, 8, 15, 2, False, True), "Recommended"),
            ("Aggressive", "#F59E0B", "Higher throughput for stronger hardware and faster cycles.", (4, 3, 25, 5, True, True), "High load"),
        ]

        for name, color, desc, values, tag in profiles:
            outer = tk.Frame(parent, bg=palette["border"], padx=1, pady=1)
            outer.pack(fill="x", pady=6)
            card = tk.Frame(outer, bg=palette["surface_alt"])
            card.pack(fill="x")

            accent = tk.Frame(card, bg=color, width=6)
            accent.pack(side="left", fill="y")

            content = tk.Frame(card, bg=palette["surface_alt"], padx=14, pady=14)
            content.pack(side="left", fill="both", expand=True)

            top = tk.Frame(content, bg=palette["surface_alt"])
            top.pack(fill="x")
            tk.Label(top, text=name, bg=palette["surface_alt"], fg=color, font=(self.display_font, 13)).pack(side="left")
            tk.Label(top, text=tag, bg=palette["surface"], fg=color, font=(self.mono_font, 8), padx=8, pady=3).pack(side="left", padx=(10, 0))
            tk.Button(
                top,
                text="Apply",
                relief="flat",
                bg=palette["surface"],
                fg=color,
                activebackground=palette["border_alt"],
                activeforeground=color,
                font=(self.mono_font, 9),
                padx=14,
                pady=6,
                cursor="hand2",
                command=lambda vals=values, profile_name=name: self._apply_settings_profile(
                    vals,
                    profile_name,
                    parallel_var,
                    boot_delay_var,
                    task_duration_var,
                    max_videos_var,
                    start_same_var,
                    use_queue_var,
                ),
            ).pack(side="right")

            tk.Label(content, text=desc, bg=palette["surface_alt"], fg=palette["muted"], font=(self.mono_font, 8), justify="left").pack(anchor="w", pady=(6, 10))

            stats = tk.Frame(content, bg=palette["surface_alt"])
            stats.pack(fill="x")
            labels = [
                f"LDs {values[0]}",
                f"Delay {values[1]}s",
                f"Duration {values[2]}m",
                f"Reels {values[3]}",
                "Sync On" if values[4] else "Sync Off",
                "Queue On" if values[5] else "Queue Off",
            ]
            for text in labels:
                tk.Label(stats, text=text, bg=palette["surface"], fg=palette["text"], font=(self.mono_font, 8), padx=8, pady=4).pack(side="left", padx=(0, 6))

    def _build_summary_page(self, parent, palette, parallel_var, boot_delay_var, task_duration_var, max_videos_var, accounts_per_ld_var, start_same_var, use_queue_var, auto_arrange_var, auto_shutdown_var, verify_account_var, reg_contact_mode_var, reg_contact_value_var, reg_phone_prefix_var, email_provider_var, email_address_var, email_sender_filter_var, email_subject_filter_var):
        self._page_heading(parent, palette, "SUMMARY", "Configuration Review", "Read the current setup before saving changes.")

        row = tk.Frame(parent, bg=palette["surface"])
        row.pack(fill="x", pady=(0, 12))

        self._summary_stat_card(row, palette, "Devices", parallel_var, "parallel")
        self._summary_stat_card(row, palette, "Startup", boot_delay_var, "sec")
        self._summary_stat_card(row, palette, "Session", task_duration_var, "min")
        self._summary_stat_card(row, palette, "Reels", max_videos_var, "items")
        self._summary_stat_card(row, palette, "Accounts / LD", accounts_per_ld_var, "loops")

        outer, detail = self._premium_card(parent, palette, "Live Readout", "Human-readable review of the active configuration.")
        outer.pack(fill="x", pady=(0, 12))
        self._summary_text_var = tk.StringVar()
        self._summary_detail_var = tk.StringVar()
        tk.Label(detail, textvariable=self._summary_text_var, bg=palette["surface_alt"], fg=palette["text"], justify="left", wraplength=640, font=(self.mono_font, 9)).pack(anchor="w")
        tk.Label(detail, textvariable=self._summary_detail_var, bg=palette["surface_alt"], fg=palette["muted"], justify="left", wraplength=640, font=(self.mono_font, 8)).pack(anchor="w", pady=(8, 0))

        outer2, impact = self._premium_card(parent, palette, "Impact Estimate", "Quick interpretation of the current setup.")
        outer2.pack(fill="x")
        self._impact_var = tk.StringVar()
        tk.Label(impact, textvariable=self._impact_var, bg=palette["surface_alt"], fg=palette["primary"], justify="left", wraplength=640, font=(self.mono_font, 9)).pack(anchor="w")

    def _summary_stat_card(self, parent, palette, title, variable, unit):
        outer, card = self._premium_card(parent, palette, title)
        outer.pack(side="left", fill="both", expand=True, padx=6)
        tk.Label(card, textvariable=variable, bg=palette["surface_alt"], fg=palette["primary"], font=(self.display_font, 22)).pack(anchor="w", pady=(6, 0))
        tk.Label(card, text=unit, bg=palette["surface_alt"], fg=palette["muted"], font=(self.mono_font, 8)).pack(anchor="w")

    def _build_premium_footer(self, parent, palette, dialog, parallel_var, boot_delay_var, task_duration_var, max_videos_var, accounts_per_ld_var, start_same_var, use_queue_var, auto_arrange_var, auto_shutdown_var, verify_account_var, reg_contact_mode_var, reg_contact_value_var, reg_phone_prefix_var, email_provider_var, email_address_var, email_app_password_var, email_imap_server_var, email_imap_port_var, email_mailbox_var, email_use_ssl_var, email_unread_only_var, email_sender_filter_var, email_subject_filter_var, email_timeout_var, email_poll_interval_var, email_mark_as_seen_var, appearance_vars):
        footer = tk.Frame(parent, bg=palette["surface_alt"], padx=18, pady=14, highlightthickness=1, highlightbackground=palette["border_alt"])
        footer.pack(fill="x")

        left = tk.Frame(footer, bg=palette["surface_alt"])
        left.pack(side="left", fill="x", expand=True)
        self._footer_state_var = tk.StringVar(value="Changes are local until saved.")
        tk.Label(left, textvariable=self._footer_state_var, bg=palette["surface_alt"], fg=palette["muted"], font=(self.mono_font, 9)).pack(anchor="w")

        right = tk.Frame(footer, bg=palette["surface_alt"])
        right.pack(side="right")

        self._footer_button(right, palette, "Cancel", palette["muted"], palette["surface"], lambda: self._close_settings_dialog(dialog))
        self._footer_button(
            right,
            palette,
            "Reset Defaults",
            "#F59E0B",
            palette["surface"],
            lambda: self._apply_settings_profile((2, 8, 15, 2, False, True), "Balanced", parallel_var, boot_delay_var, task_duration_var, max_videos_var, start_same_var, use_queue_var),
        )
        self._footer_button(
            right,
            palette,
            "Save & Apply",
            palette["surface"],
            palette["primary"],
            lambda: self._save_settings_from_dialog(dialog, parallel_var, boot_delay_var, task_duration_var, max_videos_var, accounts_per_ld_var, start_same_var, use_queue_var, auto_arrange_var, auto_shutdown_var, verify_account_var, reg_contact_mode_var, reg_contact_value_var, reg_phone_prefix_var, email_provider_var, email_address_var, email_app_password_var, email_imap_server_var, email_imap_port_var, email_mailbox_var, email_use_ssl_var, email_unread_only_var, email_sender_filter_var, email_subject_filter_var, email_timeout_var, email_poll_interval_var, email_mark_as_seen_var, appearance_vars),
            filled=True,
        )

    def _footer_button(self, parent, palette, text, fg, bg, command, filled=False):
        wrap = tk.Frame(parent, bg=bg, padx=1, pady=1)
        wrap.pack(side="right", padx=4)
        tk.Button(
            wrap,
            text=text,
            relief="flat",
            bg=bg if filled else palette["surface_alt"],
            fg=fg,
            activebackground=palette["border_alt"],
            activeforeground=fg,
            font=(self.mono_font, 9),
            padx=14,
            pady=7,
            cursor="hand2",
            command=command,
        ).pack()

    def _bind_summary_refresh(self, parallel_var, boot_delay_var, task_duration_var, max_videos_var, accounts_per_ld_var, start_same_var, use_queue_var, auto_arrange_var, auto_shutdown_var, verify_account_var, reg_contact_mode_var, reg_contact_value_var, reg_phone_prefix_var, email_provider_var, email_address_var, email_sender_filter_var, email_subject_filter_var):
        def refresh(*_):
            profile = self._detect_profile(parallel_var.get(), boot_delay_var.get(), task_duration_var.get(), max_videos_var.get(), bool(start_same_var.get()), bool(use_queue_var.get()))
            self._header_status_var.set(profile)
            self._header_meta_var.set(f"{parallel_var.get()} LD • {'Queue On' if use_queue_var.get() else 'Queue Off'}")
            self._settings_overview_var.set(
                f"{parallel_var.get()} LD • {boot_delay_var.get()}s boot\n{task_duration_var.get()} min session • {max_videos_var.get()} reels"
            )
            if hasattr(self, "_summary_text_var"):
                self._summary_text_var.set(
                    f"Profile: {profile}\nParallel launch: {parallel_var.get()} device(s)\nBoot delay: {boot_delay_var.get()} second(s)\nTask duration: {task_duration_var.get()} minute(s)\nMax reels: {max_videos_var.get()} item(s)\nStart same time: {'Enabled' if start_same_var.get() else 'Disabled'}\nUse queue: {'Enabled' if use_queue_var.get() else 'Disabled'}\nAuto arrange LD: {'Enabled' if auto_arrange_var.get() else 'Disabled'}\nAuto shutdown PC: {'Enabled' if auto_shutdown_var.get() else 'Disabled'}\nVerify account: {'Enabled' if verify_account_var.get() else 'Disabled'}\nReg contact mode: {reg_contact_mode_var.get()}\nReg contact value: {reg_contact_value_var.get() or '-'}\nReg phone prefix: {reg_phone_prefix_var.get() or '-'}\nEmail provider: {email_provider_var.get()}\nEmail address: {email_address_var.get() or '-'}\nEmail filters: from='{email_sender_filter_var.get() or '*'}', subject='{email_subject_filter_var.get() or '*'}'"
                )
            if hasattr(self, "_summary_detail_var"):
                self._summary_detail_var.set(
                    "Balanced pacing is recommended for most systems. Aggressive values increase throughput but also raise system load and startup risk."
                )
            if hasattr(self, "_impact_var"):
                load = "High" if parallel_var.get() >= 4 or start_same_var.get() else "Medium" if parallel_var.get() >= 2 else "Low"
                self._impact_var.set(f"Estimated load: {load}. Keep queue enabled for a cleaner execution flow.")
            if hasattr(self, "_footer_state_var"):
                self._footer_state_var.set(f"Current profile: {profile}. Review summary before saving.")

        for var in (parallel_var, boot_delay_var, task_duration_var, max_videos_var, start_same_var, use_queue_var, auto_arrange_var, auto_shutdown_var, verify_account_var, reg_contact_mode_var, reg_contact_value_var, reg_phone_prefix_var, email_provider_var, email_address_var, email_sender_filter_var, email_subject_filter_var):
            var.trace_add("write", refresh)
        refresh()

    def _bind_summary_refresh_with_accounts(self, parallel_var, boot_delay_var, task_duration_var, max_videos_var, accounts_per_ld_var, start_same_var, use_queue_var, auto_arrange_var, auto_shutdown_var, verify_account_var, reg_contact_mode_var, reg_contact_value_var, reg_phone_prefix_var, email_provider_var, email_address_var, email_sender_filter_var, email_subject_filter_var):
        def refresh(*_):
            profile = self._detect_profile(
                parallel_var.get(),
                boot_delay_var.get(),
                task_duration_var.get(),
                max_videos_var.get(),
                bool(start_same_var.get()),
                bool(use_queue_var.get()),
            )
            self._header_status_var.set(profile)
            self._header_meta_var.set(f"{parallel_var.get()} LD | {'Queue On' if use_queue_var.get() else 'Queue Off'}")
            self._settings_overview_var.set(
                f"{parallel_var.get()} LD | {boot_delay_var.get()}s boot\n"
                f"{task_duration_var.get()} min session | {max_videos_var.get()} reels | {accounts_per_ld_var.get()} acc/LD"
            )
            if hasattr(self, "_summary_text_var"):
                self._summary_text_var.set(
                    f"Profile: {profile}\n"
                    f"Parallel launch: {parallel_var.get()} device(s)\n"
                    f"Boot delay: {boot_delay_var.get()} second(s)\n"
                    f"Task duration: {task_duration_var.get()} minute(s)\n"
                    f"Max reels: {max_videos_var.get()} item(s)\n"
                    f"Accounts per LD: {accounts_per_ld_var.get()}\n"
                    f"Start same time: {'Enabled' if start_same_var.get() else 'Disabled'}\n"
                    f"Use queue: {'Enabled' if use_queue_var.get() else 'Disabled'}\n"
                    f"Auto arrange LD: {'Enabled' if auto_arrange_var.get() else 'Disabled'}\n"
                    f"Auto shutdown PC: {'Enabled' if auto_shutdown_var.get() else 'Disabled'}\n"
                    f"Verify account: {'Enabled' if verify_account_var.get() else 'Disabled'}\n"
                    f"Reg contact mode: {reg_contact_mode_var.get()}\n"
                    f"Reg contact value: {reg_contact_value_var.get() or '-'}\n"
                    f"Reg phone prefix: {reg_phone_prefix_var.get() or '-'}\n"
                    f"Email provider: {email_provider_var.get()}\n"
                    f"Email address: {email_address_var.get() or '-'}\n"
                    f"Email filters: from='{email_sender_filter_var.get() or '*'}', subject='{email_subject_filter_var.get() or '*'}'"
                )
            if hasattr(self, "_summary_detail_var"):
                self._summary_detail_var.set(
                    "Balanced pacing is recommended for most systems. Aggressive values increase throughput but also raise system load and startup risk."
                )
            if hasattr(self, "_impact_var"):
                load = "High" if parallel_var.get() >= 4 or start_same_var.get() else "Medium" if parallel_var.get() >= 2 else "Low"
                self._impact_var.set(f"Estimated load: {load}. Keep queue enabled for a cleaner execution flow.")
            if hasattr(self, "_footer_state_var"):
                self._footer_state_var.set(f"Current profile: {profile}. Review summary before saving.")

        for var in (
            parallel_var,
            boot_delay_var,
            task_duration_var,
            max_videos_var,
            accounts_per_ld_var,
            start_same_var,
            use_queue_var,
            auto_arrange_var,
            auto_shutdown_var,
            verify_account_var,
            reg_contact_mode_var,
            reg_contact_value_var,
            reg_phone_prefix_var,
            email_provider_var,
            email_address_var,
            email_sender_filter_var,
            email_subject_filter_var,
        ):
            var.trace_add("write", refresh)
        refresh()

    def _detect_profile(self, parallel, delay, duration, reels, start_same, use_queue):
        profiles = {
            "Safe": (1, 12, 10, 1, False, True),
            "Balanced": (2, 8, 15, 2, False, True),
            "Aggressive": (4, 3, 25, 5, True, True),
        }
        current = (parallel, delay, duration, reels, start_same, use_queue)
        for name, values in profiles.items():
            if current == values:
                return name
        return "Custom"

    def _info_row(self, parent, palette, label, text):
        row = tk.Frame(parent, bg=palette["surface_alt"])
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label.upper(), bg=palette["surface_alt"], fg=palette["primary"], font=(self.mono_font, 8), width=15, anchor="w").pack(side="left")
        tk.Label(row, text=text, bg=palette["surface_alt"], fg=palette["text"], font=(self.mono_font, 8), anchor="w", justify="left", wraplength=520).pack(side="left", fill="x", expand=True)

    def _open_settings_page(self, key):
        for name, page in getattr(self, "_settings_pages", {}).items():
            if name == key:
                page.lift()
        for name, widgets in getattr(self, "_settings_nav_buttons", {}).items():
            outer, accent, btn = widgets
            active = name == key
            active_bg = self.palette.get("nav_active_bg", self.palette["surface_alt"])
            outer.config(bg=self.palette["border_alt"] if active else self.palette["surface_alt"])
            accent.config(bg=self.palette["primary"] if active else self.palette["surface_alt"])
            btn.config(bg=active_bg if active else self.palette["surface_alt"])
            for child in btn.winfo_children():
                try:
                    child.config(bg=active_bg if active else self.palette["surface_alt"])
                except Exception:
                    pass
                for sub in getattr(child, "winfo_children", lambda: [])():
                    try:
                        sub.config(bg=active_bg if active else self.palette["surface_alt"])
                    except Exception:
                        pass

    def _apply_settings_profile(self, values, profile_name, parallel_var, boot_delay_var, task_duration_var, max_videos_var, start_same_var, use_queue_var):
        parallel, delay, duration, reels, start_same, use_queue = values
        parallel_var.set(parallel)
        boot_delay_var.set(delay)
        task_duration_var.set(duration)
        max_videos_var.set(reels)
        start_same_var.set(start_same)
        use_queue_var.set(use_queue)
        if hasattr(self, "_footer_state_var"):
            self._footer_state_var.set(f"Applied profile: {profile_name}.")

    def _save_settings_from_dialog(self, dialog, parallel_var, boot_delay_var, task_duration_var, max_videos_var, accounts_per_ld_var, start_same_var, use_queue_var, auto_arrange_var, auto_shutdown_var, verify_account_var, reg_contact_mode_var, reg_contact_value_var, reg_phone_prefix_var, email_provider_var, email_address_var, email_app_password_var, email_imap_server_var, email_imap_port_var, email_mailbox_var, email_use_ssl_var, email_unread_only_var, email_sender_filter_var, email_subject_filter_var, email_timeout_var, email_poll_interval_var, email_mark_as_seen_var, appearance_vars):
        self.parallel_ld.set(parallel_var.get())
        self.boot_delay.set(boot_delay_var.get())
        self.task_duration.set(task_duration_var.get())
        self.max_videos.set(max_videos_var.get())
        self.accounts_per_ld.set(accounts_per_ld_var.get())
        self.start_same_time.set(start_same_var.get())
        self.use_content_queue.set(use_queue_var.get())
        self.auto_arrange_ld.set(auto_arrange_var.get())
        self.auto_shutdown_pc.set(auto_shutdown_var.get())
        self.verify_account.set(verify_account_var.get())
        self.reg_contact_mode.set(reg_contact_mode_var.get())
        self.reg_contact_value.set(reg_contact_value_var.get())
        self.reg_phone_prefix.set(reg_phone_prefix_var.get())
        self.email_provider.set(email_provider_var.get())
        self.email_address.set(email_address_var.get())
        self.email_app_password.set(email_app_password_var.get())
        self.email_imap_server.set(email_imap_server_var.get())
        self.email_imap_port.set(email_imap_port_var.get())
        self.email_mailbox.set(email_mailbox_var.get())
        self.email_use_ssl.set(email_use_ssl_var.get())
        self.email_unread_only.set(email_unread_only_var.get())
        self.email_sender_filter.set(email_sender_filter_var.get())
        self.email_subject_filter.set(email_subject_filter_var.get())
        self.email_timeout_seconds.set(email_timeout_var.get())
        self.email_poll_interval_seconds.set(email_poll_interval_var.get())
        self.email_mark_as_seen.set(email_mark_as_seen_var.get())
        self.theme_preset.set(appearance_vars["theme_preset"].get())
        self.accent_color.set(appearance_vars["accent_color"].get())
        self.ui_density.set(appearance_vars["ui_density"].get())
        self.ui_scale.set(appearance_vars["ui_scale"].get())
        if hasattr(self, "apply_appearance_settings"):
            self.apply_appearance_settings()
        if hasattr(self, "save_settings"):
            try:
                self.save_settings()
            except Exception:
                pass
        self._close_settings_dialog(dialog)

    def _close_settings_dialog(self, dialog):
        current = getattr(self, "_settings_dialog", None)
        if current is dialog:
            self._settings_dialog = None
        try:
            if dialog.winfo_exists():
                try:
                    dialog.grab_release()
                except Exception:
                    pass
                dialog.destroy()
        except Exception:
            pass
