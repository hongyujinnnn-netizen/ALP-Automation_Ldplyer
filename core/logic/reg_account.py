import random
import string
import time
from dataclasses import dataclass

from core.logic.task_scroll import ScrollTaskHandler
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
        "Liam", "Noah", "Mason", "Ethan", "Lucas", "Ava", "Emma", "Mia", "Sofia", "Ella",
    ]
    LAST_NAMES = [
        "Smith", "Johnson", "Brown", "Taylor", "Anderson", "Thomas", "Martin", "Walker",
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

        self.log(f"Opening Facebook: {name}")
        if not self.open_facebook(d):
            self.log(f"Failed to open Facebook for registration: {name}")
            return False

        self.push_runtime_state(name, state="Running", task="Starting registration", progress=45)
        if not self._start_registration_flow(d, name):
            self.log(f"Could not open create-account flow on {name}")
            return False

        self._check_and_skip_email_autofill_dialog(d)
        self._check_and_allow_contacts_permission(d)

        if not self._fill_name_step(d, name, profile):
            self.log(f"Failed on name step for {name}")
            return False
        
        time.sleep(2)

        if not self._fill_birthdate_step(d, name, profile):
            self.log(f"Failed on birth date step for {name}")
            return False
        
        time.sleep(2)

        if not self._fill_gender_step(d, name, profile):
            self.log(f"Failed on gender step for {name}")
            return False

        time.sleep(2)

        if not self._fill_contact_step(d, name, profile):
            self.log(f"Failed on contact step for {name}")
            return False
        
        time.sleep(2)

        if not self._fill_password_step(d, name, profile):
            self.log(f"Failed on password step for {name}")
            return False
        
        time.sleep(2)

        self.tap_i_agree(d)
        
        if not self._submit_signup_step(d, name):
            self.log(f"Failed on final signup step for {name}")
            return False

        self.log(f"Create-account flow completed on LD: {name}")
        self.log(f"Generated account {profile.contact_label}: {profile.contact_value}")
        self.log(f"Generated account password: {profile.password}")
        self.push_runtime_state(name, state="Completed", task="Account form submitted", progress=100)
        return True

    def _build_profile(self, kwargs):
        first_name = str(kwargs.get("first_name") or random.choice(self.FIRST_NAMES))
        last_name = str(kwargs.get("last_name") or random.choice(self.LAST_NAMES))
        birth_day = int(kwargs.get("birth_day") or random.randint(23, 25))
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

        if mode == "fixed_email" and fixed_value:
            return "email", fixed_value
        if mode == "fixed_phone" and fixed_value:
            return "phone", fixed_value
        if mode == "random_phone":
            return "phone", self._generate_phone(phone_prefix)
        return "email", self._generate_email(first_name, last_name)

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
        target_year = random.randint(2005, 2007)

        pickers = list(d(className="android.widget.NumberPicker"))
        if len(pickers) < 3:
            self.log("Birth date picker not found")
            return False

        targets = [
            self.MONTHS[profile.birth_month - 1],   # month text like "Aug"
            str(profile.birth_day),            # day like "19"
            str(target_year),                  # year like "1994"
        ]

        for index, (picker, target) in enumerate(zip(pickers[:3], targets)):
            year_bounds = (2005, 2007) if index == 2 else None
            if not self._scroll_picker_to_value(d, picker, target, numeric_bounds=year_bounds):
                self.log(f"Failed to set picker to {target}")
                return False

        self.log(
            f"Selecting birth date: {profile.birth_day:02d}/{profile.birth_month:02d}/{target_year}"
        )
        self.push_runtime_state(name, task="Birth date selected", progress=68)
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
    def _scroll_picker_to_value(self, d, picker, target, max_attempts=30, numeric_bounds=None):
        for _ in range(max_attempts):
            current = self._get_picker_center_value(picker)
            if current is None:
                time.sleep(0.2)
                continue

            if str(current).strip() == str(target).strip():
                return True

            bounds = picker.info.get("bounds", {})
            cx = (bounds["left"] + bounds["right"]) // 2
            top = bounds["top"] + int((bounds["bottom"] - bounds["top"]) * 0.25)
            bottom = bounds["bottom"] - int((bounds["bottom"] - bounds["top"]) * 0.25)

            if numeric_bounds is not None:
                try:
                    current_num = int(str(current).strip())
                    target_num = int(str(target).strip())
                    min_year, max_year = numeric_bounds
                    current_num = min(max_year, max(min_year, current_num))
                    target_num = min(max_year, max(min_year, target_num))
                    if current_num < target_num:
                        d.swipe(cx, bottom, cx, top, 0.15)
                    else:
                        d.swipe(cx, top, cx, bottom, 0.15)
                except Exception:
                    d.swipe(cx, bottom, cx, top, 0.15)
            else:
                d.swipe(cx, bottom, cx, top, 0.15)
            time.sleep(0.4)

        return False


    def _get_picker_center_value(self, picker):
        try:
            children = picker.child(className="android.widget.EditText")
            if children.exists:
                return children.get_text()

            text_views = list(picker.descendants(className="android.widget.TextView"))
            if not text_views:
                return None

            picker_bounds = picker.info.get("bounds", {})
            picker_center_y = (picker_bounds["top"] + picker_bounds["bottom"]) // 2

            best_text = None
            best_dist = float("inf")

            for tv in text_views:
                info = tv.info
                text = info.get("text", "").strip()
                bounds = info.get("bounds", {})
                cy = (bounds.get("top", 0) + bounds.get("bottom", 0)) // 2
                dist = abs(cy - picker_center_y)

                if text and dist < best_dist:
                    best_dist = dist
                    best_text = text

            return best_text
        except Exception:
            return None


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

        if not self._set_text_inputs(d, [profile.contact_value], hints=hints):
            return False
        self.push_runtime_state(name, task=f"{profile.contact_label.title()} entered", progress=80)
        return self._tap_continue(d)

    def _fill_password_step(self, d, name, profile):
        self.log("Entering password")
        if not self._set_text_inputs(d, [profile.password], hints=("password",)):
            return False
        self.push_runtime_state(name, task="Password entered", progress=86)
        return self._tap_continue(d)

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

    def _set_text_inputs(self, d, values, hints=(), exact_count=None):
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
