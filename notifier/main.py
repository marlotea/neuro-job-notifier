"""Entry point: python -m notifier.main [--dry-run] [--seed]

Pipeline: fetch each source -> filter -> drop already-seen jobs -> email the
rest -> record what was sent in state/seen.json.
"""

import argparse
import functools
import logging
import sys
from collections.abc import Callable
from pathlib import Path

from notifier import companies as companies_mod, filters, state as state_mod
from notifier.dedupe import job_keys, remove_duplicates
from notifier.emailer import Emailer, format_email
from notifier.models import Job
from notifier.sources import ashby, greenhouse, lever, simplify

log = logging.getLogger("notifier")

ROOT = Path(__file__).resolve().parent.parent
KEYWORDS_PATH = ROOT / "config" / "keywords.yaml"

# Safety cap: a bug that makes every job look "new" should not send 500 emails.
MAX_EMAILS_PER_RUN = 25

# Job board fetchers, by the "ats" value in companies.yaml.
FETCHERS = {
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
    "ashby": ashby.fetch,
}


def build_sources(companies: list[companies_mod.Company]) -> dict[str, Callable[[], list[Job]]]:
    """Map each source name to a function that returns its jobs.

    Each watchlist company's job board is its own source (e.g.
    "greenhouse/neuralink"), so one broken board doesn't hide the others, and a
    newly added company gets its own first-run seed.
    """
    sources = {}
    for company in companies:
        if company.ats in FETCHERS:
            # functools.partial makes a function that calls fetch(company) later.
            sources[company.board_key] = functools.partial(FETCHERS[company.ats], company)
    # Simplify goes last. When a job is on both a company board and Simplify,
    # the first copy wins, and the board's copy has the description.
    sources["simplify"] = simplify.fetch
    return sources


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="print emails instead of sending, and don't update seen.json")
    parser.add_argument("--seed", action="store_true",
                        help="mark every current job as seen without emailing")
    parser.add_argument("--state", type=Path, default=state_mod.DEFAULT_PATH,
                        help="path to seen.json (default: state/seen.json)")
    parser.add_argument("--test-email", action="store_true",
                        help="send one sample email to EMAIL_TO to check your settings, then stop")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    _load_dotenv()

    if args.test_email:
        return _send_test_email()

    state = state_mod.load(args.state)
    matcher = filters.KeywordMatcher.from_yaml(KEYWORDS_PATH)
    companies = companies_mod.load()
    watchlist = companies_mod.Watchlist.from_companies(companies)
    sources = build_sources(companies)

    fetched: dict[str, int] = {}
    kept: dict[str, int] = {}
    seeded: dict[str, int] = {}
    errors: list[str] = []
    new_jobs: list[Job] = []

    for name, fetch in sources.items():
        # One broken source must not stop the others, so catch everything here.
        try:
            jobs = fetch()
        except Exception as exc:
            log.error("source %s failed: %s", name, exc)
            errors.append(f"{name}: {exc}")
            continue

        fetched[name] = len(jobs)
        # Simplify jobs from a watchlist company (e.g. a Neuralink internship)
        # get the same treatment as jobs fetched from that company directly.
        for job in jobs:
            if not job.from_watchlist and watchlist.contains(job.company):
                job.from_watchlist = True
        relevant = filters.filter_jobs(jobs, matcher, watchlist)
        kept[name] = len(relevant)

        # First successful run of this source (or --seed): remember everything
        # it has right now, but don't email any of it.
        if args.seed or name not in state.seeded_sources:
            for j in relevant:
                state.seen_ids.update(job_keys(j))
            state.seeded_sources.add(name)
            seeded[name] = len(relevant)
            log.info("seeded %s: marked %d current jobs as seen, no emails", name, len(relevant))
            if args.dry_run:
                for j in relevant:
                    print(f"  [would seed] {j.company}: {j.title} ({j.location})")
            continue

        # A job counts as seen if any of its IDs is in seen.json. That catches
        # a Simplify listing we already emailed from the company's own board.
        new_jobs.extend(j for j in relevant if not job_keys(j) & state.seen_ids)

    new_jobs = remove_duplicates(new_jobs)
    # Newest first, so if the cap kicks in, the freshest postings go out first.
    # Jobs with no date sort last.
    new_jobs.sort(key=lambda j: j.posted_at or "", reverse=True)
    if len(new_jobs) > MAX_EMAILS_PER_RUN:
        log.warning("found %d new jobs, only sending the first %d; the rest go out next run",
                    len(new_jobs), MAX_EMAILS_PER_RUN)
        new_jobs = new_jobs[:MAX_EMAILS_PER_RUN]

    # Work out why each job matched, so the email can say so.
    reasons = {j.id: filters.relevance(j, matcher, watchlist) for j in new_jobs}
    sent = _send_all(new_jobs, reasons, state, args.dry_run, errors)

    if args.dry_run:
        log.info("dry run: seen.json not updated")
    else:
        state_mod.save(state, args.state)

    _print_summary(list(sources), fetched, kept, seeded, len(new_jobs), sent, errors, args.dry_run)
    # A non-zero exit code makes the GitHub Actions run show as failed, so
    # you get notified that something needs a look.
    return 1 if errors else 0


