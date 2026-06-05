# File Magician

Scripts and instructions for organizing, deduplicating, and categorizing the Toshiba external drive (`/Volumes/toshiba`).

## Overview

**Goal:** Clean up ~600-700GB of files on `/Volumes/toshiba` in two phases:
1. Deduplication — remove exact and near-duplicate files
2. Document categorization — classify and sort documents into labeled folders using OpenAI gpt-4o-mini

Photos are out of scope.

---

## Phase 1: Deduplication

### Install tools

```bash
brew install jdupes czkawka
```

- **jdupes** — fast, hash-based exact duplicate finder
- **czkawka** — near-duplicate detection (similar images, near-identical docs)

### Step 1: Dry run (no changes)

Always start here. Review before deleting anything.

```bash
jdupes -r -S /Volumes/toshiba
```

Flags:
- `-r` recursive (all subdirectories)
- `-S` show size of duplicate sets

### Step 2: Save report to file

```bash
jdupes -r -S /Volumes/toshiba > dupes_report.txt
```

Open `dupes_report.txt` and review before proceeding.

### Step 3: Automated duplicate mover

Use `dedup.py` instead of `jdupes -d`. It keeps the first copy in each duplicate group and moves all others to `/Volumes/toshiba/_deleted/` for review — no manual confirmation needed.

```bash
# Preview first (always)
python dedup.py --dry-run

# Run for real
python dedup.py
```

`dedup.py` skips the `_deleted/` and `_Organized/` folders automatically so re-runs are safe. After running, review `/Volumes/toshiba/_deleted/` and delete it when satisfied.

### Step 4: Near-duplicate scan (optional, after exact dedup)

```bash
czkawka_cli similar-images --directories /Volumes/toshiba
```

Review the output — near-duplicate image removal is manual, as automated removal risks deleting files that look similar but aren't.

### Safety rules

- Never run deletion commands without doing a dry run first
- Keep at least one backup before running any cleanup
- Work on a subfolder first if unsure, e.g. `/Volumes/toshiba/Documents`

---

## Phase 2: Document Categorization

`categorize.py` is a two-pass script that uses OpenAI gpt-4o-mini to discover categories from your files and then sort everything into them.

### How it works

**Pass 1 — discover categories (`sample`)**
Randomly samples up to 200 documents, extracts text snippets, and sends them to the model in batches. The model analyzes the content mix and proposes a category list (e.g. `Finance`, `Contracts`, `Personal`, `Work`). The list is saved to `categories.txt` for you to review and edit before anything is moved.

**Pass 2 — classify and move (`run`)**
Reads your approved `categories.txt`, processes every file on the drive, and moves each one to `/Volumes/toshiba/_Organized/<Category>/`. Non-documents (videos, archives, executables) go to `_Other/`. Documents the model can't confidently place go to `_Unsorted/`. The run is resumable — if interrupted or paused by the guardian, restart the same command and it will continue from where it stopped.

### Output structure

```
/Volumes/toshiba/_Organized/
├── Finance/
├── Personal/
├── Work/
├── ...           ← whatever categories the model proposed and you approved
├── _Unsorted/    ← documents that couldn't be classified
└── _Other/       ← non-document files (videos, zips, executables, etc.)
```

### Supported file types

Text extraction works for: `.pdf`, `.doc`, `.docx`, `.txt`, `.md`, `.rtf`, `.csv`, `.xlsx`, `.xls`, `.pptx`, `.ppt`, `.pages`, `.numbers`, `.keynote`, `.odt`, `.ods`, `.odp`

Everything else is treated as a non-document and moved to `_Other/`.

### Setup

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Create your .env file from the template
cp .env.example .env
```

Open `.env` and fill in your OpenAI API key. All other values are optional (defaults are shown in `.env.example`).

### Usage

**Step 1 — run the sampler**

```bash
python categorize.py sample
```

This walks the drive, samples up to 200 documents, and writes `categories.txt`. Takes a couple of minutes.

**Step 2 — review and edit categories**

Open `categories.txt` and adjust the list to your liking. Add, remove, or rename categories. Lines starting with `#` are ignored.

```
# Edit this list before running: python categorize.py run
Finance
Personal
Work
Legal
Medical
Travel
```

**Step 3 — dry run (always do this first)**

```bash
python categorize.py run --dry-run
```

Prints every proposed move to the terminal. Nothing is touched. Review the output and make sure the classifications look sensible before proceeding.

**Step 4 — live run**

```bash
python categorize.py run
```

Before any API calls, the script prints a cost/token estimate and asks you to confirm:

```
Pre-flight estimate
  Documents to classify : 4,200
  Other files (_Other)  : 800
  API batches           : 210
  Est. tokens           : ~1,150,000
  Est. cost             : ~$0.21
  Budget remaining      : 2,000,000 tokens

Proceed? [y/N]
```

After confirming, the run starts. Progress is saved after every batch. If the run is interrupted, restart the same command and it will continue from where it stopped.

### Guardian / kill switch

The guardian monitors three things during a live run and **pauses automatically** if any limit is breached:

| Threshold | `.env` key | Default | Meaning |
|---|---|---|---|
| Token budget | `TOKEN_BUDGET` | `2000000` | Total tokens across all runs for this job |
| Unsorted rate | `MAX_UNSORTED_RATE` | `0.50` | Pause if >50% of files land in `_Unsorted` |
| Category skew | `MAX_SKEW_RATE` | `0.80` | Pause if any one category exceeds 80% of all classified files |

**Token budget is cumulative.** If you set `TOKEN_BUDGET=1000000` and the run processes 800,000 tokens before pausing, the next run starts counting from 800,000. To continue, raise `TOKEN_BUDGET` in `.env` and run again.

**High unsorted rate** usually means `categories.txt` doesn't match your files. Edit the categories and resume.

**High skew** usually means one category is too broad (e.g. `Documents` absorbing everything). Split it into narrower categories and resume.

When the guardian pauses:

```
Guardian: pausing run — _Unsorted rate 62.3% exceeds limit 50.0% — categories may not match file content

  Tokens used : 340,000 / 2,000,000
  Est. cost   : $0.0510
  Distribution (200 files):
    _Unsorted              125  (62.5%)
    Finance                 45  (22.5%)
    Work                    30  (15.0%)

Progress saved to progress.json.
Resume with:
  python categorize.py run
```

### Safety rules

- Always do the dry run first
- Never categorize files you haven't already deduped (Phase 1 should be done first)
- Keep a backup before running the live pass

---

## File Structure

```
file-magician/
├── .env              # your API key + guardian thresholds (gitignored)
├── .env.example      # template — copy to .env and fill in
├── README.md         # this file
├── requirements.txt  # Python dependencies
├── dedup.py          # automated duplicate mover (uses jdupes)
├── categorize.py     # two-pass document categorization script
├── categories.txt    # generated by `sample`, edit before `run`
└── progress.json     # auto-generated during run, deleted on completion
```
