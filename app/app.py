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
    """Try to elevate; if the user declines, keep running without admin instead of quitting."""
    if os.name != "nt":
        return False

    if _is_windows_admin():
        return False

    if not messagebox.askyesno(
        "Administrator Access",
        "Some LDPlayer controls may need admin permissions.\n\n"
        "Run as Administrator now?",
    ):
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
        messagebox.showwarning(
            "Continue Without Admin",
            "Could not elevate. Continuing without admin rights.",
        )
        return False

    return True


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

    root = tk.Tk()
    try:
        app = LDManagerApp(root)
    except Exception as exc:
        import traceback

        traceback.print_exc()
        messagebox.showerror("Startup Error", str(exc))
        raise SystemExit(1)

    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
