from dataclasses import dataclass


@dataclass
class Job:
    id: str  # stable unique ID, formatted "{source}:{source_id}"
    company: str
    title: str
    url: str
    location: str  # raw location text
    source: str  # "simplify", "greenhouse", etc.
    posted_at: str | None  # ISO date, e.g. "2026-10-29"
    description: str | None  # used only for filtering, can be truncated
    from_watchlist: bool
    # Set by sources that already know the role type ("internship" or "new_grad"),
    # e.g. Simplify's internship repo vs. its new-grad repo. None means "work it
    # out from the title".
    kind: str | None = None
