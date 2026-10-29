"""Spot the same job showing up in two sources.

Simplify often links straight to a company's Greenhouse, Lever, or Ashby
posting. If we also fetch that company's board directly, we'd get the job twice
under two different IDs. So we read the board's own job ID out of the Simplify
URL and use it as a second ID for that job.
"""

import re
from urllib.parse import parse_qs, urlparse

from notifier.models import Job

_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_PATTERNS = [
    # boards.greenhouse.io/neuralink/jobs/8005762003
    ("greenhouse", re.compile(r"greenhouse\.io/[\w-]+/jobs/(\d+)", re.IGNORECASE)),
    # jobs.lever.co/convergentresearch/d8f1da4b-...
    ("lever", re.compile(rf"jobs\.lever\.co/[\w-]+/({_UUID})", re.IGNORECASE)),
    # jobs.ashbyhq.com/metamorphic/cf518648-.../application
    ("ashby", re.compile(rf"jobs\.ashbyhq\.com/[\w.-]+/({_UUID})", re.IGNORECASE)),
]


def job_keys(job: Job) -> set[str]:
    """Every ID this job might be known by. Always includes job.id."""
    keys = {job.id}
    for ats, pattern in _PATTERNS:
        match = pattern.search(job.url)
        if match:
            keys.add(f"{ats}:{match.group(1).lower()}")
    # Company sites that embed Greenhouse use "?gh_jid=123" in their own URLs.
    gh_jid = parse_qs(urlparse(job.url).query).get("gh_jid")
    if gh_jid:
        keys.add(f"greenhouse:{gh_jid[0]}")
    return keys


def remove_duplicates(jobs: list[Job]) -> list[Job]:
    """Keep the first copy of each job. Put job board sources before Simplify
    in the list, so their copy wins (it has a description and a direct link)."""
    seen: set[str] = set()
    unique = []
    for job in jobs:
        keys = job_keys(job)
        if keys & seen:
            continue
        seen |= keys
        unique.append(job)
    return unique
