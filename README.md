# ALP Automation LDPlayer

Windows desktop control center for managing multiple LDPlayer instances, running automation batches, scheduling tasks, handling content queues, and monitoring live device activity from a single Tkinter UI.

## Overview

This project is a local GUI application for LDPlayer-based Android automation. It focuses on:

- discovering and controlling LDPlayer emulators through `dnconsole.exe` and `adb`
- launching batch automation for `scroll` and `reels` workflows
- tracking selected devices, queued devices, and live device task state
- managing accounts, content queue items, scheduled tasks, and backups
- giving operators a modern dashboard with diagnostics, settings, and tools dialogs

The app is designed for Windows and assumes LDPlayer is installed locally.

## Current UI Areas

- `Dashboard`
  Fleet overview, emulator table, task configuration, system health, live logs.
- `Devices`
  Live operations page showing each LD's current task, runtime, queue position, and selected waiting devices.
- `Tasks`
  Task settings and automation controls.
- `Scheduler`
  Scheduled automation configuration.
- `Content`
  Content queue and related content management.
- `Logs`
  Runtime log viewer.
- `Tools Center`
  Quick actions, diagnostics, and ADB console.
- `Settings`
  Menu-based configuration dialog for launch, behavior, profiles, and summary.

## Features

- Multi-instance LDPlayer management
- Batch start, stop, restart, and automation execution
- ADB tools console inside the app
- Reels and scroll task orchestration
- Live device runtime tracking during automation
- Schedule persistence with repeat support
- Content queue persistence
- Account mapping dialog
- Backup, restore, and backup cleanup actions
- Performance and system diagnostics panels
- Automatic relaunch into local `.venv` when available
- Optional Windows admin elevation prompt at startup

## Requirements

- Windows 10 or newer
- Python 3.13 or newer
- LDPlayer 9 installed locally
- ADB available either from LDPlayer or system PATH

Default LDPlayer path used by the app:

```text
C:\LDPlayer\LDPlayer9
```

If your LDPlayer installation is somewhere else, update the path in [core/emulator.py](/d:/Application/Tools/ALP-Automation_Ldplyer/core/emulator.py).

## Python Dependencies

From [requirements.txt](/d:/Application/Tools/ALP-Automation_Ldplyer/requirements.txt):

- `psutil`
- `ttkbootstrap`
- `uiautomator2`

## Installation

