from __future__ import annotations

import html
import re
from html.parser import HTMLParser

DEFAULT_OTP_PATTERNS: list[str] = [
    r"(?i)\bverification code(?:\s+is|\s*[:=-])?\s*([0-9]{4,8})\b",
    r"(?i)\botp(?:\s+code)?(?:\s+is|\s*[:=-])?\s*([0-9]{4,8})\b",
    r"(?i)\bsecurity code(?:\s+is|\s*[:=-])?\s*([0-9]{4,8})\b",
    r"(?i)\b(?:one[- ]time|confirmation|confirm(?:ation)?)\s+(?:password|passcode|code)(?:\s+is|\s*[:=-])?\s*([0-9]{4,8})\b",
    r"(?i)\bcode(?:\s+is|\s*[:=-])?\s*([0-9]{4,8})\b",
    r"(?<!\d)([0-9]{4,8})(?!\d)",
]


class _HTMLTextExtractor(HTMLParser):
    """Small HTML-to-text helper that preserves readable spacing."""

    BLOCK_TAGS = {"br", "div", "p", "li", "tr", "td", "th", "section", "article", "h1", "h2", "h3", "h4"}

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self.BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if data:
            self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts)


def html_to_text(raw_html: str) -> str:
    """Convert HTML into plain text for OTP parsing fallback."""

    parser = _HTMLTextExtractor()
    parser.feed(str(raw_html or ""))
    parser.close()
    return normalize_text(html.unescape(parser.get_text()))


def normalize_text(text: str) -> str:
    """Normalize whitespace while keeping content readable."""

    collapsed = re.sub(r"[ \t\r\f\v]+", " ", str(text or ""))
    collapsed = re.sub(r"\n{3,}", "\n\n", collapsed)
    return collapsed.strip()


def extract_otp(text: str, patterns: list[str] | None = None) -> str | None:
    """Extract the best OTP-like code from text using ordered regex patterns."""

    normalized = normalize_text(text)
    if not normalized:
        return None

    active_patterns = patterns if patterns is not None else DEFAULT_OTP_PATTERNS
    for index, pattern in enumerate(active_patterns):
        for match in re.finditer(pattern, normalized):
            candidate = _extract_candidate(match)
            if not candidate:
                continue
            if index == len(active_patterns) - 1 and not _is_reasonable_fallback(
                candidate, normalized, match.start()
            ):
                continue
            return candidate
    return None


def _extract_candidate(match: re.Match[str]) -> str | None:
    if match.lastindex:
        for group_index in range(1, match.lastindex + 1):
            value = match.group(group_index)
            if value:
                return value.strip()
    value = match.group(0)
    return value.strip() if value else None


def _is_reasonable_fallback(candidate: str, text: str, start_index: int) -> bool:
    if not 4 <= len(candidate) <= 8:
        return False

    if candidate[0] == candidate[-1] and len(set(candidate)) == 1:
        return False

    window_start = max(0, start_index - 40)
    context = text[window_start:start_index].lower()
    if any(keyword in context for keyword in ("code", "otp", "verification", "security", "confirm")):
        return True

    return len(candidate) in {6, 8}
