import base64
import hashlib
import hmac
import json
import struct
import time
from dataclasses import dataclass
from datetime import datetime

from core.logic.reg_account import RegAccountTaskHandler
from core.paths import get_app_paths
from core.settings import _atomic_write_json
from core.task_base import U2_AVAILABLE, u2
from utils.ip_guard import check_ld_ip_allowed


@dataclass(slots=True)
class LoginCredentials:
    identifier: str  # email, phone, or username
    password: str
    label: str = ""  # "email" | "phone" | "username" (free-form, for record)


class LoginAccountTaskHandler(RegAccountTaskHandler):
    """Log into an existing Facebook account in the mobile app."""

    LOGIN_PACKAGE = "com.facebook.katana"
    LOGIN_ACTIVITY = "com.facebook.katana.LoginActivity"

    def execute(self, name, duration=300, **kwargs):
        if self.check_paused():
            return False

        creds = self._build_credentials(kwargs)
        if not creds:
            self.log(f"Login skipped for {name}: missing identifier or password")
            return False

        verify_2fa = bool(kwargs.get("verify_2fa", True))
        twofa_email = (kwargs.get("twofa_email") or "").strip()
        twofa_secret = (
            kwargs.get("twofa_secret")
            or kwargs.get("twofa")
            or kwargs.get("two_factor_secret")
            or ""
        )
        twofa_secret = str(twofa_secret or "").strip()

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
            boot_timeout = max(90, int(getattr(self.emulator, "boot_delay", 20)) * 6)
            if not self.ensure_device_ready(name, timeout=boot_timeout):
                self.log(f"Device not ready after startup: {name}")
                return False

        if not self.ensure_device_ready(name, timeout=60):
            self.log(f"Device is not ready for login task: {name}")
            return False

        blocked_countries = getattr(self, "blocked_countries", None)
        if blocked_countries and not check_ld_ip_allowed(serial, blocked_countries, self.log, ld_name=name):
            try:
                if hasattr(self.emulator, "quit_ld"):
                    self.emulator.quit_ld(name)
            except Exception:
                pass
            return False

        try:
            if not U2_AVAILABLE:
                self.log("uiautomator2 not available. Cannot run login task.")
                return False
            d = u2.connect(serial)
        except Exception as exc:
            self.log(f"Failed to connect {serial}: {exc}")
            return False

        self.push_runtime_state(name, state="Running", task="Opening Facebook", progress=20)
        if not self.open_facebook(d):
            self.log(f"Failed to open Facebook on {name}")
            return False

        self.push_runtime_state(name, state="Running", task="Submitting credentials", progress=45)
        if not self._run_login_steps_with_retry(d, name, creds):
            return False

        time.sleep(8)

        login_status = self._detect_login_status(d)
        self.log(f"Detected login status for {name}: {login_status}")

        if login_status == "WrongPassword":
            self.log(f"Login failed for {name}: wrong credentials")
            return False

        if login_status == "Otp" and (verify_2fa or twofa_secret):
            handled_2fa = False
            if twofa_secret:
                handled_2fa = self.handle_2fa(d, twofa_secret=twofa_secret)
                if not handled_2fa:
                    self.log(f"Failed to submit app 2FA code for {name}")

            if not handled_2fa and verify_2fa:
                otp_code = self._resolve_login_otp(twofa_email)
                if not otp_code:
                    self.log(f"Login OTP required but no code available for {name}")
                    return False
                if not self.enter_confirmation_code(d, otp_code):
                    self.log(f"Failed to submit login OTP for {name}")
                    return False
            elif not handled_2fa:
                return False
            time.sleep(8)
            login_status = self._detect_login_status(d)
            self.log(f"Post-OTP login status for {name}: {login_status}")

        if login_status == "Checkpoint" or self.detect_human_confirm_screen(d) == "Dead":
            self.log(f"Login blocked by checkpoint/human-verify for {name}")
            return False

        self._handle_save_login_info_prompt(d)
        time.sleep(4)

        # Confirm we landed on the feed
        if not self._is_logged_in(d):
            self.log(f"Could not confirm logged-in state for {name}")
            return False

        facebook_uid = ""
        try:
            facebook_uid = self.check_uid_account(d, before_ids=before_ids)
        except Exception as exc:
            self.log(f"UID lookup after login failed for {name}: {exc}")

        self._save_logged_account(name, serial, creds, facebook_uid=facebook_uid)
        self.push_runtime_state(name, state="Completed", task="Logged in", progress=100)
        self.log(f"Login complete for {name} (uid={facebook_uid or 'unknown'})")
        return True

    # ------------------------------------------------------------------
    # Credentials & retry orchestration
    # ------------------------------------------------------------------

    def _build_credentials(self, kwargs):
        identifier = (
            kwargs.get("identifier")
            or kwargs.get("email")
            or kwargs.get("phone")
            or kwargs.get("username")
            or ""
        )
        identifier = str(identifier).strip()
        password = str(kwargs.get("password") or "").strip()
        if not identifier or not password:
            return None

        label = str(kwargs.get("identifier_label") or "").strip().lower()
        if not label:
            if "@" in identifier:
                label = "email"
            elif identifier.lstrip("+").isdigit():
                label = "phone"
            else:
                label = "username"

        return LoginCredentials(identifier=identifier, password=password, label=label)

    def _run_login_steps_with_retry(self, d, name, creds, retries=2, retry_delay=4):
        total_attempts = retries + 1
        for attempt in range(1, total_attempts + 1):
            if self._run_login_steps_once(d, name, creds):
                return True

            if attempt >= total_attempts:
                self.log(f"Login flow failed for {name} after {attempt} attempts")
                return False

            self.log(f"Login attempt {attempt}/{retries} failed for {name}, retrying in {retry_delay}s")
            time.sleep(retry_delay)
            self._reset_registration_apps(d)
            time.sleep(2)
            if not self.open_facebook(d):
                continue
        return False

    def _run_login_steps_once(self, d, name, creds):
        # Some Facebook builds show a landing screen before the login form.
        self._open_existing_account_login(d)

        # If an account picker shows up, jump to "Log into another account".
        self._dismiss_account_picker(d)

        if not self._fill_identifier(d, creds.identifier):
            self.log(f"Could not enter identifier for {name}")
            return False

        if not self._fill_password(d, creds.password):
            self.log(f"Could not enter password for {name}")
            return False

        if not self._submit_login(d):
            self.log(f"Could not tap Log In button for {name}")
            return False

        return True

    # ------------------------------------------------------------------
    # Login UI steps
    # ------------------------------------------------------------------

    def _open_existing_account_login(self, d):
        """Tap the pre-login entry point before entering credentials."""
        clicked = self._click_xpath(
            d,
            '//android.widget.Button[@content-desc="I already have an account"]/android.view.ViewGroup',
            timeout=3,
            required=False,
        )
        if clicked:
            return True

        return self._click_any_selector(
            d,
            [
                {"description": "I already have an account"},
                {"descriptionContains": "I already have an account"},
                {"text": "I already have an account"},
                {"textContains": "already have an account"},
            ],
            timeout=3,
            required=False,
        )

    def _click_xpath(self, d, xpath_expr, timeout=5, required=True):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.check_paused():
                return False
            try:
                obj = d.xpath(xpath_expr)
                if obj.exists:
                    obj.click()
                    time.sleep(2)
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        return not required

    def _dismiss_account_picker(self, d):
        """If FB shows a saved-account picker, route to the explicit login form."""
        return self._click_any_selector(
            d,
            [
                {"text": "Log into another account"},
                {"text": "Log Into Another Account"},
                {"textContains": "another account"},
                {"text": "Switch account"},
                {"textContains": "Switch account"},
            ],
            timeout=3,
            required=False,
        )

    def _fill_identifier(self, d, identifier):
        return self._set_text_inputs(
            d,
            [identifier],
            hints=("email", "phone", "mobile", "username", "log in", "user"),
            require_hint_match=False,
        )

    def _fill_password(self, d, password):
        # Password input is the second EditText on the standard FB login screen,
        # but on some layouts it's the only field on a follow-up screen.
        deadline = time.time() + 8
        while time.time() < deadline:
            try:
                fields = list(d(className="android.widget.EditText"))
            except Exception:
                fields = []

            password_field = None
            for field in fields:
                info = getattr(field, "info", {}) or {}
                label = " ".join(
                    str(info.get(key, "") or "")
                    for key in ("text", "hint", "contentDescription", "resourceId")
                ).lower()
                is_password = bool(info.get("password")) or "password" in label
                if is_password:
                    password_field = field
                    break

            if password_field is None and len(fields) >= 2:
                password_field = fields[1]

            if password_field is not None:
                try:
                    password_field.click()
                    time.sleep(0.3)
                    password_field.clear_text()
                except Exception:
                    pass
                try:
                    password_field.set_text(password)
                    time.sleep(0.5)
                    return True
                except Exception:
                    try:
                        d.send_keys(password, clear=True)
                        return True
                    except Exception:
                        return False

            time.sleep(0.5)

        return False

    def _submit_login(self, d):
        return self._click_any_selector(
            d,
            [
                {"text": "Log In"},
                {"text": "Log in"},
                {"text": "LOG IN"},
                {"description": "Log In"},
                {"descriptionContains": "Log In"},
                {"textContains": "Log in"},
                {"resourceIdMatches": r".*login_login_button.*"},
            ],
            timeout=8,
            required=False,
        )

    def _handle_save_login_info_prompt(self, d):
        # Decline saving by default to keep app in a clean state across runs.
        self._click_any_selector(
            d,
            [
                {"text": "Not Now"},
                {"text": "Not now"},
                {"text": "NOT NOW"},
                {"text": "Skip"},
                {"text": "SKIP"},
                {"textContains": "Not now"},
            ],
            timeout=4,
            required=False,
        )

    # ------------------------------------------------------------------
    # State detection
    # ------------------------------------------------------------------

    def _detect_login_status(self, d):
        """Inspect the screen and classify post-login state.

        Returns one of: "Otp", "WrongPassword", "Checkpoint", "Ok", "Unknown".
        """
        try:
            xml = d.dump_hierarchy().lower()
        except Exception:
            return "Unknown"

        if any(p in xml for p in (
            "enter login code",
            "two-factor authentication",
            "enter the code",
            "enter the confirmation code",
            "we sent a code",
            "approve from another device",
        )):
            return "Otp"

        if any(p in xml for p in (
            "wrong password",
            "incorrect password",
            "the password you entered is incorrect",
            "couldn't find your account",
            "account not found",
        )):
            return "WrongPassword"

        if any(p in xml for p in (
            "account suspended",
            "we suspended your account",
            "confirm your identity",
            "confirm it's you",
            "we need to confirm",
            "review login",
        )):
            return "Checkpoint"

        if self._is_logged_in_xml(xml):
            return "Ok"

        return "Unknown"

    def _is_logged_in_xml(self, xml_lower):
        markers = (
            "what's on your mind",
            "whats on your mind",
            "news feed",
            "stories",
            "marketplace",
            "tab_feed",
            "feed_tab",
        )
        return any(m in xml_lower for m in markers)

    def _is_logged_in(self, d):
        try:
            return self._is_logged_in_xml(d.dump_hierarchy().lower())
        except Exception:
            return False

    # ------------------------------------------------------------------
    # App-based 2FA
    # ------------------------------------------------------------------

    def handle_2fa(self, d, twofa_secret="", code=None, timeout=12):
        if not code:
            code = self._generate_totp_code(twofa_secret)
        code = str(code or "").strip()
        if not code:
            self.log("2FA skipped: no app code could be generated")
            return False
        if not code.isdigit() or len(code) != 6:
            self.log(f"Invalid 2FA code generated: {code}")
            return False

        if not self._looks_like_2fa_screen(d):
            self.log("2FA screen text not matched; trying app code input anyway")

        self.log("2FA screen detected; entering app code")
        if not self.enter_confirmation_code(d, code, timeout=timeout):
            return False

        self._trust_login_device_if_present(d)
        return True

    def _generate_totp_code(self, secret, for_time=None, period=30, digits=6):
        clean_secret = "".join(str(secret or "").split()).upper()
        if not clean_secret:
            return ""
        padding = "=" * ((8 - len(clean_secret) % 8) % 8)
        try:
            key = base64.b32decode(clean_secret + padding, casefold=True)
        except Exception as exc:
            self.log(f"Invalid 2FA secret: {exc}")
            return ""

        counter = int((time.time() if for_time is None else for_time) // period)
        digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        token = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
        return str(token % (10 ** digits)).zfill(digits)

    def _looks_like_2fa_screen(self, d):
        selectors = [
            {"textContains": "authentication app"},
            {"descriptionContains": "authentication app"},
            {"textContains": "Enter the 6-digit code"},
            {"descriptionContains": "Enter the 6-digit code"},
            {"textContains": "login code"},
            {"descriptionContains": "login code"},
            {"textContains": "two-factor"},
            {"descriptionContains": "two-factor"},
        ]
        return self._selector_exists(d, selectors, timeout=2)

    def _trust_login_device_if_present(self, d):
        try:
            if self._selector_exists(
                d,
                [
                    {"textContains": "Trust this device"},
                    {"descriptionContains": "Trust this device"},
                ],
                timeout=1,
            ):
                checkbox = d(className="android.widget.CheckBox")
                if checkbox.exists(timeout=1):
                    info = getattr(checkbox, "info", {}) or {}
                    if not info.get("checked", False):
                        checkbox.click()
                        self.log("Checked Trust this device.")
        except Exception as exc:
            self.log(f"Could not handle Trust this device option: {exc}")

    # ------------------------------------------------------------------
    # OTP retrieval
    # ------------------------------------------------------------------

    def _resolve_login_otp(self, twofa_email):
        """Try to fetch an OTP via the same email pipeline registration uses."""
        if not twofa_email:
            twofa_email = self._resolve_confirmation_email() or ""
        if not twofa_email:
            return ""
        try:
            return self._wait_for_confirmation_otp(twofa_email) or ""
        except Exception as exc:
            self.log(f"OTP fetch error: {exc}")
            return ""

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_logged_account(self, ld_name, ld_adb, creds, facebook_uid=""):
        paths = get_app_paths()
        account_file = paths.config_dir / "logged_accounts.json"
        record = {
            "facebook_uid": str(facebook_uid or "").strip(),
            "identifier": creds.identifier,
            "identifier_label": creds.label,
            "email": creds.identifier if creds.label == "email" else "",
            "phone": creds.identifier if creds.label == "phone" else "",
            "username": creds.identifier if creds.label == "username" else "",
            "password": creds.password,
            "ld_adb": str(ld_adb or "").strip(),
            "instance": str(ld_name or "").strip(),
            "device_name": str(ld_name or "").strip(),
            "logged_at": datetime.now().isoformat(timespec="seconds"),
        }

        existing = []
        if account_file.exists():
            try:
                with account_file.open("r", encoding="utf-8") as handle:
                    loaded = json.load(handle)
                if isinstance(loaded, list):
                    existing = [row for row in loaded if isinstance(row, dict)]
            except (OSError, json.JSONDecodeError) as exc:
                self.log(f"Logged account file was invalid, resetting it: {exc}")

        existing.append(record)
        _atomic_write_json(account_file, existing)
        self.log(f"Saved logged account record for {creds.identifier}")
