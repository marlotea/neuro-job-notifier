"""Write the JSON files the website in docs/ reads.

docs/data/jobs.json lists every job that currently passes the filters (not
only the new ones that got emailed). It's rebuilt on every run:

- a job that's gone from its source (filled or closed) drops off the list
- if a source fails, its jobs from the last run are kept, so one broken board
  doesn't empty the site
- "first_seen" is the date a job first appeared on the site. The site sorts by
  "posted_at" when the source gives one, and by "first_seen" otherwise.

"checked_at" is the time of the run (UTC). It changes every run, so the
workflow commits jobs.json twice a day even when no jobs changed.

docs/data/companies.json is the watchlist from config/companies.yaml, with how
many open jobs each company has.
"""

import json
from datetime import date, datetime, timezone
from pathlib import Path

from notifier import filters
from notifier.companies import CATEGORIES, Company, normalize_name
from notifier.dedupe import remove_duplicates
from notifier.models import Job

DATA_DIR = Path(__file__).resolve().parent.parent / "docs" / "data"


def write(listings: dict[str, list[Job]], failed: set[str], companies: list[Company],
          matcher: filters.KeywordMatcher, watchlist, data_dir: Path = DATA_DIR,
          today: str | None = None) -> None:
    """listings maps each source that worked this run to its filtered jobs.
    failed is the set of sources that errored."""
    today = today or date.today().isoformat()
    jobs_path = data_dir / "jobs.json"
    previous = _load(jobs_path).get("jobs", [])
    first_seen = {j["id"]: j.get("first_seen") or today for j in previous}

    # Board sources come before Simplify in `listings`, so remove_duplicates
    # keeps the board's copy of a job that's on both.
    current = remove_duplicates([job for jobs in listings.values() for job in jobs])
    source_of = {job.id: name for name, jobs in listings.items() for job in jobs}
    entries = [_entry(job, source_of[job.id], first_seen.get(job.id, today), matcher, watchlist)
               for job in current]
    present = {e["id"] for e in entries}
    entries += [e for e in previous if e.get("source") in failed and e["id"] not in present]
    entries.sort(key=lambda e: (e.get("posted_at") or e["first_seen"], e["company"]), reverse=True)

    data_dir.mkdir(parents=True, exist_ok=True)
    # When this run happened, so the site can say when jobs were last checked.
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _dump(jobs_path, {"updated": today, "checked_at": checked_at, "jobs": entries})
    _dump(data_dir / "companies.json", {
        "checked_at": checked_at,
        "categories": [{"id": k, "label": v} for k, v in CATEGORIES.items()],
        "companies": [_company_entry(c, entries) for c in companies],
    })


def _entry(job: Job, source: str, first_seen: str, matcher, watchlist) -> dict:
    why = filters.relevance(job, matcher, watchlist)
    return {
        "id": job.id,
        "company": job.company,
        "title": job.title,
        "url": job.url,
        "location": job.location,
        "kind": filters.role_kind(job),
        "posted_at": job.posted_at,
        "first_seen": first_seen,
        "source": source,
        "reason": why.reason if why else None,
    }


def _company_entry(c: Company, jobs: list[dict]) -> dict:
    names = {normalize_name(n) for n in [c.name, *c.aliases]}
    return {
        "name": c.name,
        "category": c.category,
        "description": c.description,
        "website": c.website or c.careers_url,
        "linkedin": c.linkedin,
        "careers_url": c.careers_url,
        "tracked": c.ats != "unknown",  # its job board is fetched directly
        "open_jobs": sum(1 for j in jobs if normalize_name(j["company"]) in names),
    }


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _dump(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
