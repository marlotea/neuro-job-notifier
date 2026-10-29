"""Build and send one email per job through Gmail SMTP.

Each email has two versions of the same content: HTML (what Gmail shows) and
plain text (a fallback for clients that don't show HTML).
"""

import os
import smtplib
from datetime import date
from email.message import EmailMessage
from html import escape

from notifier.filters import Relevance, role_label
from notifier.models import Job

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465  # SSL from the start of the connection (not STARTTLS)
TIMEOUT_SECONDS = 15

SOURCE_NAMES = {
    "simplify": "SimplifyJobs list",
    "greenhouse": "Greenhouse",
    "lever": "Lever",
    "ashby": "Ashby",
}


def format_email(job: Job, why: Relevance | None = None, today: date | None = None) -> tuple[str, str, str]:
    """Return (subject, plain text body, HTML body)."""
    subject = f"[Job] {job.company}: {job.title}"
    rows = _detail_rows(job, why, today or date.today())
    return subject, _text_body(job, rows, why), _html_body(job, rows, why)


def _detail_rows(job: Job, why: Relevance | None, today: date) -> list[tuple[str, list[str]]]:
    """The label/value rows shared by both versions. Values are lists of lines."""
    locations = [loc.strip() for loc in job.location.split(";") if loc.strip()] or ["Not listed"]
    rows = [
        ("Role type", [role_label(job)]),
        ("Location", locations),
        ("Posted", [_posted(job.posted_at, today)]),
        ("Source", [_source(job)]),
    ]
    if why:
        rows.append(("Why it's here", [why.reason]))
    return rows


def _posted(posted_at: str | None, today: date) -> str:
    if not posted_at:
        return "Unknown"
    posted = date.fromisoformat(posted_at)
    days = (today - posted).days
    ago = "today" if days <= 0 else "yesterday" if days == 1 else f"{days} days ago"
    return f"{posted:%b} {posted.day}, {posted.year} ({ago})"


def _source(job: Job) -> str:
    name = SOURCE_NAMES.get(job.source, job.source)
    if job.source == "simplify":
        return name
    return f"{job.company} job board ({name})"


def _text_body(job: Job, rows, why: Relevance | None) -> str:
    lines = [f"{job.company} - {job.title}", ""]
    for label, values in rows:
        # Line the values up in a column: "Location       Austin, TX".
        lines.append(f"  {label:<15}{values[0]}")
        lines.extend(f"  {'':<15}{v}" for v in values[1:])
    if why and why.context:
        before, keyword, after = why.context
        lines += ["", f'  "...{before}{keyword}{after}..."']
    # The URL goes on its own line so email clients turn it into a link.
    lines += ["", "Apply:", job.url, ""]
    return "\n".join(lines)


def _html_body(job: Job, rows, why: Relevance | None) -> str:
    # Email clients ignore <style> blocks and modern CSS, so everything uses
    # inline styles and tables. That's normal for HTML email.
    detail_rows = "".join(
        f"""<tr>
          <td style="padding:6px 16px 6px 0;color:#6b7280;font-size:13px;white-space:nowrap;vertical-align:top;">{escape(label)}</td>
          <td style="padding:6px 0;color:#111827;font-size:14px;">{"<br>".join(escape(v) for v in values)}</td>
        </tr>"""
        for label, values in rows
        if label != "Role type"  # already shown as the colored badge
    )

    context_block = ""
    if why and why.context:
        before, keyword, after = (escape(part) for part in why.context)
        context_block = f"""
        <div style="margin:4px 0 20px;padding:10px 14px;background:#f9fafb;border-left:3px solid #d1d5db;color:#4b5563;font-size:13px;line-height:1.5;">
          &hellip;{before}<strong style="color:#111827;background:#fef3c7;">{keyword}</strong>{after}&hellip;
        </div>"""

    role = role_label(job)
    badge_color = "#1d4ed8" if role.startswith("Intern") else "#047857"
    url = escape(job.url, quote=True)

    return f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f3f4f6;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;padding:24px 12px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border:1px solid #e5e7eb;border-radius:10px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
        <tr><td style="padding:28px 28px 8px;">
          <div style="font-size:12px;letter-spacing:0.06em;text-transform:uppercase;color:#6b7280;font-weight:600;">{escape(job.company)}</div>
          <h1 style="margin:6px 0 12px;font-size:21px;line-height:1.3;color:#111827;font-weight:700;">{escape(job.title)}</h1>
          <span style="display:inline-block;padding:3px 10px;border-radius:999px;background:{badge_color};color:#ffffff;font-size:12px;font-weight:600;">{escape(role)}</span>
        </td></tr>
        <tr><td style="padding:16px 28px 4px;">
          <table role="presentation" cellpadding="0" cellspacing="0" style="border-top:1px solid #f3f4f6;width:100%;padding-top:8px;">
            {detail_rows}
          </table>
        </td></tr>
        <tr><td style="padding:12px 28px 28px;">
          {context_block}
          <a href="{url}" style="display:inline-block;padding:12px 22px;background:#111827;color:#ffffff;text-decoration:none;border-radius:8px;font-size:15px;font-weight:600;">View job posting &rarr;</a>
          <div style="margin-top:14px;font-size:12px;color:#9ca3af;word-break:break-all;">{url}</div>
        </td></tr>
      </table>
      <div style="max-width:560px;margin-top:12px;font-family:Arial,sans-serif;font-size:11px;color:#9ca3af;">
        Sent by neuro-job-scraper. One email per new job, checked twice a day.
      </div>
    </td></tr>
  </table>
</body>
</html>
"""


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

    def send(self, job: Job, why: Relevance | None = None) -> None:
        """Send one job. Raises an exception if sending fails."""
        subject, text, html = format_email(job, why)
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.user
        msg["To"] = self.to
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")  # Gmail shows this version
        # A fresh connection per email. With at most 25 emails per run, this is
        # simpler than reusing one connection and handling it dropping halfway.
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=TIMEOUT_SECONDS) as smtp:
            smtp.login(self.user, self.password)
            smtp.send_message(msg)
