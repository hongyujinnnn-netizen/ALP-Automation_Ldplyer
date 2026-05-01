import json
import random
import re
import string
import subprocess
import time
from datetime import datetime
from typing import Any, Callable, TYPE_CHECKING

from core.email_models import EmailAccountConfig, OTPRequest
from core.paths import get_app_paths
from core.settings import SettingsError, load_app_settings
from services.otp_service import OTPService

class RegAccountHandlerMixin:
    if TYPE_CHECKING:
        FIRST_NAMES: list[str]
        LAST_NAMES: list[str]
        MONTHS: list[str]
        emulator: Any
        log: Callable[..., None]

        def check_paused(self) -> bool: ...
        def open_facebook(self, d: Any) -> bool: ...
        def push_runtime_state(self, name: str, **payload: Any) -> None: ...

    def enter_email(self, d, email, timeout=5):
        """
        Smart handler to find email input field and enter value
        Works across different layouts (text, hint, class)
        """

        email_text = str(email or "").strip()
        if not email_text:
            self.log("Email input skipped: empty email value")
            return False

        self.log(f"Entering email: {email_text}")
        deadline = time.time() + max(3, timeout)
        while time.time() < deadline:
            if self._set_text_inputs(
                d,
                [email_text],
                hints=("email", "mail", "address"),
                require_hint_match=False,
            ):
                time.sleep(1)

                try:
                    edit_fields = list(d(className="android.widget.EditText"))
                except Exception:
                    edit_fields = []

                typed_ok = False
                for field in edit_fields:
                    try:
                        info = getattr(field, "info", {}) or {}
                        current_text = str(info.get("text", "") or "").strip()
                        if current_text == email_text:
                            typed_ok = True
                            break
                    except Exception:
                        continue

                if not typed_ok:
                    self.log("Email text was not visible after input, retrying")
                    time.sleep(0.8)
                    continue
                if self._tap_next(d) or self._request_email_code(d):
                    self.log("Email entered and Next tapped")
                    return True

                self.log("Email entered but Next button was not available")
                return False

            time.sleep(0.5)

        self.log("Email input not found")
        return False

    def enter_confirmation_code(self, d, otp_code, timeout=12):
        code_text = str(otp_code or "").strip()
        if not code_text:
            self.log("OTP input skipped: empty confirmation code")
            return False

        self.log(f"Entering confirmation code: {'*' * len(code_text)}")
        deadline = time.time() + max(5, timeout)

        while time.time() < deadline:
            edit_fields = self._get_edit_text_fields(d, hints=("code", "otp", "confirmation", "security"))
            if not edit_fields:
                time.sleep(0.5)
                continue

            if self._set_confirmation_code_inputs(d, edit_fields, code_text):
                time.sleep(1)
                if self._confirm_code_text_visible(edit_fields, code_text):
                    if self._submit_confirmation_code(d):
                        self.log("Confirmation code entered and submitted")
                        return True
                    self.log("Confirmation code entered but submit button was not available")
                    return False

                self.log("Confirmation code was not visible after input, retrying")
            time.sleep(0.5)

        self.log("Confirmation code input not found")
        return False

    def _tap_next(self, d, timeout=3):
        selectors = [
            {"text": "Next"},
            {"textContains": "Next"},
            {"descriptionContains": "Next"},
        ]

        for sel in selectors:
            btn = d(**sel)
            if btn.exists(timeout=1):
                btn.click()
                return True
        return False

    def _request_email_code(self, d, timeout=6):
        return self._click_any_selector(
            d,
            [
                {"text": "Next"},
                {"text": "Continue"},
                {"text": "Send code"},
                {"text": "Send Code"},
                {"textContains": "Send code"},
                {"textContains": "Send Code"},
                {"textContains": "Resend code"},
                {"textContains": "Resend Code"},
                {"textContains": "Continue"},
                {"textContains": "Next"},
            ],
            timeout=timeout,
            required=False,
        )

    def _handle_confirm_by_email(self, d, timeout=5):
        self.log("Checking for 'Confirm by email' option")
        if self._click_any_selector(
            d,
            [
                {"text": "Confirm by email"},
                {"textContains": "Confirm by email"},
                {"description": "Confirm by email"},
                {"descriptionContains": "Confirm by email"},
            ],
            timeout=timeout,
            required=False,
        ):
            self.log("Tapped 'Confirm by email'")
            time.sleep(5)

            return True
        self.log("'Confirm by email' option not shown")
        return False

    def _handle_didnt_get_code_step(self, d, timeout=8):
        self.log("Checking for 'I didn't get the code' option")
        variants = (
            "I didn't get the code",
            "I didnâ€™t get the code",
            "didn't get the code",
            "didnâ€™t get the code",
            "didnt get the code",
            "I didn't get a code",
            "I didnâ€™t get a code",
        )

        if self._click_any_selector(
            d,
            [
                {"text": "I didn't get the code"},
                {"text": "I didnâ€™t get the code"},
                {"textContains": "I didn't get the code"},
                {"textContains": "I didnâ€™t get the code"},
                {"textContains": "didn't get the code"},
                {"textContains": "didnâ€™t get the code"},
                {"textContains": "didnt get the code"},
                {"description": "I didn't get the code"},
                {"description": "I didnâ€™t get the code"},
                {"descriptionContains": "didn't get the code"},
                {"descriptionContains": "didnâ€™t get the code"},
                {"descriptionContains": "didnt get the code"},
            ],
            timeout=timeout,
            required=False,
        ) or self._click_text_variants(
            d,
            variants,
            timeout=timeout,
        ):
            self.log("Tapped 'I didn't get the code'")
            time.sleep(2)
            return True

        self.log("'I didn't get the code' option not shown")
        return False

    def _click_text_variants(self, d, variants, timeout=5):
        normalized_variants = [
            self._normalize_ui_text(variant)
            for variant in variants
            if str(variant or "").strip()
        ]
        if not normalized_variants:
            return False

        deadline = time.time() + timeout
        class_names = (
            "android.widget.Button",
            "android.widget.TextView",
            "android.view.View",
        )

        while time.time() < deadline:
            for class_name in class_names:
                try:
                    candidates = list(d(className=class_name))
                except Exception:
                    candidates = []

                for candidate in candidates:
                    try:
                        info = getattr(candidate, "info", {}) or {}
                        label = " ".join(
                            str(info.get(key, "") or "")
                            for key in ("text", "contentDescription", "hint")
                        )
                        normalized_label = self._normalize_ui_text(label)
                        if not normalized_label:
                            continue
                        if any(variant in normalized_label for variant in normalized_variants):
                            if self._click_best_target(d, candidate):
                                return True
                    except Exception:
                        continue
            time.sleep(0.4)

        return False

    def _normalize_ui_text(self, value):
        text = str(value or "")
        text = text.replace("\u2019", "'").replace("\u2018", "'")
        text = re.sub(r"\s+", " ", text).strip().lower()
        return text

    def clear_app_storage(self, d, name, package_name="com.facebook.katana"):
        """Clear Android app storage for the target package on the active device."""
        serial = getattr(d, "serial", None) or self.emulator.name_to_serial.get(name, name)
        if not serial:
            self.log(f"Cannot clear app storage for {package_name}: missing device serial for {name}")
            return False

        try:
            d.app_stop(package_name)
        except Exception as exc:
            self.log(f"Failed to stop {package_name} before clearing on {name}: {exc}")

        try:
            result = subprocess.run(
                ["adb", "-s", serial, "shell", "pm", "clear", package_name],
                capture_output=True,
                text=True,
                timeout=20,
            )
        except subprocess.TimeoutExpired:
            self.log(f"Timed out while clearing {package_name} storage on {name}")
            return False
        except Exception as exc:
            self.log(f"Failed to clear {package_name} storage on {name}: {exc}")
            return False

        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        if result.returncode == 0 and "Success" in stdout:
            self.log(f"Cleared {package_name} storage on {name}")
            return True

        details = stderr or stdout or f"exit code {result.returncode}"
        self.log(f"Could not clear {package_name} storage on {name}: {details}")
        return False

    def _clear_app_data(self, d, package_name, name=None):
        """Backward-compatible wrapper for older cleanup call sites."""
        resolved_name = name or getattr(d, "serial", None) or package_name
        return self.clear_app_storage(d, resolved_name, package_name=package_name)

    def _run_registration_steps_with_retry(self, d, name, profile, retries=2, retry_delay=3):
        total_attempts = retries + 1
        delay_fb = 2
        for attempt in range(1, total_attempts + 1):
            delay_fb += 2
            ok, failed_step = self._run_registration_steps_once(d, name, profile, delay_fb)
            if ok:
                return True

            if attempt >= total_attempts:
                self.log(f"Registration failed on {failed_step} step for {name} after {attempt} attempts")
                return False

            self.log(
                f"Registration step '{failed_step}' failed for {name}. "
                f"Retrying after {retry_delay}s ({attempt}/{retries})"
            )
            time.sleep(retry_delay)
            self._reset_registration_apps(d)

        return False

    def _run_registration_steps_once(self, d, name, profile, delay_fb):
        self.log(f"Opening Facebook: {name}")
        if not self.open_facebook(d):
            self.log(f"Failed to open Facebook for registration: {name}")
            return False, "open_facebook"
        time.sleep(delay_fb)
        self.push_runtime_state(name, state="Running", task="Starting registration", progress=45)
        if not self._start_registration_flow(d, name):
            self.log(f"Could not open create-account flow on {name}")
            return False, "start_registration_flow"

        if not self._fill_name_step(d, name, profile):
            self.log(f"Failed on name step for {name}")
            return False, "name"

        time.sleep(3)
        skip_contact = False
        if not self._fill_birthdate_step(d, name, profile):
            try:
                self._fill_contact_step(d, name, profile)
                self._check_Continue_creating_account(d)
                skip_contact = True
                time.sleep(3)
                if self._fill_birthdate_step(d, name, profile):
                    time.sleep(4)
                else:
                    self.log(f"Failed on birth date step for {name}")
                    return False, "birthdate"
            except Exception:
                self.log(f"Failed on birth date step for {name}")
                return False, "birthdate"
        else:
            time.sleep(4)

        if not self._fill_gender_step(d, name, profile):
            self.log(f"Failed on gender step for {name}")
            return False, "gender"

        time.sleep(4)
        if not skip_contact:
            if self._fill_contact_step(d, name, profile):
                self._check_Continue_creating_account(d)
            else:
                self.log(f"Failed on contact step for {name}")  
            
        time.sleep(4)
        if not self._fill_password_step(d, name, profile):
            self.log(f"Failed on password step for {name}")
            return False, "password"
        
        time.sleep(4)

        self._handle_save_step(d)
        self.tap_i_agree(d)

        self._handle_create_new_step(d)

        return True, ""

    def _reset_registration_apps(self, d):
        serial = getattr(d, "serial", None)
        try:
            d.app_stop("com.facebook.katana")
        except Exception:
            pass
        try:
            d.app_stop("com.android.settings")
        except Exception:
            pass
        self._clear_recent_apps(d)
        if serial:
            try:
                subprocess.run(
                    ["adb", "-s", serial, "shell", "am", "kill-all"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            except Exception:
                pass
        try:
            d.press("home")
        except Exception:
            pass

    def _clear_recent_apps(self, d):
        serial = getattr(d, "serial", None)
        try:
            try:
                d.press("recent")
            except Exception:
                if serial:
                    subprocess.run(
                        ["adb", "-s", serial, "shell", "input", "keyevent", "187"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
            time.sleep(2)

            clear_selectors = [
                {"resourceId": "com.android.systemui:id/clear_all"},
                {"text": "Clear all"},
                {"text": "CLEAR ALL"},
                {"text": "Close all"},
                {"text": "CLOSE ALL"},
                {"text": "Clear"},
                {"text": "CLEAR"},
            ]

            for selector in clear_selectors:
                try:
                    obj = d(**selector)
                    if obj.exists(timeout=1):
                        obj.click()
                        self.log("Cleared recent apps")
                        time.sleep(2)
                        break
                except Exception:
                    continue
            return True
        except Exception as exc:
            self.log(f"Failed to clear recent apps: {exc}")
            return False

    def detect_account_status(self, d):
        """
        Detect account status from screen text.

        Returns:
            "Novery"  -> need verification (OTP screen)
            "Dead"    -> account suspended
            "Unknown" -> nothing matched
        """

        try:
            # Get all visible text from screen
            xml = d.dump_hierarchy()
            xml_lower = xml.lower()

            # Case 1: OTP verification screen
            if "enter the confirmation code" in xml_lower:
                return "Novery"

            # Case 2: Account suspended
            if "account suspended" in xml_lower or "180 days" in xml_lower:
                return "Dead"

            return "Unknown"

        except Exception as e:
            print(f"[ERROR] detect_account_status: {e}")
            return "Unknown"


    def check_uid_account(self, d, before_ids=None):
        if d is None:
            self.log("Cannot check Facebook UID without a device session")
            return ""

        before_ids = list(before_ids or [])
        self.log(f"Facebook IDs before registration snapshot: {before_ids}")

        after_ids = self.get_facebook_account_ids_from_settings(d)
        self.log(f"Facebook IDs after registration snapshot: {after_ids}")

        account_number_uid = self.resolve_new_facebook_uid(before_ids, after_ids)
        if account_number_uid:
            self.log(f"Resolved Facebook UID: {account_number_uid}")
            return account_number_uid

        self.log("Facebook account number not found in Settings > Accounts")
        return ""

    def _open_settings_accounts(self, d, max_scrolls=8):
        self.log("Opening Android Settings")

        try:
            d.app_stop("com.android.settings")
        except Exception:
            pass

        try:
            d.app_start("com.android.settings")
        except Exception as exc:
            self.log(f"Failed to open Settings: {exc}")
            return False

        time.sleep(3)

        account_patterns = (
            "accounts",
            "users & accounts",
            "passwords & accounts",
        )

        for attempt in range(max_scrolls):

            # 1) Try exact visible text search first
            if self._click_settings_accounts_row(d, account_patterns):
                if self._is_accounts_screen_open(d):
                    self.log("Opened Accounts in Settings")
                    return True

            # 2) Fallback selectors
            selectors = [
                d(textMatches=r"(?i)^accounts$"),
                d(textMatches=r"(?i)^users\s*&\s*accounts$"),
                d(textMatches=r"(?i)^passwords\s*&\s*accounts$"),
                d(textContains="Accounts"),
                d(descriptionContains="Accounts"),
            ]

            for obj in selectors:
                try:
                    if obj.exists:
                        if self._click_best_target(d, obj):
                            time.sleep(2)
                            if self._is_accounts_screen_open(d):
                                self.log("Opened Accounts in Settings")
                                return True
                except Exception:
                    pass

            # 3) Scroll down and retry
            try:
                scrollable = d(scrollable=True)
                if scrollable.exists:
                    scrollable.scroll.vert.forward(steps=30)
                else:
                    d.swipe(360, 1180, 360, 420, 0.2)
            except Exception:
                try:
                    d.swipe(360, 1180, 360, 420, 0.2)
                except Exception:
                    pass

            time.sleep(1.5)

        self.log("Could not find Accounts in Settings")
        return False

    def _click_settings_accounts_row(self, d, patterns):
        """
        Find visible Accounts-like text and click the full row or fallback to bounds center.
        """
        text_views = list(d(className="android.widget.TextView"))

        for node in text_views:
            try:
                text = (node.info.get("text") or "").strip()
                if not text:
                    continue

                normalized = re.sub(r"\s+", " ", text.lower()).strip()
                if normalized in patterns:
                    self.log(f"Matched settings row text: {text}")
                    return self._click_best_target(d, node)

            except Exception:
                continue

        return False

    def _click_best_target(self, d, obj):
        """
        Try clicking object directly, then clickable parent, then bounds center.
        """
        try:
            if obj.exists:
                info = obj.info

                if info.get("clickable"):
                    obj.click()
                    return True
        except Exception:
            pass

        # Try parent / clickable ancestor
        try:
            current = obj
            for _ in range(5):
                current = current.xpath("..")
                if not current.exists:
                    break

                try:
                    parent_info = current.info
                    if parent_info.get("clickable"):
                        current.click()
                        return True
                except Exception:
                    pass
        except Exception:
            pass

        # Fallback: click center of bounds
        try:
            info = obj.info
            bounds = info.get("bounds", {})
            left = bounds.get("left", 0)
            top = bounds.get("top", 0)
            right = bounds.get("right", 0)
            bottom = bounds.get("bottom", 0)

            if right > left and bottom > top:
                cx = (left + right) // 2
                cy = (top + bottom) // 2
                d.click(cx, cy)
                return True
        except Exception:
            pass

        return False

    def _is_accounts_screen_open(self, d):
        """
        Verify that we are really inside the Accounts page.
        """
        checks = [
            d(textMatches=r"(?i)^accounts$"),
            d(textContains="Accounts for"),
            d(textContains="Add account"),
            d(textContains="Automatically sync data"),
            d(textContains="Google"),
            d(textContains="Facebook"),
        ]

        for obj in checks:
            try:
                if obj.exists:
                    return True
            except Exception:
                pass

        return False

    def _collect_text_view_items(self, d):
        items = []
        try:
            text_views = list(d(className="android.widget.TextView"))
        except Exception as exc:
            self.log(f"Failed to collect TextView items: {exc}")
            return items

        for node in text_views:
            try:
                info = getattr(node, "info", {}) or {}
                text = str(info.get("text") or "").strip()
                bounds = info.get("bounds", {}) or {}
                left = int(bounds.get("left", 0) or 0)
                top = int(bounds.get("top", 0) or 0)
                right = int(bounds.get("right", 0) or 0)
                bottom = int(bounds.get("bottom", 0) or 0)

                if not text or right <= left or bottom <= top:
                    continue

                items.append(
                    {
                        "text": text,
                        "bounds": bounds,
                        "left": left,
                        "top": top,
                        "right": right,
                        "bottom": bottom,
                        "center_x": (left + right) // 2,
                        "center_y": (top + bottom) // 2,
                    }
                )
            except Exception:
                continue

        items.sort(key=lambda item: (item["top"], item["left"], item["text"]))
        return items

    def detect_facebook_account_numbers(self, d, max_scrolls=5):
        facebook_ids = []
        seen_ids = set()
        seen_screens = set()
        numeric_pattern = re.compile(r"\d{10,20}")

        for scroll_index in range(max(1, int(max_scrolls or 1))):
            items = self._collect_text_view_items(d)
            if not items:
                self.log(f"No TextView items found while scanning Facebook accounts (page {scroll_index + 1})")
            else:
                screen_signature = tuple((item["text"], item["top"], item["left"]) for item in items)
                if screen_signature in seen_screens:
                    self.log(f"Accounts screen content repeated on page {scroll_index + 1}, stopping scan")
                    break
                seen_screens.add(screen_signature)

            numeric_items = [
                item for item in items
                if numeric_pattern.fullmatch(item["text"])
            ]
            facebook_items = [
                item for item in items
                if item["text"].strip().lower() == "facebook"
            ]

            self.log(
                f"Scanning Accounts page {scroll_index + 1}: "
                f"{len(facebook_items)} Facebook rows, {len(numeric_items)} numeric rows"
            )

            for facebook_item in facebook_items:
                candidates = []
                for numeric_item in numeric_items:
                    if numeric_item["center_y"] > facebook_item["center_y"]:
                        continue

                    vertical_gap = max(0, facebook_item["top"] - numeric_item["bottom"])
                    horizontal_gap = abs(numeric_item["center_x"] - facebook_item["center_x"])
                    same_column = (
                        min(numeric_item["right"], facebook_item["right"])
                        - max(numeric_item["left"], facebook_item["left"])
                    ) > 0
                    candidates.append(
                        (
                            0 if same_column else 1,
                            vertical_gap,
                            horizontal_gap,
                            -numeric_item["center_y"],
                            numeric_item,
                        )
                    )

                if not candidates:
                    self.log(
                        "Found a Facebook row but no numeric text above it on the current page"
                    )
                    continue

                best_match = min(candidates)[-1]
                facebook_id = best_match["text"]
                if facebook_id not in seen_ids:
                    seen_ids.add(facebook_id)
                    facebook_ids.append(facebook_id)
                    self.log(
                        f"Matched Facebook row at y={facebook_item['center_y']} "
                        f"to numeric ID {facebook_id}"
                    )

            if scroll_index >= max_scrolls - 1:
                break

            moved = False
            try:
                scrollable = d(scrollable=True)
                if scrollable.exists:
                    moved = bool(scrollable.scroll.vert.forward(steps=25))
                if not moved:
                    d.swipe(360, 1180, 360, 420, 0.2)
                    moved = True
            except Exception:
                try:
                    d.swipe(360, 1180, 360, 420, 0.2)
                    moved = True
                except Exception:
                    moved = False

            if not moved:
                self.log("Could not scroll further while scanning Facebook accounts")
                break

            time.sleep(1)

        self.log(f"Collected Facebook account IDs from visible Settings pages: {facebook_ids}")
        return facebook_ids

    def get_facebook_account_ids_from_settings(self, d):
        if d is None:
            self.log("Cannot collect Facebook account IDs without a device session")
            return []

        if not self._open_settings_accounts(d):
            self.log("Failed to open Settings > Accounts for Facebook ID collection")
            return []

        time.sleep(3)
        facebook_ids = self.detect_facebook_account_numbers(d)
        self.log(f"Facebook IDs collected from Settings > Accounts: {facebook_ids}")
        return facebook_ids

    def resolve_new_facebook_uid(self, before_ids, after_ids) -> str:
        before_ids = [str(item).strip() for item in (before_ids or []) if str(item).strip()]
        after_ids = [str(item).strip() for item in (after_ids or []) if str(item).strip()]

        before_seen = set()
        normalized_before = []
        for item in before_ids:
            if item not in before_seen:
                before_seen.add(item)
                normalized_before.append(item)

        after_seen = set()
        normalized_after = []
        for item in after_ids:
            if item not in after_seen:
                after_seen.add(item)
                normalized_after.append(item)

        new_ids = [item for item in normalized_after if item not in before_seen]

        self.log(f"Resolving Facebook UID from before={normalized_before} after={normalized_after}")
        self.log(f"New Facebook IDs after comparison: {new_ids}")

        if len(new_ids) == 1:
            self.log("Exactly one new Facebook ID detected")
            return new_ids[0]

        if len(new_ids) > 1:
            self.log("Multiple new Facebook IDs detected, using the last/newest visible ID")
            return new_ids[-1]

        if normalized_after:
            self.log("No unique new Facebook ID found, falling back to the last visible Facebook ID")
            return normalized_after[-1]

        self.log("No Facebook IDs available after registration")
        return ""

    def _build_profile(self, kwargs):
        first_name = str(kwargs.get("first_name") or random.choice(self.FIRST_NAMES))
        last_name = str(kwargs.get("last_name") or random.choice(self.LAST_NAMES))
        birth_day = int(kwargs.get("birth_day") or random.randint(24, 26))
        birth_month = int(kwargs.get("birth_month") or random.randint(3, 5))
        birth_year = int(kwargs.get("birth_year") or random.randint(2005, 2007))
        gender = str(kwargs.get("gender") or random.choice(["Female", "Male"]))
        contact_label, contact_value = self._build_contact(first_name, last_name, kwargs)
        password = str(kwargs.get("password") or self._generate_password())
        return AccountProfile(
            first_name=first_name,
            last_name=last_name,
            birth_day=birth_day,
            birth_month=birth_month,
            birth_year=birth_year,
            gender=gender,
            contact_value=contact_value,
            contact_label=contact_label,
            password=password,
        )

    def _build_contact(self, first_name, last_name, kwargs):
        mode = str(kwargs.get("contact_mode") or getattr(self, "contact_mode", "random_phone")).strip().lower()
        fixed_value = str(kwargs.get("contact_value") or getattr(self, "contact_value", "")).strip()
        phone_prefix = str(kwargs.get("phone_prefix") or getattr(self, "phone_prefix", "+1")).strip() or "+1"
        fixed_pool = self._parse_contact_pool(fixed_value)

        if mode == "fixed_email" and fixed_value:
            return "email", random.choice(fixed_pool) if fixed_pool else fixed_value
        if mode == "fixed_phone" and fixed_value:
            return "phone", random.choice(fixed_pool) if fixed_pool else fixed_value
        if mode == "random_phone":
            return "phone", self._generate_phone(phone_prefix)
        return "email", self._generate_email(first_name, last_name)

    def _parse_contact_pool(self, raw_value):
        cleaned = str(raw_value or "").strip()
        if not cleaned:
            return []

        if cleaned[0] in "([{" and cleaned[-1] in ")]}":
            cleaned = cleaned[1:-1].strip()

        if not cleaned:
            return []

        return [
            part.strip().strip("\"'")
            for part in cleaned.split(",")
            if part.strip().strip("\"'")
        ]

    def _generate_email(self, first_name, last_name):
        suffix = random.randint(1000, 99999)
        return f"{first_name.lower()}.{last_name.lower()}{suffix}@gmail.com"

    def _resolve_confirmation_email(self):
        try:
            settings = load_app_settings(get_app_paths().settings_file)
        except SettingsError as exc:
            self.log(f"Failed to load email settings for confirmation email: {exc}")
            return None

        main_email = str(getattr(settings, "email_address", "") or "").strip()
        if not main_email:
            return None

        provider = str(getattr(settings, "email_provider", "") or "").strip().lower()
        alias_email = self._build_yandex_clone_email(main_email) if self._is_yandex_address(main_email, provider) else main_email
        self.log(f"Using confirmation email: {alias_email}")
        return alias_email

    def _wait_for_confirmation_otp(self, confirmation_email=None):
        config, request = self._load_confirmation_otp_settings()
        if not config:
            return None

        mailbox_label = str(confirmation_email or config.email_address or "").strip() or "configured mailbox"
        self.log(f"Waiting for OTP in {mailbox_label}")

        service = OTPService(
            ui_log_func=lambda message, level="INFO": self.log(message, level),
        )
        result = service.wait_for_otp(config, request)
        if not result.success or not result.code:
            self.log(result.error or "No matching OTP email found.", "WARNING")
            return None

        self.log(f"Fetched confirmation code from email for {mailbox_label}")
        return str(result.code).strip()

    def _load_confirmation_otp_settings(self):
        try:
            settings = load_app_settings(get_app_paths().settings_file)
        except SettingsError as exc:
            self.log(f"Failed to load OTP settings: {exc}")
            return None, None

        config = EmailAccountConfig(
            provider=settings.email_provider,
            email_address=settings.email_address,
            app_password=settings.email_app_password,
            imap_server=settings.email_imap_server,
            imap_port=settings.email_imap_port,
            mailbox=settings.email_mailbox,
            use_ssl=settings.email_use_ssl,
        ).with_provider_defaults()

        if not config.email_address or not config.app_password:
            self.log("Email OTP settings are incomplete. Configure email address and app password first.")
            return None, None

        request = self._build_confirmation_otp_request(settings)
        return config, request

    @staticmethod
    def _build_confirmation_otp_request(settings):
        sender_filter = str(getattr(settings, "email_sender_filter", "") or "").strip()
        subject_filter = str(getattr(settings, "email_subject_filter", "") or "").strip()
        timeout_seconds = max(30, int(getattr(settings, "email_timeout_seconds", 90) or 90))
        poll_interval_seconds = max(2, int(getattr(settings, "email_poll_interval_seconds", 5) or 5))
        mark_as_seen = bool(getattr(settings, "email_mark_as_seen", False))
        return OTPRequest(
            sender_filter=sender_filter or "facebook",
            subject_filter=subject_filter,
            unread_only=True,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            mark_as_seen=mark_as_seen,
        )

    @staticmethod
    def _is_yandex_address(email_address, provider=""):
        normalized_provider = str(provider or "").strip().lower()
        if normalized_provider == "yandex":
            return True

        parts = str(email_address or "").strip().lower().rsplit("@", 1)
        if len(parts) != 2:
            return False

        domain = parts[1]
        return domain in {"yandex.com", "yandex.ru", "ya.ru", "yandex.by", "yandex.kz", "yandex.ua"}

    @staticmethod
    def _build_yandex_clone_email(main_email):
        email_text = str(main_email or "").strip()
        if not email_text or "@" not in email_text:
            return None

        local_part, domain = email_text.rsplit("@", 1)
        base_local = local_part.split("+", 1)[0].strip()
        domain = domain.strip()
        if not base_local or not domain:
            return None

        alias_suffix = f"{random.randint(0, 999999):06d}"
        return f"{base_local}+{alias_suffix}@{domain}"

    def _get_edit_text_fields(self, d, hints=()):
        try:
            edit_fields = list(d(className="android.widget.EditText"))
        except Exception:
            edit_fields = []

        if not hints or not edit_fields:
            return edit_fields

        ranked = []
        fallback = []
        for field in edit_fields:
            try:
                info = getattr(field, "info", {}) or {}
                label = " ".join(
                    str(info.get(key, "") or "")
                    for key in ("text", "hint", "contentDescription", "resourceId")
                ).lower()
                rank = sum(1 for hint in hints if hint in label)
                if rank > 0:
                    ranked.append((rank, field))
                else:
                    fallback.append(field)
            except Exception:
                fallback.append(field)

        ranked.sort(key=lambda item: item[0], reverse=True)
        ordered = [field for _, field in ranked]
        return ordered or fallback

    def _set_confirmation_code_inputs(self, d, edit_fields, code_text):
        if not edit_fields:
            return False

        if len(edit_fields) >= len(code_text) and len(code_text) <= 8:
            typed_digits = 0
            for index, digit in enumerate(code_text):
                if index >= len(edit_fields):
                    break
                field = edit_fields[index]
                if self._set_single_field_text(d, field, digit):
                    typed_digits += 1
            if typed_digits == len(code_text):
                return True

        return self._set_single_field_text(d, edit_fields[0], code_text)

    def _set_single_field_text(self, d, field, value):
        try:
            field.click()
            time.sleep(0.2)
            try:
                field.clear_text()
            except Exception:
                pass
            field.set_text(str(value))
            time.sleep(0.2)
            return True
        except Exception:
            try:
                d.send_keys(str(value), clear=True)
                time.sleep(0.2)
                return True
            except Exception:
                return False

    def _confirm_code_text_visible(self, edit_fields, code_text):
        combined_text = []
        for field in edit_fields:
            try:
                info = getattr(field, "info", {}) or {}
                current_text = str(info.get("text", "") or "").strip()
                if current_text:
                    combined_text.append(current_text)
            except Exception:
                continue

        visible_text = "".join(combined_text)
        return visible_text == code_text or code_text in visible_text

    def _submit_confirmation_code(self, d):
        return self._click_any_selector(
            d,
            [
                {"text": "Next"},
                {"text": "Continue"},
                {"text": "Confirm"},
                {"text": "Submit"},
                {"text": "OK"},
                {"textContains": "Next"},
                {"textContains": "Continue"},
                {"textContains": "Confirm"},
                {"textContains": "Submit"},
                {"descriptionContains": "Next"},
                {"descriptionContains": "Continue"},
            ],
            timeout=6,
            required=False,
        )

    def _generate_phone(self, prefix):
        digits = "".join(random.choices(string.digits, k=9))
        return f"{prefix}{digits}"

    def _generate_password(self):
        letters = "".join(random.choices(string.ascii_letters, k=7))
        digits = "".join(random.choices(string.digits, k=3))
        return f"{letters}{digits}Aa!"

    def _save_created_account(self, ld_name, ld_adb, profile, facebook_uid="", account_status=""):
        paths = get_app_paths()
        account_file = paths.config_dir / "created_accounts.json"
        record = {
            "facebook_uid": str(facebook_uid or "").strip(),
            "name": f"{profile.first_name} {profile.last_name}".strip(),
            "gender": profile.gender,
            "status": str(account_status or "").strip(),
            "phone": profile.contact_value if profile.contact_label == "phone" else "",
            "email": profile.contact_value if profile.contact_label == "email" else "",
            "password": profile.password,
            "ld_adb": str(ld_adb or "").strip(),
            "instance": str(ld_name or "").strip(),
            "device_name": str(ld_name or "").strip(),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }

        existing_records = []
        if account_file.exists():
            try:
                with account_file.open("r", encoding="utf-8") as handle:
                    loaded = json.load(handle)
                if isinstance(loaded, list):
                    existing_records = []
                    for row in loaded:
                        if not isinstance(row, dict):
                            continue
                        normalized = dict(row)
                        normalized.setdefault("gender", "")
                        normalized.setdefault("status", "")
                        existing_records.append(normalized)
            except (OSError, json.JSONDecodeError) as exc:
                self.log(f"Created account file was invalid, resetting it: {exc}")

        existing_records.append(record)
        _atomic_write_json(account_file, existing_records)
        self.log(f"Saved created account {profile.last_name} {profile.first_name}")

    def _check_and_allow_contacts_permission(self, d):
        try:
            page_text = []
            for element in d(className="android.widget.TextView"):
                text = str(element.info.get("text", "") or "").strip()
                if text:
                    page_text.append(text.lower())
        except Exception:
            page_text = []

        joined = " ".join(page_text)
        permission_markers = [
            "allow facebook to access your contacts",
            "access your contacts",
            "your contacts",
        ]
        if not any(marker in joined for marker in permission_markers):
            return False

        self.log("Contacts permission detected, clicking ALLOW")
        if self._click_any_selector(
            d,
            [
                {"text": "ALLOW"},
                {"text": "Allow"},
                {"textContains": "ALLOW"},
                {"textContains": "Allow"},
            ],
            timeout=5,
            required=False,
        ):
            time.sleep(2)
            return True

        try:
            buttons = list(d(className="android.widget.Button"))
            if len(buttons) >= 2:
                rightmost = max(
                    buttons,
                    key=lambda btn: (btn.info.get("bounds", {}) or {}).get("right", 0),
                )
                rightmost.click()
                self.log("Clicked right-side permission button")
                time.sleep(2)
                return True
        except Exception:
            pass

        self.log("Contacts permission dialog found but ALLOW was not clicked")
        return False

    def _check_and_skip_email_autofill_dialog(self, d):
        try:
            page_text = []
            for element in d(className="android.widget.TextView"):
                text = str(element.info.get("text", "") or "").strip()
                if text:
                    page_text.append(text.lower())
        except Exception:
            page_text = []

        joined = " ".join(page_text)
        markers = [
            "choose an email to autofill your details",
            "autofill your details",
            "autofill your contact info",
            "confirm your facebook account",
        ]
        if not any(marker in joined for marker in markers):
            return False

        self.log("Email autofill dialog detected, clicking SKIP")
        if self._click_any_selector(
            d,
            [
                {"text": "SKIP"},
                {"text": "Skip"},
                {"textContains": "SKIP"},
                {"textContains": "Skip"},
            ],
            timeout=5,
            required=False,
        ):
            time.sleep(2)
            return True

        try:
            buttons = list(d(className="android.widget.Button"))
            if buttons:
                leftmost = min(
                    buttons,
                    key=lambda btn: (btn.info.get("bounds", {}) or {}).get("left", 99999),
                )
                leftmost.click()
                self.log("Clicked left-side button for email autofill dialog")
                time.sleep(2)
                return True
        except Exception:
            pass

        self.log("Email autofill dialog found but SKIP was not clicked")
        return False

    def _start_registration_flow(self, d, name):
        self.push_runtime_state(name, task="Opening registration flow", progress=55)
        start_selectors = [
            {"textContains": "Get started"},
            {"text": "Create new Facebook account"},
            {"text": "Create new account"},
            {"textContains": "Create new"},
            {"textContains": "Sign up"},
            {"descriptionContains": "Create new"},
        ]
        if not self._click_any_selector(d, start_selectors, timeout=8):
            return False

        time.sleep(2)
        if self._click_any_selector(d, start_selectors, timeout=3, required=False):
            self.log("Registration entry still visible, clicked it again")
            time.sleep(2)

        self._click_any_selector(
            d,
            [
                {"text": "Get started"},
                {"text": "Next"},
                {"textContains": "Get started"},
            ],
            timeout=8,
            required=False,
        )
        time.sleep(2)
        return True

    def _fill_name_step(self, d, name, profile):
        self._check_and_skip_email_autofill_dialog(d)
        self._check_and_allow_contacts_permission(d)
        self.log(f"Entering name: {profile.first_name} {profile.last_name}")
        if not self._set_text_inputs(
            d,
            [profile.first_name, profile.last_name],
            hints=("first", "last", "surname", "given"),
        ):
            return False
        self.push_runtime_state(name, task="Name entered", progress=62)
        return self._tap_continue(d)

    def _fill_birthdate_step(self, d, name, profile):
        target_year = int(profile.birth_year)
        target_month = self.MONTHS[profile.birth_month - 1]
        target_day = str(int(profile.birth_day))
        self.log(
            f"Selecting birth date: {profile.birth_day:02d}/{profile.birth_month:02d}/{target_year}"
        )

        pickers = list(d(className="android.widget.NumberPicker"))
        if len(pickers) < 3:
            self.log("Birth date picker not found")
            return False

        detected = self._detect_date_pickers(pickers[:3])
        month_picker = detected.get("month")
        day_picker = detected.get("day")
        year_picker = detected.get("year")

        if not month_picker or not day_picker or not year_picker:
            self.log(f"Could not reliably detect all birth date pickers: {sorted(detected.keys())}")
            return False

        if not self._scroll_picker_to_value(d, month_picker, target_month, kind="month"):
            self.log(f"Failed to set month picker to {target_month}")
            return False

        if not self._scroll_picker_to_value(d, day_picker, target_day, kind="day", numeric_bounds=(1, 31)):
            self.log(f"Failed to set day picker to {target_day}")
            return False

        if not self._scroll_picker_to_value(
            d,
            year_picker,
            str(target_year),
            kind="year",
            numeric_bounds=(1900, 2100),
            max_attempts=25,
        ):
            self.log(f"Failed to set year picker to {target_year}")
            return False

        self.push_runtime_state(name, task="Birth date selected", progress=68)
        time.sleep(0.8)
        return self._tap_set_or_continue(d)

    def tap_i_agree(self, d, timeout=10):
        try:
            if self._click_any_selector(
                d,
                [
                    {"text": "I agree"},
                    {"textContains": "I agree"},
                    {"text": "Agree"},
                    {"textContains": "Agree"},
                    {"textContains": "Create account"},
                    {"textContains": "Sign up"},
                    {"textMatches": "(?i).*agree.*"},
                ],
                timeout=timeout,
                required=False,
            ):
                self.log("Agreement button tapped")
                time.sleep(2)
                return True

            self.log("Agreement button not shown, continuing to submit step")
            return False
        except Exception as exc:
            self.log(f"Failed while checking agreement button: {exc}")
            return False
    def _detect_date_pickers(self, pickers):
        detected = {}
        for picker in pickers:
            value = self._get_picker_center_value(picker)
            kind = self._classify_picker_value(value)
            if kind and kind not in detected:
                detected[kind] = picker
        return detected

    def _classify_picker_value(self, value):
        text = str(value or "").strip()
        if not text:
            return None

        month_text = text[:3].title()
        if month_text in self.MONTHS:
            return "month"

        if text.isdigit() and len(text) == 4:
            return "year"

        if text.isdigit():
            number = int(text)
            if 1 <= number <= 31:
                return "day"

        return None

    def _scroll_picker_to_value(self, d, picker, target, kind="generic", numeric_bounds=None, max_attempts=20):
        target = str(target).strip()
        for attempt in range(max_attempts):
            current = self._get_picker_center_value(picker)
            current_text = str(current or "").strip()
            if current_text == target:
                return True

            direction = self._decide_picker_direction(current_text, target, kind, numeric_bounds=numeric_bounds)
            step_scale = self._get_picker_step_scale(current_text, target, kind)

            if direction == "up":
                self._swipe_picker_up(d, picker, step_scale=step_scale)
            elif direction == "down":
                self._swipe_picker_down(d, picker, step_scale=step_scale)
            else:
                if attempt % 2 == 0:
                    self._swipe_picker_up(d, picker, step_scale=step_scale)
                else:
                    self._swipe_picker_down(d, picker, step_scale=step_scale)
            time.sleep(0.18 if kind == "year" else 0.35)

        self.log(f"[{kind}] smart picker scrolling failed, trying brute-force recovery")
        for direction, retries in (("up", 10), ("down", 15)):
            for _ in range(retries):
                current = self._get_picker_center_value(picker)
                if str(current or "").strip() == target:
                    return True
                if direction == "up":
                    self._swipe_picker_up(d, picker, step_scale=0.85 if kind == "year" else 0.55)
                else:
                    self._swipe_picker_down(d, picker, step_scale=0.85 if kind == "year" else 0.55)
                time.sleep(0.16 if kind == "year" else 0.25)

        return str(self._get_picker_center_value(picker) or "").strip() == target

    def _get_picker_step_scale(self, current, target, kind):
        if kind != "year":
            return 0.55

        try:
            current_num = int(str(current or "").strip())
            target_num = int(str(target or "").strip())
        except Exception:
            return 0.75

        gap = abs(target_num - current_num)
        if gap >= 15:
            return 0.90
        if gap >= 8:
            return 0.78
        if gap >= 4:
            return 0.65
        return 0.50

    def _get_picker_center_value(self, picker):
        try:
            children = picker.child(className="android.widget.EditText")
            if children.exists:
                try:
                    text = children.get_text()
                    if text:
                        return str(text).strip()
                except Exception:
                    pass

            info = picker.info
            text = str(info.get("text") or "").strip()
            if text:
                return text

            text_views = list(picker.descendants(className="android.widget.TextView"))
            if text_views:
                picker_bounds = info.get("bounds", {})
                picker_center_y = (picker_bounds["top"] + picker_bounds["bottom"]) // 2

                best_text = None
                best_dist = float("inf")
                for tv in text_views:
                    tv_info = tv.info
                    tv_text = str(tv_info.get("text") or "").strip()
                    bounds = tv_info.get("bounds", {})
                    cy = (bounds.get("top", 0) + bounds.get("bottom", 0)) // 2
                    dist = abs(cy - picker_center_y)
                    if tv_text and dist < best_dist:
                        best_dist = dist
                        best_text = tv_text
                if best_text:
                    return best_text

            for child in picker.children():
                try:
                    child_text = str(child.info.get("text") or "").strip()
                    if child_text:
                        return child_text
                except Exception:
                    continue
        except Exception:
            pass

        return None

    def _decide_picker_direction(self, current, target, kind, numeric_bounds=None):
        current = str(current or "").strip()
        target = str(target or "").strip()
        if not current or current == target:
            return None

        if kind == "month":
            month_map = {month: index for index, month in enumerate(self.MONTHS, start=1)}
            current_num = month_map.get(current[:3].title())
            target_num = month_map.get(target[:3].title())
        elif current.isdigit() and target.isdigit():
            current_num = int(current)
            target_num = int(target)
            if numeric_bounds is not None:
                min_value, max_value = numeric_bounds
                current_num = min(max_value, max(min_value, current_num))
                target_num = min(max_value, max(min_value, target_num))
        else:
            return None

        if current_num is None or target_num is None or current_num == target_num:
            return None

        # Default assumption: swipe up moves to a larger value.
        return "up" if target_num > current_num else "down"

    def _swipe_picker_up(self, d, picker, step_scale=0.55):
        bounds = (picker.info.get("bounds", {}) or {})
        left = int(bounds.get("left", 0))
        right = int(bounds.get("right", 0))
        top = int(bounds.get("top", 0))
        bottom = int(bounds.get("bottom", 0))
        cx = (left + right) // 2
        height = max(1, bottom - top)
        step_scale = min(0.9, max(0.35, float(step_scale)))
        center_y = (top + bottom) // 2
        delta = max(int(height * 0.18), int(height * step_scale * 0.5))
        start_y = min(bottom - 4, center_y + delta)
        end_y = max(top + 4, center_y - delta)

        try:
            d.swipe(cx, start_y, cx, end_y, 0.18)
        except Exception as exc:
            self.log(f"Picker swipe up failed: {exc}")

    def _swipe_picker_down(self, d, picker, step_scale=0.55):
        bounds = (picker.info.get("bounds", {}) or {})
        left = int(bounds.get("left", 0))
        right = int(bounds.get("right", 0))
        top = int(bounds.get("top", 0))
        bottom = int(bounds.get("bottom", 0))
        cx = (left + right) // 2
        height = max(1, bottom - top)
        step_scale = min(0.9, max(0.35, float(step_scale)))
        center_y = (top + bottom) // 2
        delta = max(int(height * 0.18), int(height * step_scale * 0.5))
        start_y = max(top + 4, center_y - delta)
        end_y = min(bottom - 4, center_y + delta)

        try:
            d.swipe(cx, start_y, cx, end_y, 0.18)
        except Exception as exc:
            self.log(f"Picker swipe down failed: {exc}")


    def _tap_set_or_continue(self, d):
        for label in ("SET", "Set"):
            btn = d(text=label)
            if btn.exists:
                btn.click()
                time.sleep(3)
                next_btn = d(textContains="Next")
                if next_btn.exists:
                    next_btn.click()
                    time.sleep(1)
                return True

        for label in ("OK", "Next", "Continue"):
            btn = d(text=label)
            if btn.exists:
                btn.click()
                time.sleep(1)
                return True

        next_btn = d(textContains="Next")
        if next_btn.exists:
            next_btn.click()
            time.sleep(1)
            return True
        return False
    def _fill_gender_step(self, d, name, profile):
        self.log(f"Selecting gender: {profile.gender}")
        gender_selectors = (
            [{"text": "Female"}, {"textContains": "Woman"}]
            if profile.gender.lower().startswith("f")
            else [{"text": "Male"}, {"textContains": "Man"}]
        )
        if not self._click_any_selector(d, gender_selectors, timeout=6):
            return False
        self.push_runtime_state(name, task="Gender selected", progress=74)
        return self._tap_continue(d)

    def _fill_contact_step(self, d, name, profile):
        self.log(f"Entering {profile.contact_label}: {profile.contact_value}")
        if profile.contact_label == "email":
            self._click_any_selector(
                d,
                [
                    {"textContains": "email"},
                    {"textContains": "Use email"},
                    {"textContains": "Sign up with email"},
                ],
                timeout=5,
                required=False,
            )
            hints = ("email", "mobile", "phone")
        else:
            hints = ("mobile", "phone", "number", "contact")

        if not self._set_text_inputs(d, [profile.contact_value], hints=hints, require_hint_match=True):
            return False
        self.push_runtime_state(name, task=f"{profile.contact_label.title()} entered", progress=80)
        return self._click_any_selector(
            d,
            [
                {"text": "Next"},
                {"text": "Continue"},
                {"textContains": "Next"},
                {"textContains": "Continue"},
            ],
            timeout=6,
            required=False,
        )
          
    def _fill_password_step(self, d, name, profile):
        self.log("Entering password")
        if not self._set_text_inputs(d, [profile.password], hints=("password",), require_hint_match=True):
            return False
        self.push_runtime_state(name, task="Password entered", progress=86)
        return self._tap_continue(d)

    def _handle_save_step(self, d, timeout=5):
        if self._click_any_selector(
            d,
            [
                {"text": "Save"},
                {"textContains": "Save"},
            ],
            timeout=timeout,
            required=False,
        ):
            self.log("Save button tapped")
            time.sleep(2)
            return True

        self.log("Save button not shown, continuing")
        return False

    def _submit_signup_step(self, d, name):
        self.log("Submitting create-account form")
        if not self._click_any_selector(
            d,
            [
                {"text": "Sign up"},
                {"textContains": "Get started"},
                {"textContains": "Sign up"},
                {"textContains": "I agree"},
                {"textContains": "Agree"},
                {"textContains": "Create account"},
            ],
            timeout=8,
            required=False,
        ):
            if not self._tap_continue(d, required=False):
                return False

        time.sleep(5)
        verification_markers = [
            {"textContains": "Enter the confirmation code"},
            {"textContains": "confirmation code"},
            {"textContains": "Check your email"},
            {"textContains": "We sent you a code"},
            {"textContains": "Confirm your account"},
        ]
        if self._selector_exists(d, verification_markers, timeout=8):
            self.push_runtime_state(name, task="Waiting for verification code", progress=94)
        return True

    def _handle_create_new_step(self, d):
        selectors = [
            {"text": "No, creating new account"},
            {"textContains": "No, creating new account"},
            {"description": "No, creating new account"},
            {"descriptionContains": "No, creating new account"},
            {"textContains": "creating new account"},
            {"descriptionContains": "creating new account"},
            {"textContains": "create new account"},
            {"descriptionContains": "create new account"}
        ]
        if self._click_any_selector(
            d,
            selectors,
            timeout=6,
            required=False,
        ):
            self.log("Handled existing-account prompt")
            return True

        try:
            buttons = [
                btn for btn in list(d(className="android.widget.Button"))
                if btn.exists and btn.info.get("enabled", True)
            ]
            button_labels = []
            for btn in buttons:
                info = getattr(btn, "info", {}) or {}
                label = " ".join(
                    str(info.get(key, "") or "")
                    for key in ("text", "contentDescription")
                ).strip()
                if label:
                    button_labels.append(label.lower())

            joined = " | ".join(button_labels)
            negative_markers = ("already have", "log in", "login", "sign in")
            if any(marker in joined for marker in negative_markers) and len(buttons) >= 2:
                rightmost = max(
                    buttons,
                    key=lambda btn: (btn.info.get("bounds", {}) or {}).get("right", 0),
                )
                rightmost.click()
                self.log("Clicked right-side button on existing-account prompt")
                time.sleep(2)
                return True
        except Exception:
            pass

        self.log("Existing-account prompt not shown, continuing")
        return False

    def _handle_contact_continue_step(self, d):
        
        if self._click_any_selector(
            d,
            [
                {"text": "Continue creating account"},
                {"textContains": "Continue creating account"},
                {"description": "Continue creating account"},
                {"descriptionContains": "Continue creating account"},
            ],
            timeout=5,
            required=False,
        ):
            return self._wait_for_password_step(d)

        if self._click_any_selector(
            d,
            [
                {"text": "Next"},
                {"text": "Continue"},
                {"textContains": "Next"},
                {"textContains": "Continue"},
                {"description": "Next"},
                {"description": "Continue"},
                {"descriptionContains": "Next"},
                {"descriptionContains": "Continue"},
            ],
            timeout=6,
            required=False,
        ):
            return self._wait_for_password_step(d)

        try:
            buttons = [
                btn for btn in list(d(className="android.widget.Button"))
                if btn.exists and btn.info.get("enabled", True)
            ]
            if buttons:
                rightmost = max(
                    buttons,
                    key=lambda btn: (btn.info.get("bounds", {}) or {}).get("right", 0),
                )
                rightmost.click()
                self.log("Clicked right-side action button after contact step")
                time.sleep(2)
                return self._wait_for_password_step(d)
        except Exception:
            pass

        self.log("No continue button detected after contact step")
        return False    

    def _tap_continue(self, d, required=True):
        return self._click_any_selector(
            d,
            [
                {"text": "Next"},
                {"text": "Continue"},
                {"textContains": "Next"},
                {"textContains": "Continue"},
            ],
            timeout=6,
            required=required,
        )

    def _selector_exists(self, d, selectors, timeout=3):
        deadline = time.time() + timeout
        while time.time() < deadline:
            for selector in selectors:
                try:
                    if d(**selector).exists:
                        return True
                except Exception:
                    continue
            time.sleep(0.5)
        return False

    def _click_any_selector(self, d, selectors, timeout=5, required=True):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.check_paused():
                return False
            for selector in selectors:
                try:
                    obj = d(**selector)
                    if obj.exists:
                        obj.click()
                        time.sleep(2)
                        return True
                except Exception:
                    continue
            time.sleep(0.5)
        return not required

    def _wait_for_password_step(self, d, timeout=8):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                for field in list(d(className="android.widget.EditText")):
                    info = getattr(field, "info", {}) or {}
                    label = " ".join(
                        str(info.get(key, "") or "")
                        for key in ("text", "hint", "contentDescription", "resourceId")
                    ).lower()
                    if "password" in label:
                        return True
            except Exception:
                pass

            if self._selector_exists(
                d,
                [
                    {"textContains": "password"},
                    {"descriptionContains": "password"},
                ],
                timeout=0.5,
            ):
                return True
            time.sleep(0.5)

        self.log("Password step did not appear after contact continue")
        return False

    def _set_text_inputs(self, d, values, hints=(), exact_count=None, require_hint_match=False):
        deadline = time.time() + 8
        while time.time() < deadline:
            edit_fields = []
            try:
                edit_fields = list(d(className="android.widget.EditText"))
            except Exception:
                edit_fields = []

            if hints and edit_fields:
                ranked = []
                for field in edit_fields:
                    info = getattr(field, "info", {}) or {}
                    label = " ".join(
                        str(info.get(key, "") or "")
                        for key in ("text", "hint", "contentDescription", "resourceId")
                    ).lower()
                    rank = 0
                    for hint in hints:
                        if hint in label:
                            rank += 1
                    ranked.append((rank, field))
                ranked.sort(key=lambda item: item[0], reverse=True)
                if require_hint_match:
                    edit_fields = [field for rank, field in ranked if rank > 0]
                else:
                    edit_fields = [field for _, field in ranked]

            if exact_count is not None and len(edit_fields) < exact_count:
                time.sleep(0.5)
                continue

            if len(edit_fields) >= len(values):
                for field, value in zip(edit_fields, values):
                    try:
                        field.click()
                        time.sleep(0.4)
                        field.clear_text()
                    except Exception:
                        pass
                    try:
                        field.set_text(str(value))
                    except Exception:
                        try:
                            d.send_keys(str(value), clear=True)
                        except Exception:
                            return False
                    time.sleep(0.8)
                return True

            time.sleep(0.5)

        return False

    # Detect if the account has been flagged for human verification
    def detect_human_confirm_screen(self, d, timeout=12):
        dead_phrases = (
            "confirm you're human",
            "confirm you are human",
            "confirm it's you",
            "confirm it is you",
            "confirm this is you",
            "verify it's you",
            "verify it is you",
            "verify your identity",
            "security check",
            "tap and hold",
        )

        # phrases from your screenshot
        active_phrases = (
            "add a profile picture",
            "add profile picture",
            "add a picture",
            "add picture",
            "everyone will be able to see your picture",
            "so your friends know it's you",
            "skip",
        )

        def _normalize(value):
            value = str(value or "").strip().lower()
            value = value.replace("\u2019", "'")   # smart quote -> normal quote
            value = re.sub(r"\s+", " ", value)     # collapse spaces/newlines
            return value

        def _exists_by_phrase(phrase):
            selectors = (
                {"textContains": phrase},
                {"descriptionContains": phrase},
            )
            for selector in selectors:
                try:
                    if d(**selector).exists:
                        return True
                except Exception:
                    pass
            return False

        deadline = time.time() + max(3, timeout)
        last_error = None

        while time.time() < deadline:
            try:
                # 1) DEAD check first
                for phrase in dead_phrases:
                    if _exists_by_phrase(phrase):
                        self.log(f"Human confirmation screen detected: {phrase}")
                        return "Dead"

                # 2) ACTIVE check for screen like screenshot
                # stronger check: heading + button/skip
                add_profile_title = (
                    _exists_by_phrase("add a profile picture") or
                    _exists_by_phrase("add profile picture")
                )
                add_picture_btn = _exists_by_phrase("add picture")
                skip_btn = _exists_by_phrase("skip")

                if add_profile_title and (add_picture_btn or skip_btn):
                    self.log("Profile picture screen detected")
                    return "Active"

                # 3) fallback from XML hierarchy
                xml_lower = _normalize(d.dump_hierarchy())

                # DEAD from XML
                if any(_normalize(p) in xml_lower for p in dead_phrases):
                    self.log("Human confirmation screen detected from UI hierarchy")
                    return "Dead"

                if "human" in xml_lower and ("confirm" in xml_lower or "verify" in xml_lower):
                    self.log("Human confirmation keywords detected from UI hierarchy")
                    return "Dead"

                # ACTIVE from XML
                active_hits = sum(1 for p in active_phrases if _normalize(p) in xml_lower)

                # require at least 2 signals to reduce false match
                if active_hits >= 2:
                    self.log("Profile picture screen detected from UI hierarchy")
                    return "Active"

            except Exception as exc:
                last_error = exc

            time.sleep(1)

        if last_error:
            self.log(f"Screen detection fallback to Novery. Last error: {last_error}")
        else:
            self.log("Screen not matched: returning Novery")

        return "Novery"

    def _check_Continue_creating_account(self, d):
        if self._click_any_selector(
            d,
            [
                {"text": "Continue creating account"},
                {"textContains": "Continue creating account"},
                {"description": "Continue creating account"},
                {"descriptionContains": "Continue creating account"},
            ],
            timeout=5,
            required=False,
        ):
            self.log("Tapped 'Continue creating account' before entering contact")
            time.sleep(2)
        else:
            self.log("'Continue creating account' not shown, continuing to contact entry")
