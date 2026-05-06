from __future__ import annotations

from collections.abc import Callable
from typing import Dict, Optional


# ==================== ENHANCED ERROR HANDLER ====================
class EnhancedErrorHandler:
    """
    Small helper to centralise retry budgeting for ADB‑style errors.

    It is intentionally lightweight so it can be safely created per task
    handler without adding heavy dependencies.
    """

    def __init__(self, log_func: Callable[[str, str], None]) -> None:
        self.log: Callable[[str, str], None] = log_func
        self.error_count: Dict[str, int] = {}
        self.max_retries: int = 3

    def handle_adb_error(self, device_name: str, operation: str, error: BaseException) -> bool:
        """
        Register an error and decide whether to retry.

        Returns True if the caller SHOULD retry, False if it should give up.
        """
        key = f"{device_name}_{operation}"
        self.error_count[key] = self.error_count.get(key, 0) + 1

        if self.error_count[key] <= self.max_retries:
            self.log(
                f"🔄 Retrying {operation} on {device_name} (attempt {self.error_count[key]})",
                "WARNING",
            )
            return True

        self.log(f"❌ Max retries exceeded for {operation} on {device_name}", "ERROR")
        return False

    def reset_counters(self, device_name: Optional[str] = None) -> None:
        """Clear retry state either for a single device or globally."""
        if device_name is not None:
            keys = [k for k in self.error_count.keys() if device_name in k]
            for key in keys:
                del self.error_count[key]
            return

        self.error_count.clear()
