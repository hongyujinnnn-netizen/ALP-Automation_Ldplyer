"""OS-level power actions used as post-run side effects.

Kept separate from the GUI so the action can be triggered from any
driver (GUI, CLI, scheduler). Windows-only today; platform checks are
made explicit and reported via the supplied ``log`` callable.
"""

from __future__ import annotations

import platform
import subprocess
from typing import Any, Callable

LogFn = Callable[..., Any]


def schedule_pc_shutdown(log: LogFn, *, delay_seconds: int = 30) -> bool:
    """Schedule a Windows ``shutdown /s`` after ``delay_seconds``.

    Returns ``True`` if the command was dispatched, ``False`` otherwise.
    All user-visible outcomes are reported through ``log`` to preserve
    current logging behavior.
    """
    if platform.system().lower() != "windows":
        log("Auto shutdown is only supported on Windows.", "WARNING")
        return False

    try:
        subprocess.Popen(
            [
                "shutdown",
                "/s",
                "/t",
                str(delay_seconds),
                "/c",
                "ALP Automation completed all selected tasks.",
            ]
        )
    except Exception as exc:
        log(f"Failed to schedule PC shutdown: {exc}", "ERROR")
        return False

    log(
        f"Automation completed. PC shutdown scheduled in {delay_seconds} seconds."
        " Run 'shutdown /a' to cancel.",
        "WARNING",
    )
    return True
