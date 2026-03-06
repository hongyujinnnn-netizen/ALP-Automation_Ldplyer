import tkinter as tk
from tkinter import messagebox
import ctypes
import os
import subprocess
from pathlib import Path
import sys


def _is_windows_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _request_admin_and_relaunch() -> bool:
    if os.name != "nt":
        return False

    if _is_windows_admin():
        return False

    if getattr(sys, "frozen", False):
        executable = sys.executable
        params = subprocess.list2cmdline(sys.argv[1:])
    else:
        script_path = os.path.abspath(sys.argv[0])
        executable = sys.executable
        params = subprocess.list2cmdline([script_path, *sys.argv[1:]])

    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        executable,
        params,
        None,
        1,
    )
    if result <= 32:
        messagebox.showerror(
            "Administrator Access Required",
            "This app must be started as Administrator.",
        )
        raise SystemExit(1)

    return True


def _relaunch_in_project_venv_if_available() -> None:
    """Relaunch using local .venv Python when started from a global interpreter."""
    if getattr(sys, "frozen", False):
        return

    in_venv = sys.prefix != sys.base_prefix
    if in_venv:
        return

    # app.py lives in project root, so use its parent directory directly.
    project_root = Path(__file__).resolve().parent
    if os.name == "nt":
        venv_python = project_root / ".venv" / "Scripts" / "python.exe"
    else:
        venv_python = project_root / ".venv" / "bin" / "python"

    if not venv_python.exists():
        return

    script_path = os.path.abspath(sys.argv[0])
    args = [str(venv_python), script_path, *sys.argv[1:]]
    completed = subprocess.run(args, check=False)
    raise SystemExit(completed.returncode)


def main() -> None:
    _relaunch_in_project_venv_if_available()

    try:
        from gui.ld_manager_app import LDManagerApp
    except ModuleNotFoundError as exc:
        missing = getattr(exc, "name", "dependency")
        messagebox.showerror(
            "Missing Dependency",
            (
                f"Missing Python package: {missing}\n\n"
                "Install project dependencies, then relaunch:\n"
                "  .\\.venv\\Scripts\\python -m pip install -r requirements.txt"
            ),
        )
        raise SystemExit(1) from exc

    if _request_admin_and_relaunch():
        raise SystemExit(0)

    root = tk.Tk()
    app = LDManagerApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
