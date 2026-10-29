"""Send one email per job through Gmail SMTP."""

import os
import smtplib
from email.message import EmailMessage

from notifier.models import Job

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465  # SSL from the start of the connection (not STARTTLS)
TIMEOUT_SECONDS = 15


def format_email(job: Job) -> tuple[str, str]:
    subject = f"[Job] {job.company}: {job.title}"
    body = "\n".join([
        f"Company:  {job.company}",
        f"Title:    {job.title}",
        f"Location: {job.location or 'not listed'}",
        f"Source:   {job.source}",
        f"Posted:   {job.posted_at or 'unknown'}",
        "",
        # The URL goes on its own line so email clients turn it into a link.
        job.url,
        "",
    ])
    return subject, body


class Emailer:
    def __init__(self):
        # Read the settings when we're about to send, so --dry-run works
        # without any email settings.
        missing = [v for v in ("SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO") if not os.environ.get(v)]
        if missing:
            raise RuntimeError(f"missing environment variables: {', '.join(missing)}")
        self.user = os.environ["SMTP_USER"]
        self.password = os.environ["SMTP_PASSWORD"]
        self.to = os.environ["EMAIL_TO"]

    def send(self, job: Job) -> None:
        """Send one job. Raises an exception if sending fails."""
        subject, body = format_email(job)
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.user
        msg["To"] = self.to
        msg.set_content(body)
        # A fresh connection per email. With at most 25 emails per run, this is
        # simpler than reusing one connection and handling it dropping halfway.
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=TIMEOUT_SECONDS) as smtp:
            smtp.login(self.user, self.password)
            smtp.send_message(msg)
