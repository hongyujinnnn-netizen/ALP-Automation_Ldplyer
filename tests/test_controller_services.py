import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

from controllers.app_controller import AppController
from controllers.task_controller import TaskController
from core.managers import AccountManager
from core.paths import AppPaths
from core.settings import AppSettings, SettingsError
from services.adb_service import ADBService
from services.emulator_service import EmulatorService, EmulatorServiceConfig
from services.logging_service import AppLogger
from services.scheduler_service import SchedulerService
from services.settings_service import SettingsService
from services.task_service import TaskRunRequest, TaskService
from gui.main_window import MainWindow


def build_test_paths(root: Path) -> AppPaths:
    config_dir = root / "config"
    return AppPaths(
        project_root=root,
        config_dir=config_dir,
        content_dir=root / "content",
        backup_dir=root / "backups",
        logs_dir=root / "logs",
        settings_file=config_dir / "setting.json",
        schedule_settings_file=config_dir / "setting_schedule.json",
        accounts_file=config_dir / "created_accounts.json",
        content_queue_file=config_dir / "content_queue.json",
        scheduled_tasks_file=config_dir / "scheduled_tasks.json",
    )


class TestControllerAndServices(unittest.TestCase):
    def test_main_window_waits_for_reels_task_threads_until_they_finish(self) -> None:
        class FakeThread:
            def __init__(self, cycles: int) -> None:
                self.cycles = cycles
                self.join_calls: list[float | None] = []

            def is_alive(self) -> bool:
                return self.cycles > 0

            def join(self, timeout=None) -> None:
                self.join_calls.append(timeout)
                if self.cycles > 0:
                    self.cycles -= 1

        emulator = Mock()
        emulator.name_to_serial = {}

        window = MainWindow(
            selected_ld_names=[],
            running_flag=lambda: True,
            ld_thread=1,
            log_func=lambda *_args, **_kwargs: None,
            task_type="reels",
            emulator=emulator,
        )
        window.reels_task_join_poll_seconds = 0.01

        fake = FakeThread(cycles=3)

        window._wait_for_stage_threads([fake], "task")

        self.assertEqual(fake.join_calls, [0.01, 0.01, 0.01])
        self.assertFalse(fake.is_alive())

    def test_settings_service_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = build_test_paths(Path(tmp_dir))
            paths.ensure_runtime_dirs()
            service = SettingsService(paths)

            service.save_app_settings(
                AppSettings(
                    parallel_ld=5,
                    boot_delay=12,
                    page_per_account=3,
                    task_type="reels",
                    task_template="content_day",
                    clear_cache=False,
                    verify_account=False,
                    ld_groups={"Night Shift": ["US - 01"]},
                )
            )
            loaded = service.load_app_settings()

            self.assertEqual(loaded.parallel_ld, 5)
            self.assertEqual(loaded.boot_delay, 12)
            self.assertEqual(loaded.page_per_account, 3)
            self.assertEqual(loaded.task_type, "reels")
            self.assertEqual(loaded.task_template, "content_day")
            self.assertFalse(loaded.clear_cache)
            self.assertFalse(loaded.verify_account)
            self.assertEqual(loaded.ld_groups, {"Night Shift": ["US - 01"]})

    def test_app_controller_returns_defaults_when_settings_load_fails(self) -> None:
        settings_service = Mock()
        settings_service.load_app_settings.side_effect = SettingsError("boom")
        log_messages: list[tuple[str, str]] = []

        controller = AppController(
            settings_service,
            log_func=lambda message, level: log_messages.append((level, message)),
        )

        loaded = controller.load_app_settings()

        self.assertIsInstance(loaded, AppSettings)
        self.assertEqual(loaded.parallel_ld, AppSettings().parallel_ld)
        self.assertEqual(log_messages[0][0], "WARNING")
        self.assertIn("Failed to load settings", log_messages[0][1])

    def test_app_logger_writes_json_log_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = build_test_paths(Path(tmp_dir))
            logger = AppLogger(paths, logger_name="ldmanager-test")

            logger.log("INFO", "Refresh completed", event="refresh_devices", device_count=4)
            logger.close()

            log_path = paths.logs_dir / "app.jsonl"
            self.assertTrue(log_path.exists())

            payload = json.loads(log_path.read_text(encoding="utf-8").strip())
            self.assertEqual(payload["message"], "Refresh completed")
            self.assertEqual(payload["event"], "refresh_devices")
            self.assertEqual(payload["device_count"], 4)
            self.assertEqual(payload["ui_level"], "INFO")

    def test_adb_service_normalizes_non_prefixed_command(self) -> None:
        service = ADBService()
        self.assertEqual(service.normalize_command("devices"), ["adb", "devices"])
        self.assertEqual(service.normalize_command(["shell", "getprop"]), ["adb", "shell", "getprop"])

    def test_emulator_service_uses_adb_service_for_custom_commands(self) -> None:
        adb_service = Mock()
        adb_service.run_text_command.return_value = "ok"
        emulator = Mock()
        service = EmulatorService(
            config=EmulatorServiceConfig(),
            adb_service=adb_service,
            emulator=emulator,
        )

        output = service.run_adb_command("adb devices")

        self.assertEqual(output, "ok")
        adb_service.run_text_command.assert_called_once_with("adb devices", timeout=15)

    def test_emulator_service_checks_running_status_via_adb_devices(self) -> None:
        adb_service = Mock()
        adb_service.is_serial_online.return_value = True
        emulator = Mock()
        emulator.name_to_serial = {"US - 01": "127.0.0.1:5555"}
        service = EmulatorService(
            config=EmulatorServiceConfig(),
            adb_service=adb_service,
            emulator=emulator,
        )

        self.assertTrue(service.is_ld_running("US - 01"))
        adb_service.is_serial_online.assert_called_once_with("127.0.0.1:5555")

    def test_scheduler_service_should_run_for_matching_daily_time(self) -> None:
        service = SchedulerService()

        should_run = service.should_run(
            now=datetime(2026, 3, 17, 9, 0),
            schedule_time="09:00",
            schedule_daily=True,
            schedule_days={"Tuesday": True},
            is_running=False,
        )

        self.assertTrue(should_run)

    def test_task_controller_builds_request(self) -> None:
        controller = TaskController(TaskService())

        request = controller.build_request(
            selected_ld_names=["US - 01"],
            task_type="scroll",
            task_template="custom",
            parallel_ld=2,
            start_same_time=False,
            auto_arrange_ld=False,
            boot_delay=8,
            task_duration_seconds=900,
            max_videos=2,
            page_per_account=2,
            scroll_after_post=True,
            clear_cache=False,
            verify_account=False,
        )

        self.assertIsInstance(request, TaskRunRequest)
        self.assertEqual(request.selected_ld_names, ["US - 01"])
        self.assertEqual(request.task_type, "scroll")
        self.assertEqual(request.task_template, "custom")
        self.assertEqual(request.page_per_account, 2)
        self.assertTrue(request.scroll_after_post)
        self.assertFalse(request.clear_cache)
        self.assertFalse(request.verify_account)

    def test_account_manager_imports_json_accounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = build_test_paths(Path(tmp_dir))
            paths.ensure_runtime_dirs()
            source = paths.config_dir / "import_accounts.json"
            source.write_text(
                json.dumps(
                    [
                        {
                            "instance": "US - 01",
                            "name": "Alice",
                            "email": "alice@example.com",
                            "password": "Secret123!",
                            "status": "active",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            manager = AccountManager(paths)
            imported = manager.import_accounts(source)

            self.assertEqual(imported, 1)
            account = manager.get_device_account("US - 01")
            self.assertEqual(account["email"], "alice@example.com")
            self.assertEqual(account["instance"], "US - 01")
            self.assertEqual(account["instance"], "US - 01")
            self.assertEqual(account["device_name"], "US - 01")

    def test_account_manager_imports_csv_accounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = build_test_paths(Path(tmp_dir))
            paths.ensure_runtime_dirs()
            source = paths.config_dir / "import_accounts.csv"
            source.write_text(
                "instance,name,email,password,status\n"
                "US - 02,Bob,bob@example.com,TopSecret!,idle\n",
                encoding="utf-8",
            )

            manager = AccountManager(paths)
            imported = manager.import_accounts(source)

            self.assertEqual(imported, 1)
            rows = manager.list_accounts()
            self.assertEqual(rows[0]["instance"], "US - 02")
            self.assertEqual(rows[0]["status"], "idle")
            self.assertEqual(rows[0]["email"], "bob@example.com")

    def test_account_manager_updates_and_removes_by_uid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = build_test_paths(Path(tmp_dir))
            paths.ensure_runtime_dirs()
            manager = AccountManager(paths)

            created = manager.create_account(
                {
                    "instance": "US - 03",
                    "name": "Cara",
                    "phone": "+15551234567",
                    "password": "EditMe123!",
                    "status": "active",
                }
            )

            updated = manager.update_account(
                created["account_id"],
                {
                    "status": "error",
                    "notes": "verification required",
                },
            )

            self.assertEqual(updated["status"], "error")
            self.assertEqual(updated["notes"], "verification required")

            manager.remove_account(created["account_id"])
            self.assertEqual(manager.list_accounts(), [])

    def test_account_manager_exports_txt_and_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = build_test_paths(Path(tmp_dir))
            paths.ensure_runtime_dirs()
            manager = AccountManager(paths)
            manager.create_account(
                {
                    "instance": "US - 07",
                    "name": "Delta",
                    "phone": "+15557654321",
                    "password": "TopSecret123!",
                    "status": "novery",
                    "ld_adb": "127.0.0.1:5555",
                }
            )

            txt_path = paths.config_dir / "accounts.txt"
            pdf_path = paths.config_dir / "accounts.pdf"

            manager.export_accounts(txt_path)
            manager.export_accounts(pdf_path)

            self.assertTrue(txt_path.exists())
            self.assertIn("Delta", txt_path.read_text(encoding="utf-8"))
            self.assertTrue(pdf_path.exists())
            self.assertTrue(pdf_path.read_bytes().startswith(b"%PDF-1.4"))

    def test_new_layer_modules_are_importable(self) -> None:
        from app.app import main
        from core.models import DeviceRuntimeState, EmulatorInstance
        from core.state_machine import TaskStateMachine
        from gui.pages.emulator_page import EmulatorPageMixin
        from gui.pages.settings_page import SettingsPageMixin
        from gui.pages.task_page import TaskPageMixin
        from utils.helpers import AppUtils
        from utils.logger import AppLogger as CompatibilityLogger

        self.assertTrue(callable(main))
        self.assertEqual(EmulatorInstance(name="A", serial="B").serial, "B")
        self.assertEqual(DeviceRuntimeState().state, "Idle")
        self.assertEqual(TaskStateMachine().normalize("running"), "Running")
        self.assertIsNotNone(EmulatorPageMixin)
        self.assertIsNotNone(TaskPageMixin)
        self.assertIsNotNone(SettingsPageMixin)
        self.assertIs(AppUtils, AppUtils)
        self.assertIsNotNone(CompatibilityLogger)


if __name__ == "__main__":
    unittest.main()
