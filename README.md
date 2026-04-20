# 🚀 ALP Automation LDPlayer

> **Professional Windows Desktop Control Center for Android Emulator Automation**

A feature-rich Tkinter + ttkbootstrap desktop application for managing LDPlayer Android emulator instances at scale. Automate repetitive tasks across multiple devices, orchestrate complex workflows, monitor system health in real-time, and manage device scheduling with precision.

**Perfect for:** Automation engineers, QA teams, content creators, and operations teams managing fleet-wide Android device automation.

---

## ✨ Key Features

### 🎛️ Fleet Management
- **Instance Discovery** — Automatically detect and list available LDPlayer instances
- **Batch Control** — Start, stop, and restart multiple emulators simultaneously
- **Device Monitoring** — Real-time status tracking and live activity feeds for all devices
- **Account Assignment** — Assign and manage multiple accounts across emulator instances
- **ADB Integration** — Direct ADB tool access within the UI for advanced debugging

### 🤖 Automation Capabilities
- **Scroll Automation** — Automated feed scrolling with configurable duration and timing
- **Reels Automation** — Video content interaction automation
- **Account Registration** — Automated account registration workflow
- **Task Templates** — Reusable automation templates with batch execution
- **Content Queue** — Manage content assignments and task batching
- **Crash Recovery** — Auto-restart on crash with configurable recovery strategies

### 📅 Intelligent Scheduling
- **Time Window Scheduling** — Define automation run windows (start/stop times)
- **Weekly Patterns** — Configure daily or custom weekly automation patterns
- **Smart Throttling** — Prevent resource overload with intelligent device sequencing
- **Next-Run Preview** — See scheduled automation timeline at a glance
- **Pause & Resume** — Manually override scheduled automation when needed

### 🔐 Security & OTP
- **Email OTP Integration** — Automated IMAP mailbox monitoring for OTP codes
- **Multi-Mailbox Support** — Connect to multiple owned or authorized email accounts
- **OTP Polling** — Intelligent polling system for time-sensitive OTP retrieval
- **Account Authorization** — Manage access control for mailbox connections

### 📊 Operations Dashboard
- **Live Metrics** — Real-time KPI cards showing fleet health
- **Alert System** — Critical, warning, and info alerts for anomalies
- **Performance Monitoring** — CPU, RAM, disk, and temperature tracking
- **Activity Feed** — Live device status and current task information
- **Health Distribution** — Visual breakdown of device states (running, active, failed, etc.)
- **Recent Events** — High-signal event summary from structured logs

### 📋 Comprehensive Logging
- **Structured Logging** — JSON-formatted logs with timestamps and severity
- **Live Log Panel** — Color-coded event streaming in real-time
- **Log Export** — Backup and export automation session logs
- **Event Search** — Find and filter important events by level and timestamp

---

## 🏗️ Architecture

This project follows a **layered, service-oriented architecture** for maintainability and testability:

```
┌─────────────────────────────────────────┐
│         GUI Layer (Tkinter UI)          │  ← User interaction, visual state
├─────────────────────────────────────────┤
│      Controllers (Coordination)          │  ← UI logic, request handling
├─────────────────────────────────────────┤
│       Services (Business Logic)          │  ← Emulator, task, scheduler,
│                                         │     settings, logging, OTP
├─────────────────────────────────────────┤
│    Core (Models, State, Handlers)       │  ← Task runners, email, models,
│                                         │     persistence, emulator control
├─────────────────────────────────────────┤
│        Utils (Helpers, Adapters)        │  ← Shared utilities, helpers
└─────────────────────────────────────────┘
```

### Layer Breakdown

#### **GUI Layer** (`gui/`)
- `ld_manager_app.py` — Main application shell and frame orchestration
- `pages/` — Tab-based page components (dashboard, devices, tasks, schedule, logs)
- `dialogs/` — Modal dialogs for settings, tools, OTP config, and account management
- `components/` — Reusable UI widgets (cards, trees, progress bars)
- `mixins/` — UI-only helper mixins for organization
- `styles.py` — ttkbootstrap theme configuration and custom styles
- `sidebar.py`, `topbar.py`, `status_bar.py` — Main window chrome

#### **Controllers** (`controllers/`)
Thin coordination layer between UI and services:
- `app_controller.py` — Settings persistence, app-wide configuration
- `emulator_controller.py` — Emulator state changes and discovery
- `otp_controller.py` — Email OTP setup, validation, and test actions
- `task_controller.py` — Task creation, batching, and runner delegation

