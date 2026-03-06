# 🚀 ALP Automation LDPlayer

<div align="center">
  <img src="https://img.shields.io/badge/Python-3.13+-blue.svg" alt="Python Version">
  <img src="https://img.shields.io/badge/Windows-10%2B-blue.svg" alt="Windows Support">
  <img src="https://img.shields.io/badge/LDPlayer-9+-green.svg" alt="LDPlayer Version">
  <img src="https://img.shields.io/github/stars/hongyujinnnn-netizen/ALP-Automation_Ldplyer?style=social" alt="GitHub Stars">
  <img src="https://img.shields.io/github/license/hongyujinnnn-netizen/ALP-Automation_Ldplyer" alt="License">
</div>

<div align="center">
  <h3>🎮 Desktop Automation Control Center for LDPlayer Instances</h3>
  <p><em>Manage multiple LDPlayer emulators with ease - batch tasks, scheduling, and monitoring all in one sleek UI!</em></p>
</div>

---

## ✨ Features

<table>
  <tr>
    <td>🎯 <strong>Multi-Device Control</strong></td>
    <td>Discover, select, and control multiple LDPlayer instances from a single interface</td>
  </tr>
  <tr>
    <td>⚡ <strong>Batch Automation</strong></td>
    <td>Execute scroll/reels workflows across devices simultaneously</td>
  </tr>
  <tr>
    <td>📅 <strong>Smart Scheduling</strong></td>
    <td>Daily, weekly, or interval-based task scheduling</td>
  </tr>
  <tr>
    <td>📋 <strong>Content Queue</strong></td>
    <td>Manage content with JSON persistence and queue management</td>
  </tr>
  <tr>
    <td>👤 <strong>Account Mapping</strong></td>
    <td>Assign accounts to specific devices for organized automation</td>
  </tr>
  <tr>
    <td>💾 <strong>Backup & Restore</strong></td>
    <td>Create and restore project backups with ease</td>
  </tr>
  <tr>
    <td>🔄 <strong>Auto Relaunch</strong></td>
    <td>Automatic relaunch into virtual environment when available</td>
  </tr>
  <tr>
    <td>🛡️ <strong>Admin Elevation</strong></td>
    <td>Automatic admin prompt for Windows LDPlayer actions</td>
  </tr>
</table>

## 🏗️ Tech Stack

<div align="center">
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Tkinter-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Tkinter">
  <img src="https://img.shields.io/badge/ADB-3DDC84?style=for-the-badge&logo=android&logoColor=white" alt="ADB">
  <img src="https://img.shields.io/badge/LDPlayer-FF6B35?style=for-the-badge" alt="LDPlayer">
</div>

- **🐍 Python 3.13+** - Core language
- **🖥️ Tkinter + ttkbootstrap** - Modern GUI framework
- **📱 ADB + LDPlayer** - Android device/emulator control
- **🤖 uiautomator2** - UI automation for tasks
- **⚙️ psutil** - System and process utilities

## 📁 Project Structure

```
ALP-v1.0.0/
├── 📄 app.py                     # 🚀 Main entrypoint with venv relaunch & admin elevation
├── 🔧 core/
│   ├── emulator.py              # 🎮 LDPlayer/ADB control & readiness checks
│   ├── task_handlers.py         # ⚙️ Automation task handlers
│   ├── managers.py              # 👥 Account, queue, scheduler, backup management
│   ├── paths.py                 # 🗂️ Centralized runtime paths
│   └── settings.py              # ⚙️ Typed settings load/save
├── 🎨 gui/
│   ├── ld_manager_app.py        # 🏠 Main application window
│   ├── main_window.py           # 🎭 Batch stage orchestration
│   └── components/              # 🧩 UI components
├── ⚙️ config/                   # 📋 Persisted JSON settings & data
├── 📦 content/                  # 🎬 Content assets
├── 📝 logs/                     # 📊 Runtime logs
└── 💾 backups/                  # 📦 Generated backups
```

## 🚀 Quick Start

### Prerequisites
- 🪟 **Windows 10+**
- 🎮 **LDPlayer 9+** installed at `C:\LDPlayer\LDPlayer9`
- 📱 **ADB** (comes with LDPlayer or system ADB)
- 🐍 **Python 3.13+**

### Installation

```powershell
# 1️⃣ Navigate to project directory
cd D:\Application\ALP-v1.0.0

# 2️⃣ Create virtual environment
python -m venv .venv

# 3️⃣ Activate and install dependencies
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### Usage

```powershell
# 🚀 Launch the application
python app.py
```

> 💡 **Pro Tip**: The app automatically relaunches into `.venv` and prompts for admin permissions when needed!

## ⚙️ Configuration

| File | Purpose |
|------|---------|
| `config/setting.json` | 🎛️ Main app preferences |
| `config/setting_schedule.json` | 📅 Schedule settings |
| `config/accounts.json` | 👤 Device-account mapping |
| `config/content_queue.json` | 📋 Queued content metadata |
| `config/scheduled_tasks.json` | ⏰ Saved scheduled tasks |

## 🔧 Troubleshooting

### 🐛 Module Not Found Error
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 🎮 LDPlayer Not Detected
- ✅ Verify LDPlayer path in `core/emulator.py`
- ✅ Confirm `dnconsole.exe` exists
- ✅ Start LDPlayer manually first

### 📱 ADB Issues
```powershell
# Restart ADB server
adb kill-server
adb start-server

# Check connected devices
adb devices
```

## 📊 Screenshots

*Add screenshots here to showcase your awesome UI!*

## 🤝 Contributing

1. 🍴 Fork the repository
2. 🌿 Create a feature branch (`git checkout -b feature/amazing-feature`)
3. 💾 Commit changes (`git commit -m 'Add amazing feature'`)
4. 🚀 Push to branch (`git push origin feature/amazing-feature`)
5. 🔄 Open a Pull Request

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 👨‍💻 Author

**Bunhong**  
[![GitHub](https://img.shields.io/badge/GitHub-100000?style=for-the-badge&logo=github&logoColor=white)](https://github.com/hongyujinnnn-netizen)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-0077B5?style=for-the-badge&logo=linkedin&logoColor=white)](https://linkedin.com/in/bunhong)

---

<div align="center">
  <p>⭐ Star this repo if you found it helpful!</p>
  <p>Made with ❤️ for the automation community</p>
</div>
