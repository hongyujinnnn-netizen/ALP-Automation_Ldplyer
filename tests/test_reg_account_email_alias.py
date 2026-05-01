from __future__ import annotations

import unittest

from core.tasks.reg_account import RegAccountTaskHandler
from core.settings import AppSettings


class TestRegAccountEmailAlias(unittest.TestCase):
    def test_build_yandex_clone_email_keeps_base_and_adds_six_digits(self) -> None:
        alias = RegAccountTaskHandler._build_yandex_clone_email("zhiiko@yandex.com")

        self.assertIsNotNone(alias)
        self.assertRegex(alias or "", r"^zhiiko\+\d{6}@yandex\.com$")

    def test_build_yandex_clone_email_replaces_existing_plus_alias(self) -> None:
        alias = RegAccountTaskHandler._build_yandex_clone_email("zhiiko+oldtag@yandex.com")

        self.assertIsNotNone(alias)
        self.assertRegex(alias or "", r"^zhiiko\+\d{6}@yandex\.com$")
        self.assertNotIn("oldtag", alias or "")

    def test_is_yandex_address_detects_provider_or_domain(self) -> None:
        self.assertTrue(RegAccountTaskHandler._is_yandex_address("user@example.com", "yandex"))
        self.assertTrue(RegAccountTaskHandler._is_yandex_address("user@yandex.com"))
        self.assertFalse(RegAccountTaskHandler._is_yandex_address("user@gmail.com"))

    def test_build_confirmation_otp_request_defaults_to_unread_facebook_mail(self) -> None:
        settings = AppSettings(
            email_sender_filter="",
            email_subject_filter="",
            email_timeout_seconds=10,
            email_poll_interval_seconds=1,
            email_mark_as_seen=True,
        )

        request = RegAccountTaskHandler._build_confirmation_otp_request(settings)

        self.assertEqual(request.sender_filter, "facebook")
        self.assertEqual(request.subject_filter, "")
        self.assertTrue(request.unread_only)
        self.assertEqual(request.timeout_seconds, 30)
        self.assertEqual(request.poll_interval_seconds, 2)
        self.assertTrue(request.mark_as_seen)


if __name__ == "__main__":
    unittest.main()
