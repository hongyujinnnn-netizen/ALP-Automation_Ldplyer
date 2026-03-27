from __future__ import annotations

import time
from collections.abc import Callable

from core.email_models import EmailAccountConfig, OTPRequest, OTPResult
from core.otp_parser import extract_otp
from services.email_service import EmailService, EmailServiceError


class OTPService:
    """Coordinate mailbox polling and OTP extraction."""

    def __init__(
        self,
        email_service: EmailService | None = None,
        ui_log_func: Callable[[str, str], None] | None = None,
        structured_log_func: Callable[..., None] | None = None,
        sleep_func: Callable[[float], None] | None = None,
        time_func: Callable[[], float] | None = None,
    ) -> None:
        self.email_service = email_service or EmailService()
        self._ui_log = ui_log_func
        self._structured_log = structured_log_func
        self._sleep = sleep_func or time.sleep
        self._time = time_func or time.monotonic

    def fetch_latest_otp(self, config: EmailAccountConfig, request: OTPRequest) -> OTPResult:
        """Scan the mailbox once and return the newest matching OTP if present."""

        return self._run_polling(config, request, poll_until_timeout=False)

    def wait_for_otp(self, config: EmailAccountConfig, request: OTPRequest) -> OTPResult:
        """Poll the mailbox until a matching OTP is found or timeout elapses."""

        return self._run_polling(config, request, poll_until_timeout=True)

    def _run_polling(
        self,
        config: EmailAccountConfig,
        request: OTPRequest,
        poll_until_timeout: bool,
    ) -> OTPResult:
        deadline = self._time() + max(1, int(request.timeout_seconds))
        processed_ids: set[str] = set()
        resolved = config.with_provider_defaults()

        self._emit(
            "INFO",
            "otp.poll.started",
            f"Starting OTP poll for {resolved.email_address or 'configured mailbox'}",
            provider=resolved.provider,
            mailbox=resolved.mailbox,
            timeout_seconds=int(request.timeout_seconds),
            poll_interval_seconds=int(request.poll_interval_seconds),
            unread_only=bool(request.unread_only),
            sender_filter=request.sender_filter,
            subject_filter=request.subject_filter,
        )

        self._emit(
            "INFO",
            "email.connect.started",
            f"Connecting to {resolved.imap_server}:{resolved.imap_port}",
            provider=resolved.provider,
            imap_server=resolved.imap_server,
            imap_port=resolved.imap_port,
            mailbox=resolved.mailbox,
        )

        try:
            self.email_service.connect(resolved)
            self._emit(
                "SUCCESS",
                "email.connect.succeeded",
                f"Connected to mailbox {resolved.mailbox}",
                provider=resolved.provider,
                mailbox=resolved.mailbox,
            )
        except EmailServiceError as exc:
            self._emit(
                "ERROR",
                "email.connect.failed",
                f"Email connection failed: {exc}",
                provider=resolved.provider,
                mailbox=resolved.mailbox,
                error=str(exc),
            )
            return OTPResult(success=False, error=f"Email connection failed: {exc}")

        try:
            while True:
                result = self._scan_once(request, processed_ids)
                if result.success:
                    return result

                if not poll_until_timeout:
                    return OTPResult(success=False, error="No matching OTP email found.")

                remaining = deadline - self._time()
                if remaining <= 0:
                    self._emit(
                        "WARNING",
                        "otp.timeout",
                        "Timed out waiting for OTP email",
                        timeout_seconds=int(request.timeout_seconds),
                        unread_only=bool(request.unread_only),
                    )
                    return OTPResult(success=False, error="Timed out waiting for OTP email.")

                self._sleep(min(max(0, float(request.poll_interval_seconds)), remaining))
        except EmailServiceError as exc:
            return OTPResult(success=False, error=f"Mailbox polling failed: {exc}")
        finally:
            self.email_service.disconnect()

    def _scan_once(self, request: OTPRequest, processed_ids: set[str]) -> OTPResult:
        message_ids = self.email_service.search_message_ids(unread_only=bool(request.unread_only))
        for message_id in reversed(message_ids):
            if message_id in processed_ids:
                continue
            processed_ids.add(message_id)

            message = self.email_service.fetch_message(message_id)
            if message is None:
                continue

            sender = self.email_service.get_message_from(message)
            subject = self.email_service.get_message_subject(message)
            if not self.matches_filters(sender, subject, request):
                continue

            body_text = self.email_service.get_message_text(message)
            combined_text = "\n".join(part for part in (subject, body_text) if part)
            code = extract_otp(combined_text, request.otp_patterns)
            if code:
                self._emit(
                    "SUCCESS",
                    "otp.parse.success",
                    f"Extracted OTP from {sender or 'message'}",
                    code_length=len(code),
                    matched_sender=sender,
                    matched_subject=subject,
                    source_message_id=message_id,
                )
                if request.mark_as_seen:
                    self.email_service.mark_seen(message_id)
                self._emit(
                    "SUCCESS",
                    "otp.poll.match_found",
                    f"Found matching OTP in {subject or 'email'}",
                    matched_sender=sender,
                    matched_subject=subject,
                    source_message_id=message_id,
                )
                return OTPResult(
                    success=True,
                    code=code,
                    matched_sender=sender or None,
                    matched_subject=subject or None,
                    source_message_id=self.email_service.get_message_header_id(message) or message_id,
                )

            self._emit(
                "WARNING",
                "otp.parse.failed",
                f"No OTP pattern matched for {subject or 'candidate email'}",
                matched_sender=sender,
                matched_subject=subject,
                source_message_id=message_id,
            )

        self._emit(
            "INFO",
            "otp.poll.no_match",
            "No matching OTP found in current mailbox scan",
            unread_only=bool(request.unread_only),
            sender_filter=request.sender_filter,
            subject_filter=request.subject_filter,
            checked_messages=len(processed_ids),
        )
        return OTPResult(success=False, error="No matching OTP email found.")

    @staticmethod
    def matches_filters(sender: str, subject: str, request: OTPRequest) -> bool:
        """Return True when sender and subject match the optional filters."""

        sender_filter = str(request.sender_filter or "").strip().lower()
        subject_filter = str(request.subject_filter or "").strip().lower()
        sender_text = str(sender or "").lower()
        subject_text = str(subject or "").lower()

        if sender_filter and sender_filter not in sender_text:
            return False
        if subject_filter and subject_filter not in subject_text:
            return False
        return True

    def _emit(self, level: str, event: str, message: str, **context: object) -> None:
        if callable(self._ui_log):
            try:
                self._ui_log(message, level)
            except Exception:
                pass

        if callable(self._structured_log):
            try:
                self._structured_log(level, event, event=event, **context)
            except Exception:
                pass