def _send_all(jobs: list[Job], reasons: dict[str, filters.Relevance | None],
              state: state_mod.State, dry_run: bool, errors: list[str]) -> int:
    if not jobs:
        return 0
    if dry_run:
        for job in jobs:
            subject, body, _html = format_email(job, reasons.get(job.id))
            print("=" * 70)
            print(f"Subject: {subject}\n")
            print(body)
        return len(jobs)

    try:
        emailer = Emailer()
    except RuntimeError as exc:
        log.error("can't send email: %s", exc)
        errors.append(f"email: {exc}")
        return 0

    sent = 0
    for job in jobs:
        try:
            emailer.send(job, reasons.get(job.id))
        except Exception as exc:
            # The job is not marked as seen, so it gets retried next run.
            log.error("failed to email %s: %s", job.id, exc)
            errors.append(f"email {job.id}: {exc}")
            continue
        # Only mark as seen once the email has actually gone out.
        state.seen_ids.update(job_keys(job))
        sent += 1
    return sent


SAMPLE_JOB = Job(
    id="sample:1",
    company="Neuralink",
    title="Software Engineer Intern, BCI Applications",
    url="https://boards.greenhouse.io/neuralink/jobs/6594422003",
    location="Austin, Texas, United States; South San Francisco, California, United States",
    source="greenhouse",
    posted_at=None,
    description=None,
    from_watchlist=True,
    kind="internship",
)


def _send_test_email() -> int:
    try:
        emailer = Emailer()
        emailer.send(SAMPLE_JOB, filters.Relevance("Test email: your settings work"))
    except Exception as exc:
        log.error("test email failed: %s", exc)
        return 1
    print(f"Sent a test email to {emailer.to}")
    return 0


def _print_summary(source_names, fetched, kept, seeded, new_count, sent, errors, dry_run):
    print()
    print("Run summary" + (" (dry run)" if dry_run else ""))
    for name in source_names:
        if name in fetched:
            line = f"  {name}: fetched {fetched[name]}, after filtering {kept[name]}"
            if name in seeded:
                line += f" (seeded {seeded[name]}, not emailed)"
            print(line)
        else:
            print(f"  {name}: FAILED")
    print(f"  new jobs: {new_count}")
    print(f"  emails {'printed' if dry_run else 'sent'}: {sent}")
    print(f"  errors: {len(errors)}")
    for err in errors:
        print(f"    - {err}")


def _load_dotenv():
    # Locally, read settings from a .env file if python-dotenv is installed.
    # On GitHub Actions the values come from repository secrets instead.
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(ROOT / ".env")


if __name__ == "__main__":
    sys.exit(main())
