import base64
import hashlib
import hmac
import json
import re
import struct
import time
from datetime import datetime
from typing import Any, Callable, TYPE_CHECKING

from core.paths import get_app_paths
from core.settings import _atomic_write_json

class LoginHandlerMixin:
    if TYPE_CHECKING:
        emulator: Any
        last_renamed_to: str
        log: Callable[..., None]

        def check_paused(self) -> bool: ...
        def enter_confirmation_code(self, d: Any, otp_code: Any, timeout: int = 12) -> bool: ...
        def open_facebook(self, d: Any) -> bool: ...
        def _click_any_selector(
            self,
            d: Any,
            selectors: list[dict[str, Any]],
            timeout: int = 5,
            required: bool = True,
        ) -> bool: ...
        def _click_prompt_selector(self, d: Any, selectors: list[dict[str, Any]], timeout: int = 2) -> bool: ...
        def _reset_registration_apps(self, d: Any) -> bool: ...
        def _resolve_confirmation_email(self) -> str: ...
        def _selector_exists(self, d: Any, selectors: list[dict[str, Any]], timeout: int = 3) -> bool: ...
        def _set_text_inputs(
            self,
            d: Any,
            values: list[str],
            hints: tuple[str, ...] = (),
            exact_count: int | None = None,
            require_hint_match: bool = False,
        ) -> bool: ...
        def _wait_for_confirmation_otp(self, confirmation_email: str | None = None) -> str | None: ...

    # ------------------------------------------------------------------
    # Credentials & retry orchestration
    # ------------------------------------------------------------------

    def _build_credentials(self, kwargs):
        from core.tasks.login_account import LoginCredentials

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

    def _handle_skip_notifications_prompt(self, d, max_skips=6):
        """Click repeated post-login Skip/Not Now prompts until none remain."""
        selectors = [
            {"text": "Skip"},
            {"text": "SKIP"},
            {"text": "Skip for now"},
            {"text": "Not Now"},
            {"text": "Not now"},
            {"text": "NOT NOW"},
            {"text": "Maybe Later"},
            {"text": "Maybe later"},
            {"textContains": "Skip"},
            {"textContains": "skip"},
            {"textContains": "Not now"},
            {"textContains": "not now"},
            {"textContains": "Maybe later"},
            {"description": "Skip"},
            {"description": "Not Now"},
            {"description": "Not now"},
            {"descriptionContains": "Skip"},
            {"descriptionContains": "skip"},
            {"descriptionContains": "Not now"},
            {"descriptionContains": "not now"},
        ]

        skipped = 0
        for _ in range(max(1, int(max_skips))):
            if self.check_paused():
                break
            if not self._click_prompt_selector(d, selectors, timeout=2):
                break
            skipped += 1
            time.sleep(1.5)

        if skipped:
            self.log(f"Skipped {skipped} post-login prompt(s)")
        return skipped

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
            "Go to your authentication app",
            "authentication app"
        )):
            return "Otp"
        
        if any(p in xml for p in (
            "check your notifications on another device",
            "we sent a notification to your other device",
            "Waiting for approval on your other device",
        )):
            return "Otp2"
        
        # choose method screen
        if any(p in xml for p in (
            "choose a way to confirm",
            "confirm it's you",
            "notification on another device",
            "authentication app",
            "available confirmation methods",
        )):
            return "Otp2"

        if any(p in xml for p in (
            "wrong password",
            "incorrect password",
            "the password you entered is incorrect",
            "couldn't find your account",
            "account not found",
        )):
            return "WrongPassword"
        
        if any(p in xml for p in (
            "Save your login info?",
            "We'll save the login info for",
            "you restore."
        )):
            return "SussaveLogininfo"

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

    def _rename_ld_to_facebook_name(self, d, name, creds, account_name=""):
        """Rename the LDPlayer instance to the logged-in Facebook profile name.

        Resolution order:
          1. Profile name read from the Facebook app (most accurate)
          2. ``account_name`` from the saved account record (e.g. "Patrick R. Mcnutt")
          3. Credential identifier as last-resort fallback (uid/email/phone)
        """
        try:
            fb_name = self._extract_facebook_profile_name(d)
        except Exception as exc:
            self.log(f"Could not read Facebook profile name on {name}: {exc}")
            fb_name = None

        candidate = (fb_name or "").strip()
        if not candidate:
            candidate = (account_name or "").strip()
        if not candidate:
            candidate = (getattr(creds, "identifier", "") or "").strip()

        new_name = self._sanitize_ld_name(candidate)
        if not new_name or new_name == name:
            return False

        # Avoid colliding with another LD that already has this name.
        existing = set(getattr(self.emulator, "name_to_serial", {}).keys())
        if new_name in existing:
            new_name = self._unique_ld_name(new_name, existing)

        rename_fn = getattr(self.emulator, "rename_ld", None)
        if not callable(rename_fn):
            self.log("Emulator does not support rename; skipping LD rename")
            return False

        if rename_fn(name, new_name):
            self.log(f"Renamed LD '{name}' to '{new_name}'")
            # Expose the new name so the caller (dashboard worker) can sync
            # its persisted instance record after the task completes.
            self.last_renamed_to = new_name
            return True
        self.log(f"Failed to rename LD '{name}' to '{new_name}'")
        return False

    def _extract_facebook_profile_name(self, d):
        """Best-effort extraction of the logged-in account's display name.

        Tries the bookmarks/menu tab where the profile name is typically a
        large header item. Falls back to None if nothing matches.
        """
        # Open the Menu/bookmarks tab where the profile entry lives.
        tab_selectors = [
            {"descriptionMatches": r"(?i)^menu$"},
            {"descriptionContains": "Menu"},
            {"resourceIdMatches": r".*(tab_bar_menu|tab_menu|menu_tab).*"},
        ]
        for sel in tab_selectors:
            try:
                node = d(**sel)
                if node.exists:
                    node.click()
                    time.sleep(2.5)
                    break
            except Exception:
                continue

        # Profile entry on the Menu screen is typically a button whose
        # contentDescription is "<Name>, profile" or just "<Name>".
        candidates = [
            {"resourceIdMatches": r".*profile_switcher.*"},
            {"resourceIdMatches": r".*(menu_profile|profile_name|profile_entry).*"},
            {"descriptionMatches": r"(?i).+,\s*profile"},
        ]
        for sel in candidates:
            try:
                matches = d(**sel)
                count = int(getattr(matches, "count", 0) or (1 if matches.exists else 0))
                for idx in range(min(count, 5)):
                    node = matches[idx] if count > 1 else matches
                    info = node.info or {}
                    text = (info.get("text") or "").strip()
                    desc = (info.get("contentDescription") or "").strip()
                    name = text or desc
                    if not name:
                        continue
                    # Strip trailing ", profile" / ", button" suffixes.
                    for suffix in (", profile", ", button", " profile", " button"):
                        if name.lower().endswith(suffix):
                            name = name[: -len(suffix)].rstrip(", ").strip()
                    if name and len(name) <= 64:
                        return name
            except Exception:
                continue

        return None

    @staticmethod
    def _sanitize_ld_name(raw):
        """Return a name safe for use as an LDPlayer instance title."""
        if not raw:
            return ""
        # LDPlayer titles cannot contain path/quote characters.
        forbidden = '\\/:*?"<>|'
        cleaned = "".join(ch for ch in str(raw) if ch not in forbidden).strip()
        # Collapse internal whitespace.
        cleaned = " ".join(cleaned.split())
        return cleaned[:48]

    @staticmethod
    def _unique_ld_name(base, existing):
        if base not in existing:
            return base
        for i in range(2, 100):
            candidate = f"{base} ({i})"
            if candidate not in existing:
                return candidate
        return f"{base} ({int(time.time())})"

    def _check_sucessful_login(self, d, name, timeout=10):
        """Confirm a successful login by detecting the Facebook home indicator.

        The Facebook home feed exposes an element with
        contentDescription="Facebook logo" (//android.view.View[@content-desc="Facebook logo"]).
        Seeing it is a strong signal we landed on the feed.
        """
        try:
            if d(description="Facebook logo").wait(timeout=timeout):
                self.log(f"Login confirmed via Facebook logo on {name}")
                return True
        except Exception as exc:
            self.log(f"Facebook logo detection failed for {name}: {exc}")
        return False

    def _is_logged_in_xml(self, xml_lower):
        markers = (
            "what's on your mind"
            "news feed"
            "stories"
            "marketplace"
            "tab_feed"
            "feed_tab"
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

    def handle_facebook_2fa(self, d, timeout=60):
        def log(msg):
            try:
                self.log(msg)
            except:
                print(msg)

        def click_if_exists(selector, timeout=2):
            try:
                obj = d(**selector)
                if obj.exists(timeout=timeout):
                    obj.click()
                    time.sleep(1)
                    return True
            except:
                pass
            return False

        def click_text_contains(text, timeout=2):
            try:
                obj = d(textContains=text)
                if obj.exists(timeout=timeout):
                    obj.click()
                    time.sleep(1)
                    log(f"Clicked: {text}")
                    return True
            except:
                pass
            return False

        start = time.time()

        while time.time() - start < timeout:
            xml = ""
            try:
                xml = d.dump_hierarchy().lower()
            except:
                pass

            # =========================
            # STEP 1: Click "Try another way"
            # =========================
            if "check your notifications" in xml or "waiting for approval" in xml:
                log("STEP 1: Found approval screen")

                # click immediately (NO 15s delay)
                d.swipe_ext("up", scale=0.5)
                if click_text_contains("Try another way"):
                    log("Clicked Try another way â†’ moving to step 2")
                    time.sleep(2)
                    continue

            # =========================
            # STEP 2: Select Authentication app
            # =========================
            if "choose a way to confirm" in xml or "authentication app" in xml:
                log("STEP 2: Found method selection screen")

                # select Authentication app radio
                if click_text_contains("authentication app"):
                    log("Selected Authentication app")

                    time.sleep(1)

                    # =========================
                    # STEP 3: Click Continue
                    # =========================
                    if click_if_exists({"text": "Continue"}):
                        log("Clicked Continue")
                        return "auth_app_selected"

                    # fallback (important for FB UI)
                    try:
                        w, h = d.window_size()
                        d.click(w // 2, int(h * 0.93))
                        log("Fallback Continue click")
                        return "auth_app_selected"
                    except:
                        pass

            time.sleep(1)

        log("2FA handling timeout")
        return False
