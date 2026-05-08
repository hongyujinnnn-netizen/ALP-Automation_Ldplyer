from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from utils.uiwait import wait_for_any, wait_for_gone, wait_until


def _make_device(selector_results: dict[tuple, list[bool]]):
    """Build a fake uiautomator2 device.

    ``selector_results`` maps a selector kwargs tuple (sorted items) to a list
    of booleans returned successively from ``.exists()``.
    """
    device = MagicMock()

    def call(**kwargs):
        key = tuple(sorted(kwargs.items()))
        results = selector_results.get(key, [False])
        obj = MagicMock(name=f"obj({kwargs})")

        def exists(timeout=0):
            if len(results) > 1:
                return results.pop(0)
            return results[0]

        obj.exists.side_effect = exists
        return obj

    device.side_effect = call
    return device


class TestWaitForAny(unittest.TestCase):
    def test_returns_first_matching_selector(self):
        d = _make_device({(("text", "Feed"),): [True]})
        result = wait_for_any(d, [{"text": "Feed"}, {"text": "Other"}], timeout=1)
        self.assertIsNotNone(result)

    def test_returns_none_on_timeout_without_raising(self):
        d = _make_device({})
        result = wait_for_any(d, [{"text": "Nope"}], timeout=0.2, poll_interval=0.05)
        self.assertIsNone(result)

    def test_tries_all_selectors_each_cycle(self):
        # Only the second selector matches.
        d = _make_device({(("resourceId", "abc"),): [True]})
        result = wait_for_any(
            d,
            [{"text": "Missing"}, {"resourceId": "abc"}],
            timeout=1,
            poll_interval=0.05,
        )
        self.assertIsNotNone(result)

    def test_respects_timeout_via_monotonic(self):
        # monotonic returns 0, then 0.5, then 100 -> loop exits after second poll.
        ticks = iter([0.0, 0.0, 0.5, 100.0, 100.0, 100.0])
        with patch("utils.uiwait.time.monotonic", side_effect=lambda: next(ticks)), \
             patch("utils.uiwait.time.sleep"):
            d = _make_device({})
            result = wait_for_any(d, [{"text": "x"}], timeout=10, poll_interval=0.5)
        self.assertIsNone(result)

    def test_swallows_exceptions_from_selector(self):
        d = MagicMock()

        def raising(**kwargs):
            raise RuntimeError("boom")

        d.side_effect = raising
        # Should not raise; should hit timeout and return None.
        result = wait_for_any(d, [{"text": "x"}], timeout=0.2, poll_interval=0.05)
        self.assertIsNone(result)


class TestWaitUntil(unittest.TestCase):
    def test_returns_true_when_condition_eventually_truthy(self):
        results = iter([False, False, True])
        result = wait_until(lambda: next(results), timeout=2, poll_interval=0.01)
        self.assertTrue(result)

    def test_returns_false_on_timeout(self):
        result = wait_until(lambda: False, timeout=0.2, poll_interval=0.05)
        self.assertFalse(result)

    def test_swallows_exceptions_from_condition(self):
        calls = {"n": 0}

        def cond():
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("transient")
            return True

        result = wait_until(cond, timeout=2, poll_interval=0.01)
        self.assertTrue(result)


class TestWaitForGone(unittest.TestCase):
    def test_returns_true_when_element_disappears(self):
        d = _make_device({(("text", "Spinner"),): [True, True, False]})
        result = wait_for_gone(d, {"text": "Spinner"}, timeout=2, poll_interval=0.01)
        self.assertTrue(result)

    def test_returns_true_when_existence_check_raises(self):
        d = MagicMock()

        def raising(**kwargs):
            raise RuntimeError("device disconnected")

        d.side_effect = raising
        result = wait_for_gone(d, {"text": "x"}, timeout=1, poll_interval=0.05)
        self.assertTrue(result)

    def test_returns_false_on_timeout(self):
        d = _make_device({(("text", "Stuck"),): [True]})
        result = wait_for_gone(d, {"text": "Stuck"}, timeout=0.2, poll_interval=0.05)
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
