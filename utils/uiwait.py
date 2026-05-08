"""Smart waiters for uiautomator2 device polling.

These helpers replace blind ``time.sleep(N)`` calls with predicate-based
polling so fast machines don't waste budget and slow machines don't crash
because the UI hasn't rendered yet.

All waiters are non-raising: timeout returns ``None`` / ``False`` so the
caller can decide how to recover.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


def wait_for_any(
    d,
    selectors: list[dict],
    timeout: float = 10.0,
    poll_interval: float = 0.5,
    log: Callable[[str], None] | None = None,
) -> Any | None:
    """Poll several uiautomator2 selectors and return the first matching UiObject.

    Each ``selector`` is a dict of kwargs passed to ``d(**selector)``. Useful
    when Facebook A/B tests, locale, or version differences mean an element
    can be addressed by ``text``, ``resourceId`` *or* ``description``.

    Returns the matched UiObject, or ``None`` on timeout.

    Example:
        >>> obj = wait_for_any(
        ...     d,
        ...     [{"text": "Feed"}, {"resourceId": "com.facebook.katana:id/feed_tab"}],
        ...     timeout=15,
        ... )
        >>> if obj is not None:
        ...     obj.click()
    """
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        for selector in selectors:
            try:
                obj = d(**selector)
                if obj.exists(timeout=0.1):
                    return obj
            except Exception as exc:
                last_error = exc
                continue
        time.sleep(poll_interval)

    if log and last_error:
        log(f"wait_for_any timed out after {timeout}s; last error: {last_error}")
    return None


def wait_until(
    condition: Callable[[], bool],
    timeout: float = 10.0,
    poll_interval: float = 0.5,
    log: Callable[[str], None] | None = None,
) -> bool:
    """Poll a callable until it returns truthy or ``timeout`` expires.

    Generic predicate-based waiter for non-UI conditions ("is process
    running", "is file present"). Exceptions raised by the condition are
    swallowed — a transient failure mid-poll is not the same as a final
    timeout.

    Returns ``True`` if the condition became truthy, ``False`` on timeout.

    Example:
        >>> ready = wait_until(lambda: os.path.exists("/tmp/ready"), timeout=30)
    """
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            if condition():
                return True
        except Exception as exc:
            last_error = exc
        time.sleep(poll_interval)

    if log and last_error:
        log(f"wait_until timed out after {timeout}s; last error: {last_error}")
    return False


def wait_for_gone(
    d,
    selector: dict,
    timeout: float = 10.0,
    poll_interval: float = 0.5,
    log: Callable[[str], None] | None = None,
) -> bool:
    """Wait until a UI element no longer exists.

    Useful for waiting on loading spinners or modal dialogs to dismiss
    before proceeding. If the existence check itself raises (e.g. the
    element is gone and the underlying lookup fails), the element is
    treated as gone.

    Returns ``True`` once the element is absent, ``False`` on timeout.

    Example:
        >>> wait_for_gone(d, {"resourceId": "com.facebook.katana:id/progress"}, timeout=20)
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if not d(**selector).exists(timeout=0.1):
                return True
        except Exception:
            return True
        time.sleep(poll_interval)

    if log:
        log(f"wait_for_gone timed out after {timeout}s for selector {selector}")
    return False
