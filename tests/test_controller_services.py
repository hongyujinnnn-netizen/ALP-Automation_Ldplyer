import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

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
from gui.ld_manager_app import LDManagerApp
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
    @patch("gui.ld_manager_app.platform.system", return_value="Windows")
    def test_ld_manager_app_maximizes_window_on_windows_startup(self, _mock_system) -> None:
        root = Mock()
        app = LDManagerApp.__new__(LDManagerApp)
        app.root = root

        app._maximize_on_startup()

        root.state.assert_called_once_with("zoomed")
        root.attributes.assert_not_called()
        root.geometry.assert_not_called()

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
                    accounts_per_ld=4,
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
            self.assertEqual(loaded.accounts_per_ld, 4)
            self.assertEqual(loaded.task_type, "reels")
            self.assertEqual(loaded.task_template, "content_day")
            self.assertFalse(loaded.clear_cache)
            self.assertFalse(loaded.verify_account)
            self.assertEqual(loaded.ld_groups, {"Night Shift": ["US - 01"]})

    def test_settings_password_persists_to_keyring_not_json(self) -> None:
        from core import credential_store
        from core.settings import load_app_settings, save_app_settings

        fake_vault: dict[tuple[str, str], str] = {}
        fake = Mock()
        fake.set_password.side_effect = lambda svc, user, pwd: fake_vault.__setitem__((svc, user), pwd)
        fake.get_password.side_effect = lambda svc, user: fake_vault.get((svc, user))
        fake.delete_password.side_effect = lambda svc, user: fake_vault.pop((svc, user), None)

        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch.object(credential_store, "keyring", fake),
            patch.object(credential_store, "_AVAILABLE", True),
        ):
            paths = build_test_paths(Path(tmp_dir))
            paths.ensure_runtime_dirs()

            settings = AppSettings(
                email_address="alice@example.com",
                email_app_password="hunter2",
            )
            save_app_settings(paths.settings_file, settings)

            on_disk = paths.settings_file.read_text(encoding="utf-8")
            self.assertNotIn("hunter2", on_disk)
            self.assertNotIn("email_app_password", on_disk)
            self.assertEqual(fake_vault[("alp-automation", "alice@example.com")], "hunter2")

            loaded = load_app_settings(paths.settings_file)
            self.assertEqual(loaded.email_app_password, "hunter2")

    def test_settings_legacy_plaintext_migrates_to_keyring(self) -> None:
        from core import credential_store
        from core.settings import load_app_settings

        fake_vault: dict[tuple[str, str], str] = {}
        fake = Mock()
        fake.set_password.side_effect = lambda svc, user, pwd: fake_vault.__setitem__((svc, user), pwd)
        fake.get_password.side_effect = lambda svc, user: fake_vault.get((svc, user))
        fake.delete_password.side_effect = lambda svc, user: fake_vault.pop((svc, user), None)

        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch.object(credential_store, "keyring", fake),
            patch.object(credential_store, "_AVAILABLE", True),
        ):
            paths = build_test_paths(Path(tmp_dir))
            paths.ensure_runtime_dirs()
            paths.settings_file.write_text(
                json.dumps(
                    {
                        "email_address": "bob@example.com",
                        "email_app_password": "legacy-plain-text",
                    }
                ),
                encoding="utf-8",
            )

            loaded = load_app_settings(paths.settings_file)

            self.assertEqual(loaded.email_app_password, "legacy-plain-text")
            self.assertEqual(fake_vault[("alp-automation", "bob@example.com")], "legacy-plain-text")
            on_disk = paths.settings_file.read_text(encoding="utf-8")
            self.assertNotIn("legacy-plain-text", on_disk)

    def test_settings_keeps_plaintext_when_keyring_unavailable(self) -> None:
        from core import credential_store
        from core.settings import load_app_settings

        with tempfile.TemporaryDirectory() as tmp_dir, patch.object(credential_store, "_AVAILABLE", False):
            paths = build_test_paths(Path(tmp_dir))
            paths.ensure_runtime_dirs()
            paths.settings_file.write_text(
                json.dumps(
                    {
                        "email_address": "carol@example.com",
                        "email_app_password": "still-plain",
                    }
                ),
                encoding="utf-8",
            )

            loaded = load_app_settings(paths.settings_file)
            self.assertEqual(loaded.email_app_password, "still-plain")
            on_disk = paths.settings_file.read_text(encoding="utf-8")
            self.assertIn("still-plain", on_disk)

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
            accounts_per_ld=3,
            scroll_after_post=True,
            clear_cache=False,
            verify_account=False,
        )

        self.assertIsInstance(request, TaskRunRequest)
        self.assertEqual(request.selected_ld_names, ["US - 01"])
        self.assertEqual(request.task_type, "scroll")
        self.assertEqual(request.task_template, "custom")
        self.assertEqual(request.page_per_account, 2)
        self.assertEqual(request.accounts_per_ld, 3)
        self.assertTrue(request.scroll_after_post)
        self.assertFalse(request.clear_cache)
        self.assertFalse(request.verify_account)

    def test_main_window_loops_reg_account_task_for_accounts_per_ld(self) -> None:
        emulator = Mock()
        emulator.name_to_serial = {"US - 01": "127.0.0.1:5555"}
        emulator.quit_ld.return_value = True
        handler = Mock()
        handler.execute.return_value = True

        progress_updates: list[float] = []
        state_updates: list[tuple[str, dict]] = []

        window = MainWindow(
            selected_ld_names=["US - 01"],
            running_flag=lambda: True,
            ld_thread=1,
            log_func=lambda *_args, **_kwargs: None,
            task_type="reg_account",
            task_handler=handler,
            progress_callback=progress_updates.append,
            verify_account=False,
            accounts_per_ld=3,
            emulator=emulator,
            state_callback=lambda name, payload: state_updates.append((name, payload)),
        )

        with patch("gui.main_window.time.sleep", return_value=None):
            window.ld_task_stage("US - 01", "task")

        self.assertEqual(handler.execute.call_count, 3)
        emulator.quit_ld.assert_called_once_with("US - 01")
        for call in handler.execute.call_args_list:
            self.assertEqual(call.args[:2], ("US - 01", window.task_duration))
            self.assertEqual(call.kwargs["verify"], False)
        self.assertEqual(progress_updates, [100.0])
        self.assertTrue(any(payload.get("state") == "Completed" for _, payload in state_updates))
        self.assertEqual(state_updates[-1][1].get("state"), "Idle")

    def test_main_window_close_stage_skips_duplicate_shutdown_for_reg_account(self) -> None:
        emulator = Mock()
        emulator.name_to_serial = {"US - 01": "127.0.0.1:5555"}
        emulator.quit_ld.return_value = True
        handler = Mock()
        handler.execute.return_value = True

        window = MainWindow(
            selected_ld_names=["US - 01"],
            running_flag=lambda: True,
            ld_thread=1,
            log_func=lambda *_args, **_kwargs: None,
            task_type="reg_account",
            task_handler=handler,
            verify_account=False,
            accounts_per_ld=1,
            emulator=emulator,
        )

        with patch("gui.main_window.time.sleep", return_value=None):
            window.ld_task_stage("US - 01", "task")
            window.ld_task_stage("US - 01", "close")

        emulator.quit_ld.assert_called_once_with("US - 01")

    @staticmethod
    def _fake_keyring():
        from unittest.mock import Mock as _Mock

        vault: dict[tuple[str, str], str] = {}
        fake = _Mock()
        fake.set_password.side_effect = lambda svc, user, pwd: vault.__setitem__((svc, user), pwd)
        fake.get_password.side_effect = lambda svc, user: vault.get((svc, user))
        fake.delete_password.side_effect = lambda svc, user: vault.pop((svc, user), None)
        return fake, vault

    def test_account_manager_writes_password_to_keyring_not_json(self) -> None:
        from core import credential_store
        from core.managers import AccountManager

        fake, vault = self._fake_keyring()
        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch.object(credential_store, "keyring", fake),
            patch.object(credential_store, "_AVAILABLE", True),
        ):
            paths = build_test_paths(Path(tmp_dir))
            paths.ensure_runtime_dirs()
            manager = AccountManager(paths)
            created = manager.create_account(
                {
                    "instance": "US - 09",
                    "name": "Eve",
                    "phone": "+15550000000",
                    "password": "VerySecret!",
                    "status": "active",
                }
            )
            on_disk = paths.accounts_file.read_text(encoding="utf-8")

            self.assertNotIn("VerySecret!", on_disk)
            account_id = created["account_id"]
            self.assertEqual(vault[("alp-automation", f"{account_id}::password")], "VerySecret!")

            # Reloading via a fresh AccountManager hydrates from keyring transparently.
            manager2 = AccountManager(paths)
            self.assertEqual(manager2.get_account(account_id)["password"], "VerySecret!")

    def test_account_manager_remove_account_clears_keyring(self) -> None:
        from core import credential_store
        from core.managers import AccountManager

        fake, vault = self._fake_keyring()
        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch.object(credential_store, "keyring", fake),
            patch.object(credential_store, "_AVAILABLE", True),
        ):
            paths = build_test_paths(Path(tmp_dir))
            paths.ensure_runtime_dirs()
            manager = AccountManager(paths)
            created = manager.create_account(
                {
                    "instance": "US - 10",
                    "password": "ToBeDeleted!",
                    "phone": "+15551110000",
                }
            )
            account_id = created["account_id"]
            self.assertIn(("alp-automation", f"{account_id}::password"), vault)

            manager.remove_account(account_id)

        self.assertNotIn(("alp-automation", f"{account_id}::password"), vault)

    def test_account_manager_migrates_legacy_plaintext(self) -> None:
        from core import credential_store
        from core.managers import AccountManager

        fake, vault = self._fake_keyring()
        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch.object(credential_store, "keyring", fake),
            patch.object(credential_store, "_AVAILABLE", True),
        ):
            paths = build_test_paths(Path(tmp_dir))
            paths.ensure_runtime_dirs()
            paths.accounts_file.write_text(
                json.dumps(
                    [
                        {
                            "account_id": "legacy-1",
                            "facebook_uid": "12345",
                            "name": "Legacy",
                            "password": "leaked-plain",
                            "status": "idle",
                            "device_name": "US - 11",
                            "instance": "US - 11",
                            "email": "",
                            "phone": "",
                            "ld_adb": "",
                            "gender": "",
                            "notes": "",
                            "username": "Legacy",
                            "created_at": "2026-01-01T00:00:00",
                            "updated_at": "2026-01-01T00:00:00",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            manager = AccountManager(paths)
            on_disk_after = paths.accounts_file.read_text(encoding="utf-8")

        self.assertEqual(vault[("alp-automation", "legacy-1::password")], "leaked-plain")
        self.assertNotIn("leaked-plain", on_disk_after)
        self.assertEqual(manager.accounts[0]["password"], "leaked-plain")

    def test_account_manager_keeps_plaintext_when_keyring_unavailable(self) -> None:
        from core import credential_store
        from core.managers import AccountManager

        with tempfile.TemporaryDirectory() as tmp_dir, patch.object(credential_store, "_AVAILABLE", False):
            paths = build_test_paths(Path(tmp_dir))
            paths.ensure_runtime_dirs()
            paths.accounts_file.write_text(
                json.dumps(
                    [
                        {
                            "account_id": "no-vault-1",
                            "name": "NoVault",
                            "password": "still-here",
                            "status": "idle",
                            "device_name": "US - 12",
                            "instance": "US - 12",
                            "email": "",
                            "phone": "+15552220000",
                            "ld_adb": "",
                            "gender": "",
                            "notes": "",
                            "username": "NoVault",
                            "facebook_uid": "",
                            "created_at": "2026-01-01T00:00:00",
                            "updated_at": "2026-01-01T00:00:00",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            manager = AccountManager(paths)
            on_disk = paths.accounts_file.read_text(encoding="utf-8")

        self.assertIn("still-here", on_disk)
        self.assertEqual(manager.accounts[0]["password"], "still-here")

    def test_logged_accounts_password_persists_to_keyring(self) -> None:
        from core import credential_store
        from core.tasks.handler.handler_login import LoginHandlerMixin

        fake, vault = self._fake_keyring()

        class LoggedCreds:
            identifier = "alice@example.com"
            label = "email"
            password = "LoggedSecret!"

        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch.object(credential_store, "keyring", fake),
            patch.object(credential_store, "_AVAILABLE", True),
        ):
            paths = build_test_paths(Path(tmp_dir))
            paths.ensure_runtime_dirs()
            handler = LoginHandlerMixin.__new__(LoginHandlerMixin)
            handler.log = lambda *_args, **_kwargs: None
            with patch("core.tasks.handler.handler_login.get_app_paths", return_value=paths):
                handler._save_logged_account("LD A", "127.0.0.1:5555", LoggedCreds(), facebook_uid="fbuid-1")
            content = (paths.config_dir / "logged_accounts.json").read_text(encoding="utf-8")

        self.assertNotIn("LoggedSecret!", content)
        self.assertEqual(vault[("alp-automation", "fbuid-1::password")], "LoggedSecret!")

    def test_logged_accounts_migration_skips_when_already_redacted(self) -> None:
        from core import credential_store
        from core.tasks.handler.handler_login import LoginHandlerMixin

        fake, vault = self._fake_keyring()

        class LoggedCreds:
            identifier = "bob@example.com"
            label = "email"
            password = "NewPw!"

        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch.object(credential_store, "keyring", fake),
            patch.object(credential_store, "_AVAILABLE", True),
        ):
            paths = build_test_paths(Path(tmp_dir))
            paths.ensure_runtime_dirs()
            log_path = paths.config_dir / "logged_accounts.json"
            log_path.write_text(
                json.dumps(
                    [
                        {"facebook_uid": "old-uid-1", "password": ""},
                        {"facebook_uid": "old-uid-2", "password": ""},
                    ]
                ),
                encoding="utf-8",
            )
            handler = LoginHandlerMixin.__new__(LoginHandlerMixin)
            handler.log = lambda *_args, **_kwargs: None
            with patch("core.tasks.handler.handler_login.get_app_paths", return_value=paths):
                handler._save_logged_account("LD B", "127.0.0.1:5556", LoggedCreds(), facebook_uid="fbuid-2")

        # Migration optimization: existing entries had empty passwords, so set_password was
        # called only for the newly appended record.
        password_writes = [
            call for call in fake.set_password.call_args_list if call.args[1].endswith("::password")
        ]
        self.assertEqual(len(password_writes), 1)
        self.assertEqual(password_writes[0].args[1], "fbuid-2::password")

    def test_account_manager_imports_json_accounts(self) -> None:
        from core import credential_store

        self._kr_patch_a = patch.object(credential_store, "_AVAILABLE", False)
        self._kr_patch_a.start()
        self.addCleanup(self._kr_patch_a.stop)
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
        from core import credential_store

        kp = patch.object(credential_store, "_AVAILABLE", False)
        kp.start()
        self.addCleanup(kp.stop)
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = build_test_paths(Path(tmp_dir))
            paths.ensure_runtime_dirs()
            source = paths.config_dir / "import_accounts.csv"
            source.write_text(
                "instance,name,email,password,status\nUS - 02,Bob,bob@example.com,TopSecret!,idle\n",
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
        from core import credential_store

        kp = patch.object(credential_store, "_AVAILABLE", False)
        kp.start()
        self.addCleanup(kp.stop)
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
        from core import credential_store

        kp = patch.object(credential_store, "_AVAILABLE", False)
        kp.start()
        self.addCleanup(kp.stop)
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
