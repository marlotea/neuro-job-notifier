"""Lever public postings API. Docs: https://github.com/lever/postings-api"""

from notifier.companies import Company
from notifier.http import get_json
from notifier.models import Job
from notifier.sources.common import html_to_text, millis_to_date

URL = "https://api.lever.co/v0/postings/{slug}?mode=json"


def fetch(company: Company) -> list[Job]:
    return [_to_job(item, company) for item in get_json(URL.format(slug=company.slug))]


def _to_job(item: dict, company: Company) -> Job:
    categories = item.get("categories") or {}
    locations = list(categories.get("allLocations") or [categories.get("location") or ""])
    if item.get("workplaceType") == "remote":
        locations.append("Remote")
    # The description comes in parts: intro, bullet lists (as HTML), and closing text.
    lists = " ".join(f"{part.get('text', '')} {part.get('content', '')}" for part in item.get("lists") or [])
    description = " ".join([item.get("descriptionPlain") or "", lists, item.get("additionalPlain") or ""])
    return Job(
        id=f"lever:{item['id']}",
        company=company.name,
        title=item["text"].strip(),
        url=item["hostedUrl"],
        location="; ".join(loc for loc in locations if loc),
        source="lever",
        posted_at=millis_to_date(item.get("createdAt")),
        description=html_to_text(description),
        from_watchlist=True,
    )
