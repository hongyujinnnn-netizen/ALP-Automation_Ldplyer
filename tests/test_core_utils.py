import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core.emulator import ControlEmulator
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

        original = AppSettings(parallel_ld=3, boot_delay=7, task_duration=11, max_videos=4)
        save_app_settings(tmp_path, original)
        loaded = load_app_settings(tmp_path)
        self.assertEqual(loaded.parallel_ld, 3)
        self.assertEqual(loaded.boot_delay, 7)
        self.assertEqual(loaded.task_duration, 11)
        self.assertEqual(loaded.max_videos, 4)

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


if __name__ == "__main__":
    unittest.main()

