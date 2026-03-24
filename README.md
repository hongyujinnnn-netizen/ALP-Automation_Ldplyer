# ALP Automation LDPlayer

Windows desktop control center for managing LDPlayer instances, running automation batches, scheduling work, and monitoring live device activity from a Tkinter UI.

## Status

This project currently works as a Windows-first desktop app and is being refactored incrementally toward a layered architecture:

`GUI -> Controller -> Service -> Core/Utils`

The codebase is not a full clean-slate rewrite. Some new layers are already in place, and some legacy flow still exists behind compatibility wrappers. The goal is to improve maintainability without breaking working behavior.

## What The App Does

- discovers LDPlayer instances
- starts, stops, and restarts selected emulators
- runs automation batches for `scroll` and `reels`
- manages content queue, account assignments, backups, and schedule settings
- exposes ADB tools inside the desktop UI
- shows fleet state, live task status, system metrics, and logs

## Architecture

### Current Layer Design

```text
app/
  app.py                    # real application entrypoint

gui/
  ld_manager_app.py         # main Tk shell
  pages/                    # dashboard/devices/tasks/schedule/content/logs
  dialogs/                  # settings/tools/account/perf dialogs
  mixins/                   # UI-only helpers

controllers/
  app_controller.py
  emulator_controller.py
  task_controller.py

services/
  adb_service.py
  emulator_service.py
  logging_service.py
  scheduler_service.py
  settings_service.py
  task_service.py

core/
  emulator.py
  managers.py
  models.py
  paths.py
  settings.py
  state_machine.py
  task_handlers.py

utils/
  app_utils.py
  helpers.py
  logger.py
  performance_monitor.py
  rate_limiter.py
  ...
```

### Layer Intent

- `app/`
  Startup, relaunch, and bootstrapping only.
- `gui/`
  Tkinter widgets, layouts, dialogs, visual state, and user interaction.
- `controllers/`
  Thin coordination layer between UI and services.
- `services/`
  Emulator, ADB, settings, scheduling, task-run orchestration, and logging boundaries.
- `core/`
  Shared models, paths, persistent settings, task handlers, and lower-level logic.
- `utils/`
  Reusable helpers and compatibility adapters.

## Entry Points

- `python app.py`
  Safe root shim that forwards to `app/app.py`
- `python -m app.app`
  Direct package entrypoint

Current startup behavior:

- if a local `.venv` exists and the app is launched outside it, the app relaunches inside `.venv`
- on Windows, the app can request administrator rights because some LDPlayer actions may require elevation

## Main Runtime Flow

1. `app/app.py` boots the application.
2. `gui/ld_manager_app.py` builds the main shell.
3. `controllers/*` translate UI actions into service calls.
4. `services/*` coordinate emulator, ADB, task-run, scheduler, and settings behavior.
5. `core/*` provides shared persistence and lower-level execution pieces.

## Current Important Files

- `app/app.py`
  Real application startup path.
- `app.py`
  Compatibility launcher.
- `gui/ld_manager_app.py`
  Main UI shell. Still the largest class and the main ongoing refactor target.
- `controllers/app_controller.py`
  Settings-focused UI coordination.
- `controllers/emulator_controller.py`
  Emulator-related UI coordination.
- `controllers/task_controller.py`
  Task request creation and runner delegation.
- `services/emulator_service.py`
  Emulator facade used by the UI and orchestration layer.
- `services/adb_service.py`
  Centralized ADB command execution.
- `services/task_service.py`
  Task runner creation boundary.
- `services/scheduler_service.py`
  Scheduling decision logic.
- `services/logging_service.py`
  Structured JSON logging.
- `core/emulator.py`
  Legacy emulator control implementation still used underneath the service layer.
- `core/task_handlers.py`
  Scroll and reels automation handlers.

## Project Layout Notes

Not every new module is a final implementation yet.

Examples:

- `gui/pages/emulator_page.py`, `gui/pages/task_page.py`, and `gui/pages/settings_page.py` are compatibility page aliases added to match the new structure.
- `services/task_service.py` still creates the current `MainWindow` runner rather than owning the full task engine yet.
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

## Testing

Current unit tests cover the extracted non-UI seams and selected core utilities.

Run:

```powershell
python -m unittest tests.test_core_utils tests.test_controller_services
```

Current test focus:

- settings round-trip
- structured logging
- ADB service normalization
- emulator service delegation
- scheduler decision logic
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
