"""
core/ld_recovery.py
Detect and recover from LDPlayer / VirtualBox boot failures — most notably
the ``uCountStat < 100`` STAM assertion that wedges instances after long
runs or VBox upgrades.

Strategy:
  1. Scrape per-instance VBox.log for known assertion / abort signatures.
  2. Hard-quit the LD via dnconsole, kill orphaned VBoxHeadless / dnplayer
     processes that belong to that instance, and relaunch.
  3. If multiple instances are wedged at once, the caller may invoke
     ``kill_global_vboxsvc`` as a last-resort — that affects every running
     instance, so it is opt-in.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

# ── Known wedging signatures ─────────────────────────────────────────── #
# Substrings (case-insensitive) — match anywhere in the VBox log line.
ASSERTION_SIGNATURES = (
    "ucountstat",  # STAM counter overflow — the headline error
    "assertmsgfailed",  # generic VBox assertion
    "guru meditation",  # VBox VM gone toxic
    "verr_nem_",  # Hyper-V / NEM conflict
    "machinestate: aborted",
    "fatal error",
)

# Substrings that imply the *instance* is fine but the GLOBAL VBox broker
# is wedged — caller should consider the nuclear path.
GLOBAL_SIGNATURES = (
    "vboxsvc",
    "out of memory",
)


@dataclass
class HealthIssue:
    """A single signal scraped from a VBox log."""

    signature: str
    line: str
    log_path: str
    is_global: bool = False


@dataclass
class RecoveryResult:
    name: str
    recovered: bool = False
    attempts: int = 0
    issues: List[HealthIssue] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def __bool__(self):
        return self.recovered


# ── Log scraping ────────────────────────────────────────────────────── #


def _instance_log_dir(ld_dir: str, index: int) -> str:
    """LDPlayer 9 stores per-instance VBox logs under vms/leidian{N}/Logs."""
    return os.path.join(ld_dir, "vms", f"leidian{index}", "Logs")


def _candidate_log_paths(ld_dir: str, index: int) -> List[str]:
    log_dir = _instance_log_dir(ld_dir, index)
    if not os.path.isdir(log_dir):
        return []
    candidates = []
    for fname in ("VBox.log", "VBox.log.1", "VBox.log.2"):
        path = os.path.join(log_dir, fname)
        if os.path.exists(path):
            candidates.append(path)
    return candidates


def scan_vbox_log(
    ld_dir: str,
    index: int,
    *,
    tail_bytes: int = 200_000,
) -> List[HealthIssue]:
    """Scrape the per-instance VBox.log for known wedging signatures.

    Reads only the tail of each log (default ~200 KB) — enough to catch the
    last few minutes of activity, cheap on huge logs.
    """
    issues: List[HealthIssue] = []
    for path in _candidate_log_paths(ld_dir, index):
        try:
            size = os.path.getsize(path)
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                if size > tail_bytes:
                    f.seek(size - tail_bytes)
                tail = f.read()
        except Exception:
            continue
        lower = tail.lower()
        for sig in ASSERTION_SIGNATURES:
            if sig in lower:
                # Pull the offending line for the log surface.
                for line in tail.splitlines():
                    if sig in line.lower():
                        issues.append(HealthIssue(sig, line.strip(), path, is_global=False))
                        break
        for sig in GLOBAL_SIGNATURES:
            if sig in lower:
                for line in tail.splitlines():
                    if sig in line.lower():
                        issues.append(HealthIssue(sig, line.strip(), path, is_global=True))
                        break
    return issues


def scan_dnconsole_output(text: str) -> List[HealthIssue]:
    """Spot the same signatures in dnconsole stdout/stderr."""
    issues = []
    if not text:
        return issues
    lower = text.lower()
    for sig in ASSERTION_SIGNATURES + GLOBAL_SIGNATURES:
        if sig in lower:
            for line in text.splitlines():
                if sig in line.lower():
                    issues.append(HealthIssue(sig, line.strip(), "<dnconsole>", sig in GLOBAL_SIGNATURES))
                    break
    return issues


# ── Process surgery ─────────────────────────────────────────────────── #


def _run(cmd, timeout=10):
    """Quiet subprocess.run that swallows non-zero exits."""
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
        )
    except Exception:
        return None


def _wmic_pids_for(image_name: str, cmdline_match: str) -> List[int]:
    """Return PIDs of <image_name> whose command line contains <cmdline_match>.

    Uses WMIC because it ships with every Windows. Falls back to empty list
    on failure — recovery never *requires* this to succeed.
    """
    proc = _run(
        [
            "wmic",
            "process",
            "where",
            f"name='{image_name}'",
            "get",
            "ProcessId,CommandLine",
            "/format:csv",
        ],
        timeout=15,
    )
    if not proc or proc.returncode != 0:
        return []
    pids = []
    needle = cmdline_match.lower()
    for line in proc.stdout.splitlines():
        if needle not in line.lower():
            continue
        # CSV format: Node,CommandLine,ProcessId — last column is PID.
        m = re.search(r",(\d+)\s*$", line)
        if m:
            try:
                pids.append(int(m.group(1)))
            except ValueError:
                pass
    return pids


def kill_instance_processes(ld_dir: str, name: str, index: int) -> List[str]:
    """Force-kill orphan VBox/dnplayer processes that belong to this instance.

    Returns the list of human-readable actions taken (for logging).
    """
    actions = []
    # Match by leidian{N} since that token appears in VBoxHeadless cmdline
    # and in the dnplayer arguments.
    needle = f"leidian{index}"
    candidates = [
        ("VBoxHeadless.exe", needle),
        ("dnplayer.exe", needle),
    ]
    for image, match in candidates:
        for pid in _wmic_pids_for(image, match):
            res = _run(["taskkill", "/F", "/PID", str(pid)], timeout=10)
            if res and res.returncode == 0:
                actions.append(f"killed {image} pid={pid}")
            else:
                actions.append(f"failed to kill {image} pid={pid}")
    return actions


def kill_global_vboxsvc() -> List[str]:
    """Last-resort: kill the global VBoxSVC broker. Affects ALL instances."""
    actions = []
    res = _run(["taskkill", "/F", "/IM", "VBoxSVC.exe"], timeout=10)
    if res and res.returncode == 0:
        actions.append("killed VBoxSVC.exe")
    else:
        actions.append("VBoxSVC.exe not running or kill failed")
    return actions


# ── High-level orchestration ────────────────────────────────────────── #


def recover_instance(
    emulator,
    name: str,
    *,
    attempts: int = 2,
    cooldown_seconds: float = 4.0,
    boot_timeout: int = 120,
    log: Optional[Callable[[str, str], None]] = None,
) -> RecoveryResult:
    """Quit → kill orphans → relaunch → wait_for_ld_ready, up to ``attempts``.

    ``log(message, level)`` is optional; defaults to print().
    """

    def _log(msg, level="INFO"):
        if log:
            try:
                log(msg, level)
                return
            except Exception:
                pass
        print(f"[{level}] {msg}")

    result = RecoveryResult(name=name)

    index = None
    instance_index_fn = getattr(emulator, "_instance_index", None)
    if callable(instance_index_fn):
        try:
            index = instance_index_fn(name)
        except Exception:
            index = None

    if index is None:
        result.error = "could not resolve LD index"
        _log(f"Recovery aborted for '{name}': no index", "ERROR")
        return result

    # Initial diagnostic — record what we saw before touching anything.
    try:
        result.issues = scan_vbox_log(emulator.ld_dir, index)
    except Exception:
        pass
    if result.issues:
        sigs = sorted({i.signature for i in result.issues})
        _log(
            f"Detected wedging signatures in '{name}' VBox log: {', '.join(sigs)}",
            "WARNING",
        )

    for attempt in range(1, max(1, attempts) + 1):
        result.attempts = attempt
        _log(f"Recovery attempt {attempt}/{attempts} for '{name}'", "INFO")

        try:
            emulator.quit_ld(name)
            result.actions.append(f"attempt{attempt}: dnconsole quit")
        except Exception as exc:
            _log(f"quit_ld failed for '{name}': {exc}", "WARNING")

        time.sleep(cooldown_seconds)

        try:
            killed = kill_instance_processes(emulator.ld_dir, name, index)
        except Exception as exc:
            killed = []
            _log(f"orphan-process kill failed for '{name}': {exc}", "WARNING")
        if killed:
            for action in killed:
                result.actions.append(f"attempt{attempt}: {action}")
                _log(action, "INFO")

        time.sleep(cooldown_seconds)

        try:
            started = emulator.start_ld(
                name,
                delay_between_starts=getattr(emulator, "boot_delay", 10),
            )
        except Exception as exc:
            started = False
            _log(f"start_ld during recovery failed for '{name}': {exc}", "ERROR")

        if not started:
            result.actions.append(f"attempt{attempt}: start_ld returned False")
            continue

        try:
            ready = emulator.wait_for_ld_ready(name, timeout=boot_timeout, poll_interval=2)
        except Exception as exc:
            ready = False
            _log(f"wait_for_ld_ready raised for '{name}': {exc}", "ERROR")

        if ready:
            result.recovered = True
            result.actions.append(f"attempt{attempt}: ready")
            _log(f"'{name}' recovered on attempt {attempt}", "SUCCESS")
            return result

        _log(f"'{name}' still not ready after attempt {attempt}", "WARNING")

    result.error = "all attempts exhausted"
    return result


def diagnose(emulator, name: str) -> List[HealthIssue]:
    """Read-only check — what does the VBox log say about this LD right now?"""
    instance_index_fn = getattr(emulator, "_instance_index", None)
    if not callable(instance_index_fn):
        return []
    try:
        index = instance_index_fn(name)
    except Exception:
        return []
    if index is None:
        return []
    try:
        return scan_vbox_log(emulator.ld_dir, index)
    except Exception:
        return []
