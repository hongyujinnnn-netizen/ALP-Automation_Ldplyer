from __future__ import annotations

from dataclasses import dataclass, field

from core.credential_store import CredentialStore


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


@dataclass(slots=True, init=False)
class EmailAccountConfig:
    """IMAP mailbox configuration for an authorized email account.

    The mailbox app password is never stored on this dataclass as a regular
    field. It lives in the OS credential vault (via :class:`CredentialStore`)
    and is exposed through the :attr:`app_password` property, with an in-process
    cache held in ``_runtime_password`` for the current session.
    """

    provider: str
    email_address: str
    imap_server: str
    imap_port: int
    mailbox: str
    use_ssl: bool
    _runtime_password: str = field(default="", repr=False, compare=False)

    def __init__(
        self,
        provider: str = "yandex",
        email_address: str = "",
        app_password: str = "",
        imap_server: str = "imap.yandex.com",
        imap_port: int = 993,
        mailbox: str = "INBOX",
        use_ssl: bool = True,
    ) -> None:
        self.provider = provider
        self.email_address = email_address
        self.imap_server = imap_server
        self.imap_port = imap_port
        self.mailbox = mailbox
        self.use_ssl = use_ssl
        self._runtime_password = ""
        if app_password:
            self.app_password = str(app_password)

    @property
    def app_password(self) -> str:
        if self._runtime_password:
            return self._runtime_password
        if self.email_address:
            stored = CredentialStore().get_password(self.email_address)
            if stored:
                return stored
        return ""

    @app_password.setter
    def app_password(self, value: object) -> None:
        text = str(value or "")
        self._runtime_password = text
        if self.email_address and text:
            CredentialStore().set_password(self.email_address, text)

    def clear_password(self) -> None:
        """Wipe the in-process cache and the keyring entry for this account."""

        self._runtime_password = ""
        if self.email_address:
            CredentialStore().delete_password(self.email_address)

    def with_provider_defaults(self) -> "EmailAccountConfig":
        """Return a copy with provider defaults filled in for blank values."""

        defaults = get_provider_defaults(self.provider)
        new = EmailAccountConfig(
            provider=str(self.provider or "custom").strip().lower() or "custom",
            email_address=str(self.email_address or "").strip(),
            imap_server=str(self.imap_server or defaults.get("imap_server") or "").strip(),
            imap_port=int(self.imap_port or defaults.get("imap_port") or 993),
            mailbox=str(self.mailbox or defaults.get("mailbox") or "INBOX").strip(),
            use_ssl=bool(defaults.get("use_ssl", True) if self.use_ssl is None else self.use_ssl),
        )
        # Copy the runtime cache directly to avoid a redundant keyring write
        # on every defaults-resolve call.
        new._runtime_password = self._runtime_password
        return new


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
