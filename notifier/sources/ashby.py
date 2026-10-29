"""Ashby public job board API. Docs: https://developers.ashbyhq.com/docs/public-job-posting-api"""

from notifier.companies import Company
from notifier.http import get_json
from notifier.models import Job
from notifier.sources.common import iso_to_date, truncate

URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"


def fetch(company: Company) -> list[Job]:
    data = get_json(URL.format(slug=company.slug))
    return [_to_job(item, company) for item in data.get("jobs", []) if item.get("isListed", True)]


def _to_job(item: dict, company: Company) -> Job:
    locations = [item.get("location") or ""]
    locations += [loc.get("location", "") for loc in item.get("secondaryLocations") or []]
    if item.get("isRemote"):
        locations.append("Remote")
    return Job(
        id=f"ashby:{item['id']}",
        company=company.name,
        title=item["title"].strip(),
        url=item["jobUrl"],
        location="; ".join(loc.strip() for loc in locations if loc.strip()),
        source="ashby",
        posted_at=iso_to_date(item.get("publishedAt")),
        description=truncate(item.get("descriptionPlain")),
        from_watchlist=True,
    )
