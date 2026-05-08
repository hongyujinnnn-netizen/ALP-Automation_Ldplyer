"""LDPlayer / system popup dismissal helpers.

The "Welcome to LDPlayer" game-recommendation modal and a small set of
related system popups (update prompts, "Rate LDPlayer", etc.) periodically
steal focus from Facebook automation. These helpers detect and dismiss
them using the same predicate-based polling style as ``utils.uiwait``.

No ``time.sleep(N)`` for UI waits — every wait is bounded by a deadline or
``exists(timeout=...)``. Pure uiautomator2, no extra dependencies.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

FACEBOOK_PACKAGES = ("com.facebook.katana", "com.facebook.lite")

# A "signature" is a set of anchor selectors that uniquely identify a popup,
# plus dismissal strategies tried in order. Easy to extend: append a dict.
PopupSignature = dict[str, Any]

LDPLAYER_WELCOME: PopupSignature = {
    "name": "LDPlayer Welcome / Game Recommendation",
    "anchors_ui": [
        {"text": "Welcome to LDPlayer"},
        {"textContains": "Please install the game"},
        {"textContains": "app you want to play"},
        {"description": "Close"},
    ],
    "anchors_xml": [
        ("text", "Welcome to LDPlayer"),
        ("text-contains", "Please install"),
        ("content-desc", "Close"),
    ],
    "dismiss_ui": [
        {"description": "Close"},
        {"resourceId": "com.android.vending:id/0_resource_name_obfuscated"},
        {"resourceId": "android:id/closeButton"},
        {"className": "android.widget.ImageButton", "descriptionContains": "close"},
    ],
    # Relative coordinates (fractions of screen w/h), not absolute pixels —
    # safe across LDPlayer resolutions.
    "dismiss_taps": [(0.95, 0.08), (0.93, 0.10)],
}

LDPLAYER_UPDATE: PopupSignature = {
    "name": "LDPlayer Update Prompt",
    "anchors_ui": [
        {"textContains": "new version"},
        {"textContains": "Update"},
        {"textContains": "LDPlayer"},
    ],
    "anchors_xml": [("text-contains", "new version"), ("text-contains", "Update")],
    "dismiss_ui": [
        {"text": "Later"},
        {"text": "Cancel"},
        {"text": "Not now"},
        {"description": "Close"},
    ],
    "dismiss_taps": [],
}

LDPLAYER_RATE: PopupSignature = {
    "name": "Rate LDPlayer",
    "anchors_ui": [
        {"textContains": "Rate"},
        {"textContains": "rating"},
    ],
    "anchors_xml": [("text-contains", "Rate"), ("text-contains", "rating")],
    "dismiss_ui": [
        {"text": "Later"},
        {"text": "No thanks"},
        {"text": "Cancel"},
    ],
    "dismiss_taps": [],
}

KNOWN_POPUPS: list[PopupSignature] = [LDPLAYER_WELCOME, LDPLAYER_UPDATE, LDPLAYER_RATE]


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _save_debug_artifacts(d, label: str, log: Callable[[str], None] | None) -> None:
    """Dump screenshot + XML to debug/ on dismiss failure (mirrors crash logging)."""
    debug_dir = Path("debug")
    try:
        debug_dir.mkdir(exist_ok=True)
        stamp = _now_stamp()
        png_path = debug_dir / f"{label}_{stamp}.png"
        xml_path = debug_dir / f"{label}_{stamp}.xml"
        try:
            d.screenshot(str(png_path))
        except Exception as exc:
            if log:
                log(f"[popup] screenshot failed: {exc}")
        try:
            xml_path.write_text(d.dump_hierarchy(), encoding="utf-8")
        except Exception as exc:
            if log:
                log(f"[popup] hierarchy dump failed: {exc}")
        if log:
            log(f"[popup] debug artifacts saved: {png_path.name}, {xml_path.name}")
    except Exception as exc:
        if log:
            log(f"[popup] could not write debug artifacts: {exc}")


def _detect_via_ui(d, anchors: list[dict]) -> dict | None:
    """First-pass detection: native uiautomator2 selectors."""
    for sel in anchors:
        try:
            if d(**sel).exists(timeout=0.2):
                return sel
        except Exception:
            continue
    return None


def _detect_via_xml(d, xml_anchors: list[tuple[str, str]]) -> tuple[str, str] | None:
    """Fallback for Facebook-style lazy rendering: walk dump_hierarchy() XML.

    Some LDPlayer popups render their text into nodes that ``d(text=...)``
    misses on the first query because the modal animates in. Parsing the
    hierarchy directly catches them.
    """
    try:
        xml = d.dump_hierarchy()
    except Exception:
        return None
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None

    for attr, needle in xml_anchors:
        attr_keys = {
            "text": "text",
            "text-contains": "text",
            "content-desc": "content-desc",
        }
        key = attr_keys.get(attr, attr)
        contains = attr.endswith("-contains") or attr == "text-contains"
        for node in root.iter():
            value = node.attrib.get(key, "")
            if not value:
                continue
            if contains and needle in value:
                return (attr, needle)
            if not contains and value == needle:
                return (attr, needle)
    return None


def _try_dismiss_selectors(d, selectors: list[dict]) -> str | None:
    """Click the first matching dismissal selector; return its label."""
    for sel in selectors:
        try:
            obj = d(**sel)
            if obj.exists(timeout=0.2):
                obj.click()
                return f"selector={sel}"
        except Exception:
            continue
    return None


def _try_dismiss_taps(d, taps: list[tuple[float, float]]) -> str | None:
    """Tap relative-coordinate fallbacks (typically the X icon)."""
    if not taps:
        return None
    try:
        info = d.window_size()
        w, h = info[0], info[1]
    except Exception:
        return None
    for fx, fy in taps:
        try:
            x, y = int(w * fx), int(h * fy)
            d.click(x, y)
            return f"tap=({fx:.2f},{fy:.2f})->({x},{y})"
        except Exception:
            continue
    return None


def _dismiss_one(
    d,
    sig: PopupSignature,
    log: Callable[[str], None] | None,
) -> tuple[bool, str | None]:
    """Detect + dismiss a single popup signature. Returns (found, method_used)."""
    anchor = _detect_via_ui(d, sig["anchors_ui"])
    detect_path = "ui"
    if anchor is None:
        xml_hit = _detect_via_xml(d, sig["anchors_xml"])
        if xml_hit is None:
            return False, None
        detect_path = f"xml({xml_hit[0]}={xml_hit[1]!r})"

    if log:
        log(f"[popup] detected '{sig['name']}' via {detect_path}")

    method = _try_dismiss_selectors(d, sig["dismiss_ui"])
    if method:
        return True, f"click {method}"

    method = _try_dismiss_taps(d, sig["dismiss_taps"])
    if method:
        return True, f"coord {method}"

    try:
        d.press("back")
        return True, "press(back)"
    except Exception:
        return True, None  # detected but every dismissal path failed


def dismiss_ldplayer_popup(d, timeout: float = 5.0, max_attempts: int = 3) -> bool:
    """Detect and dismiss the "Welcome to LDPlayer" popup.

    Detection uses multiple anchor strategies (native selectors first, XML
    hierarchy fallback). Dismissal cascades through close-by-description,
    close-by-resource-id, relative-coordinate tap on the X, and finally
    ``d.press("back")``.

    Returns ``True`` if a popup was found and dismissed, ``False`` if none
    appeared. Re-runs up to ``max_attempts`` because the popup occasionally
    re-renders after the first close.
    """
    log = getattr(d, "info_log", None) or print
    deadline = time.monotonic() + timeout
    dismissed_any = False

    for attempt in range(1, max_attempts + 1):
        if time.monotonic() >= deadline and dismissed_any:
            break

        found, method = _dismiss_one(d, LDPLAYER_WELCOME, log)
        if not found:
            if dismissed_any:
                return True
            return False

        dismissed_any = True
        if method:
            log(f"[popup] attempt {attempt}/{max_attempts} dismissed via {method}")
        else:
            log(f"[popup] attempt {attempt}/{max_attempts} detected but dismissal failed")
            _save_debug_artifacts(d, "ldplayer_welcome_dismiss_fail", log)

        # Brief settle window — bounded poll, not a blind sleep — to let the
        # modal animate out before re-checking.
        settle = time.monotonic() + 1.0
        while time.monotonic() < settle:
            if not d(**LDPLAYER_WELCOME["anchors_ui"][0]).exists(timeout=0.1):
                break
            time.sleep(0.1)

        if not _detect_via_ui(d, LDPLAYER_WELCOME["anchors_ui"]):
            return True

    if dismissed_any:
        _save_debug_artifacts(d, "ldplayer_welcome_persistent", log)
    return dismissed_any


def ensure_clean_state(
    d,
    facebook_packages: tuple[str, ...] = FACEBOOK_PACKAGES,
    extra_popups: list[PopupSignature] | None = None,
    relaunch: Callable[[], None] | None = None,
) -> bool:
    """Dismiss all known LDPlayer popups and verify Facebook is foregrounded.

    Pass ``extra_popups`` to extend the dismissal set without editing this
    module. Pass ``relaunch`` (a zero-arg callable) to be invoked when
    Facebook is no longer the foreground app after dismissal.

    Returns ``True`` if state is clean (Facebook foregrounded and no known
    popups present), ``False`` otherwise.
    """
    log = getattr(d, "info_log", None) or print
    signatures = list(KNOWN_POPUPS)
    if extra_popups:
        signatures.extend(extra_popups)

    dismiss_ldplayer_popup(d)

    for sig in signatures:
        if sig is LDPLAYER_WELCOME:
            continue
        found, method = _dismiss_one(d, sig, log)
        if found and method:
            log(f"[popup] dismissed '{sig['name']}' via {method}")
        elif found:
            log(f"[popup] '{sig['name']}' detected but dismissal failed")
            _save_debug_artifacts(d, f"{sig['name'].replace(' ', '_')}_fail", log)

    try:
        current = d.app_current() or {}
    except Exception as exc:
        log(f"[popup] app_current() failed: {exc}")
        return False

    pkg = current.get("package", "")
    if pkg in facebook_packages:
        return True

    log(f"[popup] foreground is {pkg!r}, expected Facebook")
    if relaunch is not None:
        try:
            relaunch()
            return True
        except Exception as exc:
            log(f"[popup] relaunch failed: {exc}")
    return False
