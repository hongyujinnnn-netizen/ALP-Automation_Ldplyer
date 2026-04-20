from __future__ import annotations

import threading
import tkinter as tk

import ttkbootstrap as tb

from core.email_models import EmailAccountConfig, OTPRequest, get_provider_defaults


class EmailSettingsDialogMixin:
    """Email OTP settings UI helpers for the main settings dialog."""

    def _build_email_settings_page(
        self,
        parent,
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
        appearance_vars=None,
    ):
        self._page_heading(
            parent,
            palette,
            "EMAIL OTP",
            "Mailbox Reader",
            "Configure authorized IMAP access, test connectivity, and poll for one-time codes without putting mailbox logic in the GUI layer.",
        )

        outer, account_card = self._premium_card(
            parent,
            palette,
            "Mailbox Configuration",
            "Yandex is prefilled. Gmail, Outlook, or custom IMAP values can be entered for authorized mailboxes later.",
        )
        outer.pack(fill="x", pady=(0, 12))

        grid = tk.Frame(account_card, bg=palette["surface_alt"])
        grid.pack(fill="x")
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)

        provider_combo = tb.Combobox(
            grid,
            textvariable=email_provider_var,
            values=("yandex", "gmail", "outlook", "custom"),
            state="readonly",
            width=24,
        )
        self._email_form_field(
            grid,
            palette,
            0,
            0,
            "Provider",
            provider_combo,
        )
        self._email_form_field(
            grid,
            palette,
            0,
            1,
            "Email Address",
            tk.Entry(
                grid,
                textvariable=email_address_var,
                bg=palette["surface"],
                fg=palette["text"],
                insertbackground=palette["text"],
            ),
        )
        self._email_form_field(
            grid,
            palette,
            1,
            0,
            "App Password",
            tk.Entry(
                grid,
                textvariable=email_app_password_var,
                show="*",
                bg=palette["surface"],
                fg=palette["text"],
                insertbackground=palette["text"],
            ),
        )
        self._email_form_field(
            grid,
            palette,
            1,
            1,
            "IMAP Server",
            tk.Entry(
                grid,
                textvariable=email_imap_server_var,
                bg=palette["surface"],
                fg=palette["text"],
                insertbackground=palette["text"],
            ),
        )
        self._email_form_field(
            grid,
            palette,
            2,
            0,
            "Port",
            tk.Entry(
                grid,
                textvariable=email_imap_port_var,
                bg=palette["surface"],
                fg=palette["text"],
                insertbackground=palette["text"],
            ),
        )
        self._email_form_field(
            grid,
            palette,
            2,
            1,
            "Mailbox",
            tk.Entry(
                grid,
                textvariable=email_mailbox_var,
                bg=palette["surface"],
                fg=palette["text"],
                insertbackground=palette["text"],
            ),
        )

        toggle_row = tk.Frame(account_card, bg=palette["surface_alt"])
        toggle_row.pack(fill="x", pady=(10, 0))
        tb.Checkbutton(toggle_row, text="Use SSL/TLS", variable=email_use_ssl_var, bootstyle="round-toggle").pack(side="left")
        tk.Label(
            toggle_row,
            text="Use app-password-based login for mailboxes you own or are explicitly authorized to access.",
            bg=palette["surface_alt"],
            fg=palette["muted"],
            font=(self.mono_font, 8),
        ).pack(side="left", padx=(12, 0))

        outer2, polling_card = self._premium_card(
            parent,
            palette,
            "Polling & Filters",
            "Filters are optional substring matches. Subject and sender are checked before OTP extraction.",
        )
        outer2.pack(fill="x", pady=(0, 12))

        grid2 = tk.Frame(polling_card, bg=palette["surface_alt"])
        grid2.pack(fill="x")
        grid2.grid_columnconfigure(0, weight=1)
        grid2.grid_columnconfigure(1, weight=1)

        self._email_form_field(
            grid2,
            palette,
            0,
            0,
            "Sender Filter",
            tk.Entry(
                grid2,
                textvariable=email_sender_filter_var,
                bg=palette["surface"],
                fg=palette["text"],
                insertbackground=palette["text"],
            ),
        )
        self._email_form_field(
            grid2,
            palette,
            0,
            1,
            "Subject Filter",
            tk.Entry(
                grid2,
                textvariable=email_subject_filter_var,
                bg=palette["surface"],
                fg=palette["text"],
                insertbackground=palette["text"],
            ),
        )
        self._email_form_field(
            grid2,
            palette,
            1,
            0,
            "Timeout (sec)",
            tk.Entry(
                grid2,
                textvariable=email_timeout_var,
                bg=palette["surface"],
                fg=palette["text"],
                insertbackground=palette["text"],
            ),
        )
        self._email_form_field(
            grid2,
            palette,
            1,
            1,
            "Poll Interval (sec)",
            tk.Entry(
                grid2,
                textvariable=email_poll_interval_var,
                bg=palette["surface"],
                fg=palette["text"],
                insertbackground=palette["text"],
            ),
        )

        toggle_row2 = tk.Frame(polling_card, bg=palette["surface_alt"])
        toggle_row2.pack(fill="x", pady=(10, 0))
        tb.Checkbutton(toggle_row2, text="Unread only", variable=email_unread_only_var, bootstyle="round-toggle").pack(side="left")
        tb.Checkbutton(toggle_row2, text="Mark matched email as seen", variable=email_mark_as_seen_var, bootstyle="round-toggle").pack(side="left", padx=(16, 0))

        outer3, actions_card = self._premium_card(
            parent,
            palette,
            "Test Actions",
            "Connection test only verifies IMAP access. OTP actions use the controller and service layers.",
        )
        outer3.pack(fill="x")

        self._email_action_status_var = tk.StringVar(value="Ready. Save settings after confirming the mailbox connection.")
        tk.Label(
            actions_card,
            textvariable=self._email_action_status_var,
            bg=palette["surface_alt"],
            fg=palette["primary"],
            justify="left",
            wraplength=640,
            font=(self.mono_font, 9),
        ).pack(anchor="w")

        action_row = tk.Frame(actions_card, bg=palette["surface_alt"])
        action_row.pack(fill="x", pady=(12, 0))
        self._email_action_buttons = []

        save_btn = self._email_action_button(
            action_row,
            palette,
            "Save Settings",
            lambda: self._save_email_settings_only(
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
            ),
            filled=False,
        )
        test_connection_btn = self._email_action_button(
            action_row,
            palette,
            "Test Connection",
            lambda: self._run_email_action(
                "connection",
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
            ),
            filled=False,
        )
        test_fetch_btn = self._email_action_button(
            action_row,
            palette,
            "Test OTP Fetch",
            lambda: self._run_email_action(
                "fetch",
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
            ),
            filled=False,
        )
        wait_btn = self._email_action_button(
            action_row,
            palette,
            "Wait For OTP",
            lambda: self._run_email_action(
                "wait",
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
            ),
            filled=True,
        )
        self._email_action_buttons.extend([save_btn, test_connection_btn, test_fetch_btn, wait_btn])

        provider_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._apply_email_provider_defaults(
                email_provider_var,
                email_imap_server_var,
                email_imap_port_var,
                email_mailbox_var,
                email_use_ssl_var,
            ),
        )

    def _email_form_field(self, parent, palette, row, column, label, widget):
        label_row = row * 2
        field_row = label_row + 1
        tk.Label(
            parent,
            text=label,
            bg=palette["surface_alt"],
            fg=palette["text"],
            font=(self.mono_font, 8),
        ).grid(row=label_row, column=column, sticky="w", padx=6, pady=(6, 0))
        widget.grid(row=field_row, column=column, sticky="ew", padx=6, pady=(4, 10))

    def _email_action_button(self, parent, palette, text, command, filled=False):
        wrap = tk.Frame(parent, bg=palette["surface"] if filled else palette["surface_alt"], padx=1, pady=1)
        wrap.pack(side="left", padx=(0, 8))
        button = tk.Button(
            wrap,
            text=text,
            relief="flat",
            bg=palette["primary"] if filled else palette["surface"],
            fg=palette["surface"] if filled else palette["text"],
            activebackground=palette["border_alt"],
            activeforeground=palette["text"] if not filled else palette["surface"],
            font=(self.mono_font, 9),
            padx=14,
            pady=7,
            cursor="hand2",
            command=command,
        )
        button.pack()
        return button

    def _apply_email_provider_defaults(
        self,
        provider_var,
        imap_server_var,
        imap_port_var,
        mailbox_var,
        use_ssl_var,
    ):
        defaults = get_provider_defaults(provider_var.get())
        if not defaults:
            return
        imap_server_var.set(str(defaults.get("imap_server") or ""))
        imap_port_var.set(int(defaults.get("imap_port") or 993))
        mailbox_var.set(str(defaults.get("mailbox") or "INBOX"))
        use_ssl_var.set(bool(defaults.get("use_ssl", True)))

    def _save_email_settings_only(
        self,
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
    ):
        if not hasattr(self, "otp_controller"):
            self._email_action_status_var.set("OTP controller is not available.")
            return

        config, request = self._build_email_models_from_vars(
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
        )
        if not self.otp_controller.save_email_settings(config, request):
            self._email_action_status_var.set("Email OTP settings could not be saved. Check the log for details.")
            return

        self._sync_email_dialog_vars_to_app_vars(
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
        )
        self._email_action_status_var.set("Email OTP settings saved.")

    def _run_email_action(
        self,
        action_name,
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
    ):
        if not hasattr(self, "otp_controller"):
            self._email_action_status_var.set("OTP controller is not available.")
            return

        config, request = self._build_email_models_from_vars(
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
        )

        validation_error = self.otp_controller.validate(config, request)
        if action_name == "connection":
            validation_error = self.otp_controller.validate_config(config)
        if validation_error:
            self._email_action_status_var.set(validation_error)
            self.log(validation_error, "WARNING")
            return

        self._set_email_action_buttons_state("disabled")
        self._email_action_status_var.set(
            {
                "connection": "Testing mailbox connection...",
                "fetch": "Scanning current mailbox for a matching OTP...",
                "wait": "Polling mailbox until a matching OTP arrives...",
            }.get(action_name, "Working...")
        )

        def worker():
            if action_name == "connection":
                result = self.otp_controller.test_connection(config)
            elif action_name == "fetch":
                result = self.otp_controller.test_fetch_latest_otp(config, request)
            else:
                result = self.otp_controller.wait_for_otp(config, request)

            def finish():
                self._set_email_action_buttons_state("normal")
                if result.success and result.code:
                    self._email_action_status_var.set(f"OTP found: {result.code}")
                elif result.success:
                    self._email_action_status_var.set(result.details or "Action completed successfully.")
                else:
                    self._email_action_status_var.set(result.error or "The requested email action failed.")

            self.root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def _set_email_action_buttons_state(self, state):
        for button in getattr(self, "_email_action_buttons", []):
            try:
                button.config(state=state)
            except Exception:
                pass

    def _build_email_models_from_vars(
        self,
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
    ):
        imap_port = self._safe_int_var_value(email_imap_port_var, 993)
        timeout_seconds = self._safe_int_var_value(email_timeout_var, 90)
        poll_interval_seconds = self._safe_int_var_value(email_poll_interval_var, 5)
        config = EmailAccountConfig(
            provider=str(email_provider_var.get() or "yandex"),
            email_address=str(email_address_var.get() or "").strip(),
            app_password=str(email_app_password_var.get() or ""),
            imap_server=str(email_imap_server_var.get() or "").strip(),
            imap_port=imap_port,
            mailbox=str(email_mailbox_var.get() or "INBOX").strip(),
            use_ssl=bool(email_use_ssl_var.get()),
        )
        request = OTPRequest(
            sender_filter=str(email_sender_filter_var.get() or "").strip(),
            subject_filter=str(email_subject_filter_var.get() or "").strip(),
            unread_only=bool(email_unread_only_var.get()),
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            mark_as_seen=bool(email_mark_as_seen_var.get()),
        )
        return config, request

    def _sync_email_dialog_vars_to_app_vars(
        self,
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
    ):
        self.email_provider.set(email_provider_var.get())
        self.email_address.set(email_address_var.get())
        self.email_app_password.set(email_app_password_var.get())
        self.email_imap_server.set(email_imap_server_var.get())
        self.email_imap_port.set(self._safe_int_var_value(email_imap_port_var, 993))
        self.email_mailbox.set(email_mailbox_var.get())
        self.email_use_ssl.set(bool(email_use_ssl_var.get()))
        self.email_unread_only.set(bool(email_unread_only_var.get()))
        self.email_sender_filter.set(email_sender_filter_var.get())
        self.email_subject_filter.set(email_subject_filter_var.get())
        self.email_timeout_seconds.set(self._safe_int_var_value(email_timeout_var, 90))
        self.email_poll_interval_seconds.set(self._safe_int_var_value(email_poll_interval_var, 5))
        self.email_mark_as_seen.set(bool(email_mark_as_seen_var.get()))

    @staticmethod
    def _safe_int_var_value(var, default):
        try:
            return int(var.get())
        except (tk.TclError, TypeError, ValueError):
            return int(default)
