from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

SERVICE_NAME = "alp-automation"

try:
    import keyring
    from keyring.errors import KeyringError, PasswordDeleteError

    _AVAILABLE = True
except ImportError:
    keyring = None  # type: ignore[assignment]
    KeyringError = Exception  # type: ignore[assignment,misc]
    PasswordDeleteError = Exception  # type: ignore[assignment,misc]
    _AVAILABLE = False
    logger.warning(
        "keyring package is not installed; email passwords will not be stored "
        "in the OS credential vault. Install 'keyring>=24.0' to enable secure storage."
    )


class CredentialStore:
    """Thin wrapper around the OS credential vault for email app passwords."""

    def __init__(self, service_name: str = SERVICE_NAME) -> None:
        self.service_name = service_name

    @property
    def is_available(self) -> bool:
        return _AVAILABLE

    def set_password(self, username: str, password: str) -> bool:
        if not _AVAILABLE:
            return False
        if not username:
            logger.warning("CredentialStore.set_password called with empty username; skipping.")
            return False
        try:
            keyring.set_password(self.service_name, username, password)
            return True
        except KeyringError as exc:
            logger.warning("Failed to store credential for %s: %s", username, exc)
            return False

    def get_password(self, username: str) -> str | None:
        if not _AVAILABLE:
            return None
        if not username:
            return None
        try:
            return keyring.get_password(self.service_name, username)
        except KeyringError as exc:
            logger.warning("Failed to read credential for %s: %s", username, exc)
            return None

    def delete_password(self, username: str) -> bool:
        if not _AVAILABLE:
            return False
        if not username:
            return False
        try:
            keyring.delete_password(self.service_name, username)
            return True
        except PasswordDeleteError:
            return True
        except KeyringError as exc:
            logger.warning("Failed to delete credential for %s: %s", username, exc)
            return False

    @staticmethod
    def _composite_key(account_id: str, field: str) -> str:
        return f"{account_id}::{field}"

    def set_account_secret(self, account_id: str, field: str, value: str) -> bool:
        if not account_id or not field:
            return False
        return self.set_password(self._composite_key(account_id, field), value)

    def get_account_secret(self, account_id: str, field: str) -> str | None:
        if not account_id or not field:
            return None
        return self.get_password(self._composite_key(account_id, field))

    def delete_account_secret(self, account_id: str, field: str) -> bool:
        if not account_id or not field:
            return False
        return self.delete_password(self._composite_key(account_id, field))

    def delete_all_account_secrets(self, account_id: str, fields: list[str]) -> bool:
        if not account_id:
            return True
        all_ok = True
        for field in fields:
            if not self.delete_account_secret(account_id, field):
                all_ok = False
        return all_ok
