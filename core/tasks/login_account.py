import time
from dataclasses import dataclass

from core.tasks.handler.handler_login import LoginHandlerMixin
from core.tasks.reg_account import RegAccountTaskHandler
from utils.ip_guard import check_ld_ip_allowed


@dataclass(slots=True)
class LoginCredentials:
    identifier: str  # email, phone, or username
    password: str
    label: str = ""  # "email" | "phone" | "username" (free-form, for record)


class LoginAccountTaskHandler(LoginHandlerMixin, RegAccountTaskHandler):
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

        account_name = str(kwargs.get("account_name") or "").strip()
        verify_2fa = bool(kwargs.get("verify_2fa", True))
        twofa_email = (kwargs.get("twofa_email") or "").strip()
        twofa_secret = (
            kwargs.get("twofa_secret") or kwargs.get("twofa") or kwargs.get("two_factor_secret") or ""
        )
        twofa_secret = str(twofa_secret or "").strip()

        # Start the LD instance first so the serial mapping is populated
        # before we try to connect ADB. Running the login task on a stopped
        # LD previously failed because the serial lookup fell back to the
        # friendly name and ADB connect could not resolve it.
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

        serial = self.emulator.name_to_serial.get(name)
        if not serial:
            self.log(f"No serial found for {name}")
            return False

        if not self._ensure_adb_connection(serial):
            self.log(f"Failed to connect to device {serial}")
            return False

        blocked_countries = getattr(self, "blocked_countries", None)
        if blocked_countries and not check_ld_ip_allowed(serial, blocked_countries, self.log, ld_name=name):
            try:
                if hasattr(self.emulator, "quit_ld"):
                    self.emulator.quit_ld(name)
            except Exception:
                pass
            return False

        self.push_runtime_state(name, state="Running", task="Opening Facebook", progress=20)
        success, d, serial = self.open_facebook_with_recovery(name, serial, max_retries=1)
        if not success:
            self.log(f"Failed to open Facebook on {name}")
            return False

        self.push_runtime_state(name, state="Running", task="Submitting credentials", progress=45)
        if not self._run_login_steps_with_retry(d, name, creds):
            return False

        if self.interruptible_sleep(12):
            return False

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
            if self.interruptible_sleep(8):
                return False
            login_status = self._detect_login_status(d)
            self.log(f"Post-OTP login status for {name}: {login_status}")

        if login_status == "Otp2":
            if self.handle_facebook_2fa(d):
                handled_2fa = self.handle_2fa(d, twofa_secret=twofa_secret)
                if self.interruptible_sleep(5):
                    return False
                if not handled_2fa:
                    self.log(f"Failed to submit Facebook 2FA code for {name}")
                    return False
            else:
                self.log(f"Failed to handle Facebook 2FA for {name}")
                return False

        if login_status == "Checkpoint":
            self.log(f"Login blocked by checkpoint/human-verify for {name}")
            return False

        if login_status == "SussaveLogininfo":
            self.log(f"Login is succeeded for {name}, status: {login_status}")

        time.sleep(2)
        self._handle_save_login_info_prompt(d)
        if self.interruptible_sleep(4):
            return False
        self._handle_skip_notifications_prompt(d)
        if self.interruptible_sleep(4):
            return False

        sucess = self._check_sucessful_login(d, name)
        if not sucess:
            self.log(f"Login flow did not complete successfully for {name}")
            return False

        self.log(f"Login flow completed successfully for {name}")

        # Rename the LD instance to the Facebook profile name so the logged
        # account is easy to identify in the device list.
        self._rename_ld_to_facebook_name(d, name, creds, account_name=account_name)

        return True
