from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone


_WHITESPACE_RE = re.compile(r"\s+")


def normalize_keyword(value: str) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = _WHITESPACE_RE.sub(" ", text.strip())
    return text.casefold()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
