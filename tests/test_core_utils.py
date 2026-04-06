import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core.emulator import ControlEmulator
from tests.test_feature import TestFeatureTaskHandler
from core.logic.task_reels import ReelsTaskHandler
from core.managers import AccountManager
from core.paths import get_app_paths
from core.settings import AppSettings, save_app_settings, load_app_settings
from utils.app_utils import AppUtils
from utils.performance_monitor import PerformanceMonitor
from utils.rate_limiter import RateLimiter


class TestCoreUtilities(unittest.TestCase):
    def test_settings_roundtrip(self) -> None:
        paths = get_app_paths()
        tmp_path = paths.config_dir / "test_settings_roundtrip.json"
        if tmp_path.exists():
            tmp_path.unlink()

        original = AppSettings(
            parallel_ld=3,
            boot_delay=7,
            task_duration=11,
            max_videos=4,
            page_per_account=3,
            task_type="reels",
            task_template="content_day",
            scroll_after_post=False,
            clear_cache=False,
            verify_account=False,
            ld_groups={"Farm A": ["US - 01", "US - 02"]},
        )
        save_app_settings(tmp_path, original)
        loaded = load_app_settings(tmp_path)
        self.assertEqual(loaded.parallel_ld, 3)
        self.assertEqual(loaded.boot_delay, 7)
        self.assertEqual(loaded.task_duration, 11)
        self.assertEqual(loaded.max_videos, 4)
        self.assertEqual(loaded.page_per_account, 3)
        self.assertEqual(loaded.task_type, "reels")
        self.assertEqual(loaded.task_template, "content_day")
        self.assertFalse(loaded.scroll_after_post)
        self.assertFalse(loaded.clear_cache)
        self.assertFalse(loaded.verify_account)
        self.assertEqual(loaded.ld_groups, {"Farm A": ["US - 01", "US - 02"]})

    def test_rate_limiter_budget_and_wait(self) -> None:
        limiter = RateLimiter(max_actions_per_hour=3)
        self.assertTrue(limiter.can_perform_action("x"))
        self.assertTrue(limiter.can_perform_action("x"))
        self.assertTrue(limiter.can_perform_action("x"))
        self.assertFalse(limiter.can_perform_action("x"))
        self.assertGreaterEqual(limiter.get_wait_time(), 0.0)
        self.assertEqual(limiter.get_remaining_actions(), 0)

    def test_performance_monitor_counts(self) -> None:
        mon = PerformanceMonitor()
        mon.start_task_timer("t1")
        time.sleep(0.01)
        mon.end_task_timer(success=True)
        stats = mon.get_stats()
        self.assertEqual(stats["completed"], 1)
        self.assertEqual(stats["failed"], 0)
        self.assertGreaterEqual(stats["avg_duration"], 0.0)

    def test_app_utils_system_info_keys(self) -> None:
        info = AppUtils.get_system_info()
        # At minimum, platform and memory fields should be present.
        self.assertIn("platform", info)
        self.assertIn("memory_total", info)

    def test_test_feature_starts_ld_and_opens_facebook(self) -> None:
        emulator = unittest.mock.Mock()
        emulator.is_ld_running.return_value = False
        emulator.start_ld.return_value = True
        emulator.open_facebook.return_value = True
        emulator.boot_delay = 10

        pause_event = unittest.mock.Mock()
        pause_event.is_set.return_value = True

        handler = TestFeatureTaskHandler(
            emulator,
            lambda message, level="INFO": None,
            pause_event,
            lambda: True,
        )

        result = handler.execute("US - 01")

        self.assertTrue(result)
        emulator.start_ld.assert_called_once_with("US - 01")
        emulator.open_facebook.assert_called_once_with("US - 01")

    def test_test_feature_fails_when_facebook_cannot_open(self) -> None:
        emulator = unittest.mock.Mock()
        emulator.is_ld_running.return_value = True
        emulator.open_facebook.return_value = False
        emulator.boot_delay = 10

        pause_event = unittest.mock.Mock()
        pause_event.is_set.return_value = True

        handler = TestFeatureTaskHandler(
            emulator,
            lambda message, level="INFO": None,
            pause_event,
            lambda: True,
        )

        result = handler.execute("US - 02")

        self.assertFalse(result)
        emulator.start_ld.assert_not_called()
        emulator.open_facebook.assert_called_once_with("US - 02")

    @patch("core.emulator.subprocess.run")
    def test_control_emulator_run_adb_command(self, mock_run) -> None:
        mock_run.return_value = unittest.mock.Mock(
            stdout="List of devices attached\nemulator-5554\tdevice\n",
            stderr="",
            returncode=0,
        )
        emulator = ControlEmulator.__new__(ControlEmulator)

        output = emulator.run_adb_command("adb devices")

        self.assertIn("emulator-5554", output)
        mock_run.assert_called_once_with(
            ["adb", "devices"],
            capture_output=True,
            text=True,
            timeout=15,
        )

    @patch("core.logic.task_reels.check_ld_ip_allowed")
    def test_reels_task_blocks_when_ld_ip_is_blocked(self, mock_check_ld_ip_allowed) -> None:
        mock_check_ld_ip_allowed.return_value = False
        emulator = unittest.mock.Mock()
        emulator.is_ld_running.return_value = True
        emulator.name_to_serial = {"US - 01": "127.0.0.1:5555"}

        pause_event = unittest.mock.Mock()
        pause_event.is_set.return_value = True
        handler = ReelsTaskHandler(
            emulator,
            lambda message, level="INFO": None,
            pause_event,
            lambda: True,
        )
        handler.blocked_countries = ["US"]

        result = handler.execute("US - 01", duration=60, max_videos=1)

        self.assertFalse(result)
        mock_check_ld_ip_allowed.assert_called_once_with(
            "127.0.0.1:5555",
            ["US"],
            handler.log,
            ld_name="US - 01",
        )
        emulator.quit_ld.assert_called_once_with("US - 01")


if __name__ == "__main__":
    unittest.main()

