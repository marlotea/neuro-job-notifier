"""Load the company watchlist from config/companies.yaml."""

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "companies.yaml"

SUPPORTED_ATS = {"greenhouse", "lever", "ashby"}


@dataclass
class Company:
    name: str
    ats: str  # greenhouse | lever | ashby | unknown
    slug: str | None
    careers_url: str | None
    big_company: bool
    # Other names the company goes by. Simplify, for example, might list
    # "Forest Neurotech" under its new name.
    aliases: list[str] = field(default_factory=list)

    @property
    def board_key(self) -> str:
        """Short name for this company's job board, e.g. "greenhouse/neuralink".
        Each board is seeded separately, so adding a company later won't email
        its whole backlog."""
        return f"{self.ats}/{self.slug}"


def load(path: Path = DEFAULT_PATH) -> list[Company]:
    entries = yaml.safe_load(path.read_text()) or []
    companies = []
    for entry in entries:
        company = Company(
            name=entry["name"],
            ats=entry.get("ats", "unknown"),
            slug=entry.get("slug"),
            careers_url=entry.get("careers_url"),
            big_company=bool(entry.get("big_company", False)),
            aliases=entry.get("aliases") or [],
        )
        if company.ats in SUPPORTED_ATS and not company.slug:
            raise ValueError(f"{company.name}: ats is {company.ats} but no slug is set")
        companies.append(company)
    return companies


_SUFFIXES = {"inc", "llc", "ltd", "corp", "corporation", "co", "the"}


def normalize_name(name: str) -> str:
    """Lowercase, drop punctuation and words like "Inc.", so "Neuralink, Inc."
    and "neuralink" compare equal. We don't do fuzzy matching, because
    "BlackRock" (finance) and "Blackrock Neurotech" are different companies."""
    words = re.findall(r"[a-z0-9]+", name.lower())
    return " ".join(w for w in words if w not in _SUFFIXES)


@dataclass
class Watchlist:
    """Quick lookups by company name, used by the filters."""
    names: set[str]  # normalized names and aliases of every watchlist company
    big_names: set[str]  # the subset with big_company: true

    @classmethod
    def from_companies(cls, companies: list[Company]) -> "Watchlist":
        names, big = set(), set()
        for c in companies:
            for n in [c.name, *c.aliases]:
                names.add(normalize_name(n))
                if c.big_company:
                    big.add(normalize_name(n))
        return cls(names, big)

    def contains(self, company_name: str) -> bool:
        return normalize_name(company_name) in self.names

    def is_big(self, company_name: str) -> bool:
        return normalize_name(company_name) in self.big_names
