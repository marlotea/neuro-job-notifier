"""Greenhouse public job board API. Docs: https://developers.greenhouse.io/job-board.html"""

from notifier.companies import Company
from notifier.http import get_json
from notifier.models import Job
from notifier.sources.common import html_to_text, iso_to_date

URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"


def fetch(company: Company) -> list[Job]:
    data = get_json(URL.format(slug=company.slug))
    return [
        Job(
            id=f"greenhouse:{item['id']}",
            company=company.name,
            title=item["title"].strip(),
            url=item["absolute_url"],
            location=(item.get("location") or {}).get("name", ""),
            source="greenhouse",
            posted_at=iso_to_date(item.get("first_published") or item.get("updated_at")),
            description=html_to_text(item.get("content")),
            from_watchlist=True,
        )
        for item in data.get("jobs", [])
    ]
