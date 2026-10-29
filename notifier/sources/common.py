"""Small helpers shared by the job board fetchers."""

import html
import re
from datetime import datetime, timezone

# We only use descriptions for keyword matching, so there's no need to keep
# huge ones in memory.
MAX_DESCRIPTION_CHARS = 5000


def html_to_text(raw: str | None) -> str | None:
    """Turn an HTML job description into plain text for keyword matching."""
    if not raw:
        return None
    text = html.unescape(raw)  # Greenhouse escapes its HTML ("&lt;p&gt;")
    text = re.sub(r"<[^>]+>", " ", text)  # drop tags
    text = html.unescape(text)  # entities inside the HTML, like "&amp;"
    text = re.sub(r"\s+", " ", text).strip()
    return text[:MAX_DESCRIPTION_CHARS]


def truncate(text: str | None) -> str | None:
    return text[:MAX_DESCRIPTION_CHARS] if text else None


def iso_to_date(value: str | None) -> str | None:
    """"2026-02-18T17:29:03-05:00" -> "2026-02-18"."""
    return value[:10] if value else None


def millis_to_date(value: int | None) -> str | None:
    """Lever gives timestamps in milliseconds since 1970."""
    if not value:
        return None
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).date().isoformat()
