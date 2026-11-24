// Renders docs/index.html (jobs) and docs/companies.html from the JSON files
// that notifier/site.py writes to docs/data/ on every run.

"use strict";

const SVG_NS = "http://www.w3.org/2000/svg";

// Small DOM helper. Text always goes in through textContent, never innerHTML,
// because job titles come from outside sources.
function el(tag, attrs, ...children) {
  const node = tag.startsWith("svg:") ? document.createElementNS(SVG_NS, tag.slice(4)) : document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.setAttribute("class", value);
    else if (key === "style") node.style.cssText = value;
    else node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

const external = (href) => ({ href, target: "_blank", rel: "noopener noreferrer" });

async function loadJson(path) {
  const response = await fetch(path, { cache: "no-cache" });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

// Fade rows in one after another (capped, so long lists don't drag).
function reveal(nodes) {
  nodes.forEach((node, i) => {
    node.classList.add("reveal-item");
    node.style.setProperty("--i", Math.min(i, 10));
  });
  return nodes;
}

// --- Contour figure ----------------------------------------------------------
// Same wobbly rings as the portfolio's hero (src/lib/contour.ts), with three
// lettered callouts. The center holds a big number instead of a photo.

function contourPath(cx, cy, r, k, phase = 0, points = 72) {
  let d = "";
  for (let i = 0; i < points; i++) {
    const a = (i / points) * Math.PI * 2;
    const rr = r * (1 +
      0.09 * Math.sin(3 * a + 0.7 * k + phase) +
      0.05 * Math.sin(7 * a + 1.3 * k + phase * 1.7) +
      0.03 * Math.sin(11 * a + phase * 0.5));
    const x = cx + Math.cos(a) * rr * 1.12;
    const y = cy + Math.sin(a) * rr * 0.88;
    d += `${i ? "L" : "M"}${x.toFixed(2)} ${y.toFixed(2)}`;
  }
  return `${d}Z`;
}

function drawFigure(center, callouts, phase) {
  const g = { w: 460, h: 230, cx: 150, cy: 115, r: 62, r0: 68, step: 8, labelX: 280, labelYs: [55, 115, 175], angles: [-38, 0, 38] };
  const rings = Array.from({ length: 6 }, (_, k) => el("svg:path", {
    d: contourPath(g.cx, g.cy, g.r0 + k * g.step, k, phase),
    "stroke-opacity": Math.max(0.05, 0.55 - 0.06 * k),
    pathLength: 1,
    class: "ring",
    style: `--k:${k};transform-origin:${g.cx}px ${g.cy}px`,
  }));
  const lines = callouts.map((c, i) => {
    const a = (g.angles[i] * Math.PI) / 180;
    const x0 = g.cx + Math.cos(a) * g.r;
    const y0 = g.cy + Math.sin(a) * g.r;
    const y = g.labelYs[i];
    return el("svg:g", { class: "callout", style: `--i:${i}` },
      el("svg:polyline", {
        points: `${x0},${y0} ${g.labelX - 14},${y} ${g.labelX - 5},${y}`,
        fill: "none", stroke: "var(--ink)", "stroke-opacity": 0.55, "stroke-width": 0.75,
      }),
      el("svg:circle", { cx: x0, cy: y0, r: 2, fill: "var(--ink)" }),
      el("svg:text", { x: g.labelX, y, "dominant-baseline": "middle", class: "callout-text", style: "font-size:12px" },
        el("svg:tspan", { class: "serif-italic", fill: "var(--accent)", style: "font-size:16px" }, c.letter),
        el("svg:tspan", { dx: 6, fill: "var(--ink)", style: "font-family:var(--mono)" }, c.text)));
  });
  const svg = el("svg:svg", { viewBox: `0 0 ${g.w} ${g.h}`, "aria-hidden": "true" },
    el("svg:g", { fill: "none", stroke: "var(--accent)", "stroke-width": 0.9, "stroke-linejoin": "round" }, rings),
    el("svg:circle", { cx: g.cx, cy: g.cy, r: g.r - 6, fill: "var(--tint)" }),
    el("svg:text", {
      x: g.cx, y: g.cy + 4, "text-anchor": "middle", "dominant-baseline": "middle",
      class: "serif-italic", fill: "var(--accent)", style: "font-size:58px",
    }, center),
    lines);
  document.getElementById("figure").replaceChildren(svg);
}

// --- Dates -------------------------------------------------------------------

const DAY = 24 * 60 * 60 * 1000;

function parseDate(iso) {
  // "2026-11-24" -> local midnight, so "today" doesn't shift with time zones.
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

const formatDate = (iso, opts = { month: "short", day: "numeric", year: "numeric" }) =>
  parseDate(iso).toLocaleDateString("en-US", opts);

function ago(iso) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const days = Math.round((today - parseDate(iso)) / DAY);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days}d ago`;
  if (days < 365) return `${Math.round(days / 30)}mo ago`;
  return `${Math.round(days / 365)}y ago`;
}

// "2h ago" for a full timestamp like "2026-11-24T15:02:11Z".
function timeAgo(iso) {
  const minutes = Math.round((Date.now() - new Date(iso)) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return days === 1 ? "yesterday" : `${days} days ago`;
}

const fullTime = (iso) => new Date(iso).toLocaleString("en-US",
  { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" });

// --- Last workflow run ---------------------------------------------------------
// Asks GitHub's API for the newest run of the notifier workflow, so the page
// shows when it last ran and whether it passed. If the API can't be reached
// (rate limit, private repo), it falls back to checked_at from the data file,
// which the run itself writes.

const REPO = "marlotea/neuro-job-notifier";
const WORKFLOW = "notify.yml";

async function showRunStatus(checkedAt) {
  const box = document.getElementById("run-status");
  const show = (dot, text, iso, href) => box.replaceChildren(
    el("span", { class: `dot ${dot}`, "aria-hidden": "true" }),
    href ? el("a", { ...external(href), title: fullTime(iso) }, text) : el("span", { title: fullTime(iso) }, text));

  if (checkedAt) show("", `last checked ${timeAgo(checkedAt)}`, checkedAt);
  try {
    const response = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?per_page=1`,
      { headers: { Accept: "application/vnd.github+json" } });
    if (!response.ok) return;
    const run = (await response.json()).workflow_runs?.[0];
    if (!run) return;
    const started = run.run_started_at || run.created_at;
    if (run.status !== "completed") {
      show("running", `workflow running now · started ${timeAgo(started)}`, started, run.html_url);
    } else {
      const passed = run.conclusion === "success";
      show(passed ? "ok" : "fail", `last workflow run ${timeAgo(started)} · ${passed ? "passed" : run.conclusion}`,
        started, run.html_url);
    }
  } catch {
    // Offline or blocked: keep the fallback text.
  }
}

