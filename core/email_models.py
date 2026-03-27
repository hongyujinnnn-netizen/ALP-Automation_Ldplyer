from __future__ import annotations

from dataclasses import dataclass


PROVIDER_DEFAULTS: dict[str, dict[str, object]] = {
    "yandex": {
        "imap_server": "imap.yandex.com",
        "imap_port": 993,
        "mailbox": "INBOX",
        "use_ssl": True,
    },
    "gmail": {
        "imap_server": "imap.gmail.com",
        "imap_port": 993,
        "mailbox": "INBOX",
        "use_ssl": True,
    },
    "outlook": {
        "imap_server": "outlook.office365.com",
        "imap_port": 993,
        "mailbox": "INBOX",
        "use_ssl": True,
    },
}


def get_provider_defaults(provider: str) -> dict[str, object]:
    """Return default IMAP settings for a provider when known."""

    return dict(PROVIDER_DEFAULTS.get(str(provider or "").strip().lower(), {}))


@dataclass(slots=True)
class EmailAccountConfig:
    """IMAP mailbox configuration for an authorized email account."""

    provider: str = "yandex"
    email_address: str = ""
    app_password: str = ""
    imap_server: str = "imap.yandex.com"
    imap_port: int = 993
    mailbox: str = "INBOX"
    use_ssl: bool = True

    def with_provider_defaults(self) -> "EmailAccountConfig":
        """Return a copy with provider defaults filled in for blank values."""

        defaults = get_provider_defaults(self.provider)
        return EmailAccountConfig(
            provider=str(self.provider or "custom").strip().lower() or "custom",
            email_address=str(self.email_address or "").strip(),
            app_password=str(self.app_password or ""),
            imap_server=str(self.imap_server or defaults.get("imap_server") or "").strip(),
            imap_port=int(self.imap_port or defaults.get("imap_port") or 993),
            mailbox=str(self.mailbox or defaults.get("mailbox") or "INBOX").strip(),
            use_ssl=bool(defaults.get("use_ssl", True) if self.use_ssl is None else self.use_ssl),
        )


@dataclass(slots=True)
class OTPRequest:
    """Polling and matching options for OTP retrieval."""

    sender_filter: str = ""
    subject_filter: str = ""
    unread_only: bool = True
    timeout_seconds: int = 90
    poll_interval_seconds: int = 5
    mark_as_seen: bool = False
    otp_patterns: list[str] | None = None


@dataclass(slots=True)
class OTPResult:
    """Structured result for OTP retrieval and related mailbox actions."""

    success: bool
    code: str | None = None
    error: str | None = None
    details: str | None = None
    matched_sender: str | None = None
    matched_subject: str | None = None
    source_message_id: str | None = None


@dataclass(slots=True)
class EmailMessageSummary:
    """Lightweight decoded mailbox metadata used by the OTP service."""

    message_id: str
    sender: str
    subject: str
