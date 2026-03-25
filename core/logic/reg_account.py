import json
import random
import string
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime

import re
from typing import Optional

from core.logic.task_scroll import ScrollTaskHandler
from core.paths import get_app_paths
from core.settings import _atomic_write_json
from core.task_base import U2_AVAILABLE, u2
from utils.ip_guard import check_ld_ip_allowed


@dataclass(slots=True)
class AccountProfile:
    first_name: str
    last_name: str
    birth_day: int
    birth_month: int
    birth_year: int
    gender: str
    contact_value: str
    contact_label: str
    password: str


class RegAccountTaskHandler(ScrollTaskHandler):
    """Create a Facebook account using the mobile app flow."""


    MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    FIRST_NAMES = [
        "Liam", "Noah", "Mason", "Ethan", "Lucas",
        "Ava", "Emma", "Mia", "Sofia", "Ella",

        "James", "William", "Benjamin", "Elijah", "Oliver",
        "Henry", "Alexander", "Michael", "Daniel", "Jacob",

        "Logan", "Jackson", "Levi", "Sebastian", "Mateo",
        "Jack", "Owen", "Theodore", "Aiden", "Samuel",

        "Joseph", "John", "David", "Wyatt", "Matthew",
        "Luke", "Asher", "Carter", "Julian", "Grayson",

        "Leo", "Jayden", "Gabriel", "Isaac", "Lincoln",
        "Anthony", "Hudson", "Dylan", "Ezra", "Thomas",

        "Charlotte", "Amelia", "Harper", "Evelyn", "Abigail",
        "Emily", "Ella", "Elizabeth", "Camila", "Luna",

        "Sofia", "Avery", "Mila", "Aria", "Scarlett",
        "Penelope", "Layla", "Chloe", "Victoria", "Madison",

        "Eleanor", "Grace", "Nora", "Riley", "Zoey",
        "Hannah", "Lily", "Addison", "Aubrey", "Ellie",

        "Stella", "Natalie", "Zoe", "Leah", "Hazel",
        "Violet", "Aurora", "Savannah", "Audrey", "Brooklyn"
    ]

    LAST_NAMES = [
        "Smith", "Johnson", "Brown", "Taylor", "Anderson",
        "Thomas", "Martin", "Walker", "White", "Harris",

        "Clark", "Lewis", "Robinson", "Young", "Allen",
        "King", "Wright", "Scott", "Torres", "Nguyen",

        "Hill", "Flores", "Green", "Adams", "Nelson",
        "Baker", "Hall", "Rivera", "Campbell", "Mitchell",

        "Carter", "Roberts", "Gomez", "Phillips", "Evans",
        "Turner", "Diaz", "Parker", "Cruz", "Edwards",

        "Collins", "Stewart", "Morris", "Rogers", "Reed",
        "Cook", "Morgan", "Bell", "Murphy", "Bailey",

        "Cooper", "Richardson", "Cox", "Howard", "Ward",
        "Peterson", "Gray", "Ramirez", "James", "Watson",

        "Brooks", "Kelly", "Sanders", "Price", "Bennett",
        "Wood", "Barnes", "Ross", "Henderson", "Coleman",

        "Jenkins", "Perry", "Powell", "Long", "Patterson",
        "Hughes", "Washington", "Butler", "Simmons", "Foster"
    ]

    def execute(self, name, duration=300, **kwargs):
        if self.check_paused():
            return False

        profile = self._build_profile(kwargs)
        serial = self.emulator.name_to_serial.get(name, name)
        if not serial:
            self.log(f"No serial found for {name}")
            return False

        if not self._ensure_adb_connection(serial):
            self.log(f"Failed to connect to device {serial}")
            return False

        if not self.emulator.is_ld_running(name):
            if not self.emulator.start_ld(name):
                self.log(f"Failed to start LD: {name}")
                return False
            self.auto_arrange_ld_windows()
            self.log(f"Waiting for emulator ready: {name}")
            if not self.ensure_device_ready(name, timeout=max(90, int(getattr(self.emulator, "boot_delay", 20)) * 6)):
                self.log(f"Device not ready after startup: {name}")
                return False

        if not self.ensure_device_ready(name, timeout=60):
            self.log(f"Device is not ready for registration task: {name}")
            return False

        blocked_countries = getattr(self, "blocked_countries", None)
        if blocked_countries:
            if not check_ld_ip_allowed(serial, blocked_countries, self.log, ld_name=name):
                try:
                    if hasattr(self.emulator, "quit_ld"):
                        self.emulator.quit_ld(name)
                except Exception:
                    pass
                return False

        try:
            if not U2_AVAILABLE:
                self.log("uiautomator2 not available. Cannot run registration task.")
                return False
            d = u2.connect(serial)
        except Exception as exc:
            self.log(f"Failed to connect {serial}: {exc}")
            return False

        if not self._run_registration_steps_with_retry(d, name, profile):
            return False
        
        time.sleep(4)

        self._handle_save_step(d)
        self.tap_i_agree(d)

        self._handle_create_new_step(d)

        time.sleep(20)
        account_status = self.detect_account_status(d)
        self.log(f"Detected account status for {name}: {account_status}")

        d.app_stop("com.facebook.katana")
        time.sleep(3)
        
        d.app_start("com.facebook.katana", "com.facebook.katana.LoginActivity")
        time.sleep(10)

        d.app_stop("com.facebook.katana")
        time.sleep(3)
        
        facebook_uid = self.check_uid_account(d)

        time.sleep(3)

        if not self._submit_signup_step(d, name):
            self.log(f"Failed on final signup step for {name}")
            return False

        self._save_created_account(
            name,
            serial,
            profile,
            facebook_uid=facebook_uid,
            account_status=account_status,
        )
        self.log(f"Create-account flow completed on LD: {name}")
        self.log(f"Generated account {profile.contact_label}: {profile.contact_value}")
        self.log(f"Generated account password: {profile.password}")
        self.push_runtime_state(name, state="Completed", task="Account form submitted", progress=100)
        return True

    def _run_registration_steps_with_retry(self, d, name, profile, retries=2, retry_delay=3):
        total_attempts = retries + 1
        for attempt in range(1, total_attempts + 1):
            ok, failed_step = self._run_registration_steps_once(d, name, profile)
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

    def _run_registration_steps_once(self, d, name, profile):
        self.log(f"Opening Facebook: {name}")
        if not self.open_facebook(d):
            self.log(f"Failed to open Facebook for registration: {name}")
            return False, "open_facebook"

        self.push_runtime_state(name, state="Running", task="Starting registration", progress=45)
        if not self._start_registration_flow(d, name):
            self.log(f"Could not open create-account flow on {name}")
            return False, "start_registration_flow"

        self._check_and_skip_email_autofill_dialog(d)
        self._check_and_allow_contacts_permission(d)

        if not self._fill_name_step(d, name, profile):
            self.log(f"Failed on name step for {name}")
            return False, "name"

        time.sleep(3)

        if not self._fill_birthdate_step(d, name, profile):
            try:
                self._fill_contact_step(d, name, profile)
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

        if not self._fill_contact_step(d, name, profile):
            self.log(f"Failed on contact step for {name}")
            return False, "contact"

        time.sleep(2)
        if not self._handle_contact_continue_step(d):
            self.log(f"Failed on contact continue step for {name}")
            return False, "contact_continue"

        time.sleep(4)

        if not self._fill_password_step(d, name, profile):
            self.log(f"Failed on password step for {name}")
            return False, "password"

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
            return "Error"


    def check_uid_account(self, d):
        if d is None:
            self.log("Cannot check Facebook UID without a device session")
            return ""

        if not self._open_settings_accounts(d):
            return ""
        time.sleep(3)

        account_number_uid = self.detect_facebook_account_number(d)
        if account_number_uid:
            self.log(f"Detected Facebook account number: {account_number_uid}")
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
            self.log(f"Searching Accounts in Settings (attempt {attempt + 1}/{max_scrolls})")

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

    def detect_facebook_account_number(self, d) -> Optional[str]:
        """
        Try to detect the numeric Facebook account on the Accounts screen.
        """
        for _ in range(5):
            try:
                text_views = list(d(className="android.widget.TextView"))
            except Exception:
                text_views = []

            for i, node in enumerate(text_views):
                try:
                    text = (node.info.get("text") or "").strip()
                    if not text:
                        continue

                    if re.fullmatch(r"\d{10,20}", text):
                        return text

                    if "facebook" in text.lower():
                        for j in range(max(0, i - 3), min(len(text_views), i + 4)):
                            near_text = (text_views[j].info.get("text") or "").strip()
                            if re.fullmatch(r"\d{10,20}", near_text):
                                return near_text
                except Exception:
                    continue

            try:
                scrollable = d(scrollable=True)
                if scrollable.exists:
                    scrollable.scroll.vert.forward(steps=25)
                else:
                    d.swipe(360, 1180, 360, 420, 0.2)
            except Exception:
                try:
                    d.swipe(360, 1180, 360, 420, 0.2)
                except Exception:
                    pass
            time.sleep(1)

        return None

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
        self.log(f"Saved created account to {account_file}")

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

            if direction == "up":
                self._swipe_picker_up(d, picker)
            elif direction == "down":
                self._swipe_picker_down(d, picker)
            else:
                if attempt % 2 == 0:
                    self._swipe_picker_up(d, picker)
                else:
                    self._swipe_picker_down(d, picker)
            time.sleep(0.35)

        self.log(f"[{kind}] smart picker scrolling failed, trying brute-force recovery")
        for direction, retries in (("up", 8), ("down", 16)):
            for _ in range(retries):
                current = self._get_picker_center_value(picker)
                if str(current or "").strip() == target:
                    return True
                if direction == "up":
                    self._swipe_picker_up(d, picker)
                else:
                    self._swipe_picker_down(d, picker)
                time.sleep(0.25)

        return str(self._get_picker_center_value(picker) or "").strip() == target

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

    def _swipe_picker_up(self, d, picker):
        bounds = (picker.info.get("bounds", {}) or {})
        left = int(bounds.get("left", 0))
        right = int(bounds.get("right", 0))
        top = int(bounds.get("top", 0))
        bottom = int(bounds.get("bottom", 0))
        cx = (left + right) // 2
        start_y = bottom - int((bottom - top) * 0.28)
        end_y = top + int((bottom - top) * 0.28)

        try:
            d.swipe(cx, start_y, cx, end_y, 0.18)
        except Exception as exc:
            self.log(f"Picker swipe up failed: {exc}")

    def _swipe_picker_down(self, d, picker):
        bounds = (picker.info.get("bounds", {}) or {})
        left = int(bounds.get("left", 0))
        right = int(bounds.get("right", 0))
        top = int(bounds.get("top", 0))
        bottom = int(bounds.get("bottom", 0))
        cx = (left + right) // 2
        start_y = top + int((bottom - top) * 0.28)
        end_y = bottom - int((bottom - top) * 0.28)

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
        self.log("Checking for Save button")
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
        self.log("Checking for existing-account prompt")
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