// posted_at comes from the job board; first_seen is when we first found it.
const jobDate = (job) => job.posted_at || job.first_seen;

// --- Jobs page ---------------------------------------------------------------

const KIND_LABEL = { internship: "internship / co-op", new_grad: "new grad" };

function jobRow(job) {
  const date = jobDate(job);
  const locations = (job.location || "location not listed").split(";").map((s) => s.trim()).filter(Boolean);
  const where = locations.length > 2 ? `${locations.slice(0, 2).join(" · ")} +${locations.length - 2}` : locations.join(" · ");
  const meta = [where, `${job.posted_at ? "posted" : "found"} ${formatDate(date)}`, job.reason].filter(Boolean).join(" · ");
  return el("li", {},
    el("a", { class: "job", ...external(job.url) },
      el("span", { class: "job-main" },
        el("span", { class: "job-title" }, job.title),
        el("span", { class: "job-org" },
          el("span", { class: "at serif-italic" }, `@ ${job.company}`),
          el("span", { class: `tag ${job.kind}` }, KIND_LABEL[job.kind] || job.kind)),
        el("span", { class: "job-meta" }, meta)),
      el("span", { class: "job-side" },
        el("span", { class: "arrow", "aria-hidden": "true" }, "↗"),
        el("span", {}, ago(date)))));
}

