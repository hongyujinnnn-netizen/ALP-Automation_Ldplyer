from __future__ import annotations

import imaplib
import socket
from email import message_from_bytes, policy
from email.header import decode_header
from email.message import Message

from core.email_models import EmailAccountConfig
from core.otp_parser import html_to_text, normalize_text


class EmailServiceError(RuntimeError):
    """Raised when mailbox operations fail."""


class EmailService:
    """IMAP mailbox access boundary for authorized email retrieval."""

    def __init__(self) -> None:
        self._connection: imaplib.IMAP4 | None = None
        self._selected_mailbox: str | None = None

    def connect(self, config: EmailAccountConfig) -> None:
        """Connect, authenticate, and select the configured mailbox."""

        resolved = config.with_provider_defaults()
        try:
            connection: imaplib.IMAP4
            if resolved.use_ssl:
                connection = imaplib.IMAP4_SSL(resolved.imap_server, resolved.imap_port)
            else:
                connection = imaplib.IMAP4(resolved.imap_server, resolved.imap_port)
            connection.login(resolved.email_address, resolved.app_password)
            status, _ = connection.select(resolved.mailbox or "INBOX")
            if status != "OK":
                connection.logout()
                raise EmailServiceError(f"Could not select mailbox '{resolved.mailbox}'.")
            self._connection = connection
            self._selected_mailbox = resolved.mailbox or "INBOX"
        except (imaplib.IMAP4.error, OSError, socket.error) as exc:
            self._connection = None
            self._selected_mailbox = None
            raise EmailServiceError(str(exc)) from exc

    def disconnect(self) -> None:
        """Close and log out from the active IMAP session."""

        if self._connection is None:
            return

        try:
            if self._selected_mailbox:
                try:
                    self._connection.close()
                except Exception:
                    pass
            self._connection.logout()
        finally:
            self._connection = None
            self._selected_mailbox = None

    def search_message_ids(self, unread_only: bool = True) -> list[str]:
        """Search the selected mailbox and return message ids."""

        connection = self._require_connection()
        status, data = connection.search(None, "UNSEEN" if unread_only else "ALL")
        if status != "OK":
            raise EmailServiceError("Failed to search mailbox.")

        raw_ids = data[0].split() if data and data[0] else []
        return [message_id.decode("utf-8", errors="ignore") for message_id in raw_ids if message_id]

    def fetch_message(self, message_id: str) -> Message | None:
        """Fetch and parse a single message by IMAP id."""

        connection = self._require_connection()
        status, data = connection.fetch(message_id, "(RFC822)")
        if status != "OK" or not data:
            return None

        for item in data:
            if isinstance(item, tuple) and len(item) >= 2 and item[1]:
                return message_from_bytes(item[1], policy=policy.default)
        return None

    def get_message_text(self, msg: Message) -> str:
        """Return the best available plain text body from a message."""

        plain_parts: list[str] = []
        html_parts: list[str] = []

        if msg.is_multipart():
            for part in msg.walk():
                content_disposition = str(part.get("Content-Disposition") or "").lower()
                if "attachment" in content_disposition:
                    continue
                content_type = str(part.get_content_type() or "").lower()
                payload = self._decode_part(part)
                if not payload:
                    continue
                if content_type == "text/plain":
                    plain_parts.append(payload)
                elif content_type == "text/html":
                    html_parts.append(payload)
        else:
            payload = self._decode_part(msg)
            content_type = str(msg.get_content_type() or "").lower()
            if content_type == "text/html":
                html_parts.append(payload)
            else:
                plain_parts.append(payload)

        if plain_parts:
            return normalize_text("\n".join(part for part in plain_parts if part))
        if html_parts:
            return html_to_text("\n".join(part for part in html_parts if part))
        return ""

    def get_message_subject(self, msg: Message) -> str:
        """Decode a subject header safely."""

        return self._decode_header_value(msg.get("Subject"))

    def get_message_from(self, msg: Message) -> str:
        """Decode a from header safely."""

        return self._decode_header_value(msg.get("From"))

    def get_message_header_id(self, msg: Message) -> str | None:
        """Return the RFC822 Message-ID when available."""

        header_value = self._decode_header_value(msg.get("Message-ID"))
        return header_value or None

    def mark_seen(self, message_id: str) -> None:
        """Mark the message as seen."""

        connection = self._require_connection()
        status, _ = connection.store(message_id, "+FLAGS", "\\Seen")
        if status != "OK":
            raise EmailServiceError(f"Failed to mark message {message_id} as seen.")

    def _require_connection(self) -> imaplib.IMAP4:
        if self._connection is None:
            raise EmailServiceError("Not connected to a mailbox.")
        return self._connection

    def _decode_part(self, part: Message) -> str:
        payload = part.get_payload(decode=True)
        if payload is None:
            raw_payload = part.get_payload()
            return normalize_text(raw_payload if isinstance(raw_payload, str) else "")

        charset = part.get_content_charset() or "utf-8"
        try:
            return normalize_text(payload.decode(charset, errors="replace"))
        except LookupError:
            return normalize_text(payload.decode("utf-8", errors="replace"))

    def _decode_header_value(self, value: object) -> str:
        if not value:
            return ""

        fragments: list[str] = []
        for fragment, encoding in decode_header(str(value)):
            if isinstance(fragment, bytes):
                try:
                    fragments.append(fragment.decode(encoding or "utf-8", errors="replace"))
                except LookupError:
                    fragments.append(fragment.decode("utf-8", errors="replace"))
            else:
                fragments.append(fragment)
        return normalize_text("".join(fragments))