#### **Services** (`services/`)
Business logic and orchestration boundaries:
- `emulator_service.py` — High-level emulator operations (start, stop, status)
- `adb_service.py` — Centralized ADB command execution with connection pooling
- `task_service.py` — Task runner creation and automation delegation
- `scheduler_service.py` — Scheduling decision logic and time window management
- `otp_service.py` — OTP polling, email integration, code extraction
- `email_service.py` — IMAP mailbox access, message search, fetch, cleanup
- `settings_service.py` — Settings persistence and validation
- `logging_service.py` — Structured JSON logging to file and UI

#### **Core** (`core/`)
Shared models, state machines, and lower-level logic:
- `models.py` — Data models (Account, Device, Task, etc.)
- `settings.py` — AppSettings and ScheduleSettings configuration objects
- `managers.py` — AccountManager, ContentManager, BackupManager, SmartScheduler
- `task_handlers.py` — Scroll and reels automation implementation
- `emulator.py` — Low-level LDPlayer/ADB control (legacy compatibility)
- `state_machine.py` — Device state transition logic
- `email_models.py` — Email and OTP-related models
- `otp_parser.py` — OTP code extraction from email content
- `paths.py` — Application path resolution and directory management
- `reg_account.py` — Account registration workflow handlers

#### **Utils** (`utils/`)
Reusable helpers and adapters:
- `performance_monitor.py` — Host system metrics (CPU, RAM, disk, temp)
- `logger.py` — Logging configuration and helpers
- `app_utils.py` — General-purpose application utilities
- `rate_limiter.py` — Request throttling and rate limiting
- `ip_guard.py` — IP-based access control validation
- `helpers.py` — Miscellaneous helper functions

---

## 🚀 Quick Start

