"""Decide which jobs are worth emailing.

Filters run in this order: location, then role type, then relevance.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from notifier.companies import Watchlist
from notifier.models import Job

# ---------------------------------------------------------------------------
# 1. Location
# ---------------------------------------------------------------------------

# Place names that mean "Canada or the US". Matched as whole words, any case.
# This list doesn't need to be complete. Most postings include a state or
# province code, and those are caught by the code lists further down.
NORTH_AMERICA_NAMES = [
    "Canada", "United States", "North America", "USA",
    # Canadian provinces and territories
    "Ontario", "Quebec", "Québec", "British Columbia", "Alberta", "Manitoba",
    "Saskatchewan", "Nova Scotia", "New Brunswick", "Newfoundland",
    "Prince Edward Island", "Yukon", "Nunavut", "Northwest Territories",
    # Canadian cities
    "Toronto", "Vancouver", "Montreal", "Montréal", "Ottawa", "Calgary",
    "Edmonton", "Waterloo", "Kitchener", "Winnipeg", "Halifax", "Mississauga",
    "Markham", "Burnaby",
    # US states
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine",
    "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi",
    "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey",
    "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio",
    "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina",
    "South Dakota", "Tennessee", "Texas", "Utah", "Vermont", "Virginia",
    "Washington", "West Virginia", "Wisconsin", "Wyoming",
    # US cities
    "San Francisco", "Bay Area", "Silicon Valley", "Seattle", "Boston",
    "Los Angeles", "Austin", "Chicago", "Palo Alto", "Mountain View",
    "Menlo Park", "Sunnyvale", "San Jose", "Santa Clara", "Redmond",
    "Pittsburgh", "Atlanta", "Denver", "Salt Lake City", "San Diego",
    "Philadelphia", "Houston", "Dallas", "Miami", "Minneapolis", "Raleigh",
    "Ann Arbor", "Brooklyn", "Berkeley", "Oakland", "Irvine", "Princeton",
    "Baltimore", "Detroit", "Phoenix", "Nashville", "Ashburn",
]

# Short uppercase forms. Matched case-sensitively so "US" doesn't match "us".
NORTH_AMERICA_ABBREVIATIONS = ["US", "U.S.", "U.S.A.", "SF", "NYC", "DC"]

# US state and Canadian province codes. To avoid false matches, these only
# count after a comma, as in "Boston, MA" or "Toronto, ON".
STATE_AND_PROVINCE_CODES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC",
    "ON", "QC", "BC", "AB", "MB", "SK", "NS", "NB", "NL", "PE", "YT", "NT", "NU",
]

# Places outside North America that often follow "Remote", as in "Remote in UK".
# We use this list only for remote jobs. Plain "Remote" is kept, but
# "Remote in Germany" is dropped.
NON_NORTH_AMERICA = [
    "UK", "United Kingdom", "England", "Scotland", "Ireland", "Europe", "EU",
    "EMEA", "APAC", "LATAM", "Germany", "France", "Spain", "Portugal", "Italy",
    "Netherlands", "Belgium", "Switzerland", "Austria", "Poland", "Czechia",
    "Sweden", "Norway", "Denmark", "Finland", "Romania", "Greece", "Israel",
    "India", "China", "Japan", "Korea", "Singapore", "Taiwan", "Australia",
    "New Zealand", "Brazil", "Mexico", "Argentina", "Colombia", "Philippines",
    "Russia", "Ukraine", "Turkey", "Slovenia", "North Macedonia", "Serbia",
    "Hungary", "Estonia", "Lithuania", "Latvia", "Bulgaria", "Croatia",
]


def _words_regex(words: list[str], ignore_case: bool) -> re.Pattern:
    # Lookarounds instead of \b, so entries ending in "." (like "U.S.") still
    # work, and short words never match inside longer ones ("US" in "USB").
    alternatives = "|".join(re.escape(w) for w in words)
    flags = re.IGNORECASE if ignore_case else 0
    return re.compile(rf"(?<![A-Za-z0-9])(?:{alternatives})(?![A-Za-z0-9])", flags)


_NA_NAMES_RE = _words_regex(NORTH_AMERICA_NAMES, ignore_case=True)
_NA_ABBREV_RE = _words_regex(NORTH_AMERICA_ABBREVIATIONS, ignore_case=False)
_CODES_RE = re.compile(
    r",\s*(?:" + "|".join(STATE_AND_PROVINCE_CODES) + r")(?![A-Za-z])"
)
_REMOTE_RE = re.compile(r"\bremote\b", re.IGNORECASE)
_NON_NA_RE = _words_regex(NON_NORTH_AMERICA, ignore_case=True)


def location_ok(location: str) -> bool:
    text = (location or "").strip()
    if not text:
        return True  # empty location is often a remote job, so keep it
    if _NA_NAMES_RE.search(text) or _NA_ABBREV_RE.search(text) or _CODES_RE.search(text):
        return True
    if _REMOTE_RE.search(text) and not _NON_NA_RE.search(text):
        return True
    return False


# ---------------------------------------------------------------------------
# 2. Role type
# ---------------------------------------------------------------------------

_INTERN_RE = re.compile(r"\b(intern|interns|internship|co-?op)\b", re.IGNORECASE)
_EARLY_CAREER_RE = re.compile(
    r"\b(intern|interns|internship|co-?op|new grad|new graduate|graduate|"
    r"entry[- ]level|junior|2027|2028)\b",
    re.IGNORECASE,
)
_SENIOR_RE = re.compile(
    r"\b(senior|sr|staff|principal|lead|manager|director)\b", re.IGNORECASE
)
_YEAR_RE = re.compile(r"\b(20\d\d)\b")


def role_label(job: Job) -> str:
    """Human-friendly role type for emails."""
    kind = job.kind or ("internship" if _INTERN_RE.search(job.title) else "new_grad")
    return "Internship / co-op" if kind == "internship" else "New grad"


def role_type_ok(job: Job) -> bool:
    title = job.title
    if _SENIOR_RE.search(title):
        return False
    # Sources like Simplify only list early-career roles, so their titles
    # don't need to say "intern" or "new grad". Other sources must say so.
    if job.kind is None and not _EARLY_CAREER_RE.search(title):
        return False
    return _year_ok(job)


def _year_ok(job: Job) -> bool:
    """If the title names a year, check it matches what we want:
    internships for 2027, new grad roles starting 2027 or later."""
    years = {int(y) for y in _YEAR_RE.findall(job.title)}
    if not years:
        return True  # no year mentioned, so we can't rule it out
    kind = job.kind or ("internship" if _INTERN_RE.search(job.title) else "new_grad")
    if kind == "internship":
        return 2027 in years
    return max(years) >= 2027


# ---------------------------------------------------------------------------
# 3. Relevance
# ---------------------------------------------------------------------------


def _term_regex(term: str) -> str:
    """Turn one keyword from keywords.yaml into a regex fragment.

    - Spaces and hyphens are interchangeable: "brain-computer" also matches
      "brain computer".
    - A trailing "*" means "any ending": "neuro*" matches "neurotechnology".
    - An optional plural "s" is allowed: "BCI" also matches "BCIs".
    """
    prefix = term.endswith("*")
    word = term.rstrip("*")
    parts = [re.escape(p) for p in re.split(r"[\s-]+", word)]
    pattern = r"[\s-]+".join(parts)
    return pattern + (r"[A-Za-z]*" if prefix else r"s?")


class KeywordMatcher:
    def __init__(self, terms: list[str], exclude: list[str] | None = None):
        def build(items):
            if not items:
                return None
            body = "|".join(_term_regex(t) for t in items)
            # Whole words only: the term can't have a letter or digit right
            # before or after it. That stops "BCI" from matching inside "ABCIX".
            return re.compile(
                rf"(?<![A-Za-z0-9])(?:{body})(?![A-Za-z0-9])", re.IGNORECASE
            )

        self._terms = build(terms)
        self._exclude = build(exclude)

    @classmethod
    def from_yaml(cls, path: Path) -> "KeywordMatcher":
        data = yaml.safe_load(path.read_text()) or {}
        return cls(data.get("terms", []), data.get("exclude", []))

    def find(self, text: str | None) -> re.Match | None:
        """Return the first keyword match in text, or None."""
        if not text or self._terms is None:
            return None
        # Blank out phrases like "neural network" first, so they can't count
        # as a match. Other terms in the same text still can. We replace them
        # with the same number of spaces so match positions still line up
        # with the original text.
        if self._exclude is not None:
            text = self._exclude.sub(lambda m: " " * len(m.group(0)), text)
        return self._terms.search(text)

    def matches(self, text: str | None) -> bool:
        return self.find(text) is not None


@dataclass
class Relevance:
    """Why a job passed the relevance filter. Shown in the email so you can
    quickly judge borderline matches."""
    reason: str  # e.g. 'Keyword "EEG" in description'
    # For description matches: the text around the keyword, split into
    # (before, keyword, after) so the email can highlight the keyword.
    context: tuple[str, str, str] | None = None


def relevance(job: Job, matcher: KeywordMatcher, watchlist: Watchlist | None = None) -> Relevance | None:
    """Return why the job is relevant, or None if it isn't."""
    # Small watchlist companies (neurotech startups etc.) are relevant by
    # default: any early-career role there, SWE included, is worth a look.
    is_big = watchlist is not None and watchlist.is_big(job.company)
    if job.from_watchlist and not is_big:
        return Relevance("Watchlist company (every early-career role counts)")
    # Everyone else (big companies, and Simplify jobs from companies not on
    # the watchlist) must mention a neuro keyword.
    match = matcher.find(job.title)
    if match:
        return Relevance(f'Keyword "{match.group(0)}" in title')
    match = matcher.find(job.description)
    if match:
        text = job.description
        start, end = match.span()
        context = (text[max(0, start - 90):start], text[start:end], text[end:end + 90])
        return Relevance(f'Keyword "{match.group(0)}" in description', context)
    return None


def is_relevant(job: Job, matcher: KeywordMatcher, watchlist: Watchlist | None = None) -> bool:
    return relevance(job, matcher, watchlist) is not None


# ---------------------------------------------------------------------------


def filter_jobs(jobs: list[Job], matcher: KeywordMatcher, watchlist: Watchlist | None = None) -> list[Job]:
    return [
        j for j in jobs
        if location_ok(j.location) and role_type_ok(j) and is_relevant(j, matcher, watchlist)
    ]
