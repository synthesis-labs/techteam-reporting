# Handover Runbook — TechTeam Reporting

**Purpose:** what to do to keep the monthly AI adoption dashboard running while
Archana is away. This is the operational companion to [README.md](README.md)
(which explains *how the system is built*). Read this for *what to do, when, and
what to do when it breaks*.

**Dashboard (public):** https://synthesis-labs.github.io/techteam-reporting/dashboard/

**Two repos:**
- `synthesis-labs/techteam-reporting` (public) — code + workflow. You rarely touch this.
- `synthesis-labs/techteam-reporting-data` (private) — where the monthly raw exports land (Himesh / Azure pipeline / Kieron). This is what you keep an eye on.

---

## TL;DR — what you actually do each month

Most of the data is produced by other people on a schedule (see
[Who owns what](#who-owns-what-and-when)). While covering, your job is to
**coordinate and verify**, not to produce the exports yourself:

1. **First week of the month:** confirm **Himesh** has dropped the tool exports
   into `YYYY-MM/raw/` in the **private** repo, and confirm the **Azure
   pipeline** populated `projects.csv` (if it failed, ask **Kieron** for a manual
   export). Assessments only update every 2 months (Kieron).
2. Each push to the private repo triggers the build automatically — no action
   needed from you beyond making sure the files landed.
3. Wait ~5–10 min, then **confirm the dashboard updated**
   (see [How to confirm it worked](#how-to-confirm-it-worked)).
4. If anyone's data is missing or a build is red, follow
   [When it breaks](#when-it-breaks--triage) and ping the relevant owner.

You do **not** run any Python or Quarto by hand for the normal monthly update.
The whole pipeline runs in GitHub Actions.

---

## What "running the process" means

```
  drop raw exports          private repo CI            public repo CI
  into private repo   ──►    standardises data   ──►    aggregates + rebuilds   ──►   GitHub Pages
  (YOUR manual step)         (load.py)                  dashboard, publishes          (live site)
```

The only manual step is the first box. The rest is triggered by your push.

---

## Monthly process (step by step)

### 1. Gather the exports

For month `YYYY-MM`, the files below land in the private repo. **Most of these
are not your job** — see [Who owns what](#who-owns-what-and-when) for who updates
each and when. This table is the full set so you know what a complete month looks
like:

| File | Source | Owner / cadence |
|------|--------|-----------------|
| `employees.csv` (or `employee.xlsx`) | HR employee master | **Himesh** — first week of month |
| `claude.csv` | Claude admin console export | **Himesh** — first week of month |
| `cursor.csv` | Cursor admin export | **Himesh** — first week of month |
| `chatgpt.csv` | ChatGPT admin export | **Himesh** — first week of month |
| `gemini.csv` | Gemini admin export | **Himesh** — first week of month |
| `copilot.csv` | GitHub Copilot admin export | **Himesh** — first week of month |
| `projects.csv` | PS Project Tracker export | **Azure pipeline** (auto); **Kieron** manual export if it fails |
| `assessments.xlsx` | AI Maturity Self Assessment responses | **Kieron** — every 2 months, from his feedback survey |

> Tool exports change format sometimes. **Drop them in exactly as downloaded** —
> the loader knows the quirks (alternating rows, NBSP separators, etc., see
> [data/schema.md](data/schema.md#source-quirks)). If a tool is missing one
> month, just leave it out; the pipeline tolerates missing tools.

### Who owns what (and when)

You are **coordinating**, not producing most of these. Your job while covering is
to make sure each owner has done their part and to push/verify the build.

- **Himesh — first week of every month.** Updates `employees`, `claude`,
  `cursor`, `chatgpt`, `gemini`, and `copilot` into that month's
  `YYYY-MM/raw/` folder in the private repo.
- **Azure pipeline — automatic.** Updates `projects.csv` on its own.
  **Check in the first week of the month that it actually ran.** If it failed,
  **Kieron** pulls a manual `projects.csv` export and drops it in.
- **Kieron — every 2 months.** Updates `assessments.xlsx` based on the feedback
  survey he sends out. (So in off-months there's simply no new assessments file —
  that's expected, not a failure.)

If you're covering and a month's data looks incomplete, the first move is to
ping **Himesh** (tool exports) or **Kieron** (projects fallback / assessments).

### 2. Add to the private repo

In `synthesis-labs/techteam-reporting-data`:

```
YYYY-MM/
  raw/
    employees.csv
    claude.csv
    ... (all the files above)
```

You can do this via the GitHub web UI (upload files) or git. Then **commit and
push to `main`**.

### 3. Let CI run

- The **private** repo's CI runs `load.py` and writes `YYYY-MM/standardised/`,
  then notifies the public repo.
- The **public** repo's CI ("Build dashboard" workflow) then aggregates,
  rebuilds the pages, and publishes to GitHub Pages.

Watch it here:
- Public repo → **Actions** tab → **Build dashboard** workflow.

### 4. Confirm (see next section).

### 5. (If needed) Fix unmatched people

Some tool rows won't auto-match to an employee (new starters, handles, typo'd
emails). They land in `standardised/unmatched.csv`. To fix:

- Edit **`aliases.csv`** at the root of the **private** repo. Add a row:
  `source_value, source_type (email|handle), employee_code, notes`.
- Commit and push. CI re-runs automatically and the person gets matched.

You don't *have* to resolve every unmatched row for the dashboard to build —
it builds regardless. Resolve them when you want the numbers to be accurate.

---

## How to confirm it worked

1. **Actions tab (public repo):** the latest "Build dashboard" run is green ✅.
2. **The live site updated:** open the dashboard URL above. The new month should
   appear in the left sidebar under **Snapshots** (newest first), and the URL
   `.../dashboard/snapshot-YYYY-MM.html` should load.
3. **Trends home** shows the new month's data point on the charts.

GitHub Pages can lag ~1 min after the green checkmark. A hard refresh
(Cmd+Shift+R) clears stale caching.

---

## When it breaks — triage

Work top to bottom. Most failures are in the **private** repo's standardise step
or a malformed export.

### The "Build dashboard" run is red ❌

Open the failed run in the public repo's **Actions** tab and find the failed step:

| Failed step | Most likely cause | What to do |
|-------------|-------------------|------------|
| **Fetch private data repo** | Deploy key expired/rotated, or private repo renamed | Check `DATA_REPO_KEY` secret still valid — see [Credentials](#credentials--access). |
| **Aggregate history** (`aggregate.py`) | A malformed export or unexpected column in this month's data | Read the Python traceback; it names the file/column. Usually a bad export — re-download and re-push. |
| **Regenerate snapshot / trends** (`build*.py`) | Same as above, or a brand-new tool/tag not handled | Read traceback. If a new column broke parsing, that's a code change — escalate. |
| **Render dashboard** (Quarto) | Rare; usually a syntax issue in generated markdown | Re-run the job once (transient). If it persists, escalate. |
| **Publish to gh-pages** | Pages/permissions issue | Confirm Pages still points at `gh-pages` branch — see [README one-time Pages setup](README.md#one-time-github-pages-setup). |

**First move for a red run:** click **Re-run jobs**. A surprising number of
failures are transient (network, runner hiccups).

### The private repo's CI failed (data never reached the public repo)

Check the **private** repo's Actions tab → `standardise.yml`. If `load.py`
failed, the standardised data was never produced, so the public dashboard
won't update. The traceback names the offending file. Re-download that export
and push again.

### Nothing happened at all after my push

- Did the push actually land on `main` of the **private** repo?
- A push to the private repo's `main` fires a `data-updated` event that rebuilds
  the public dashboard automatically (this is the normal path — it's set up and
  live). If that notification didn't fire (check the private repo's Actions tab
  for a failed/missing `notify` run), trigger the build manually:
  Public repo → Actions → **Build dashboard** → **Run workflow** (workflow_dispatch).

### Last resort — run it locally

If CI is down and you must publish, you can run the whole pipeline by hand
(requires [Quarto](https://quarto.org) + `pip install plotly` + SSH access to
the private repo):

```bash
./data/sync_private.sh          # pull private data into data/
python data/aggregate.py
python dashboard/build.py
python dashboard/build_trends.py
cd dashboard && quarto render
# preview:
open ../dist/dashboard/index.html
```

This only previews locally. Publishing still goes through CI / the `gh-pages`
branch — don't hand-push to `gh-pages` unless you know what you're doing.

---

## Credentials & access

As the coordinator you need, **before** Archana leaves:

| What | Where | Needed for |
|------|-------|-----------|
| Write access to `synthesis-labs/techteam-reporting-data` (private) | GitHub org | Spot-checking / dropping files if an owner can't |
| Write access to `synthesis-labs/techteam-reporting` (public) | GitHub org | Re-running workflows, code fixes |

The people who actually produce the data hold the tool-specific access:

- **Himesh** — admin export access to Claude / Cursor / ChatGPT / Gemini /
  Copilot + the HR employee master.
- **Kieron** — PS Project Tracker access (manual `projects.csv` fallback) and the
  AI Maturity Self Assessment feedback survey + responses.

You don't need each tool's admin access yourself unless you're stepping in for an
owner — in which case get it from that owner.

**Secrets already configured in CI (you should not need to touch these):**
- `DATA_REPO_KEY` — deploy key letting public CI read the private repo. Lives in
  public repo → Settings → Secrets and variables → Actions.
- `PUBLIC_REPO_PAT` — PAT in the private repo that dispatches the `data-updated`
  event to the public repo (this powers the automatic rebuild-on-push).

If a key is rotated or expires, the re-setup steps are in
[README → Setup: private data repo + CI key](README.md#setup-private-data-repo--ci-key).

---

## Backfilling old months

Exactly the same as a current month: drop the older month's raw exports into
`YYYY-MM/raw/` in the private repo and push. CI rebuilds and the month appears
in the sidebar in date order.

---

## What NOT to do

- **Don't** rename or "clean up" raw exports before dropping them in — the loader
  expects the raw format.
- **Don't** commit raw data or `aliases.csv` to the **public** repo — it contains
  PII and is `.gitignore`d there for a reason. All source data lives in the
  private repo only.
- **Don't** hand-edit `data/history/*.csv`, the `snapshot-*.md` files, or
  `_quarto.yml` — they're all generated. Edit the inputs and let CI regenerate.
- **Don't** hand-push to the `gh-pages` branch — it's overwritten on every build.

---

## Escalation

If a build fails with a code-level error you can't resolve from a bad export
(e.g. a new tool format, a new column, a Python traceback in `aggregate.py` /
`build.py`), that's a code change, not an ops fix. Capture:

- The failed run URL (Actions tab),
- The full traceback,
- Which export/month triggered it,

and hand it to whoever owns the code (Archana). For *data* problems instead of
code problems, the owner depends on the file: tool exports / employees →
**Himesh**; `projects.csv` (Azure pipeline failure) or `assessments.xlsx` →
**Kieron**. The dashboard
keeps serving the last good build in the meantime — nothing is lost.
