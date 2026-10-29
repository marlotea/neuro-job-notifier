<img src="assets/icon.svg" width="64" height="64" alt="">

# neuro-job-scraper

A job notifier that runs twice a day on GitHub Actions. It looks for new
neuroscience-related ML and software roles: 2027 internships and co-ops, and
new grad roles starting in 2028 or later, in Canada, the US, or remote. It
sends one email per new job, with a link to the posting. If nothing new turns
up, it sends nothing.

## How it works

```
GitHub Actions cron (2x/day)
  -> run each source fetcher        (notifier/sources/)
  -> normalize every job into a Job (notifier/models.py)
  -> filter: location, role type, relevance (notifier/filters.py)
  -> drop jobs already in state/seen.json   (notifier/state.py)
  -> send one email per remaining job       (notifier/emailer.py)
  -> add sent job IDs to seen.json
  -> commit seen.json back to the repo
```

Sources so far:

| Source | What it reads |
|---|---|
| `simplify` | `listings.json` from [SimplifyJobs/Summer2027-Internships](https://github.com/SimplifyJobs/Summer2027-Internships) and [SimplifyJobs/New-Grad-Positions](https://github.com/SimplifyJobs/New-Grad-Positions) (`dev` branch) |

### Filtering rules

1. **Location:** keep the job if it mentions Canada, the US, a state or
   province, a major city, or "Remote". Drop "Remote in UK" and similar. Keep
   jobs with no location. The place lists are at the top of
   `notifier/filters.py`.
2. **Role type:** drop senior, staff, principal, lead, manager, and director
   titles. Titles from job boards must say intern, co-op, new grad, entry
   level, etc. Simplify titles don't have to, because those repos only list
   early-career roles. If a title names a year, internships must say 2027 and
   new grad roles must say 2028 or later.
3. **Relevance:** the title or description must match a term in
   `config/keywords.yaml`.

### Safety features

- **First run:** the first time a source works, every job it currently has is
  marked as seen and **no emails are sent**. This also applies to a source
  added later.
- **Cap:** at most 25 emails per run. Any extras go out on the next run.
- **Retries:** a job is only marked as seen after its email sends, so a failed
  email gets retried on the next run.
- **Errors:** if one source fails, the others still run. The run then shows
  as failed in the Actions tab (GitHub emails you about failed runs).

## Setup

### 1. Create a Gmail app password

App passwords need 2-Step Verification turned on for the Google account.

1. Go to <https://myaccount.google.com/security> and turn on **2-Step
   Verification** if it's off.
2. Go to <https://myaccount.google.com/apppasswords>, type a name like
   `job-notifier`, and click **Create**.
3. Copy the 16-character password. You won't be able to see it again.

### 2. Add the GitHub secrets

In the repo on GitHub, open **Settings → Secrets and variables → Actions →
New repository secret** and add:

| Secret | Value |
|---|---|
| `SMTP_USER` | the Gmail address that sends the emails |
| `SMTP_PASSWORD` | the app password from step 1 |
| `EMAIL_TO` | where job emails should go (can be the same address) |
| `ALERT_IMAP_USER` | *(phase 3)* the separate Gmail that receives LinkedIn alerts |
| `ALERT_IMAP_PASSWORD` | *(phase 3)* an app password for that account |

### 3. Run the first seed

You can skip this step: the first scheduled run seeds automatically. Seeding
locally lets you check the result before anything is emailed:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m notifier.main --seed      # writes state/seen.json, sends nothing
git add state/seen.json
git commit -m "Seed seen jobs"
git push
```

From then on, any job that wasn't in the seed gets an email.

### Local development

Put your settings in a `.env` file at the repo root (it's in `.gitignore`):

```
SMTP_USER=you@gmail.com
SMTP_PASSWORD=abcdefghijklmnop
EMAIL_TO=you@gmail.com
```

```bash
.venv/bin/python -m notifier.main --dry-run   # print emails, don't send, don't touch seen.json
.venv/bin/python -m notifier.main --seed      # mark everything current as seen, no emails
.venv/bin/python -m unittest discover -s tests -t .   # run the tests
```

`--state some/other.json` points the tool at a different state file, which is
handy for experiments.

To run it on GitHub by hand, go to **Actions → Job notifier → Run workflow**.

## Adding a keyword

Edit `config/keywords.yaml`. Terms match whole words in any case. A trailing
`*` matches any ending (`neuro*` matches `neurotechnology`). Put phrases that
cause false matches under `exclude:`. Then run the tests and a `--dry-run` to
see what changes.

## Note about GitHub's 60-day rule

GitHub disables scheduled workflows on repos with no activity for 60 days.
The automatic `seen.json` commits count as activity. But if no new jobs show
up for two months, nothing gets committed, and the schedule may stop. If
that happens, re-enable it in the **Actions** tab, or push any commit.
