import json
import random
import string
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime

import re

from core.email_models import EmailAccountConfig, OTPRequest
from core.tasks.task_scroll import ScrollTaskHandler
from core.tasks.handler.handler_reg import RegAccountHandlerMixin
from core.paths import get_app_paths
from core.settings import SettingsError, _atomic_write_json, load_app_settings
from core.task_base import U2_AVAILABLE, u2
from services.otp_service import OTPService
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


class RegAccountTaskHandler(RegAccountHandlerMixin, ScrollTaskHandler):
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
        "Kong", "Wright", "Scott", "Torres", "Nguyen",

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
        verify = kwargs.get("verify", True)
        before_facebook_ids = []

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

        try:
            before_facebook_ids = self.get_facebook_account_ids_from_settings(d)
            self.log(f"Facebook IDs before registration for {name}: {before_facebook_ids}")
        except Exception as exc:
            before_facebook_ids = []
            self.log(f"Failed to capture Facebook IDs before registration for {name}: {exc}")

        if not self._run_registration_steps_with_retry(d, name, profile):
            return False

        time.sleep(20)

        account_status = self.detect_account_status(d)
        self.log(f"Detected account status for {name}: {account_status}")

        if account_status == "Unknown":
            verify = False
            self.log(f"Account status is unknown for {name}, skipping verification steps")
        confirmation_email = None
        # ------------------------------------------------------------------------------------
        # Account Verification Steps
        # After registration steps, check if we hit verification (OTP) screen or got suspended
        if verify:
            time.sleep(2)
            self.log(f"Verifying account for {profile.first_name} {profile.last_name}")
            time.sleep(2)

            self._handle_didnt_get_code_step(d)
            time.sleep(3)

            self._handle_confirm_by_email(d)
            time.sleep(3)
            
            confirmation_email = self._resolve_confirmation_email()
            if not confirmation_email:
                self.log(f"No confirmation email available for {name}")
            elif not self.enter_email(d, confirmation_email):
                self.log(f"Failed to enter confirmation email for {name}")

            time.sleep(10)

            otp_code = self._wait_for_confirmation_otp(confirmation_email)
            if not otp_code:
                self.log(f"Failed to retrieve confirmation code for {name}")
                return False
            if not self.enter_confirmation_code(d, otp_code):
                self.log(f"Failed to enter confirmation code for {name}")
                return False
             
            time.sleep(10)
            account_status= self.detect_human_confirm_screen(d)
            if account_status == "Dead":
                self.log(f"Account {name} was flagged for human verification → DEAD")
                return False
            
        facebook_uid = ""
        if account_status == "Unknown":
            self.log(f"Account status is Unknown for {name}, skipping Facebook UID detection")
        else:
            time.sleep(10)
            d.app_stop("com.facebook.katana")
            time.sleep(4)
        
            d.app_start("com.facebook.katana")
            time.sleep(7)

            d.app_stop("com.facebook.katana")
            time.sleep(3)

            facebook_uid = self.check_uid_account(d, before_ids=before_facebook_ids)
            if facebook_uid == "":
                self.log(f"UID resolution failed on first attempt for {name}, retrying once")
                time.sleep(3)
                facebook_uid = self.check_uid_account(d, before_ids=before_facebook_ids)
            if facebook_uid == "":
                self.log(f"Failed to create Facebook account {name}")
                return False

        time.sleep(3)

        if not self._submit_signup_step(d, name):
            self.log(f"Failed on final signup step for {name}")
            return False
        
        if not account_status == "Unknown":
            self._save_created_account(
                name,
                serial,
                profile,
                facebook_uid=facebook_uid,
                account_status=account_status,
            )
            time.sleep(3)
            self.log(f"Account created successfully for {name} with UID: {facebook_uid}")
            self.log(f"Account status for {name}: {account_status}")
            self.log(f"Create-account flow completed on LD: {name}")
            self.log(f"Generated account {profile.contact_label}: {profile.contact_value}")
            self.log(f"Generated account password: {profile.password}")
            self.push_runtime_state(name, state="Completed", task="Account form submitted", progress=100)

        time.sleep(5)
        # Reset Facebook app data after registration to avoid stale sessions.
        self._clear_app_data(d, "com.facebook.katana", name=name)

        return True
    
    
