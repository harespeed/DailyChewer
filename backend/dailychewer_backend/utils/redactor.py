"""Sensitive information redaction helpers."""

from __future__ import annotations

import re

from dailychewer_backend.config import PrivacyConfig


EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_PATTERN = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
API_KEY_PATTERN = re.compile(
    r"\b(sk-[A-Za-z0-9_-]{8,}|api[_-]?key\s*[:=]\s*[A-Za-z0-9._-]{6,})\b",
    flags=re.IGNORECASE,
)
TOKEN_PATTERN = re.compile(
    r"\b(token\s*[:=]\s*[A-Za-z0-9._-]{6,}|bearer\s+[A-Za-z0-9._-]{6,})\b",
    flags=re.IGNORECASE,
)


def redact_sensitive_text(text: str, privacy: PrivacyConfig) -> str:
    """Redact common sensitive patterns before sending content to an LLM."""

    if not privacy.enable_redaction:
        return text

    redacted = text
    if privacy.redact_email:
        redacted = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", redacted)
    if privacy.redact_phone:
        redacted = PHONE_PATTERN.sub("[REDACTED_PHONE]", redacted)
    if privacy.redact_api_key:
        redacted = API_KEY_PATTERN.sub("[REDACTED_API_KEY]", redacted)
        redacted = TOKEN_PATTERN.sub("[REDACTED_TOKEN]", redacted)
    return redacted
