import json
import csv
import time
from datetime import datetime, timedelta
from pathlib import Path
import zipfile
import os
import textwrap
from core.paths import get_app_paths, AppPaths
from core.settings import _atomic_write_json

# ==================== ACCOUNT MANAGER ====================
class AccountManager:
    def __init__(self, paths: AppPaths | None = None):
        self.paths = paths or get_app_paths()
        self.accounts_file = self.paths.accounts_file
        self.accounts = self.load_accounts()
    
    def load_accounts(self) -> list[dict]:
        if not self.accounts_file.exists():
            return []

        try:
            with open(self.accounts_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError):
            return []
        return self._normalize_accounts(raw)

    def save_accounts(self) -> None:
        _atomic_write_json(self.accounts_file, self.accounts)

    def get_all_accounts(self) -> list[dict]:
        return [self._with_account_metadata(account) for account in self.accounts]

    def create_account(self, account_data: dict) -> dict:
        clean = self._normalize_account_record(account_data)
        self.accounts.append(clean)
        self._sort_accounts()
        self.save_accounts()
        return self._with_account_metadata(clean)

    def update_account(self, identifier: str, account_data: dict) -> dict:
        identifier = str(identifier or "").strip()
        if not identifier:
            raise ValueError("account identifier is required")

        for index, account in enumerate(self.accounts):
            if self._get_account_identifier(account) != identifier:
                continue
            merged = dict(account)
            merged.update(account_data or {})
            clean = self._normalize_account_record(merged, existing=account)
            self.accounts[index] = clean
            self._sort_accounts()
            self.save_accounts()
            return self._with_account_metadata(clean)
        raise ValueError(f"Account not found: {identifier}")

    def get_account(self, identifier: str) -> dict:
        identifier = str(identifier or "").strip()
        for account in self.accounts:
            if self._get_account_identifier(account) == identifier:
                return self._with_account_metadata(account)
        return {}

    def assign_account_to_device(self, device_name: str, account_data: dict) -> dict:
        device_name = str(device_name).strip()
        if not device_name:
            raise ValueError("device_name is required")

        candidate = self.get_device_account(device_name)
        payload = dict(account_data or {})
        payload["device_name"] = device_name
        payload["instance"] = device_name
        if candidate:
            return self.update_account(self._get_account_identifier(candidate), payload)
        return self.create_account(payload)

    def get_device_account(self, device_name: str) -> dict:
        device_name = str(device_name or "").strip()
        if not device_name:
            return {}

        matches = [
            dict(account)
            for account in self.accounts
            if str(account.get("device_name") or account.get("instance") or account.get("ld_name") or "").strip() == device_name
        ]
        if not matches:
            return {}
        matches.sort(
            key=lambda row: (
                str(row.get("created_at") or ""),
                str(row.get("updated_at") or ""),
                self._get_account_identifier(row),
            ),
            reverse=True,
        )
        return self._with_account_metadata(matches[0])

    def remove_account(self, identifier: str) -> None:
        identifier = str(identifier or "").strip()
        if not identifier:
            raise ValueError("Account identifier is required")

        original_count = len(self.accounts)
        self.accounts = [
            account for account in self.accounts
            if self._get_account_identifier(account) != identifier
            and str(account.get("device_name") or account.get("instance") or account.get("ld_name") or "") != identifier
        ]
        if len(self.accounts) != original_count:
            self.save_accounts()

    def export_accounts(self, file_path: str | Path, rows: list[dict] | None = None) -> Path:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = [dict(row) for row in (rows if rows is not None else self.list_accounts())]

        if path.suffix.lower() == ".csv":
            fieldnames = [
                "facebook_uid",
                "name",
                "phone",
                "email",
                "password",
                "ld_adb",
                "instance",
                "device_name",
                "gender",
                "status",
                "notes",
                "created_at",
                "updated_at",
            ]
            self._write_accounts_csv(path, rows, fieldnames)
        elif path.suffix.lower() == ".txt":
            self._write_accounts_txt(path, rows)
        elif path.suffix.lower() == ".pdf":
            self._write_accounts_pdf(path, rows)
        else:
            _atomic_write_json(path, rows)
        return path

    def get_account_summary(self) -> dict:
        summary = {
            "total": len(self.accounts),
            "active": 0,
            "idle": 0,
            "error": 0,
            "novery": 0,
            "dead": 0,
            "unknown": 0,
            "with_phone": 0,
            "with_email": 0,
        }
        for account in self.accounts:
            status = str(account.get("status") or "").strip().lower()
            if status in {"active", "idle", "error", "novery", "dead", "unknown"}:
                summary[status] += 1
            if str(account.get("phone") or "").strip():
                summary["with_phone"] += 1
            if str(account.get("email") or "").strip():
                summary["with_email"] += 1
        return summary

    # Small adapter used by the Account Manager dialog.
    def list_accounts(self) -> list[dict]:
        """
        Return a flat list of accounts suitable for table display.

        Each entry contains at least: name, instance and status.
        """
        rows: list[dict] = []
        for data in self.accounts:
            account = self._with_account_metadata(data)
            account["uid"] = str(account.get("facebook_uid") or "")
            account["instance"] = str(account.get("instance") or account.get("device_name") or account.get("ld_name") or "")
            account["device_name"] = account["instance"]
            account["username"] = str(
                account.get("username")
                or account.get("name")
                or account.get("email")
                or account.get("phone")
                or account["instance"]
                or "account"
            )
            account["status"] = str(account.get("status") or "idle").lower()
            rows.append(account)
        return rows

    def import_accounts(self, file_path: str | Path) -> int:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(path)

        suffix = path.suffix.lower()
        if suffix == ".csv":
            records = self._load_accounts_from_csv(path)
        elif suffix == ".json":
            records = self._load_accounts_from_json(path)
        else:
            raise ValueError("Only .csv and .json account files are supported")

        imported = 0
        for record in records:
            clean = self._normalize_account_record(record)
            existing_identifier = self._get_account_identifier(clean)
            if existing_identifier and any(self._get_account_identifier(row) == existing_identifier for row in self.accounts):
                self.update_account(existing_identifier, clean)
            else:
                self.accounts.append(clean)
            imported += 1
        self._sort_accounts()
        self.save_accounts()
        return imported

    def _normalize_accounts(self, raw) -> list[dict]:
        normalized = []

        if isinstance(raw, dict):
            iterable = []
            for device_name, account_data in raw.items():
                if not isinstance(account_data, dict):
                    continue
                row = dict(account_data)
                row.setdefault("device_name", str(device_name).strip())
                row.setdefault("instance", str(device_name).strip())
                iterable.append(row)
        elif isinstance(raw, list):
            iterable = [row for row in raw if isinstance(row, dict)]
        else:
            return []

        for account_data in iterable:
            normalized.append(self._normalize_account_record(account_data))

        normalized.sort(
            key=lambda row: (
                str(row.get("created_at") or ""),
                str(row.get("updated_at") or ""),
                self._get_account_identifier(row),
            ),
            reverse=True,
        )
        return normalized

    def _normalize_account_record(self, account_data: dict, existing: dict | None = None) -> dict:
        existing = existing or {}
        clean = {}
        for key, value in (account_data or {}).items():
            if value is None:
                continue
            text = value.strip() if isinstance(value, str) else value
            clean[str(key)] = text

        device_name = str(
            clean.get("device_name")
            or clean.get("instance")
            or clean.get("ld_name")
            or existing.get("device_name")
            or existing.get("instance")
            or existing.get("ld_name")
            or ""
        ).strip()
        adb_serial = str(
            clean.get("ld_adb")
            or existing.get("ld_adb")
            or ""
        ).strip()
        email = str(clean.get("email") or existing.get("email") or "").strip()
        phone = str(clean.get("phone") or existing.get("phone") or "").strip()
        name = str(
            clean.get("name")
            or clean.get("username")
            or existing.get("name")
            or existing.get("username")
            or email
            or phone
            or device_name
            or "account"
        ).strip()
        created_at = str(clean.get("created_at") or existing.get("created_at") or datetime.now().isoformat(timespec="seconds"))
        updated_at = str(clean.get("updated_at") or datetime.now().isoformat(timespec="seconds"))
        facebook_uid = str(
            clean.get("facebook_uid")
            or existing.get("facebook_uid")
            or ""
        ).strip()
        clean.pop("uid", None)
        clean.pop("ld_name", None)
        clean["facebook_uid"] = facebook_uid
        clean["ld_adb"] = adb_serial
        clean["device_name"] = device_name
        clean["instance"] = device_name
        clean["username"] = name
        clean["name"] = name
        clean["phone"] = phone
        clean["email"] = email
        clean["password"] = str(clean.get("password") or existing.get("password") or "")
        clean["gender"] = str(clean.get("gender") or existing.get("gender") or "")
        clean["status"] = str(clean.get("status") or existing.get("status") or "idle").lower()
        clean["notes"] = str(clean.get("notes") or existing.get("notes") or "")
        clean["created_at"] = created_at
        clean["updated_at"] = updated_at
        return clean

    def _load_accounts_from_json(self, path: Path) -> list[dict]:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)

        if isinstance(raw, dict):
            if all(isinstance(value, dict) for value in raw.values()):
                rows = []
                for key, value in raw.items():
                    row = dict(value)
                    row.setdefault("device_name", key)
                    rows.append(row)
                return rows
            return [raw]

        if isinstance(raw, list):
            return [row for row in raw if isinstance(row, dict)]

        return []

    def _load_accounts_from_csv(self, path: Path) -> list[dict]:
        with open(path, "r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            return [dict(row) for row in reader if row]

    def _sort_accounts(self) -> None:
        self.accounts.sort(
            key=lambda row: (
                str(row.get("created_at") or ""),
                str(row.get("updated_at") or ""),
                self._get_account_identifier(row),
            ),
            reverse=True,
        )

    def _get_account_identifier(self, account: dict) -> str:
        facebook_uid = str((account or {}).get("facebook_uid") or "").strip()
        if facebook_uid:
            return facebook_uid

        device_name = str(
            (account or {}).get("device_name")
            or (account or {}).get("instance")
            or (account or {}).get("ld_name")
            or ""
        ).strip()
        created_at = str((account or {}).get("created_at") or "").strip()
        name = str((account or {}).get("name") or (account or {}).get("username") or "").strip()
        return f"fallback::{device_name}::{created_at}::{name}"

    def _with_account_metadata(self, account: dict) -> dict:
        row = dict(account or {})
        row["account_id"] = self._get_account_identifier(row)
        return row

    def _write_accounts_csv(self, path: Path, rows: list[dict], fieldnames: list[str]) -> None:
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in fieldnames})

    def _write_accounts_txt(self, path: Path, rows: list[dict]) -> None:
        lines = [
            f"Account Export - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Total Accounts: {len(rows)}",
            "",
        ]
        for index, row in enumerate(rows, start=1):
            lines.extend(
                [
                    f"[{index}] {row.get('name') or row.get('username') or 'account'}",
                    f"UID: {row.get('facebook_uid', '')}",
                    f"Status: {row.get('status', '')}",
                    f"Gender: {row.get('gender', '')}",
                    f"Phone: {row.get('phone', '')}",
                    f"Email: {row.get('email', '')}",
                    f"ADB Serial: {row.get('ld_adb', '')}",
                    f"LD Instance: {row.get('instance') or row.get('device_name') or ''}",
                    f"Created: {row.get('created_at', '')}",
                    f"Updated: {row.get('updated_at', '')}",
                    f"Notes: {row.get('notes', '')}",
                    "-" * 72,
                ]
            )
        path.write_text("\n".join(lines), encoding="utf-8")

    def _write_accounts_pdf(self, path: Path, rows: list[dict]) -> None:
        page_width = 612
        page_height = 792
        left_margin = 40
        top_margin = 40
        line_height = 14
        max_chars = 88

        def _escape_pdf_text(value: str) -> str:
            return (
                str(value)
                .replace("\\", "\\\\")
                .replace("(", "\\(")
                .replace(")", "\\)")
            )

        content_lines = [
            "BT",
            "/F1 11 Tf",
        ]
        y = page_height - top_margin

        def add_line(text: str) -> None:
            nonlocal y
            if y <= 50:
                content_lines.extend(["ET", "BT", "/F1 11 Tf"])
                y = page_height - top_margin
            content_lines.append(f"1 0 0 1 {left_margin} {y} Tm ({_escape_pdf_text(text)}) Tj")
            y -= line_height

        add_line(f"Account Export - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        add_line(f"Total Accounts: {len(rows)}")
        add_line("")

        for index, row in enumerate(rows, start=1):
            block = [
                f"[{index}] {row.get('name') or row.get('username') or 'account'}",
                f"UID: {row.get('facebook_uid', '')}",
                f"Status: {row.get('status', '')}",
                f"Gender: {row.get('gender', '')}",
                f"Phone: {row.get('phone', '')}",
                f"Email: {row.get('email', '')}",
                f"ADB Serial: {row.get('ld_adb', '')}",
                f"LD Instance: {row.get('instance') or row.get('device_name') or ''}",
                f"Created: {row.get('created_at', '')}",
                f"Updated: {row.get('updated_at', '')}",
                f"Notes: {row.get('notes', '')}",
                "",
            ]
            for line in block:
                wrapped = textwrap.wrap(str(line), width=max_chars) or [""]
                for segment in wrapped:
                    add_line(segment)

        content_lines.append("ET")
        content_stream = "\n".join(content_lines).encode("latin-1", errors="replace")

        objects: list[bytes] = []
        objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
        objects.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_width} {page_height}] "
            f"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>".encode("ascii")
        )
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        objects.append(f"<< /Length {len(content_stream)} >>\nstream\n".encode("ascii") + content_stream + b"\nendstream")

        pdf = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for index, obj in enumerate(objects, start=1):
            offsets.append(len(pdf))
            pdf.extend(f"{index} 0 obj\n".encode("ascii"))
            pdf.extend(obj)
            pdf.extend(b"\nendobj\n")

        xref_offset = len(pdf)
        pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
        pdf.extend(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
        pdf.extend(
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode("ascii")
        )
        path.write_bytes(pdf)

# ==================== CONTENT MANAGER ====================
class ContentManager:
    def __init__(self, paths: AppPaths | None = None):
        self.paths = paths or get_app_paths()
        self.content_dir = self.paths.content_dir
        self.content_dir.mkdir(exist_ok=True)
        self.video_queue = []
        self.content_file = self.paths.content_queue_file
        self.load_content_queue()

    def get_queue_items(self):
        return self.video_queue

    def get_queue_details(self):
        return self.video_queue
    
    def add_video_to_queue(self, video_path, caption="", hashtags=""):
        video_data = {
            'path': str(video_path),
            'caption': caption,
            'hashtags': hashtags,
            'used': False,
            'added_date': datetime.now().isoformat(),
            'used_date': None
        }
        self.video_queue.append(video_data)
        self.save_content_queue()
        return True
    
    def get_next_video(self):
        for video in self.video_queue:
            if not video['used']:
                video['used'] = True
                video['used_date'] = datetime.now().isoformat()
                self.save_content_queue()
                return video
        return None
    
    def load_content_from_folder(self, folder_path):
        video_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv']
        folder = Path(folder_path)
        
        if not folder.exists():
            return False
        
        added_count = 0
        for ext in video_extensions:
            for video_file in folder.glob(f"*{ext}"):
                if self.add_video_to_queue(video_file):
                    added_count += 1
        
        return added_count
    
    def clear_used_videos(self):
        self.video_queue = [video for video in self.video_queue if not video['used']]
        self.save_content_queue()
    
    def get_queue_stats(self):
        total = len(self.video_queue)
        used = sum(1 for video in self.video_queue if video['used'])
        available = total - used
        return {'total': total, 'used': used, 'available': available, 'queue_size': total}
    
    def load_content_queue(self):
        if self.content_file.exists():
            try:
                with open(self.content_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.video_queue = data if isinstance(data, list) else []
            except (json.JSONDecodeError, OSError) as exc:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                corrupt_copy = self.content_file.with_suffix(f"{self.content_file.suffix}.corrupt_{timestamp}")
                try:
                    self.content_file.rename(corrupt_copy)
                except OSError:
                    pass
                print(f"Invalid content queue JSON. Resetting queue. Details: {exc}")
                self.video_queue = []
        else:
            self.video_queue = []
    
    def save_content_queue(self):
        _atomic_write_json(self.content_file, self.video_queue)

# ==================== SMART SCHEDULER ====================
class SmartScheduler:
    def __init__(self, log_func, paths: AppPaths | None = None):
        self.log = log_func
        self.paths = paths or get_app_paths()
        self.task_queue = []
        self.running = False
        self.schedule_file = self.paths.scheduled_tasks_file
        self.load_scheduled_tasks()
        
    def add_task(self, task_type, devices, schedule_time, repeat_interval=None, enabled=True):
        task = {
            'id': len(self.task_queue) + 1,
            'type': task_type,
            'devices': devices,
            'schedule_time': schedule_time,
            'repeat_interval': repeat_interval,
            'enabled': enabled,
            'last_run': None,
            'next_run': self.calculate_next_run(schedule_time, repeat_interval)
        }
        self.task_queue.append(task)
        self.save_scheduled_tasks()
        return task['id']
    
    def remove_task(self, task_id):
        self.task_queue = [task for task in self.task_queue if task['id'] != task_id]
        self.save_scheduled_tasks()
    
    def enable_task(self, task_id, enabled=True):
        for task in self.task_queue:
            if task['id'] == task_id:
                task['enabled'] = enabled
                break
        self.save_scheduled_tasks()
    
    def get_pending_tasks(self):
        now = datetime.now()
        pending = []
        
        for task in self.task_queue:
            if task['enabled'] and self.should_run_task(task, now):
                pending.append(task)
        
        return pending
    
    def should_run_task(self, task, current_time):
        if not task['enabled']:
            return False
        
        task_time = datetime.strptime(task['schedule_time'], "%H:%M").time()
        current_time_time = current_time.time()
        
        # Check if it's time to run
        if (task_time.hour == current_time_time.hour and 
            task_time.minute == current_time_time.minute):
            
            # Check if we haven't run this task in the last minute (avoid duplicates)
            if task['last_run']:
                last_run = datetime.fromisoformat(task['last_run'])
                if (current_time - last_run).total_seconds() < 55:  # 55 seconds grace period
                    return False
            
            return True
        
        return False
    
    def calculate_next_run(self, schedule_time, repeat_interval):
        if not repeat_interval:
            return None
        
        now = datetime.now()
        base_time = datetime.strptime(schedule_time, "%H:%M").time()
        base_datetime = datetime.combine(now.date(), base_time)
        
        if base_datetime < now:
            base_datetime += timedelta(hours=repeat_interval)
        
        return base_datetime.isoformat()
    
    def mark_task_completed(self, task_id):
        for task in self.task_queue:
            if task['id'] == task_id:
                task['last_run'] = datetime.now().isoformat()
                if task['repeat_interval']:
                    task['next_run'] = self.calculate_next_run(
                        task['schedule_time'], 
                        task['repeat_interval']
                    )
                break
        self.save_scheduled_tasks()
    
    def load_scheduled_tasks(self):
        if not self.schedule_file.exists():
            self.task_queue = []
            return

        try:
            with open(self.schedule_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            corrupt_copy = self.schedule_file.with_suffix(f"{self.schedule_file.suffix}.corrupt_{timestamp}")
            try:
                self.schedule_file.rename(corrupt_copy)
            except OSError:
                pass
            print(f"Invalid schedule JSON. Resetting tasks. Details: {exc}")
            self.task_queue = []
            return

        self.task_queue = data if isinstance(data, list) else []
    
    def save_scheduled_tasks(self):
        _atomic_write_json(self.schedule_file, self.task_queue)

# ==================== BACKUP MANAGER ====================
class BackupManager:
    def __init__(self, log_func, paths: AppPaths | None = None):
        self.log = log_func
        self.paths = paths or get_app_paths()
        self.backup_dir = self.paths.backup_dir
        self.backup_dir.mkdir(exist_ok=True)
    
    def create_backup(self, include_logs=True, include_content=True):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self.backup_dir / f"backup_{timestamp}.zip"
        
        try:
            with zipfile.ZipFile(backup_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Backup configurations
                config_dir = self.paths.config_dir
                if config_dir.exists():
                    for config_file in config_dir.glob("*.json"):
                        zipf.write(config_file, f"config/{config_file.name}")
                
                # Backup logs
                if include_logs:
                    log_files = list(self.paths.project_root.glob("*.log")) + list(self.paths.logs_dir.glob("*.log"))
                    for log_file in log_files:
                        if log_file.exists():
                            zipf.write(log_file, f"logs/{log_file.name}")
                
                # Backup content queue
                if include_content:
                    content_file = self.paths.content_queue_file
                    if content_file.exists():
                        zipf.write(content_file, "content/content_queue.json")
            
            self.log(f"✅ Backup created: {backup_file.name}")
            return True
            
        except Exception as e:
            self.log(f"❌ Backup failed: {e}")
            return False
    
    def list_backups(self):
        backups = list(self.backup_dir.glob("backup_*.zip"))
        return sorted(backups, reverse=True)
    
    def restore_backup(self, backup_file):
        try:
            with zipfile.ZipFile(backup_file, 'r') as zipf:
                zipf.extractall(self.paths.project_root)
            self.log(f"✅ Backup restored: {backup_file.name}")
            return True
        except Exception as e:
            self.log(f"❌ Restore failed: {e}")
            return False
    
    def cleanup_old_backups(self, keep_count=10):
        backups = self.list_backups()
        if len(backups) > keep_count:
            for backup in backups[keep_count:]:
                backup.unlink()
                self.log(f"🧹 Deleted old backup: {backup.name}")

# ==================== TASK TEMPLATES ====================
class TaskTemplates:
    TEMPLATES = {
        "morning_routine": {
            "name": "Morning Engagement",
            "tasks": [
                {"type": "scroll", "duration": 900, "intensity": "medium"},
                {"type": "reels", "max_videos": 2, "scroll_after_post": True}
            ],
            "description": "Morning engagement routine with light activity"
        },
        "evening_boost": {
            "name": "Evening Boost",
            "tasks": [
                {"type": "scroll", "duration": 1800, "intensity": "heavy"},
                {"type": "reels", "max_videos": 5, "scroll_after_post": True}
            ],
            "description": "Evening high-activity session"
        },
        "quick_session": {
            "name": "Quick Session",
            "tasks": [
                {"type": "scroll", "duration": 300, "intensity": "light"},
                {"type": "reels", "max_videos": 1, "scroll_after_post": False}
            ],
            "description": "Short quick session"
        },
        "content_day": {
            "name": "Content Day",
            "tasks": [
                {"type": "reels", "max_videos": 10, "scroll_after_post": True}
            ],
            "description": "Focus on content posting"
        }
    }
    
    @classmethod
    def get_template(cls, template_name):
        return cls.TEMPLATES.get(template_name)
    
    @classmethod
    def get_all_templates(cls):
        return cls.TEMPLATES
