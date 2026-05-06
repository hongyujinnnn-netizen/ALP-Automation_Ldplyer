from __future__ import annotations

import ctypes
import contextlib
import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox


def _is_windows_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _request_admin_and_relaunch() -> bool:
    """Require elevation on Windows; exit the current process if elevation is not granted."""
    if os.name != "nt":
        return False

    if _is_windows_admin():
        return False

    if not messagebox.askyesno(
        "Administrator Access",
        "This app requires Administrator permission to run.\n\nRun as Administrator now?",
    ):
        messagebox.showerror(
            "Administrator Required",
            "Administrator permission was not granted. The app will now close.",
        )
        raise SystemExit(1)

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
            "Administrator Required",
            "Could not start the app as Administrator. The app will now close.",
        )
        raise SystemExit(1)

    return True


def _hide_windows_console() -> None:
    """Hide the attached Windows console when launching the GUI app."""
    if os.name != "nt":
        return

    try:
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        console_hwnd = kernel32.GetConsoleWindow()
        if console_hwnd:
            SW_HIDE = 0
            user32.ShowWindow(console_hwnd, SW_HIDE)
    except Exception:
        pass


def _relaunch_in_project_venv_if_available() -> None:
    """Relaunch using local .venv Python when started from a global interpreter."""
    if getattr(sys, "frozen", False):
        return

    in_venv = sys.prefix != sys.base_prefix
    if in_venv:
        return

    project_root = Path(__file__).resolve().parents[1]
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


def _patch_uiautomator2_frozen_resources() -> None:
    """Make uiautomator2 package assets discoverable in frozen builds."""
    try:
        import uiautomator2.utils as u2_utils
    except Exception:
        return

    if getattr(u2_utils, "_alp_resource_patch_applied", False):
        return

    @contextlib.contextmanager
    def _with_package_resource(filename: str):
        try:
            from importlib.resources import as_file, files

            anchor = files("uiautomator2") / filename
            with as_file(anchor) as resource_path:
                if resource_path.exists():
                    yield resource_path
                    return
        except Exception:
            pass

        search_roots = []
        if getattr(sys, "_MEIPASS", None):
            meipass = Path(sys._MEIPASS)
            search_roots.extend(
                [
                    meipass,
                    meipass / "uiautomator2",
                    meipass / "_internal",
                    meipass / "_internal" / "uiautomator2",
                ]
            )

        binary_path = Path(sys.executable if getattr(sys, "frozen", False) else sys.argv[0]).resolve()
        search_roots.extend([binary_path.parent, Path.cwd()])

        for root in search_roots:
            candidate = root / filename
            if candidate.exists():
                yield candidate
                return

        raise FileNotFoundError(f"Resource {filename} not found in uiautomator2 package.")

    u2_utils.with_package_resource = _with_package_resource
    try:
        import uiautomator2.core as u2_core

        u2_core.with_package_resource = _with_package_resource
    except Exception:
        pass
    u2_utils._alp_resource_patch_applied = True


def main() -> None:
    _hide_windows_console()
    _relaunch_in_project_venv_if_available()
    _patch_uiautomator2_frozen_resources()

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

    # Create the main Tk root first so ttkbootstrap styles register on the
    # same root the app uses; show the splash as a Toplevel of that root.
    root = tk.Tk()
    root.withdraw()

    splash = None
    try:
        from gui.splash_screen import SplashScreen, SplashConfig

        splash = SplashScreen(SplashConfig(initial_progress=68), master=root)
        splash.show()
        splash.update_progress(75, "Loading modules...")
    except Exception:
        splash = None

    try:
        if splash is not None:
            splash.update_progress(88, "Preparing dashboard...")
        app = LDManagerApp(root)
        root.deiconify()
        if splash is not None:
            splash.update_progress(100, "Ready")
            root.after(350, splash.close)
    except Exception as exc:
        import traceback

        if splash is not None:
            try:
                splash.close()
            except Exception:
                pass
        traceback.print_exc()
        messagebox.showerror("Startup Error", str(exc))
        raise SystemExit(1)

    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
