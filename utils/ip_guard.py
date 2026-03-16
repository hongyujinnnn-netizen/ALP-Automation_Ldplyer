from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from typing import Callable, Iterable, List, Optional, Dict, Set


_IP_CACHE: Optional[Dict] = None


def _fetch_public_ip_info(timeout: float = 5.0) -> Optional[Dict]:
    """
    Fetch information about the current public IP address.

    Uses a simple external API that returns JSON with at least:
      - ip
      - country (ISO 3166-1 alpha-2)
    """
    url = "https://ipinfo.io/json"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if getattr(resp, "status", 200) != 200:
                return None
            raw = resp.read().decode("utf-8", errors="ignore")
            return json.loads(raw)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def get_cached_public_ip_info(force_refresh: bool = False) -> Optional[Dict]:
    """
    Return cached public IP info, fetching it once per run unless forced.
    """
    global _IP_CACHE
    if force_refresh or _IP_CACHE is None:
        _IP_CACHE = _fetch_public_ip_info()
    return _IP_CACHE


def normalise_country_codes(codes: Iterable[str]) -> List[str]:
    """
    Normalise a sequence of country codes to upper-case ISO-style strings.
    Empty / invalid entries are discarded.
    """
    normalised: List[str] = []
    for raw in codes:
        if not raw:
            continue
        code = "".join(ch for ch in str(raw).strip().upper() if ch.isalpha())
        if len(code) == 2:
            normalised.append(code)
    return normalised


def is_blocked_country(country_code: Optional[str], blocked: Iterable[str]) -> bool:
    """
    Decide whether the given country_code is blocked.

    If country_code is missing or empty, we treat it as blocked for safety.
    """
    blocked_set: Set[str] = set(normalise_country_codes(blocked))
    if not blocked_set:
        return False

    if not country_code:
        return True

    code = "".join(ch for ch in str(country_code).strip().upper() if ch.isalpha())
    if len(code) != 2:
        return True

    return code in blocked_set


def check_ip_allowed(
    blocked_countries: Iterable[str],
    log: Optional[Callable[[str, str], None]] = None,
    *,
    force_refresh: bool = False,
) -> bool:
    """
    Check whether automation is allowed under the current public IP.

    Returns:
      True  -> automation may proceed
      False -> automation should be blocked
    """
    def _log(msg: str, level: str = "INFO") -> None:
        if log is not None:
            try:
                log(msg, level)
            except Exception:
                pass

    blocked_list = normalise_country_codes(blocked_countries)
    if not blocked_list:
        _log("[IP Guard] No blocked countries configured; allowing automation.", "INFO")
        return True

    info = get_cached_public_ip_info(force_refresh=force_refresh)
    if info is None:
        _log("[IP Guard] Could not determine public IP; blocking automation for safety.", "WARNING")
        return False

    ip = info.get("ip", "?")
    country = info.get("country") or ""

    if is_blocked_country(country, blocked_list):
        _log(f"[IP Guard] Public IP {ip} in blocked country '{country or '??'}'; automation will not start.", "ERROR")
        return False

    _log(f"[IP Guard] Public IP {ip} in allowed country '{country}'; automation allowed.", "INFO")
    return True


# ==================== PER-LD (ADB) VARIANT ====================


def get_ld_public_ip_info(serial: str, timeout: float = 10.0) -> Optional[Dict]:
    """
    Query public IP info *from inside the LD instance* via adb shell.

    This assumes the Android environment has either `curl` or `wget` available
    (for example via busybox or a terminal app). We try curl first, then wget.
    """
    commands = [
        ["adb", "-s", serial, "shell", "curl", "-s", "https://ipinfo.io/json"],
        ["adb", "-s", serial, "shell", "wget", "-qO-", "https://ipinfo.io/json"],
    ]

    for cmd in commands:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except Exception:
            continue

        if result.returncode != 0:
            continue

        stdout = (result.stdout or "").strip()
        if not stdout:
            continue

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            continue

        # Normalise a little in case the API returns only country.
        if "ip" not in data and result.stdout:
            # Best-effort: api sometimes returns just the IP string when using /ip
            data.setdefault("ip", data.get("ip", "").strip())
        return data

    return None


def check_ld_ip_allowed(
    serial: str,
    blocked_countries: Iterable[str],
    log: Optional[Callable[[str, str], None]] = None,
    *,
    ld_name: Optional[str] = None,
    timeout: float = 10.0,
) -> bool:
    """
    Check whether automation is allowed for a specific LD instance.

    We query ipinfo.io *from inside the emulator* so that VPN/proxy rules
    applied inside LD are reflected in the detected public IP.
    """
    def _log(msg: str, level: str = "INFO") -> None:
        if log is not None:
            try:
                log(msg, level)
            except Exception:
                pass

    blocked_list = normalise_country_codes(blocked_countries)
    if not blocked_list:
        _log(f"[IP Guard] No blocked countries configured; allowing LD {ld_name or serial}.", "INFO")
        return True

    info = get_ld_public_ip_info(serial, timeout=timeout)
    if info is None:
        _log(f"[IP Guard] Could not determine public IP for LD {ld_name or serial}; blocking for safety.", "WARNING")
        return False

    ip = info.get("ip", "?")
    country = info.get("country") or ""

    if is_blocked_country(country, blocked_list):
        label = ld_name or serial
        _log(f"[IP Guard] LD {label} has public IP {ip} in blocked country '{country or '??'}'; automation will not run on this LD.", "ERROR")
        return False

    _log(f"[IP Guard] LD {ld_name or serial} has allowed public IP {ip} (country='{country}').", "INFO")
    return True