async function jobsPage() {
  const list = document.getElementById("jobs");
  let data;
  try {
    data = await loadJson("data/jobs.json");
  } catch (err) {
    list.replaceChildren(el("li", { class: "empty" }, `Couldn't load the job list (${err.message}).`));
    return;
  }
  const jobs = data.jobs;
  showRunStatus(data.checked_at);
  const params = new URLSearchParams(location.search);
  const state = {
    q: params.get("q") || "",
    company: params.get("company") || "",
    kind: params.get("kind") || "",
    sort: params.get("sort") || "newest",
  };

  const companies = [...new Set(jobs.map((j) => j.company))].sort((a, b) => a.localeCompare(b));
  const count = (kind) => jobs.filter((j) => j.kind === kind).length;
  drawFigure(String(jobs.length), [
    { letter: "a", text: `${count("internship")} internships & co-ops` },
    { letter: "b", text: `${count("new_grad")} new grad roles` },
    { letter: "c", text: `${companies.length} companies · ${formatDate(data.updated, { month: "short", day: "numeric" })}` },
  ], 0.4);

  const search = document.getElementById("search");
  const companySelect = document.getElementById("company");
  const sortSelect = document.getElementById("sort");
  const kindButtons = [...document.querySelectorAll("#kinds .pill")];
  const perCompany = Object.fromEntries(companies.map((c) => [c, jobs.filter((j) => j.company === c).length]));
  companySelect.append(...companies.map((c) => el("option", { value: c }, `${c} (${perCompany[c]})`)));
  // A link from the companies page can name a company with no jobs right now.
  if (state.company && !perCompany[state.company]) companySelect.append(el("option", { value: state.company }, `${state.company} (0)`));

  search.value = state.q;
  companySelect.value = state.company;
  sortSelect.value = state.sort;

  function render() {
    const q = state.q.trim().toLowerCase();
    const shown = jobs.filter((j) =>
      (!state.company || j.company === state.company) &&
      (!state.kind || j.kind === state.kind) &&
      (!q || `${j.title} ${j.company} ${j.location}`.toLowerCase().includes(q)));
    const byDate = (a, b) => jobDate(b).localeCompare(jobDate(a));
    if (state.sort === "oldest") shown.sort((a, b) => byDate(b, a));
    else if (state.sort === "company") shown.sort((a, b) => a.company.localeCompare(b.company) || byDate(a, b));
    else shown.sort(byDate);

    kindButtons.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.kind === state.kind)));
    document.getElementById("tally").textContent =
      shown.length === jobs.length ? `${jobs.length} roles` : `${shown.length} of ${jobs.length}`;
    list.replaceChildren(...(shown.length
      ? reveal(shown.map(jobRow))
      : [el("li", { class: "empty" }, "No roles match these filters right now.")]));

    // Keep the filters in the URL so a filtered view can be shared or bookmarked.
    const next = new URLSearchParams();
    for (const [k, v] of Object.entries(state)) if (v && !(k === "sort" && v === "newest")) next.set(k, v);
    history.replaceState(null, "", next.toString() ? `?${next}` : location.pathname);
  }

  search.addEventListener("input", () => { state.q = search.value; render(); });
  companySelect.addEventListener("change", () => { state.company = companySelect.value; render(); });
  sortSelect.addEventListener("change", () => { state.sort = sortSelect.value; render(); });
  kindButtons.forEach((b) => b.addEventListener("click", () => { state.kind = b.dataset.kind; render(); }));
  render();
}

// --- Companies page ----------------------------------------------------------

function linkedinUrl(company) {
  return company.linkedin ||
    `https://www.linkedin.com/search/results/companies/?keywords=${encodeURIComponent(company.name)}`;
}