```powershell
cd D:\Application\Tools\ALP-Automation_Ldplyer
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Running the App

```powershell
python app.py
```

Startup behavior:

- if you are not already inside the project virtual environment, `app.py` relaunches itself with `.venv\Scripts\python.exe`
- on Windows, the app can ask for administrator rights because some LDPlayer actions may need elevation

## First Run Checklist

1. Install and open LDPlayer at least once.
2. Confirm `dnconsole.exe` exists under `C:\LDPlayer\LDPlayer9`.
3. Run `adb devices` from a terminal and confirm ADB is available.
4. Launch the app with `python app.py`.
5. Open `Tools Center > ADB Console` and test a simple command such as `adb devices`.

## Typical Workflow

1. Open the app and verify emulators appear in the fleet table.
2. Select the LD instances you want to use.
3. Choose a task type in the dashboard or tasks page.
4. Adjust launch settings in the settings dialog if needed.
5. Start automation.
6. Watch the `Devices` page for:
   - what task each LD is running
   - how long the task has been running
   - which selected LDs are still waiting for work

## Project Structure

```text
ALP-Automation_Ldplyer/
|-- app.py
|-- requirements.txt
|-- README.md
|-- core/
|   |-- emulator.py
|   |-- managers.py
|   |-- paths.py
|   |-- settings.py
|   `-- task_handlers.py
|-- gui/
|   |-- ld_manager_app.py
|   |-- main_window.py
|   |-- sidebar.py
|   |-- topbar.py
|   |-- status_bar.py
|   |-- menu_bar.py
|   |-- styles.py
|   |-- gradient_progress.py
|   |-- checkbox_treeview.py
|   |-- dialogs/
|   |   |-- account_dialog.py
|   |   |-- perf_dialog.py
|   |   |-- settings_dialog.py
|   |   `-- tools_dialog.py
|   `-- pages/
|       |-- dashboard_page.py
|       |-- devices_page.py
|       |-- tasks_page.py
|       |-- schedule_page.py
|       |-- content_page.py
|       `-- logs_page.py
|-- utils/
|   |-- activity_randomizer.py
|   |-- app_utils.py
|   |-- error_handler.py
|   |-- performance_monitor.py
|   |-- rate_limiter.py
|   `-- toast.py
|-- config/
|-- content/
|-- logs/
`-- backups/
```

## Important Files

- [app.py](/d:/Application/Tools/ALP-Automation_Ldplyer/app.py)
  Entry point, `.venv` relaunch logic, Windows admin elevation prompt.
- [gui/ld_manager_app.py](/d:/Application/Tools/ALP-Automation_Ldplyer/gui/ld_manager_app.py)
  Main application shell and UI orchestration.
- [gui/main_window.py](/d:/Application/Tools/ALP-Automation_Ldplyer/gui/main_window.py)
  Batch stage execution for selected LDs.
- [gui/pages/devices_page.py](/d:/Application/Tools/ALP-Automation_Ldplyer/gui/pages/devices_page.py)
  Live device operations view.
- [core/emulator.py](/d:/Application/Tools/ALP-Automation_Ldplyer/core/emulator.py)
  LDPlayer control, emulator discovery, ADB execution, readiness checks.
- [core/task_handlers.py](/d:/Application/Tools/ALP-Automation_Ldplyer/core/task_handlers.py)
  Scroll and reels automation handlers.
- [core/managers.py](/d:/Application/Tools/ALP-Automation_Ldplyer/core/managers.py)
  Accounts, content queue, scheduler, and backup managers.

## Configuration Files

Managed under [config/](/d:/Application/Tools/ALP-Automation_Ldplyer/config):

- `setting.json`
  Main app settings such as parallel LD count, boot delay, task duration, max reels, and behavior flags.
- `setting_schedule.json`
  Scheduler settings.
- `accounts.json`
  Account mapping data.
- `content_queue.json`
  Queue items for content-driven tasks.
- `scheduled_tasks.json`
  Saved scheduled tasks.

Path definitions are centralized in [core/paths.py](/d:/Application/Tools/ALP-Automation_Ldplyer/core/paths.py).

## Testing

The repository currently includes utility-level tests in [tests/test_core_utils.py](/d:/Application/Tools/ALP-Automation_Ldplyer/tests/test_core_utils.py).

Run them with:

```powershell
python -m unittest tests\test_core_utils.py
```

## ADB and LDPlayer Notes

- The app tries to detect emulators using `dnconsole.exe list2`.
- If detection fails, it can fall back to test emulator entries.
- ADB is checked during emulator controller startup.
- The Tools Center ADB console now routes commands through the emulator backend.

Useful manual commands:

```powershell
adb devices
adb kill-server
adb start-server
```

## Troubleshooting

### LDPlayer not detected

- confirm `C:\LDPlayer\LDPlayer9\dnconsole.exe` exists
- run LDPlayer manually once
- check whether Windows elevation is required

### ADB command errors

- open `Tools Center > ADB Console`
- try `adb devices`
- restart the ADB server if needed

```powershell
adb kill-server
adb start-server
adb devices
```

### Missing Python package at startup

Install dependencies into the project virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Settings, queue, or schedule JSON corruption

The project uses atomic JSON writes where possible, but if a file becomes invalid:

- inspect the matching file in `config/`
- restore from a backup in `backups/`
- or delete the broken file and let the app recreate defaults where supported

## Known Limitations

- The project is Windows-first.
- LDPlayer path is currently hardcoded in the emulator controller.
- A number of automation outcomes depend on UI timing and device readiness.
- Some UI areas are more mature than others; this is still an actively evolving desktop tool.

## Development Notes

- Prefer running with the local `.venv`.
- The GUI is built with Tkinter plus `ttkbootstrap`.
- Runtime data directories are created automatically through [core/paths.py](/d:/Application/Tools/ALP-Automation_Ldplyer/core/paths.py).

## Author

Bunhong