### System Requirements
- **OS:** Windows 7 or later
- **Python:** 3.9+
- **LDPlayer:** Latest version with ADB enabled
- **RAM:** 8GB minimum (more recommended for large fleets)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/hongyujinnnn-netizen/ALP-Automation_Ldplyer.git
   cd ALP-Automation_Ldplyer
   ```

2. **Create virtual environment (recommended):**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application:**
   ```bash
   python app.py
   ```

   Or directly:
   ```bash
   python -m app.app
   ```

### First-Time Setup

1. **Admin Elevation** — Application will request administrator rights on Windows (required for emulator control)
2. **Emulator Discovery** — Application auto-discovers connected LDPlayer instances
3. **ADB Configuration** — Verify ADB connectivity from Tools menu
4. **Settings** — Configure schedule, OTP, and automation preferences

---

## 📖 Usage Guide

### Dashboard Operations

**View Fleet Overview:**
- KPI cards show total devices, running, active, offline, and error counts
- Alert section flags critical issues needing attention
- Fleet health distribution shows device state breakdown
- Live activity feed shows current task for each device

**Manage Automation:**
1. Select devices from the device table or use sidebar groups
2. Choose automation task type (Scroll, Reels, Register Account, etc.)
3. Configure batch size, timing, and crash recovery
4. Click **Run Automation** to start

### Scheduling

**Configure Schedule:**
1. Go to **Schedule** tab or dashboard Schedule panel
2. Set start time and stop time
3. Select active days (M, T, W, T, F, S, S)
4. Toggle **Enabled** to activate scheduling
5. Automation will run within configured windows

### Email OTP Configuration

**Add Mailbox:**
1. Go to **Settings → Email OTP**
2. Click **Add Mailbox**
3. Enter IMAP server details (Gmail: `imap.gmail.com`, port 993)
4. Enter email and app-specific password
5. Click **Test** to verify connection
6. Save configuration

### Device Management

**Emulator Table:**
- View all instances with status, assigned account, and queue position
- Select devices for batch operations
- Right-click for context menu (restart, logs, etc.)
- Drag-select for multiple selection

**Batch Operations:**
- **Start Selected** — Boot selected emulators
- **Stop Selected** — Gracefully shut down selected instances
- **Restart Selected** — Reboot selected devices

---

## 📊 Dashboard Overview

### KPI Section
| Metric | Purpose |
|--------|---------|
| **Total Devices** | Fleet size |
| **Running** | Active emulator instances |
| **Active** | Devices executing tasks |
| **Offline** | Disconnected or unresponsive devices |
| **Failures** | Tasks with errors |

### Alerts
- 🔴 **Critical** — ADB disconnection, stuck OTP, device offline
- 🟡 **Warning** — Empty queue, schedule disabled, repeated failures
- 🟢 **Info** — Next run time, schedule active

### Fleet Health
Visual distribution of device states:
- Running, Active, Inactive, Paused, Completed, Failed

### Live Activity
Current task information for active devices:
```
LD-1     → Posting reel [45% ▓▓▓▒]
LD-2     → Waiting OTP [pending]
LD-3     → Scroll feed [15 min]
LD-4     → Completed [100% ✓]
```

---

## 🔧 Configuration Files

Configuration stored in `config/` directory:

| File | Purpose |
|------|---------|
| `setting.json` | Main app settings (schedule, delays, batch size) |
| `setting_schedule.json` | Schedule configuration (times, days) |
| `created_accounts.json` | Device ↔ Account mappings |
| `test_settings_roundtrip.json` | Settings validation cache |

---

## 📝 Logging

Logs are stored in `logs/` directory:

- `app.jsonl` — Structured JSON log (all events, machine-readable)
- `facebook_pages_*.xml` — Detected pages from automation runs
- **Live Log Panel** — Color-coded event stream within UI

View full logs in the **Logs** tab with search and filter capabilities.

---

## 🛠️ Advanced Features

### Performance Monitoring
System health metrics continuously tracked:
- CPU usage with gradient visualization
- RAM consumption and allocation
- Disk I/O and available space
- Temperature monitoring

### Content Queue Management
- Import content lists (URLs, captions, media)
- Assign content to automation batches
- Track queue consumption per device
- Backup and restore queue snapshots

### Backup & Restore
- Backup app configuration and device state
- Restore previous settings/state snapshots
- Automatic backup before major operations

### ADB Tools
Access advanced debugging from **Tools → ADB Console**:
- Direct ADB command execution
- Device shell access
- Logcat streaming
- File push/pull

---

## 🏢 Project Status

**Refactor Status:** In-progress toward clean layered architecture

This project is actively being refactored to improve maintainability:
- ✅ GUI layer — Well-structured with mixins
- ✅ Controller layer — In place with service delegation
- ✅ Service layer — Core services stable
- 🔄 Core layer — Incrementally improving models and abstractions
- 📝 Ongoing — Reduce MainWindow complexity, improve testability

The application is production-ready with some legacy compatibility paths maintained during refactor. New code follows the service-oriented pattern.

---

## 📦 Dependencies

```
psutil              # System monitoring (CPU, RAM, disk, temp)
ttkbootstrap        # Modern Tkinter theme framework
uiautomator2        # Android UIAutomator for automation
```

See `requirements.txt` for complete dependency list with versions.

---

## 🤝 Contributing

Contributions welcome! Areas of focus:

- Refactoring `ld_manager_app.py` into smaller, focused components
- Adding new automation task types
- Improving OTP reliability
- Performance optimizations
- Testing infrastructure
- Documentation

Please follow the layered architecture pattern when adding new features.

---

## 📄 License

[Specify your license here]

---

## 📞 Support

**Issues & Bugs:** Open an issue with:
- Python version
- Windows version
- Error logs from `logs/app.jsonl`
- Steps to reproduce

**Feature Requests:** Describe use case and expected behavior

---

## 🎯 Roadmap

### Short Term
- [ ] Dashboard redesign with professional KPI cards and alerts
- [ ] Improved error recovery mechanisms
- [ ] Device health scoring system

### Medium Term
- [ ] REST API for remote control
- [ ] Web dashboard for monitoring
- [ ] Task template marketplace
- [ ] Advanced reporting and analytics

### Long Term
- [ ] Cross-platform support (macOS, Linux)
- [ ] Distributed architecture for multi-machine fleets
- [ ] Machine learning-based optimization
- [ ] Integration with external analytics platforms

---

**Last Updated:** April 2026  
**Current Version:** 1.0.0-refactor  
**Maintainer:** hongyujinnnn-netizen
- `services/scheduler_service.py` currently owns schedule decision logic, not the entire scheduling thread lifecycle.

This is intentional. The refactor is being done step by step to preserve behavior.

## Requirements

- Windows 10 or newer
- Python 3.13 or newer
- LDPlayer 9 installed locally
- ADB available either from LDPlayer or system PATH

Default LDPlayer install path currently assumed by the emulator layer:

```text
C:\LDPlayer\LDPlayer9
```

## Installation

```powershell
cd D:\Application\ALP-Automation_Ldplyer
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Run

```powershell
python app.py
```

## First Run Checklist

1. Install LDPlayer and open it once manually.
2. Confirm `dnconsole.exe` exists under `C:\LDPlayer\LDPlayer9`.
3. Confirm `adb devices` works in a terminal.
4. Launch the app with `python app.py`.
5. Open `Tools Center > ADB Console` and test `adb devices`.