function companyRow(c) {
  const roles = `${c.open_jobs} open role${c.open_jobs === 1 ? "" : "s"}`;
  return el("li", { class: "company" },
    el("div", { class: "company-head" },
      el("h3", { class: "company-name" }, c.name),
      c.open_jobs
        ? el("a", { class: "open-link", href: `./?company=${encodeURIComponent(c.name)}` }, `${roles} →`)
        : el("span", { class: "open-link" }, "no open roles")),
    el("p", {}, c.description),
    el("div", { class: "company-links" },
      c.website ? el("a", external(c.website), "website ↗") : null,
      el("a", external(linkedinUrl(c)), "linkedin ↗"),
      c.careers_url && c.careers_url !== c.website ? el("a", external(c.careers_url), "careers ↗") : null,
      el("span", { class: "note" }, c.tracked ? "· board checked 2×/day" : "· not fetched directly")));
}

async function companiesPage() {
  const root = document.getElementById("companies");
  let data;
  try {
    data = await loadJson("data/companies.json");
  } catch (err) {
    root.replaceChildren(el("p", { class: "empty" }, `Couldn't load the company list (${err.message}).`));
    return;
  }
  const { companies, categories } = data;
  showRunStatus(data.checked_at);
  const params = new URLSearchParams(location.search);
  const state = { q: params.get("q") || "", category: params.get("category") || "" };
  const inCategory = (id) => companies.filter((c) => c.category === id).length;

  drawFigure(String(companies.length), [
    { letter: "a", text: `${inCategory("invasive-bci")} invasive BCI` },
    { letter: "b", text: `${inCategory("noninvasive-bci")} non-invasive BCI` },
    { letter: "c", text: `${companies.filter((c) => c.tracked).length} job boards checked` },
  ], 2.1);

  const pillFor = (id, label, n) => {
    const b = el("button", { class: "pill", type: "button", "data-category": id }, label.toLowerCase(), el("span", { class: "count" }, n));
    b.addEventListener("click", () => { state.category = id; render(); });
    return b;
  };
  const pills = [pillFor("", "All", companies.length), ...categories.map((cat) => pillFor(cat.id, cat.label, inCategory(cat.id)))];
  document.getElementById("categories").replaceChildren(...pills);

  const search = document.getElementById("search");
  search.value = state.q;
  search.addEventListener("input", () => { state.q = search.value; render(); });

  function render() {
    const q = state.q.trim().toLowerCase();
    pills.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.category === state.category)));
    const sections = [];
    categories.forEach((cat, index) => {
      if (state.category && cat.id !== state.category) return;
      const shown = companies
        .filter((c) => c.category === cat.id && (!q || `${c.name} ${c.description}`.toLowerCase().includes(q)))
        // Companies with open roles first, then A–Z.
        .sort((a, b) => (b.open_jobs > 0) - (a.open_jobs > 0) || a.name.localeCompare(b.name));
      if (!shown.length) return;
      const headingId = `${cat.id}-title`;
      sections.push(el("section", { class: "section", "aria-labelledby": headingId },
        el("div", { class: "section-head" },
          el("span", { class: "num serif-italic", "aria-hidden": "true" }, String(index + 1).padStart(2, "0")),
          el("h2", { id: headingId }, cat.label),
          el("span", { class: "section-rule", "aria-hidden": "true" }),
          el("span", { class: "tally" }, String(shown.length))),
        el("ul", { class: "rows" }, reveal(shown.map(companyRow)))));
    });
    root.replaceChildren(...(sections.length ? sections : [el("p", { class: "empty" }, "No companies match.")]));

    const next = new URLSearchParams();
    for (const [k, v] of Object.entries(state)) if (v) next.set(k, v);
    history.replaceState(null, "", next.toString() ? `?${next}` : location.pathname);
  }
  render();
}

if (document.body.dataset.page === "jobs") jobsPage();
else companiesPage();
