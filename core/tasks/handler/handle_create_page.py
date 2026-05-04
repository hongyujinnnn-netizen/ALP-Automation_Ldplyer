import json
import time
from datetime import datetime

from core.paths import get_app_paths
from core.settings import _atomic_write_json


class CreatePageHandlerMixin:
    """UI steps to create a new Facebook Page from the mobile app.

    Assumes the LD instance is already logged in. Mirrors the structure of
    LoginHandlerMixin: a single retry-wrapped flow built from small,
    selector-based steps.
    """

    # ------------------------------------------------------------------
    # Profile & retry orchestration
    # ------------------------------------------------------------------

    def _build_page_profile(self, kwargs):
        from core.tasks.create_page import PageProfile

        page_name = str(kwargs.get("page_name") or kwargs.get("name") or "").strip()
        if not page_name:
            return None

        category = str(kwargs.get("category") or kwargs.get("page_category") or "").strip()
        bio = str(kwargs.get("bio") or "").strip()
        return PageProfile(name=page_name, category=category, bio=bio)

    def _run_create_page_steps_with_retry(self, d, ld_name, profile, retries=2, retry_delay=4):
        total_attempts = retries + 1
        for attempt in range(1, total_attempts + 1):
            if self._run_create_page_steps_once(d, ld_name, profile):
                return True

            if attempt >= total_attempts:
                self.log(f"Create-page flow failed for {ld_name} after {attempt} attempts")
                return False

            self.log(f"Create-page attempt {attempt}/{retries} failed for {ld_name}, retrying in {retry_delay}s")
            time.sleep(retry_delay)
            try:
                d.app_stop("com.facebook.katana")
                time.sleep(2)
            except Exception:
                pass
            if not self.open_facebook(d):
                continue
        return False

    def _run_create_page_steps_once(self, d, ld_name, profile):
        if not self._open_menu_tab(d):
            self.log(f"Could not open Menu tab on {ld_name}")
            return False

        if not self._open_pages_section(d):
            self.log(f"Could not open Pages section on {ld_name}")
            return False

        if not self._tap_create_new_page(d):
            self.log(f"Could not find Create-Page entry on {ld_name}")
            return False

        if not self._tap_get_started(d):
            self.log("No Get Started button — assuming we are already on the form")

        if not self._fill_page_name(d, profile.name):
            self.log(f"Could not enter page name for {ld_name}")
            return False

        if not self._tap_next(d):
            self.log("Could not advance after page name; trying to continue anyway")

        submitted = False
        if profile.category:
            # _fill_page_category now also clicks Create after the suggestion
            # is picked, so a successful return means the form is submitted.
            if self._fill_page_category(d, profile.category):
                submitted = True
            else:
                self.log(f"Category step failed for {ld_name}; falling back to Create button")

        if not submitted and not self._tap_create_page_submit(d):
            self.log(f"Could not submit Create Page on {ld_name}")
            return False

        time.sleep(10)
        self._handle_next_notifications_prompt(d)
        return True

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _open_menu_tab(self, d):
        return self._click_any_selector(
            d,
            [
                {"descriptionMatches": r"(?i)^menu$"},
                {"descriptionContains": "Menu"},
                {"resourceIdMatches": r".*(tab_bar_menu|tab_menu|menu_tab).*"},
                {"text": "Menu"},
            ],
            timeout=8,
            required=False,
        )

    def _open_pages_section(self, d):
        # Some FB builds need a scroll inside Menu to reveal "Pages".
        for _ in range(4):
            if self._click_any_selector(
                d,
                [
                    {"text": "Pages"},
                    {"description": "Pages"},
                    {"textContains": "Pages"},
                    {"descriptionContains": "Pages"},
                    {"resourceIdMatches": r".*(pages_entry|menu_pages).*"},
                ],
                timeout=3,
                required=False,
            ):
                time.sleep(2)
                return True
            try:
                d.swipe_ext("up", scale=0.6)
            except Exception:
                break
            time.sleep(0.6)
        return False

    def _tap_create_new_page(self, d):
        """
        Tap 'Create' / 'Create Page' button in Facebook Pages screen.
        Handles multiple UI variants + fallback.
        """

        selectors = [
            # 🔥 Primary (top chip button)
            {"text": "Create", "className": "android.view.ViewGroup"},
            {"textContains": "Create", "className": "android.view.ViewGroup"},

            # 🔥 Variants
            {"text": "Create new Page"},
            {"textContains": "Create new Page"},
            {"textContains": "Create a Page"},

            # 🔥 Accessibility (very common in FB)
            {"description": "Create"},
            {"descriptionContains": "Create"},

            # 🔥 Resource-based (rare but strong if exists)
            {"resourceIdMatches": r".*(create|page_create|pages_create).*"},
        ]

        for sel in selectors:
            try:
                el = d(**sel)

                if el.exists(timeout=2):
                    el.click()
                    self.log(f"[Create Page] Clicked using selector: {sel}")
                    return True

            except Exception as e:
                self.log(f"[Create Page] Selector failed {sel} → {e}")

        # ⚠️ Fallback: click near top chip area (based on your screenshot)
        try:
            self.log("[Create Page] Fallback → coordinate tap")
            d.click(88, 203)  # adjust if needed
            return True
        except Exception as e:
            self.log(f"[Create Page] Fallback failed → {e}")

        return False

    def _tap_get_started(self, d):
        return self._click_any_selector(
            d,
            [
                {"text": "Next"},
                {"text": "Get started"},
                {"textContains": "Get started"},
                {"textContains": "Next"},
                {"descriptionContains": "Get started"},
            ],
            timeout=4,
            required=False,
        )

    # ------------------------------------------------------------------
    # Form fields
    # ------------------------------------------------------------------

    def _fill_page_name(self, d, page_name):
        return self._set_text_inputs(
            d,
            [page_name],
            hints=("page name", "name your page", "name"),
            require_hint_match=False,
        )

    def _fill_page_category(self, d, category="Digital creator"):
        """
        Page-category flow:
          1. Type the category into the search input
          2. Click the matching suggestion row
          3. Wait until the Create button becomes enabled
          4. Click Create
        """
        if not category:
            category = "Digital creator"

        category_clean = category.strip()
        category_lower = category_clean.lower()

        # ── STEP 1: Type category ─────────────────────────────────────
        if not self._set_text_inputs(
            d,
            [category_clean],
            hints=("category", "search categor", "choose one category"),
            require_hint_match=False,
        ):
            self.log("[Page Category] Failed to type category")
            return False
        time.sleep(1.5)

        # ── STEP 2: Click suggestion ──────────────────────────────────
        if not self._click_category_suggestion(d, category_clean, category_lower):
            self.log("[Page Category] Could not select a suggestion")
            return False
        time.sleep(1.0)

        # ── STEP 3: Wait for Create button to become enabled ──────────
        create_btn = self._wait_for_create_enabled(d, timeout=12)
        if create_btn is None:
            self.log("[Page Category] Create button never became enabled")
            return False

        # ── STEP 4: Click Create ──────────────────────────────────────
        try:
            create_btn.click()
            self.log("[Page Category] Clicked Create")
        except Exception as exc:
            self.log(f"[Page Category] Click Create failed: {exc}")
            return False
        time.sleep(2)
        return True

    def _click_category_suggestion(self, d, category_clean, category_lower):
        """
        Click the first category suggestion row under the Facebook Page category input.

        Example:
            User types: digital
            First suggestion: Digital creator

        Strategy:
            1. Find visible suggestion text under input
            2. Click first matching suggestion row
            3. Try known first-row XPath
            4. Try UiSelector instance fallback
            5. Coordinate fallback
        """

        import time

        typed = (category_clean or "").strip()
        typed_lower = (category_lower or typed.lower()).strip()

        if not typed_lower:
            self.log("[Page Category] Empty category keyword")
            return False

        time.sleep(1)

        # Based on your screenshot:
        # input field is around y=188-235
        # first suggestion row starts around y=236
        MIN_SUGGESTION_Y = 235
        MAX_SUGGESTION_Y = 350

        def _get_bounds(info):
            bounds = info.get("bounds") or {}
            return (
                bounds.get("left", 0),
                bounds.get("top", 0),
                bounds.get("right", 0),
                bounds.get("bottom", 0),
            )

        def _is_valid_suggestion_node(info):
            text = (info.get("text") or "").strip()
            desc = (info.get("contentDescription") or "").strip()
            left, top, right, bottom = _get_bounds(info)

            # Skip empty/icon nodes
            if not text and not desc:
                return False

            # Skip input field and anything above it
            if bottom <= MIN_SUGGESTION_Y:
                return False

            # Skip popular chips lower down
            if top > MAX_SUGGESTION_Y:
                return False

            combined = f"{text} {desc}".lower()

            # typed "digital" should match "Digital creator"
            if typed_lower not in combined:
                return False

            return True

        # STEP 1: Search visible nodes and click first matching suggestion text
        try:
            candidates = []

            for node in d.xpath("//*").all():
                try:
                    info = node.info or {}

                    if not _is_valid_suggestion_node(info):
                        continue

                    text = (info.get("text") or "").strip()
                    desc = (info.get("contentDescription") or "").strip()
                    left, top, right, bottom = _get_bounds(info)

                    candidates.append((top, left, node, text, desc, info))

                except Exception:
                    continue

            candidates.sort(key=lambda item: (item[0], item[1]))

            if candidates:
                top, left, node, text, desc, info = candidates[0]
                node.click()
                self.log(
                    f"[Page Category] Clicked matching suggestion: "
                    f"text='{text}', desc='{desc}', bounds={info.get('bounds')}"
                )
                return True

        except Exception as exc:
            self.log(f"[Page Category] Suggestion scan failed: {exc}")

        # STEP 2: Try your known first-row XPath
        # This is layout-specific, so keep it as fallback, not primary.
        first_row_xpaths = [
            # Safer relative version: first ViewGroup inside second RecyclerView
            '(//androidx.recyclerview.widget.RecyclerView)[2]/android.view.ViewGroup/android.view.ViewGroup[1]',

            # More direct version based on your inspector path
            '(//android.widget.FrameLayout[@resource-id="com.facebook.katana:id/(name removed)"])[2]'
            '/android.view.ViewGroup/android.view.ViewGroup/android.view.ViewGroup'
            '/androidx.recyclerview.widget.RecyclerView/android.view.ViewGroup/android.view.ViewGroup[2]'
            '/androidx.recyclerview.widget.RecyclerView/android.view.ViewGroup/android.view.ViewGroup[1]',
        ]

        for xp in first_row_xpaths:
            try:
                node = d.xpath(xp)

                if node.exists:
                    info = node.info or {}
                    node.click()
                    self.log(f"[Page Category] Clicked first suggestion row by XPath: {xp}, info={info}")
                    return True

            except Exception as exc:
                self.log(f"[Page Category] First-row XPath failed: {xp} -> {exc}")

        # STEP 3: UiSelector instance fallback
        # Warning: instance(7) can change, but this matches what you found.
        try:
            el = d(className="android.view.ViewGroup", instance=7)

            if el.exists(timeout=1):
                el.click()
                self.log("[Page Category] Clicked first suggestion row by UiSelector instance(7)")
                return True

        except Exception as exc:
            self.log(f"[Page Category] UiSelector instance fallback failed: {exc}")

        # STEP 4: Coordinate fallback from your screenshot
        try:
            self.log("[Page Category] Fallback coordinate tap on first suggestion row")
            d.click(95, 252)
            return True

        except Exception as exc:
            self.log(f"[Page Category] Coordinate fallback failed: {exc}")
            return False

    def _wait_for_create_enabled(self, d, timeout=12):
        """Poll the Create button until ``info['enabled']`` is True.

        Returns the matched UI node, or ``None`` if the button stays disabled.
        """
        selectors = [
            {"text": "Create"},
            {"text": "Create Page"},
            {"description": "Create"},
            {"descriptionContains": "Create"},
            {"resourceIdMatches": r".*(create_page_button|page_create_submit|create_button).*"},
        ]

        deadline = time.time() + max(1, int(timeout))
        while time.time() < deadline:
            if self.check_paused():
                return None
            for sel in selectors:
                try:
                    node = d(**sel)
                    if not node.exists:
                        continue
                    info = getattr(node, "info", {}) or {}
                    if info.get("enabled", False):
                        self.log("[Page Category] Create button is enabled")
                        return node
                except Exception:
                    continue
            time.sleep(0.5)
        return None

    def _tap_next(self, d):
        return self._click_any_selector(
            d,
            [
                {"text": "Next"},
                {"text": "NEXT"},
                {"description": "Next"},
                {"resourceIdMatches": r".*(next_button|button_next).*"},
            ],
            timeout=5,
            required=False,
        )

    def _tap_create_page_submit(self, d):
        return self._click_any_selector(
            d,
            [
                {"text": "Create Page"},
                {"text": "Create"},
                {"text": "Done"},
                {"description": "Create Page"},
                {"resourceIdMatches": r".*(create_page_button|page_create_submit).*"},
            ],
            timeout=8,
            required=False,
        )

    # ------------------------------------------------------------------
    # State detection
    # ------------------------------------------------------------------

    def _detect_create_page_status(self, d):
        """Classify the post-submit screen.

        Returns one of: "Created", "Blocked", "Unknown".
        """
        try:
            xml = d.dump_hierarchy().lower()
        except Exception:
            return "Unknown"

        if any(p in xml for p in (
            "your page is ready",
            "page created",
            "welcome to your page",
            "invite friends to like",
        )):
            return "Created"

        if any(p in xml for p in (
            "you can't create a page",
            "page creation is unavailable",
            "we limit how often",
            "action blocked",
            "confirm your identity",
        )):
            return "Blocked"

        return "Unknown"

    def _confirm_page_created(self, d, timeout=15):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._detect_create_page_status(d) == "Created":
                return True
            time.sleep(1)
        return False

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_created_page(self, ld_name, serial, profile):
        paths = get_app_paths()
        pages_file = paths.config_dir / "created_pages.json"
        record = {
            "page_name": profile.name,
            "category": profile.category,
            "bio": profile.bio,
            "instance": str(ld_name or "").strip(),
            "device_name": str(ld_name or "").strip(),
            "ld_adb": str(serial or "").strip(),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }

        existing = []
        if pages_file.exists():
            try:
                with pages_file.open("r", encoding="utf-8") as handle:
                    loaded = json.load(handle)
                if isinstance(loaded, list):
                    existing = [row for row in loaded if isinstance(row, dict)]
            except (OSError, json.JSONDecodeError) as exc:
                self.log(f"Created-pages file was invalid, resetting it: {exc}")

        existing.append(record)
        _atomic_write_json(pages_file, existing)
        self.log(f"Saved created page record for '{profile.name}'")

    def _handle_next_notifications_prompt(self, d, max_next=12):
        """Click repeated post-login next/Not Now prompts until none remain."""
        selectors = [
            {"text": "Next"},
            {"text": "NEXT"},
            {"text": "next"},
            {"text": "Done"},
            {"text": "DONE"},
            {"text": "done"},
            {"text": "Skip"},
            {"text": "SKIP"},
            {"text": "Skip for now"},
            {"text": "Not Now"},
            {"text": "Not now"},
            {"text": "NOT NOW"},
            {"text": "Maybe Later"},
            {"text": "Maybe later"},
            {"textContains": "Next"},
            {"textContains": "next"},
            {"textContains": "Done"},
            {"textContains": "done"},
            {"textContains": "Skip"},
            {"textContains": "skip"},
            {"textContains": "Go to feed"},
            {"textContains": "Not now"},
            {"textContains": "not now"},
            {"textContains": "Maybe later"},
            {"description": "Next"},
            {"description": "Done"},
            {"description": "Skip"},
            {"description": "Not Now"},
            {"description": "Not now"},
            {"descriptionContains": "Next"},
            {"descriptionContains": "next"},
            {"descriptionContains": "Done"},
            {"descriptionContains": "done"},
            {"descriptionContains": "Skip"},
            {"descriptionContains": "skip"},
            {"descriptionContains": "Go to feed"},
            {"descriptionContains": "Not now"},
            {"descriptionContains": "not now"},
            {"descriptionContains": "Maybe later"},
        ]

        skipped = 0
        for _ in range(max(1, int(max_next))):
            if self.check_paused():
                break
            if not self._click_prompt_selector(d, selectors, timeout=2):
                break
            skipped += 1
            time.sleep(1.5)

        if skipped:
            self.log(f"next {skipped} post-login prompt(s)")
        return skipped
