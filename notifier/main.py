"""Entry point: python -m notifier.main [--dry-run] [--seed]

Pipeline: fetch each source -> filter -> drop already-seen jobs -> email the
rest -> record what was sent in state/seen.json.
"""

import argparse
import logging
import sys
from pathlib import Path

from notifier import filters, state as state_mod
from notifier.emailer import Emailer, format_email
from notifier.models import Job
from notifier.sources import simplify

log = logging.getLogger("notifier")

ROOT = Path(__file__).resolve().parent.parent
KEYWORDS_PATH = ROOT / "config" / "keywords.yaml"

# Safety cap: a bug that makes every job look "new" should not send 500 emails.
MAX_EMAILS_PER_RUN = 25

# Source name -> function that returns a list of Job objects.
# The name must match the "{source}:" prefix used in Job IDs.
SOURCES = {
    "simplify": simplify.fetch,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="print emails instead of sending, and don't update seen.json")
    parser.add_argument("--seed", action="store_true",
                        help="mark every current job as seen without emailing")
    parser.add_argument("--state", type=Path, default=state_mod.DEFAULT_PATH,
                        help="path to seen.json (default: state/seen.json)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    _load_dotenv()

    state = state_mod.load(args.state)
    matcher = filters.KeywordMatcher.from_yaml(KEYWORDS_PATH)

    fetched: dict[str, int] = {}
    kept: dict[str, int] = {}
    seeded: dict[str, int] = {}
    errors: list[str] = []
    new_jobs: list[Job] = []

    for name, fetch in SOURCES.items():
        # One broken source must not stop the others, so catch everything here.
        try:
            jobs = fetch()
        except Exception as exc:
            log.error("source %s failed: %s", name, exc)
            errors.append(f"{name}: {exc}")
            continue

        fetched[name] = len(jobs)
        relevant = filters.filter_jobs(jobs, matcher)
        kept[name] = len(relevant)

        # First successful run of this source (or --seed): remember everything
        # it has right now, but don't email any of it.
        if args.seed or name not in state.seeded_sources:
            state.seen_ids.update(j.id for j in relevant)
            state.seeded_sources.add(name)
            seeded[name] = len(relevant)
            log.info("seeded %s: marked %d current jobs as seen, no emails", name, len(relevant))
            if args.dry_run:
                for j in relevant:
                    print(f"  [would seed] {j.company}: {j.title} ({j.location})")
            continue

        new_jobs.extend(j for j in relevant if j.id not in state.seen_ids)

    new_jobs = _dedupe(new_jobs)
    # Newest first, so if the cap kicks in, the freshest postings go out first.
    # Jobs with no date sort last.
    new_jobs.sort(key=lambda j: j.posted_at or "", reverse=True)
    if len(new_jobs) > MAX_EMAILS_PER_RUN:
        log.warning("found %d new jobs, only sending the first %d; the rest go out next run",
                    len(new_jobs), MAX_EMAILS_PER_RUN)
        new_jobs = new_jobs[:MAX_EMAILS_PER_RUN]

    sent = _send_all(new_jobs, state, args.dry_run, errors)

    if args.dry_run:
        log.info("dry run: seen.json not updated")
    else:
        state_mod.save(state, args.state)

    _print_summary(fetched, kept, seeded, len(new_jobs), sent, errors, args.dry_run)
    # A non-zero exit code makes the GitHub Actions run show as failed, so
    # you get notified that something needs a look.
    return 1 if errors else 0


def _send_all(jobs: list[Job], state: state_mod.State, dry_run: bool, errors: list[str]) -> int:
    if not jobs:
        return 0
    if dry_run:
        for job in jobs:
            subject, body = format_email(job)
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
            emailer.send(job)
        except Exception as exc:
            # The job is not marked as seen, so it gets retried next run.
            log.error("failed to email %s: %s", job.id, exc)
            errors.append(f"email {job.id}: {exc}")
            continue
        # Only mark as seen once the email has actually gone out.
        state.seen_ids.add(job.id)
        sent += 1
    return sent


def _dedupe(jobs: list[Job]) -> list[Job]:
    """Drop repeated IDs (e.g. a listing that appears in two feeds)."""
    unique: dict[str, Job] = {}
    for job in jobs:
        unique.setdefault(job.id, job)
    return list(unique.values())


def _print_summary(fetched, kept, seeded, new_count, sent, errors, dry_run):
    print()
    print("Run summary" + (" (dry run)" if dry_run else ""))
    for name in SOURCES:
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
