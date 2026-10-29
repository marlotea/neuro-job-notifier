"""Tests for seeding, the safety cap, and only marking jobs seen after a successful send."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from notifier import main as main_mod
from notifier.models import Job


def neuro_job(n: int) -> Job:
    return Job(id=f"fake:{n}", company="NeuroCo", title=f"BCI Software Intern {n}",
               url=f"https://example.com/{n}", location="Remote", source="fake",
               posted_at=f"2026-10-{n % 28 + 1:02d}", description=None,
               from_watchlist=False, kind="internship")


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmp.name) / "seen.json"
        self.jobs: list[Job] = []
        # Replace the real sources with one fake source we control.
        self.sources = {"fake": lambda: list(self.jobs)}
        mock.patch.object(main_mod, "build_sources", lambda companies: self.sources).start()
        self.env = mock.patch.dict("os.environ", {"SMTP_USER": "a", "SMTP_PASSWORD": "b", "EMAIL_TO": "c"})
        self.env.start()
        self.sent: list[str] = []
        self.send = mock.patch("notifier.emailer.Emailer.send", side_effect=lambda job: self.sent.append(job.id))
        self.send.start()
        self.dotenv = mock.patch.object(main_mod, "_load_dotenv")
        self.dotenv.start()

    def tearDown(self):
        mock.patch.stopall()
        self.tmp.cleanup()

    def run_main(self, *flags) -> int:
        with redirect_stdout(io.StringIO()):
            return main_mod.main(["--state", str(self.state_path), *flags])

    def seen(self) -> set[str]:
        return set(json.loads(self.state_path.read_text())["seen_ids"])

    def test_first_run_seeds_without_emailing(self):
        self.jobs = [neuro_job(i) for i in range(5)]
        self.run_main()
        self.assertEqual(self.sent, [])
        self.assertEqual(len(self.seen()), 5)

    def test_new_job_after_seed_is_emailed_once(self):
        self.jobs = [neuro_job(1)]
        self.run_main()
        self.jobs.append(neuro_job(2))
        self.run_main()
        self.run_main()
        self.assertEqual(self.sent, ["fake:2"])

    def test_safety_cap(self):
        self.run_main()  # seed with no jobs
        self.jobs = [neuro_job(i) for i in range(40)]
        self.run_main()
        self.assertEqual(len(self.sent), 25)
        # The other 15 were never emailed, so they go out next run.
        self.run_main()
        self.assertEqual(len(self.sent), 40)

    def test_failed_email_is_retried_next_run(self):
        self.run_main()
        self.jobs = [neuro_job(1)]
        with mock.patch("notifier.emailer.Emailer.send", side_effect=OSError("smtp down")):
            self.assertEqual(self.run_main(), 1)
        self.assertNotIn("fake:1", self.seen())
        self.run_main()
        self.assertEqual(self.sent, ["fake:1"])

    def test_dry_run_does_not_write_state(self):
        self.jobs = [neuro_job(1)]
        self.run_main("--dry-run")
        self.assertFalse(self.state_path.exists())

    def test_failing_source_does_not_stop_others(self):
        def broken():
            raise RuntimeError("boom")
        self.sources["broken"] = broken
        self.run_main()
        self.jobs = [neuro_job(1)]
        self.assertEqual(self.run_main(), 1)
        self.assertEqual(self.sent, ["fake:1"])

    def test_same_job_from_board_and_simplify_is_emailed_once(self):
        board_job = Job(id="greenhouse:8005762003", company="Neuralink", title="Software Engineer Intern",
                        url="https://boards.greenhouse.io/neuralink/jobs/8005762003", location="Fremont, CA",
                        source="greenhouse", posted_at="2026-10-28", description=None,
                        from_watchlist=True)
        simplify_job = Job(id="simplify:abc", company="Neuralink", title="Software Engineer Intern",
                           url="https://boards.greenhouse.io/neuralink/jobs/8005762003?utm_source=Simplify",
                           location="Fremont, CA", source="simplify", posted_at="2026-10-29",
                           description=None, from_watchlist=False, kind="internship")
        self.run_main()  # seed with no jobs
        # Same run: both copies show up, only one email goes out.
        self.jobs = [board_job, simplify_job]
        self.run_main()
        self.assertEqual(self.sent, ["greenhouse:8005762003"])
        # A later run where only the Simplify copy is new: still no second email.
        self.run_main()
        self.assertEqual(len(self.sent), 1)


if __name__ == "__main__":
    unittest.main()
