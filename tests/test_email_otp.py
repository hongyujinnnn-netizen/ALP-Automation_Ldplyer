from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

from controllers.otp_controller import OTPController
from core.email_models import EmailAccountConfig, OTPRequest
from core.otp_parser import extract_otp, html_to_text
from core.paths import AppPaths
from services.email_service import EmailServiceError
from services.otp_service import OTPService
from services.settings_service import SettingsService


def build_test_paths(root: Path) -> AppPaths:
    config_dir = root / "config"
    return AppPaths(
        project_root=root,
        config_dir=config_dir,
        content_dir=root / "content",
        backup_dir=root / "backups",
        logs_dir=root / "logs",
        settings_file=config_dir / "setting.json",
        schedule_settings_file=config_dir / "setting_schedule.json",
        accounts_file=config_dir / "created_accounts.json",
        content_queue_file=config_dir / "content_queue.json",
        scheduled_tasks_file=config_dir / "scheduled_tasks.json",
    )


class FakeClock:
    def __init__(self) -> None:
        self.current = 0.0

    def now(self) -> float:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.current += seconds


class FakeEmailService:
    def __init__(self, messages: dict[str, dict], search_sequences: list[list[str]] | None = None, fail_connect: bool = False) -> None:
        self.messages = messages
        self.search_sequences = list(search_sequences or [list(messages.keys())])
        self.fail_connect = fail_connect
        self.connected = False
        self.marked_seen: list[str] = []

    def connect(self, config: EmailAccountConfig) -> None:
        if self.fail_connect:
            raise EmailServiceError("bad credentials")
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def search_message_ids(self, unread_only: bool = True) -> list[str]:
        if len(self.search_sequences) > 1:
            return self.search_sequences.pop(0)
        return list(self.search_sequences[0])

    def fetch_message(self, message_id: str):
        return self.messages.get(message_id)

    def get_message_from(self, msg) -> str:
        return msg.get("from", "")

    def get_message_subject(self, msg) -> str:
        return msg.get("subject", "")

    def get_message_text(self, msg) -> str:
        return msg.get("body", "")

    def get_message_header_id(self, msg) -> str | None:
        return msg.get("message_id")

    def mark_seen(self, message_id: str) -> None:
        self.marked_seen.append(message_id)


class TestEmailOTP(unittest.TestCase):
    def test_extract_otp_prefers_specific_pattern_over_generic_digits(self) -> None:
        text = "Reference 998877. Your verification code is 123456. Ignore the old value."
        self.assertEqual(extract_otp(text), "123456")

    def test_html_to_text_supports_html_derived_otp_parsing(self) -> None:
        rendered = html_to_text("<html><body><p>Security code: <strong>654321</strong></p></body></html>")
        self.assertEqual(extract_otp(rendered), "654321")

    def test_matches_filters_uses_case_insensitive_substring_matching(self) -> None:
        request = OTPRequest(sender_filter="alerts@example.com", subject_filter="verify")
        self.assertTrue(OTPService.matches_filters("Alerts <alerts@example.com>", "Please Verify Your Login", request))
        self.assertFalse(OTPService.matches_filters("Other <other@example.com>", "Please Verify Your Login", request))
        self.assertFalse(OTPService.matches_filters("Alerts <alerts@example.com>", "Weekly Digest", request))

    def test_fetch_latest_otp_checks_newest_messages_first(self) -> None:
        service = FakeEmailService(
            messages={
                "1": {
                    "from": "noreply@example.com",
                    "subject": "Verification code",
                    "body": "OTP: 111111",
                    "message_id": "<msg-1>",
                },
                "2": {
                    "from": "noreply@example.com",
                    "subject": "Verification code",
                    "body": "OTP: 222222",
                    "message_id": "<msg-2>",
                },
            },
            search_sequences=[["1", "2"]],
        )
        otp_service = OTPService(email_service=service)

        result = otp_service.fetch_latest_otp(
            EmailAccountConfig(email_address="user@example.com", app_password="secret"),
            OTPRequest(sender_filter="noreply@example.com", subject_filter="verification"),
        )

        self.assertTrue(result.success)
        self.assertEqual(result.code, "222222")
        self.assertEqual(result.source_message_id, "<msg-2>")

    def test_wait_for_otp_times_out_when_no_candidate_arrives(self) -> None:
        clock = FakeClock()
        service = FakeEmailService(messages={}, search_sequences=[[], [], []])
        otp_service = OTPService(
            email_service=service,
            sleep_func=clock.sleep,
            time_func=clock.now,
        )

        result = otp_service.wait_for_otp(
            EmailAccountConfig(email_address="user@example.com", app_password="secret"),
            OTPRequest(timeout_seconds=6, poll_interval_seconds=2),
        )

        self.assertFalse(result.success)
        self.assertIn("Timed out", result.error or "")
        self.assertEqual(clock.current, 6.0)

    def test_controller_saves_and_loads_email_settings_through_app_settings(self) -> None:
        root = Path.cwd() / "tests_runtime" / f"otp_controller_{uuid.uuid4().hex}"
        try:
            paths = build_test_paths(root)
            paths.ensure_runtime_dirs()
            controller = OTPController(SettingsService(paths))

            saved = controller.save_email_settings(
                EmailAccountConfig(
                    provider="yandex",
                    email_address="owner@example.com",
                    app_password="app-secret",
                    imap_server="imap.yandex.com",
                    imap_port=993,
                    mailbox="INBOX",
                    use_ssl=True,
                ),
                OTPRequest(
                    sender_filter="security@yandex.com",
                    subject_filter="code",
                    unread_only=False,
                    timeout_seconds=45,
                    poll_interval_seconds=3,
                    mark_as_seen=True,
                ),
            )

            loaded_config, loaded_request = controller.load_email_settings()

            self.assertTrue(saved)
            self.assertEqual(loaded_config.email_address, "owner@example.com")
            self.assertEqual(loaded_config.imap_server, "imap.yandex.com")
            self.assertFalse(loaded_request.unread_only)
            self.assertEqual(loaded_request.timeout_seconds, 45)
            self.assertTrue(loaded_request.mark_as_seen)
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