## UI Areas

- `Dashboard`
  Fleet overview, emulator table, live logs, system health, and task configuration.
- `Devices`
  Live per-device runtime status and waiting queue.
- `Tasks`
  Task configuration and automation controls.
- `Schedule`
  Scheduled automation configuration.
- `Content`
  Content queue management.
- `Logs`
  Runtime log viewer.
- `Tools Center`
  Diagnostics, quick actions, and ADB console.
- `Settings`
  Configuration dialog and profile controls.

## Configuration And Data

Runtime files are stored under:

- `config/`
  persisted settings and queue/schedule/account JSON files
- `content/`
  content assets and queue-related files
- `logs/`
  runtime log output including structured logs
- `backups/`
  backup archives

Path definitions are centralized in `core/paths.py`.

Important config files:

- `config/setting.json`
- `config/setting_schedule.json`
- `config/created_accounts.json`
- `config/content_queue.json`
- `config/scheduled_tasks.json`

## Logging

The project now uses structured Python logging through `services/logging_service.py`.

Current log behavior:

- UI log panels still show readable operator logs
- structured JSON log records are written to `logs/app.jsonl`
- email OTP actions emit structured events such as `email.connect.started`, `otp.poll.match_found`, and `otp.timeout`

## Email OTP Reader

This project now includes a generic email OTP reader for authorized mailbox access only.

What it does:

- connects to an IMAP inbox using app-password-based login
- supports Yandex first with `imap.yandex.com:993` over SSL/TLS
- polls for matching emails using optional unread, sender, and subject filters
- reads both `text/plain` and `text/html` messages
- extracts OTP codes through centralized parsing logic in `core/otp_parser.py`
- returns structured success and error results through the controller and service layers

Configuration fields:

- provider
- email address
- app password
- IMAP server
- port
- mailbox
- unread only
- sender filter
- subject filter
- timeout seconds
- poll interval seconds
- mark matched email as seen

How to test connection:

1. Open `Settings`.
2. Go to `Email OTP`.
3. Enter the mailbox configuration for an inbox you own or are explicitly authorized to access.
4. Click `Test Connection`.

How to fetch OTP:

1. Save the email settings.
2. Use `Test OTP Fetch` to scan the current mailbox once.
3. Use `Wait For OTP` to poll until a matching email arrives or the timeout expires.

Yandex example setup:

- Provider: `yandex`
- Email Address: `your_mailbox@yandex.com`
- App Password: use a Yandex app password, not the primary account password
- IMAP Server: `imap.yandex.com`
- Port: `993`
- Mailbox: `INBOX`
- Use SSL/TLS: enabled

Safety note:

- this feature is intended for generic OTP retrieval from mailboxes you own or are explicitly authorized to access
- it is not designed for stealth behavior, abuse workflows, or platform-evasion tactics

## Testing

Current unit tests cover the extracted non-UI seams and selected core utilities.

Run:

```powershell
python -m unittest tests.test_core_utils tests.test_controller_services tests.test_email_otp
```

Current test focus:

- settings round-trip
- structured logging
- ADB service normalization
- emulator service delegation
- scheduler decision logic
- OTP parsing and HTML fallback
- OTP filter matching and timeout flow
- new layer importability

## Known Design Debt

- `gui/ld_manager_app.py` is still too large
- `gui/main_window.py` still owns part of task execution flow
- `core/task_handlers.py` still contains direct execution-heavy behavior
- `core/managers.py` still groups multiple unrelated responsibilities
- some configuration is still partly hardcoded and needs further centralization

## Recommended Next Refactor Steps

1. Move `MainWindow` orchestration into `services/task_service.py`
2. Split `core/managers.py` into separate service-focused modules
3. Move remaining schedule thread ownership out of `LDManagerApp`
4. Introduce richer models in `core/models.py` and reduce dict-heavy runtime state
5. Add more unit tests around task requests, scheduler transitions, and emulator workflows

## Troubleshooting

### LDPlayer not detected

- confirm `C:\LDPlayer\LDPlayer9\dnconsole.exe` exists
- run LDPlayer manually once
- try launching the app with admin rights

### ADB errors

Use the in-app ADB console or a terminal:

```powershell
adb kill-server
adb start-server
adb devices
```

### Missing Python package on startup

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Corrupt JSON settings or queue files

- inspect `config/`
- restore a backup from `backups/`
- or remove the broken file and let the app recreate defaults where supported

## Notes

- This is a local desktop automation tool intended for a Windows + LDPlayer environment.
- The refactor is incremental by design.
- The README reflects the current structure after the recent layer split.
