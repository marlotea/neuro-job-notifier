"""Check each job board fetcher turns the API's JSON into the right Job."""

import unittest
from unittest import mock

from notifier.companies import Company
from notifier.dedupe import job_keys
from notifier.models import Job
from notifier.sources import ashby, greenhouse, lever

# Trimmed-down copies of real API responses (checked 2026-10-29).
GREENHOUSE_RESPONSE = {"jobs": [{
    "id": 7565469003,
    "title": "Software Engineer Intern, BCI Applications ",
    "absolute_url": "https://boards.greenhouse.io/neuralink/jobs/7565469003?gh_jid=7565469003",
    "location": {"name": "South San Francisco, California, United States"},
    "first_published": "2026-02-18T17:29:03-05:00",
    "updated_at": "2026-09-30T18:24:09-04:00",
    "content": "&lt;p&gt;Build software for the &lt;strong&gt;Link&lt;/strong&gt; &amp;amp; more.&lt;/p&gt;",
}]}

LEVER_RESPONSE = [{
    "id": "d8f1da4b-3c9e-4aa4-80c2-893dd4b00497",
    "text": "E11 Bio - Research Intern",
    "hostedUrl": "https://jobs.lever.co/convergentresearch/d8f1da4b-3c9e-4aa4-80c2-893dd4b00497",
    "categories": {"location": "Alameda, California", "allLocations": ["Alameda, California"]},
    "workplaceType": "onsite",
    "createdAt": 1779780849186,
    "descriptionPlain": "Map the whole mouse brain.",
    "lists": [{"text": "What you'll do", "content": "<li>Write imaging pipelines</li>"}],
    "additionalPlain": "",
}]

ASHBY_RESPONSE = {"jobs": [{
    "id": "676890d4-5bab-484c-9d46-6e176c48168d",
    "title": "Engineering Intern (Summer 2027)",
    "jobUrl": "https://jobs.ashbyhq.com/metamorphic/676890d4-5bab-484c-9d46-6e176c48168d",
    "location": "Palo Alto",
    "secondaryLocations": [{"location": "New York"}],
    "isRemote": False,
    "isListed": True,
    "publishedAt": "2026-10-20T16:47:15.227+00:00",
    "descriptionPlain": "Foundation models trained on neural data.",
}]}


def company(ats, slug, name="Test Co"):
    return Company(name=name, ats=ats, slug=slug, careers_url=None, big_company=False)


class SourceTests(unittest.TestCase):
    def test_greenhouse(self):
        with mock.patch("notifier.sources.greenhouse.get_json", return_value=GREENHOUSE_RESPONSE):
            [job] = greenhouse.fetch(company("greenhouse", "neuralink", "Neuralink"))
        self.assertEqual(job.id, "greenhouse:7565469003")
        self.assertEqual(job.company, "Neuralink")
        self.assertEqual(job.title, "Software Engineer Intern, BCI Applications")
        self.assertEqual(job.posted_at, "2026-02-18")
        self.assertEqual(job.description, "Build software for the Link & more.")
        self.assertTrue(job.from_watchlist)

    def test_lever(self):
        with mock.patch("notifier.sources.lever.get_json", return_value=LEVER_RESPONSE):
            [job] = lever.fetch(company("lever", "convergentresearch"))
        self.assertEqual(job.id, "lever:d8f1da4b-3c9e-4aa4-80c2-893dd4b00497")
        self.assertEqual(job.location, "Alameda, California")
        self.assertIn("mouse brain", job.description)
        self.assertIn("Write imaging pipelines", job.description)
        self.assertNotIn("<li>", job.description)

    def test_ashby(self):
        with mock.patch("notifier.sources.ashby.get_json", return_value=ASHBY_RESPONSE):
            [job] = ashby.fetch(company("ashby", "metamorphic", "Metamorphic"))
        self.assertEqual(job.id, "ashby:676890d4-5bab-484c-9d46-6e176c48168d")
        self.assertEqual(job.location, "Palo Alto; New York")
        self.assertEqual(job.posted_at, "2026-10-20")


class DedupeKeyTests(unittest.TestCase):
    def make(self, url):
        return Job(id="simplify:x", company="", title="", url=url, location="", source="simplify",
                   posted_at=None, description=None, from_watchlist=False)

    def test_reads_board_ids_from_simplify_urls(self):
        cases = {
            "https://boards.greenhouse.io/neuralink/jobs/8005762003": "greenhouse:8005762003",
            "https://job-boards.greenhouse.io/neuralink/jobs/8005762003?utm_source=Simplify": "greenhouse:8005762003",
            "https://neuralink.com/careers/apply/?gh_jid=8005762003": "greenhouse:8005762003",
            "https://jobs.lever.co/convergentresearch/D8F1DA4B-3c9e-4aa4-80c2-893dd4b00497/apply":
                "lever:d8f1da4b-3c9e-4aa4-80c2-893dd4b00497",
            "https://jobs.ashbyhq.com/metamorphic/cf518648-4e65-4f7d-aa05-f01066d8bd8a/application?embed=true":
                "ashby:cf518648-4e65-4f7d-aa05-f01066d8bd8a",
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(job_keys(self.make(url)), {"simplify:x", expected})

    def test_other_urls_only_have_their_own_id(self):
        self.assertEqual(job_keys(self.make("https://www.metacareers.com/jobs/123")), {"simplify:x"})


if __name__ == "__main__":
    unittest.main()
