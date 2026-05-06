"""Shared helpers for handling account credential secrets.

The credential vault (see :mod:`core.credential_store`) is the single source of
truth for ``password`` and ``twofa`` values. This module centralizes the
persist / hydrate / redact / migrate logic so every place that touches account
records on disk goes through the same path.
"""

from __future__ import annotations

import logging
from typing import Optional

from core.credential_store import CredentialStore

logger = logging.getLogger(__name__)

SECRET_ACCOUNT_FIELDS: tuple[str, ...] = ("password", "twofa")


def derive_dashboard_account_id(account: dict) -> str:
    """Stable keyring key for dashboard account blocks.

    Mirrors the convention used by ``_db_normalize_login_account`` and the
    dashboard instance account block: prefer ``account_id``, fall back to
    ``uid``, then ``email``/``mail``.
    """

    return str(
        (account or {}).get("account_id")
        or (account or {}).get("uid")
        or (account or {}).get("email")
        or (account or {}).get("mail")
        or ""
    ).strip()


def _non_empty_secret_fields(record: dict) -> list[str]:
    return [field for field in SECRET_ACCOUNT_FIELDS if str((record or {}).get(field) or "").strip()]


def has_plaintext_secrets(records: list[dict]) -> bool:
    """Cheap pre-check used to skip migration loops on already-redacted files."""

    return any(_non_empty_secret_fields(record) for record in (records or []))


def persist_secrets(
    account_id: str,
    record: dict,
    store: Optional[CredentialStore] = None,
) -> dict[str, bool]:
    """Write every non-empty secret field from ``record`` into keyring.

    Returns ``{field: success}`` for each field that was attempted. Fields that
    are absent or empty in ``record`` are not attempted.
    """

    if not account_id:
        return {}
    store = store or CredentialStore()
    results: dict[str, bool] = {}
    for field in SECRET_ACCOUNT_FIELDS:
        if field not in (record or {}):
            continue
        value = str(record.get(field) or "").strip()
        if not value:
            continue
        results[field] = store.set_account_secret(account_id, field, value)
    return results


def hydrate_secrets(
    account_id: str,
    record: dict,
    store: Optional[CredentialStore] = None,
) -> bool:
    """Pull keyring values into ``record`` in place. Keyring wins on divergence."""

    if not account_id or record is None:
        return False
    store = store or CredentialStore()
    hydrated = False
    for field in SECRET_ACCOUNT_FIELDS:
        keyring_value = store.get_account_secret(account_id, field)
        if not keyring_value:
            continue
        existing = str(record.get(field) or "").strip()
        if existing and existing != keyring_value:
            logger.warning(
                "[credential-migration] %s::%s differs between disk and keyring; keyring value wins",
                account_id,
                field,
            )
        record[field] = keyring_value
        hydrated = True
    return hydrated


def migrate_legacy_plaintext(
    account_id: str,
    record: dict,
    store: Optional[CredentialStore] = None,
) -> dict[str, str]:
    """Move plaintext secret fields into keyring when keyring lacks them.

    Returns a dict of fields successfully migrated (so callers can decide
    whether to rewrite the source JSON to redact those fields).
    """

    if not account_id or record is None:
        return {}
    store = store or CredentialStore()
    migrated: dict[str, str] = {}
    for field in SECRET_ACCOUNT_FIELDS:
        if field not in record:
            continue
        plaintext = str(record.get(field) or "").strip()
        if not plaintext:
            continue
        if store.get_account_secret(account_id, field):
            continue
        if store.set_account_secret(account_id, field, plaintext):
            migrated[field] = plaintext
    return migrated


def delete_secrets(
    account_id: str,
    store: Optional[CredentialStore] = None,
) -> bool:
    """Idempotently remove all keyring entries for ``account_id``."""

    if not account_id:
        return True
    store = store or CredentialStore()
    return store.delete_all_account_secrets(account_id, list(SECRET_ACCOUNT_FIELDS))


def redacted_copy(
    record: dict,
    persisted_fields: Optional[dict[str, bool]] = None,
) -> dict:
    """Return a copy of ``record`` with secret fields redacted to empty strings.

    If ``persisted_fields`` is provided (mapping ``field -> success``) only
    redact fields that successfully landed in keyring — any field that failed
    keyring write is left as plaintext so the user does not lose it.
    """

    out = dict(record or {})
    for field in SECRET_ACCOUNT_FIELDS:
        if field not in out:
            continue
        if out[field] is None:
            continue
        if not str(out[field] or "").strip():
            continue
        if persisted_fields is not None and not persisted_fields.get(field, False):
            continue
        out[field] = ""
    return out
