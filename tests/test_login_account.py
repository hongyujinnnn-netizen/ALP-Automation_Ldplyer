import unittest
from unittest.mock import Mock

from core.logic.login_account import LoginAccountTaskHandler, LoginCredentials


class TestLoginAccountTaskHandler(unittest.TestCase):
    def _handler(self):
        handler = LoginAccountTaskHandler.__new__(LoginAccountTaskHandler)
        handler.check_paused = lambda: False
        handler.log = Mock()
        return handler

    def test_open_existing_account_login_clicks_requested_xpath(self):
        handler = self._handler()
        clicked = Mock()
        clicked.exists = True
        device = Mock()
        device.xpath.return_value = clicked
        handler._click_any_selector = Mock(return_value=False)

        self.assertTrue(handler._open_existing_account_login(device))

        device.xpath.assert_called_with(
            '//android.widget.Button[@content-desc="I already have an account"]/android.view.ViewGroup'
        )
        clicked.click.assert_called_once()
        handler._click_any_selector.assert_not_called()

    def test_run_login_steps_opens_existing_account_before_pasting_credentials(self):
        handler = self._handler()
        calls = []
        handler._open_existing_account_login = Mock(side_effect=lambda _d: calls.append("open"))
        handler._dismiss_account_picker = Mock(side_effect=lambda _d: calls.append("dismiss"))
        handler._fill_identifier = Mock(side_effect=lambda _d, _identifier: calls.append("identifier") or True)
        handler._fill_password = Mock(side_effect=lambda _d, _password: calls.append("password") or True)
        handler._submit_login = Mock(return_value=True)

        result = handler._run_login_steps_once(
            Mock(),
            "LD A",
            LoginCredentials(identifier="user@example.com", password="Password123", label="email"),
        )

        self.assertTrue(result)
        self.assertEqual(calls, ["open", "dismiss", "identifier", "password"])

    def test_generate_totp_code_from_2fa_secret(self):
        handler = self._handler()

        code = handler._generate_totp_code(
            "GEZD GNBV GY3T QOJQ GEZD GNBV GY3T QOJQ",
            for_time=59,
        )

        self.assertEqual(code, "287082")

    def test_handle_2fa_uses_secret_generated_code(self):
        handler = self._handler()
        device = Mock()
        handler._selector_exists = Mock(return_value=True)
        handler.enter_confirmation_code = Mock(return_value=True)
        handler._trust_login_device_if_present = Mock()

        result = handler.handle_2fa(
            device,
            twofa_secret="GEZD GNBV GY3T QOJQ GEZD GNBV GY3T QOJQ",
        )

        self.assertTrue(result)
        entered_code = handler.enter_confirmation_code.call_args.args[1]
        self.assertRegex(entered_code, r"^\d{6}$")
        handler._trust_login_device_if_present.assert_called_once_with(device)

    def test_handle_2fa_attempts_code_entry_when_screen_text_does_not_match(self):
        handler = self._handler()
        device = Mock()
        handler._selector_exists = Mock(return_value=False)
        handler.enter_confirmation_code = Mock(return_value=True)
        handler._trust_login_device_if_present = Mock()

        result = handler.handle_2fa(
            device,
            twofa_secret="GEZD GNBV GY3T QOJQ GEZD GNBV GY3T QOJQ",
        )

        self.assertTrue(result)
        handler.enter_confirmation_code.assert_called_once()


if __name__ == "__main__":
    unittest.main()
