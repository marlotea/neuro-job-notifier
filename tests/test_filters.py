import unittest

from notifier import filters
from notifier.filters import KeywordMatcher, location_ok, role_type_ok
from notifier.main import KEYWORDS_PATH
from notifier.models import Job


def make_job(title="Software Engineer Intern", company="Acme", location="Boston, MA",
             description=None, kind=None, from_watchlist=False, source="greenhouse"):
    return Job(id=f"{source}:1", company=company, title=title, url="https://example.com",
               location=location, source=source, posted_at=None, description=description,
               from_watchlist=from_watchlist, kind=kind)


class LocationTests(unittest.TestCase):
    def test_keeps_north_america_and_remote(self):
        for loc in [
            "Boston, MA",
            "Toronto, ON",
            "Vancouver, British Columbia, Canada",
            "Remote in USA",
            "Remote in Canada",
            "Remote",
            "SF",
            "New York, NY; London, UK",  # one North American location is enough
            "Austin, Texas",
            "",  # empty: often remote
        ]:
            with self.subTest(loc=loc):
                self.assertTrue(location_ok(loc))

    def test_drops_everywhere_else(self):
        for loc in [
            "London, UK",
            "Remote in UK",
            "Remote in Germany",
            "Bengaluru, India",
            "Zurich, Switzerland",
            "Remote - EMEA",
            "Paris",
        ]:
            with self.subTest(loc=loc):
                self.assertFalse(location_ok(loc))

    def test_short_codes_need_a_comma(self):
        # "ON" and "IN" are normal words too, so a code only counts after a comma.
        self.assertFalse(location_ok("Work ON site in Berlin"))


class RoleTypeTests(unittest.TestCase):
    def test_keeps_early_career_titles(self):
        for title in [
            "Software Engineering Intern - Neural Interfaces",
            "Machine Learning Co-op (Winter 2027)",
            "Neuroscience Research Internship",
            "New Grad Software Engineer",
            "Junior Data Engineer",
            "Software Engineer, New Grad 2028",
        ]:
            with self.subTest(title=title):
                self.assertTrue(role_type_ok(make_job(title=title)))

    def test_drops_senior_and_non_early_career_titles(self):
        for title in [
            "Senior Software Engineer, BCI",
            "Staff Machine Learning Engineer",
            "Engineering Manager, Neural Decoding",
            "Sr. Firmware Engineer",
            "Software Engineer",  # no early-career signal from an ATS source
            "International Sales Representative",  # "intern" inside a word doesn't count
        ]:
            with self.subTest(title=title):
                self.assertFalse(role_type_ok(make_job(title=title)))

    def test_year_in_title_must_match(self):
        self.assertTrue(role_type_ok(make_job(title="Software Engineer Intern - Summer 2027")))
        self.assertFalse(role_type_ok(make_job(title="Software Engineer Intern - Summer 2026")))
        # New grad roles must start in 2028 or later.
        self.assertFalse(role_type_ok(make_job(title="New Grad Software Engineer 2027")))
        self.assertTrue(role_type_ok(make_job(title="New Grad Software Engineer 2028")))

    def test_simplify_titles_dont_need_intern_keyword(self):
        # Simplify's repos only list early-career roles, so any title is fine.
        job = make_job(title="Software Engineer - Simulation", kind="new_grad", source="simplify")
        self.assertTrue(role_type_ok(job))
        job = make_job(title="Senior Software Engineer", kind="new_grad", source="simplify")
        self.assertFalse(role_type_ok(job))


class KeywordTests(unittest.TestCase):
    def setUp(self):
        self.matcher = KeywordMatcher.from_yaml(KEYWORDS_PATH)

    def test_matches_neuro_titles(self):
        for text in [
            "Research Intern - Brain-Computer Interfaces",
            "Research Intern - Brain Computer Interfaces",
            "ML Intern, BCI Decoding",
            "Software Intern, BCIs",
            "EEG Signal Processing Intern",
            "Neuroengineering Intern",
            "Computational Neuroscience Research Intern",
            "Spike sorting algorithms intern",
            "Research Scientist Intern - AI-Driven Neural Interfaces",
            "Neural networks for EEG decoding",  # excluded phrase, but EEG still counts
        ]:
            with self.subTest(text=text):
                self.assertTrue(self.matcher.matches(text))

    def test_does_not_match_unrelated_titles(self):
        for text in [
            "Software Engineer Intern - Payments",
            "ABCIX Platform Intern",  # BCI inside a bigger word
            "Brainstorming Facilitator",  # "brain" inside a bigger word
            "Research Scientist Intern - Neural Graphics and World Models",
            "Design Verification Intern - Neural Engine",
            "ML Intern: training deep neural networks for ads ranking",
            "Simulation Engineer Intern - Neural Rendering",
        ]:
            with self.subTest(text=text):
                self.assertFalse(self.matcher.matches(text))


class RelevanceTests(unittest.TestCase):
    def setUp(self):
        self.matcher = KeywordMatcher.from_yaml(KEYWORDS_PATH)

    def test_small_watchlist_company_is_relevant_by_default(self):
        job = make_job(title="Software Engineer Intern", company="Metamorphic", from_watchlist=True)
        self.assertTrue(filters.is_relevant(job, self.matcher))

    def test_big_watchlist_company_needs_a_keyword(self):
        big = {"Meta"}
        plain = make_job(title="Software Engineer Intern", company="Meta", from_watchlist=True)
        self.assertFalse(filters.is_relevant(plain, self.matcher, big))
        neuro = make_job(title="Research Intern", company="Meta", from_watchlist=True,
                         description="Work on EMG wristband decoding at Reality Labs.")
        self.assertTrue(filters.is_relevant(neuro, self.matcher, big))

    def test_simplify_job_needs_a_keyword(self):
        job = make_job(title="Software Engineer Intern", source="simplify", kind="internship")
        self.assertFalse(filters.is_relevant(job, self.matcher))


if __name__ == "__main__":
    unittest.main()
