import unittest
from unittest.mock import MagicMock, patch

from core import credential_store
from core.credential_store import CredentialStore, SERVICE_NAME


class TestCredentialStore(unittest.TestCase):
    def test_set_then_get_round_trips(self):
        fake = MagicMock()
        store_data: dict[tuple[str, str], str] = {}

        def fake_set(service, user, pwd):
            store_data[(service, user)] = pwd

        def fake_get(service, user):
            return store_data.get((service, user))

        fake.set_password.side_effect = fake_set
        fake.get_password.side_effect = fake_get

        with patch.object(credential_store, "keyring", fake), \
             patch.object(credential_store, "_AVAILABLE", True):
            store = CredentialStore()
            self.assertTrue(store.set_password("alice@example.com", "secret123"))
            self.assertEqual(store.get_password("alice@example.com"), "secret123")
            fake.set_password.assert_called_once_with(SERVICE_NAME, "alice@example.com", "secret123")

    def test_get_password_returns_none_when_missing(self):
        fake = MagicMock()
        fake.get_password.return_value = None
        with patch.object(credential_store, "keyring", fake), \
             patch.object(credential_store, "_AVAILABLE", True):
            store = CredentialStore()
            self.assertIsNone(store.get_password("nobody@example.com"))

    def test_methods_are_safe_when_keyring_unavailable(self):
        with patch.object(credential_store, "_AVAILABLE", False):
            store = CredentialStore()
            self.assertFalse(store.is_available)
            self.assertFalse(store.set_password("a@b.com", "x"))
            self.assertIsNone(store.get_password("a@b.com"))
            self.assertFalse(store.delete_password("a@b.com"))

    def test_delete_of_missing_entry_is_idempotent(self):
        fake = MagicMock()
        fake.delete_password.side_effect = credential_store.PasswordDeleteError("not found")
        with patch.object(credential_store, "keyring", fake), \
             patch.object(credential_store, "_AVAILABLE", True):
            store = CredentialStore()
            self.assertTrue(store.delete_password("ghost@example.com"))

    def test_keyring_error_is_caught_and_logged(self):
        fake = MagicMock()
        fake.set_password.side_effect = credential_store.KeyringError("backend exploded")
        with patch.object(credential_store, "keyring", fake), \
             patch.object(credential_store, "_AVAILABLE", True), \
             self.assertLogs("core.credential_store", level="WARNING") as captured:
            store = CredentialStore()
            self.assertFalse(store.set_password("alice@example.com", "secret"))
        self.assertTrue(any("backend exploded" in line for line in captured.output))


if __name__ == "__main__":
    unittest.main()
