<img src="assets/icon.svg" width="64" height="64" alt="">

# neuro-job-scraper

A job notifier that runs twice a day on GitHub Actions. It looks for new
neuroscience-related ML and software roles: 2027 internships and co-ops, and
new grad roles starting in 2027 or later, in Canada, the US, or remote. It
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
| `greenhouse/<slug>`, `lever/<slug>`, `ashby/<slug>` | each watchlist company's public job board, from `config/companies.yaml` |

If the same job is on both a company's board and Simplify, you get one email.
Simplify usually links to the board's own posting, so the board's job ID is
read from that link and saved in `seen.json` too (`notifier/dedupe.py`).

### Filtering rules

1. **Location:** keep the job if it mentions Canada, the US, a state or
   province, a major city, or "Remote". Drop "Remote in UK" and similar. Keep
   jobs with no location. The place lists are at the top of
   `notifier/filters.py`.
2. **Role type:** drop senior, staff, principal, lead, manager, and director
   titles. Titles from job boards must say intern, co-op, new grad, entry
   level, etc. Simplify titles don't have to, because those repos only list
   early-career roles. If a title names a year, internships must say 2027 and
   new grad roles must say 2027 or later.
3. **Relevance:**
   - Watchlist companies with `big_company: false` (neurotech startups and
     neuro labs): every early-career role counts, SWE included. This also
     applies when the job comes from Simplify, as long as the company name
     matches the watchlist.
   - Everyone else (`big_company: true` companies, and Simplify jobs from
     other companies): the title or description must match a term in
     `config/keywords.yaml`.

### Safety features

- **First run:** the first time a source works, every job it currently has
  is marked as seen and **no emails are sent**. Each company board is a
  separate source, so a company you add later is also seeded quietly on its
  first run. You only hear about jobs it posts after that.
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

## Adding a company

1. Find the company's careers page and click through to one job posting.
   Look at the URL:
   - `boards.greenhouse.io/<slug>/...` or `job-boards.greenhouse.io/<slug>/...` → Greenhouse
   - `jobs.lever.co/<slug>/...` → Lever
   - `jobs.ashbyhq.com/<slug>/...` → Ashby
2. Check that the slug returns that company's jobs:
   ```bash
   curl -s "https://boards-api.greenhouse.io/v1/boards/<slug>/jobs" | head -c 500
   curl -s "https://api.lever.co/v0/postings/<slug>?mode=json" | head -c 500
   curl -s "https://api.ashbyhq.com/posting-api/job-board/<slug>" | head -c 500
   ```
   Don't trust a slug that merely returns data. `ripple`, `kernel`, and
   `vector` all exist, but belong to other companies with the same name.
3. Add an entry to `config/companies.yaml`:
   ```yaml
   - name: Example Neuro
     ats: greenhouse
     slug: exampleneuro
     careers_url: https://exampleneuro.com/careers
     big_company: false   # true = jobs must also match a keyword
   ```
   If the company uses something else (Workday, a custom site...), set
   `ats: unknown` and keep the `careers_url`. Its Simplify listings will still
   follow the `big_company` rule.
4. Run `--dry-run` to see what it picks up.

## Adding a keyword

Edit `config/keywords.yaml`. Terms match whole words in any case. A trailing
`*` matches any ending (`neuro*` matches `neurotechnology`). Put phrases that
cause false matches under `exclude:`. Then run the tests and a `--dry-run` to
see what changes.

## Not covered yet

These companies don't use Greenhouse, Lever, or Ashby, so they aren't fetched
directly (checked 2026-10-29). Their listings can still reach you through
Simplify or LinkedIn alerts (phase 3). Check their careers pages yourself now
and then.

| Company | Job system | Careers page |
|---|---|---|
| Synchron | ADP Workforce Now | https://synchron.com/careers |
| Precision Neuroscience | Kula | https://www.precisionneuro.io/careers |
| Paradromics | JazzHR | https://paradromics.com/careers/ |
| Blackrock Neurotech | Rippling | https://blackrockneurotech.com/careers/ |
| Science Corp | own site (jobs.science.xyz) | https://science.xyz/careers/ |
| Axoft | Polymer | https://axoft.us/ |
| Phantom Neuro | no careers page found | https://phantomneuro.com/ |
| Neurable | JazzHR | https://www.neurable.com/careers |
| Kernel | no careers page or listings found | https://kernel.com/ |
| Cognixion | BambooHR | https://www.cognixion.com/careers |
| InteraXon (Muse) | unknown (old Lever board removed) | https://choosemuse.com/pages/careers |
| Ripple Neuro | Greenhouse board is linked but returns "not found" | https://rippleneuro.com/careers-at-ripple/ |
| Intan Technologies | none ("no open positions") | https://intantech.com/careers.html |
| Meta (Reality Labs) | metacareers.com | https://www.metacareers.com/ |
| Google DeepMind | Google Careers | https://deepmind.google/careers/ |
| Allen Institute | not identified (loaded by script) | https://alleninstitute.org/careers |
| HHMI Janelia | Workday | https://www.hhmi.org/careers/janelia |
| Simons Foundation / Flatiron Institute | Workday + Interfolio | https://www.simonsfoundation.org/careers/ |
| Wu Tsai Neurosciences Institute | Stanford jobs site | https://neuroscience.stanford.edu/get-involved-wu-tsai-neuro/careers |
| Mila | Workable | https://mila.quebec/en/careers |
| Vector Institute | ADP Workforce Now | https://vectorinstitute.ai/about/careers/ |
| Krembil / UHN | SmartRecruiters | https://jobs.smartrecruiters.com/UniversityHealthNetwork |
| Djavad Mowafaghian Centre for Brain Health | UBC Workday | https://www.centreforbrainhealth.ca/careers/ |
| Medtronic | Workday | https://medtronic.wd1.myworkdayjobs.com/MedtronicCareers |
| Boston Scientific | Eightfold | https://bostonscientific.eightfold.ai/careers |
| Neuronetics | Rippling | https://neurostar.com/about-us/careers/ |
| Abbott | Workday | https://abbott.wd5.myworkdayjobs.com/abbottcareers |

### Company status notes

- **Forest Neurotech** is now **Arbor Neuroscience** (its website says so).
  It posts jobs on Convergent Research's Lever board, which we fetch.
- **E11 Bio** also posts on Convergent Research's Lever board.
- **Blackrock Neurotech:** news reports say Tether bought a majority stake in
  2024. The company still operates and is hiring.
- **Motif Neurotech:** its Greenhouse board works, but it had no jobs and its
  site says it isn't hiring right now. It stays on the watchlist so new
  postings get picked up.
- **Kernel:** still operating (brain-health measurement), but no careers page
  or job listings were found.

## Note about GitHub's 60-day rule

GitHub disables scheduled workflows on repos with no activity for 60 days.
The automatic `seen.json` commits count as activity. But if no new jobs show
up for two months, nothing gets committed, and the schedule may stop. If
that happens, re-enable it in the **Actions** tab, or push any commit.
