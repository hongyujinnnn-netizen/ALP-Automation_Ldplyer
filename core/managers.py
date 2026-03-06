import json
import time
from datetime import datetime, timedelta
from pathlib import Path
import zipfile
import os
from core.paths import get_app_paths, AppPaths

# ==================== ACCOUNT MANAGER ====================
class AccountManager:
    def __init__(self, paths: AppPaths | None = None):
        self.paths = paths or get_app_paths()
        self.accounts_file = self.paths.accounts_file
        self.accounts = self.load_accounts()
    
    def load_accounts(self):
        if self.accounts_file.exists():
            with open(self.accounts_file, 'r') as f:
                return json.load(f)
        return {}
    
    def assign_account_to_device(self, device_name, account_data):
        self.accounts[device_name] = {
            **account_data,
            'assigned_date': datetime.now().isoformat(),
            'last_used': datetime.now().isoformat()
        }
        self.save_accounts()
    
    def get_device_account(self, device_name):
        account = self.accounts.get(device_name, {})
        if account:
            account['last_used'] = datetime.now().isoformat()
            self.save_accounts()
        return account
    
    def remove_account(self, device_name):
        if device_name in self.accounts:
            del self.accounts[device_name]
            self.save_accounts()
    
    def save_accounts(self):
        self.accounts_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.accounts_file, 'w') as f:
            json.dump(self.accounts, f, indent=4, ensure_ascii=False)
    
    def get_all_accounts(self):
        return self.accounts

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
        self.content_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.content_file, 'w') as f:
            json.dump(self.video_queue, f, indent=4, ensure_ascii=False)

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
        if self.schedule_file.exists():
            with open(self.schedule_file, 'r') as f:
                self.task_queue = json.load(f)
        else:
            self.task_queue = []
    
    def save_scheduled_tasks(self):
        self.schedule_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.schedule_file, 'w') as f:
            json.dump(self.task_queue, f, indent=4)

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
