from __future__ import annotations

from collections.abc import Callable

from core.email_models import EmailAccountConfig, OTPRequest, OTPResult
from core.settings import AppSettings, SettingsError
from services.email_service import EmailService, EmailServiceError
from services.otp_service import OTPService
from services.settings_service import SettingsService


class OTPController:
    """UI-facing boundary for email OTP configuration and actions."""

    def __init__(
        self,
        settings_service: SettingsService,
        ui_log_func: Callable[[str, str], None] | None = None,
        structured_log_func: Callable[..., None] | None = None,
        email_service_factory: Callable[[], EmailService] | None = None,
        otp_service_factory: Callable[..., OTPService] | None = None,
    ) -> None:
        self.settings_service = settings_service
        self._ui_log = ui_log_func
        self._structured_log = structured_log_func
        self._email_service_factory = email_service_factory or EmailService
        self._otp_service_factory = otp_service_factory or OTPService

    def load_email_settings(self) -> tuple[EmailAccountConfig, OTPRequest]:
        """Load persisted email account and OTP polling defaults."""

        try:
            settings = self.settings_service.load_app_settings()
        except SettingsError as exc:
            self._emit(
                "WARNING",
                "otp.settings.load_failed",
                f"Failed to load email OTP settings: {exc}",
                error=str(exc),
            )
            settings = AppSettings()
        return self._settings_to_models(settings)

    def save_email_settings(self, config: EmailAccountConfig, request: OTPRequest) -> bool:
        """Persist email account and OTP polling defaults."""

        validation_error = self.validate(config, request)
        if validation_error:
            self._emit("WARNING", "otp.settings.invalid", validation_error)
            return False

        try:
            settings = self.settings_service.load_app_settings()
        except SettingsError:
            settings = AppSettings()

        self._apply_models_to_settings(settings, config, request)
        try:
            self.settings_service.save_app_settings(settings)
            self._emit("SUCCESS", "otp.settings.saved", "Email OTP settings saved")
            return True
        except SettingsError as exc:
            self._emit(
                "WARNING",
                "otp.settings.save_failed",
                f"Failed to save email OTP settings: {exc}",
                error=str(exc),
            )
            return False

    def test_connection(self, config: EmailAccountConfig) -> OTPResult:
        """Attempt an IMAP connection using the provided mailbox configuration."""

        validation_error = self.validate_config(config)
        if validation_error:
            return OTPResult(success=False, error=validation_error)

        resolved = config.with_provider_defaults()
        service = self._email_service_factory()
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
            service.connect(resolved)
            self._emit(
                "SUCCESS",
                "email.connect.succeeded",
                f"Connected to mailbox {resolved.mailbox}",
                provider=resolved.provider,
                mailbox=resolved.mailbox,
            )
            return OTPResult(success=True, details="Connection succeeded.")
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
        finally:
            service.disconnect()

    def test_fetch_latest_otp(self, config: EmailAccountConfig, request: OTPRequest) -> OTPResult:
        """Scan the mailbox once for the newest matching OTP."""

        validation_error = self.validate(config, request)
        if validation_error:
            return OTPResult(success=False, error=validation_error)

        service = self._otp_service_factory(
            email_service=self._email_service_factory(),
            ui_log_func=self._ui_log,
            structured_log_func=self._structured_log,
        )
        return service.fetch_latest_otp(config.with_provider_defaults(), request)

    def wait_for_otp(self, config: EmailAccountConfig, request: OTPRequest) -> OTPResult:
        """Poll the mailbox until a matching OTP is found or timeout expires."""

        validation_error = self.validate(config, request)
        if validation_error:
            return OTPResult(success=False, error=validation_error)

        service = self._otp_service_factory(
            email_service=self._email_service_factory(),
            ui_log_func=self._ui_log,
            structured_log_func=self._structured_log,
        )
        return service.wait_for_otp(config.with_provider_defaults(), request)

    def validate(self, config: EmailAccountConfig, request: OTPRequest) -> str | None:
        """Validate both mailbox configuration and OTP polling inputs."""

        config_error = self.validate_config(config)
        if config_error:
            return config_error

        if int(request.timeout_seconds) <= 0:
            return "Timeout must be greater than zero."
        if int(request.poll_interval_seconds) <= 0:
            return "Poll interval must be greater than zero."
        return None

    @staticmethod
    def validate_config(config: EmailAccountConfig) -> str | None:
        """Validate the mailbox configuration fields needed for IMAP access."""

        resolved = config.with_provider_defaults()
        if not resolved.email_address:
            return "Email address is required."
        if not resolved.app_password:
            return "App password is required."
        if not resolved.imap_server:
            return "IMAP server is required."
        if int(resolved.imap_port) <= 0:
            return "IMAP port must be greater than zero."
        if not resolved.mailbox:
            return "Mailbox is required."
        return None

    @staticmethod
    def _settings_to_models(settings: AppSettings) -> tuple[EmailAccountConfig, OTPRequest]:
        config = EmailAccountConfig(
            provider=settings.email_provider,
            email_address=settings.email_address,
            app_password=settings.email_app_password,
            imap_server=settings.email_imap_server,
            imap_port=settings.email_imap_port,
            mailbox=settings.email_mailbox,
            use_ssl=settings.email_use_ssl,
        ).with_provider_defaults()
        request = OTPRequest(
            sender_filter=settings.email_sender_filter,
            subject_filter=settings.email_subject_filter,
            unread_only=settings.email_unread_only,
            timeout_seconds=settings.email_timeout_seconds,
            poll_interval_seconds=settings.email_poll_interval_seconds,
            mark_as_seen=settings.email_mark_as_seen,
        )
        return config, request

    @staticmethod
    def _apply_models_to_settings(
        settings: AppSettings, config: EmailAccountConfig, request: OTPRequest
    ) -> None:
        resolved = config.with_provider_defaults()
        settings.email_provider = resolved.provider
        settings.email_address = resolved.email_address
        settings.email_app_password = resolved.app_password
        settings.email_imap_server = resolved.imap_server
        settings.email_imap_port = int(resolved.imap_port)
        settings.email_mailbox = resolved.mailbox
        settings.email_use_ssl = bool(resolved.use_ssl)
        settings.email_unread_only = bool(request.unread_only)
        settings.email_sender_filter = str(request.sender_filter or "")
        settings.email_subject_filter = str(request.subject_filter or "")
        settings.email_timeout_seconds = int(request.timeout_seconds)
        settings.email_poll_interval_seconds = int(request.poll_interval_seconds)
        settings.email_mark_as_seen = bool(request.mark_as_seen)

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
