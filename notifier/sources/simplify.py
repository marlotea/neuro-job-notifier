"""Fetch listings from the SimplifyJobs GitHub repos.

Simplify keeps every listing in a big JSON file inside each repo. We read the
raw file straight from GitHub (no API key needed).
"""

import logging
from datetime import datetime, timezone

import requests

from notifier.models import Job

log = logging.getLogger(__name__)

# Confirmed 2026-10-29. Both repos use the "dev" branch, not "main".
# When Simplify starts a Summer 2028 repo, these URLs will need updating.
INTERNSHIPS_URL = (
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/"
    "dev/.github/scripts/listings.json"
)
NEW_GRAD_URL = (
    "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/"
    "dev/.github/scripts/listings.json"
)

# requests applies this timeout to connecting and to each read from the socket,
# not to the whole download, so the ~13 MB files still have time to arrive.
TIMEOUT_SECONDS = 15


def fetch() -> list[Job]:
    # If either feed fails, we raise and the whole source counts as failed for
    # this run. Returning only half the listings could cause a bad first-run seed.
    jobs = []
    for url, kind in [(INTERNSHIPS_URL, "internship"), (NEW_GRAD_URL, "new_grad")]:
        response = requests.get(url, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        listings = response.json()
        jobs.extend(_to_job(item, kind) for item in listings if _keep(item, kind))
    return jobs


def _keep(item: dict, kind: str) -> bool:
    # Simplify keeps closed and hidden listings in the file; skip those.
    if not item.get("active") or not item.get("is_visible"):
        return False
    if kind == "internship":
        # The internship repo also lists older terms (e.g. "Fall 2026"). Keep
        # 2027 terms, plus "N/A" (no term given) so we don't miss anything.
        terms = item.get("terms") or ["N/A"]
        return any("2027" in t or t == "N/A" for t in terms)
    return True


def _to_job(item: dict, kind: str) -> Job:
    return Job(
        id=f"simplify:{item['id']}",
        company=item.get("company_name", "").strip(),
        title=item.get("title", "").strip(),
        url=item.get("url", ""),
        location="; ".join(item.get("locations") or []),
        source="simplify",
        posted_at=_epoch_to_date(item.get("date_posted")),
        description=None,  # Simplify listings don't include a description
        from_watchlist=False,
        kind=kind,
    )


def _epoch_to_date(seconds) -> str | None:
    if not seconds:
        return None
    return datetime.fromtimestamp(seconds, tz=timezone.utc).date().isoformat()
