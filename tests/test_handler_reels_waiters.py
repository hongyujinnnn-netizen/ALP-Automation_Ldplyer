"""Integration test: prove migrated handler_reels.py methods complete in
the time it takes the UI element to appear, not the old fixed sleep."""

from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock, Mock

from core.tasks.task_reels import ReelsTaskHandler


class TestNavigateToPicturesUsesWaiter(unittest.TestCase):
    def test_completes_in_under_old_fixed_sleep_when_ui_appears_quickly(self):
        """The pre-migration code did time.sleep(3) + time.sleep(2) = 5s minimum.

        With smart waiters and a UI element that appears on the second poll
        (~0.5s after start), the method should finish in well under 2s.
        """
        logs: list[str] = []
        emulator = Mock()
        pause_event = Mock()
        handler = ReelsTaskHandler(
            emulator,
            lambda message, level="INFO": logs.append(message),
            pause_event,
            lambda: True,
        )

        polls = {"pictures": 0, "list": 0}

        def make_pictures_obj():
            obj = MagicMock()

            def exists(timeout=0):
                polls["pictures"] += 1
                return polls["pictures"] >= 2

            obj.exists.side_effect = exists
            return obj

        def make_list_obj():
            obj = MagicMock()

            def exists(timeout=0):
                polls["list"] += 1
                return polls["list"] >= 2

            obj.exists.side_effect = exists
            return obj

        def make_absent_obj():
            obj = MagicMock()
            obj.exists = MagicMock(return_value=False)
            return obj

        def device_call(**kwargs):
            if kwargs.get("text") == "Pictures":
                return make_pictures_obj()
            if (
                kwargs.get("resourceIdMatches")
                or kwargs.get("className", "").startswith("android")
            ):
                return make_list_obj()
            return make_absent_obj()

        d = MagicMock()
        d.side_effect = device_call
        d.serial = "emulator-test"

        start = time.monotonic()
        result = handler.navigate_to_pictures(d)
        elapsed = time.monotonic() - start

        self.assertTrue(result)
        # Old code minimum: 5s. New code with element-on-second-poll: ~1s.
        self.assertLess(
            elapsed,
            2.0,
            f"Migrated waiter took {elapsed:.2f}s — should be << pre-migration 5s sleep",
        )
        # Sanity: confirm the Pictures selector was actually polled.
        self.assertGreaterEqual(polls["pictures"], 1)


if __name__ == "__main__":
    unittest.main()
