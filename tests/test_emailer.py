import unittest
from datetime import date

from notifier.emailer import format_email
from notifier.filters import KeywordMatcher, relevance
from notifier.main import KEYWORDS_PATH
from notifier.models import Job

TODAY = date(2026, 10, 29)


def make_job(**overrides):
    fields = dict(id="greenhouse:1", company="Neuralink", title="Software Engineer Intern, BCI Applications",
                  url="https://boards.greenhouse.io/neuralink/jobs/1", location="Austin, TX; Fremont, CA",
                  source="greenhouse", posted_at="2026-10-20", description=None,
                  from_watchlist=True, kind=None)
    fields.update(overrides)
    return Job(**fields)


class EmailFormatTests(unittest.TestCase):
    def test_subject_and_plain_text(self):
        subject, text, _ = format_email(make_job(), today=TODAY)
        self.assertEqual(subject, "[Job] Neuralink: Software Engineer Intern, BCI Applications")
        self.assertIn("Internship / co-op", text)
        self.assertIn("Oct 20, 2026 (9 days ago)", text)
        self.assertIn("Neuralink job board (Greenhouse)", text)
        # Each location gets its own line, and the URL sits on a line by itself.
        self.assertIn("Austin, TX\n", text)
        self.assertIn("\nhttps://boards.greenhouse.io/neuralink/jobs/1\n", text)

    def test_html_escapes_job_text(self):
        _, _, html = format_email(make_job(title="Intern <R&D>"), today=TODAY)
        self.assertIn("Intern &lt;R&amp;D&gt;", html)
        self.assertNotIn("<R&D>", html)

    def test_description_match_shows_highlighted_context(self):
        matcher = KeywordMatcher.from_yaml(KEYWORDS_PATH)
        job = make_job(company="Meta", from_watchlist=False, title="Research Scientist Intern",
                       description="Join Reality Labs to build EMG wristband decoders for AR glasses.")
        why = relevance(job, matcher)
        self.assertEqual(why.reason, 'Keyword "EMG" in description')
        _, text, html = format_email(job, why, today=TODAY)
        self.assertIn("build EMG wristband", text)
        self.assertIn(">EMG</strong>", html)

    def test_watchlist_reason(self):
        matcher = KeywordMatcher.from_yaml(KEYWORDS_PATH)
        why = relevance(make_job(title="IT Systems Administrator Intern"), matcher)
        self.assertTrue(why.reason.startswith("Watchlist company"))


if __name__ == "__main__":
    unittest.main()
