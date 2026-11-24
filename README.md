<img src="assets/icon.svg" width="64" height="64" alt="">

# neuro-job-scraper

A job notifier that runs twice a day on GitHub Actions. It looks for new
neuroscience-related ML and software roles: 2027 internships and co-ops, and
new grad roles starting in 2027 or later, in Canada, the US, or remote. It
sends one email per new job, with a link to the posting. If nothing new turns
up, it sends nothing.

It also keeps a small website (in `docs/`, served by GitHub Pages) with every
matching job that's open right now, plus a page describing each company on
the watchlist. See [Website](#website).

## How it works

```
GitHub Actions cron (2x/day)
  -> run each source fetcher        (notifier/sources/)
  -> normalize every job into a Job (notifier/models.py)
  -> filter: location, role type, relevance (notifier/filters.py)
  -> drop jobs already in state/seen.json   (notifier/state.py)
  -> send one email per remaining job       (notifier/emailer.py)
  -> add sent job IDs to seen.json
  -> write docs/data/jobs.json and companies.json (notifier/site.py)
  -> commit seen.json and docs/data/ back to the repo
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
| `SMTP_USER` | the Gmail address that sends the emails (the account you made the app password for) |
| `SMTP_PASSWORD` | the app password from step 1 |
| `EMAIL_TO` | where job emails should go (can be the same address) |

`ALERT_IMAP_USER` and `ALERT_IMAP_PASSWORD` are for LinkedIn alerts, which
aren't built yet. Leave them unset for now.

### 3. Send a test email

Put the same three values in a `.env` file at the repo root (it's in
`.gitignore`, so it never gets committed), then:

```bash
.venv/bin/python -m notifier.main --test-email
```

You should get one sample job email within a minute. If it lands in spam,
mark it "Not spam" once so later ones arrive normally. If login fails, check
that `SMTP_PASSWORD` is the 16-character app password, not your normal Gmail
password.

### 4. Run the first seed

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

Your `.env` file looks like this:

```
SMTP_USER=you@gmail.com
SMTP_PASSWORD=abcdefghijklmnop
EMAIL_TO=you@gmail.com
```

```bash
.venv/bin/python -m notifier.main --dry-run   # print emails, don't send, don't touch seen.json
.venv/bin/python -m notifier.main --seed      # mark everything current as seen, no emails
.venv/bin/python -m notifier.main --test-email  # send one sample email
.venv/bin/python -m unittest discover -s tests -t .   # run the tests
```

`--state some/other.json` points the tool at a different state file, which is
handy for experiments.

To run it on GitHub by hand, go to **Actions → Job notifier → Run workflow**.

## Website

Two static pages in `docs/`, plain HTML, CSS, and JavaScript with no build
step. The look follows the portfolio's `feat/redesign-f` design (paper and
ink; Kaisei Decol, Instrument Serif italic and DM Mono; hairline rows,
numbered sections and the contour-ring figure), with a terracotta accent
instead of violet. To try another colour, change `--accent` and `--tint` at
the top of `docs/assets/style.css`.

Both pages show when the workflow last ran and whether it passed, linking to
that run. This comes from GitHub's public API; if it can't be reached (for
example, the hourly limit of 60 requests per visitor), the page falls back to
`checked_at`, the time the run itself wrote into the data files. Because
`checked_at` changes every run, the workflow now commits twice a day even when
no jobs change.

- **Jobs** (`docs/index.html`): every job that currently passes the filters,
  not only new ones. Sort by newest, oldest, or company; filter by company,
  role type, or a search. Filters are kept in the URL, so
  `?company=Neuralink&kind=internship` is a shareable link. The date shown is
  the board's posting date, or the date the notifier first found the job when
  the board gives none.
- **Companies** (`docs/companies.html`): the watchlist, grouped by category
  (invasive BCI, non-invasive BCI, neuromodulation, neuro-AI labs, big tech,
  institutes). Each card has a one-line description, links to the website,
  LinkedIn, and careers page, and how many roles are open. That count links to
  the jobs page filtered to that company.

Each run rewrites `docs/data/jobs.json` and `docs/data/companies.json`, and the
workflow commits them. Closed jobs drop off. If a source fails, its jobs from
the last run stay up. `--dry-run` doesn't touch these files.

**Turning it on (once):** in the repo on GitHub, open **Settings → Pages**,
set **Source** to *Deploy from a branch*, pick `main` and the `/docs` folder,
and save. The site appears at `https://marlotea.github.io/neuro-job-notifier/`
a minute later. GitHub Pages is free for public repos; a private repo needs a
paid plan.

**Viewing it locally:** browsers won't load the JSON files from `file://`, so
serve the folder:

```bash
python3 -m http.server -d docs 8000   # then open http://localhost:8000
```

After editing `config/companies.yaml`, the company page updates on the next
run. To refresh the data files right away without emailing anything, seed a
throwaway copy of the state:

```bash
cp state/seen.json /tmp/seen.json
.venv/bin/python -m notifier.main --seed --state /tmp/seen.json
```

## What the emails look like

Each job gets its own email. The subject is `[Job] {company}: {title}`. The
body is a card with:

- the company, the title, and a badge (**Internship / co-op** or **New grad**)
- location (one line each), posted date (with "N days ago"), and source
- **Why it's here**: either "Watchlist company", or the keyword that matched.
  When the keyword was found in the description, the sentence around it is
  shown with the keyword highlighted, so you can quickly judge borderline
  matches.
- a **View job posting** button, with the plain link underneath

There's also a plain-text version for email apps that don't show HTML. The
template is in `notifier/emailer.py`.

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
     category: noninvasive-bci   # section on the company page
     description: One sentence on what they build.
     website: https://exampleneuro.com/
     linkedin: https://www.linkedin.com/company/exampleneuro  # optional
     ats: greenhouse
     slug: exampleneuro
     careers_url: https://exampleneuro.com/careers
     big_company: false   # true = jobs must also match a keyword
   ```
   Categories: `invasive-bci`, `noninvasive-bci`, `neuromod`, `neuro-ai`,
   `big-tech`, `institute`. Only add `linkedin` once you've confirmed the
   page (the company's own site usually links it). Without it, the site links
   to a LinkedIn search for the name.
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
directly (checked 2026-10-29, and 2026-11-24 for the BCI companies added then). Their listings can still reach you through
Simplify. Check their careers pages yourself now
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
| CorTec | own careers page (Germany) | https://www.cortec-neuro.com/careers |
| INBRAIN Neuroelectronics | Personio (jobs in Spain) | https://inbrain-neuroelectronics.jobs.personio.com/ |
| Diagnostic Biochips | none found | https://www.diagnosticbiochips.com/ |
| Emotiv | none found | https://www.emotiv.com/ |
| OpenBCI | own careers page | https://openbci.com/careers |
| Neurosity | none found | https://neurosity.co/ |
| Arctop | own careers page | https://www.arctop.com/careers |
| BrainCo | own careers page | https://www.brainco.tech/careers |
| NextSense | none found | https://www.nextsense.io/ |
| Elemind | none found | https://elemindtech.com/ |
| Openwater | none found | https://www.openwater.health/ |
| Piramidal | none found | https://piramidal.ai/ |
| ONWARD Medical | none found | https://www.onwd.com/ |
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
- **Merge Labs:** its Ashby slug is `Merge Labs`, with a space. `merge` is a
  different company (Merge, the API startup).
- **Same-name traps found on 2026-11-24:** `ashby/kernel` (a London company),
  `ashby/brainco` (an AI company), and `greenhouse/setpoint` (a finance
  company) are not the neuro companies.
- **Kernel:** still operating (brain-health measurement), but no careers page
  or job listings were found.

## Note about GitHub's 60-day rule

GitHub disables scheduled workflows on repos with no activity for 60 days.
The automatic `seen.json` commits count as activity. But if no new jobs show
up for two months, nothing gets committed, and the schedule may stop. If
that happens, re-enable it in the **Actions** tab, or push any commit.
