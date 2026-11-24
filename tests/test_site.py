"""Tests for the website's data files (docs/data/)."""

import json
import tempfile
import unittest
from pathlib import Path

from notifier import site
from notifier.companies import Company, Watchlist, load
from notifier.filters import KeywordMatcher
from notifier.models import Job

COMPANY = Company(name="Neuralink", ats="greenhouse", slug="neuralink", careers_url=None,
                  big_company=False, category="invasive-bci", description="Implants.",
                  website="https://neuralink.com/")


def job(n: int, source: str = "greenhouse", posted: str | None = "2026-11-01", **kw) -> Job:
    return Job(id=f"{source}:{n}", company=kw.get("company", "Neuralink"), title=f"Software Intern {n}",
               url=kw.get("url", f"https://example.com/{n}"), location="Austin, TX", source=source,
               posted_at=posted, description=None, from_watchlist=True)


class SiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.matcher = KeywordMatcher(["BCI"])
        self.watchlist = Watchlist.from_companies([COMPANY])

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, listings, failed=(), today="2026-11-24"):
        site.write(listings, set(failed), [COMPANY], self.matcher, self.watchlist, self.dir, today)
        return json.loads((self.dir / "jobs.json").read_text())["jobs"]

    def test_lists_jobs_newest_first_with_reason(self):
        jobs = self.write({"greenhouse/neuralink": [job(1, posted="2026-11-01"), job(2, posted="2026-11-05")]})
        self.assertEqual([j["id"] for j in jobs], ["greenhouse:2", "greenhouse:1"])
        self.assertEqual(jobs[0]["kind"], "internship")
        self.assertIn("Watchlist", jobs[0]["reason"])

    def test_first_seen_is_kept_and_closed_jobs_drop_off(self):
        self.write({"greenhouse/neuralink": [job(1), job(2)]}, today="2026-11-20")
        jobs = self.write({"greenhouse/neuralink": [job(1)]}, today="2026-11-24")
        self.assertEqual([(j["id"], j["first_seen"]) for j in jobs], [("greenhouse:1", "2026-11-20")])

    def test_failed_source_keeps_its_previous_jobs(self):
        self.write({"greenhouse/neuralink": [job(1)], "simplify": [job(9, source="simplify")]})
        jobs = self.write({"simplify": []}, failed={"greenhouse/neuralink"})
        self.assertEqual([j["id"] for j in jobs], ["greenhouse:1"])

    def test_same_job_on_board_and_simplify_listed_once(self):
        board = job(8005762003, url="https://boards.greenhouse.io/neuralink/jobs/8005762003")
        dup = job(1, source="simplify", url="https://boards.greenhouse.io/neuralink/jobs/8005762003?utm=x")
        jobs = self.write({"greenhouse/neuralink": [board], "simplify": [dup]})
        self.assertEqual([j["id"] for j in jobs], ["greenhouse:8005762003"])

    def test_companies_file_counts_open_jobs(self):
        self.write({"greenhouse/neuralink": [job(1), job(2)]})
        data = json.loads((self.dir / "companies.json").read_text())
        self.assertEqual(data["companies"][0]["open_jobs"], 2)
        self.assertTrue(data["companies"][0]["tracked"])

    def test_real_watchlist_has_site_fields(self):
        for c in load():
            self.assertTrue(c.description, c.name)
            self.assertTrue(c.website or c.careers_url, c.name)


if __name__ == "__main__":
    unittest.main()
