# file-magician v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate categorize.py from Anthropic/Claude Haiku to OpenAI/gpt-4o-mini, add project-local `.env` credentials, and add a `RunGuardian` that pauses (with progress saved) when token budget, unsorted rate, or category skew thresholds are breached.

**Architecture:** All logic stays in `categorize.py` — a single-file script. A new `RunGuardian` class owns all monitoring state and threshold checks. Progress tracking is extended to persist cumulative token spend so the budget spans multiple runs. A pre-flight estimate function prints cost/token projections and requires an explicit `y` before any live API calls.

**Tech Stack:** Python 3.10+, `openai` SDK, `python-dotenv`, `pytest` (tests only), existing text-extraction libraries unchanged.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `.env.example` | Create | Template with all configurable keys documented |
| `.gitignore` | Create | Exclude `.env`, generated files, `__pycache__` |
| `requirements.txt` | Modify | Swap `anthropic` → `openai`; add `python-dotenv`, `pytest` |
| `categorize.py` | Modify | All logic changes (guardian, OpenAI, dotenv, pre-flight) |
| `tests/test_guardian.py` | Create | Unit tests for `RunGuardian` |
| `README.md` | Modify | Updated setup + guardian documentation |

---

### Task 1: Project scaffold

**Files:**
- Create: `.env.example`
- Create: `.gitignore`
- Modify: `requirements.txt`

- [ ] **Step 1: Create `.env.example`**

```
# Copy this file to .env and fill in your values.
# Never commit .env — it is gitignored.

# Required: get from https://platform.openai.com/api-keys
OPENAI_API_KEY=sk-...

# Guardian thresholds (optional — defaults shown below)

# Cumulative token cap across all runs. Raise this value to continue after a pause.
TOKEN_BUDGET=2000000

# Pause if more than this fraction of files land in _Unsorted.
# A high rate usually means categories.txt doesn't match the file content.
MAX_UNSORTED_RATE=0.50

# Pause if any single category claims more than this fraction of all classified files.
# High skew usually means one category is too broad and is absorbing everything.
MAX_SKEW_RATE=0.80
```

Save to: `.env.example`

- [ ] **Step 2: Create `.gitignore`**

```
.env
categories.txt
progress.json
__pycache__/
*.pyc
.DS_Store
```

Save to: `.gitignore`

- [ ] **Step 3: Update `requirements.txt`**

Replace the entire file with:

```
openai
python-dotenv
pypdf
python-docx
openpyxl
python-pptx
pytest
```

- [ ] **Step 4: Install dependencies**

```bash
pip install -r requirements.txt
```

Expected: all packages install without errors.

- [ ] **Step 5: Commit**

```bash
git add .env.example .gitignore requirements.txt
git commit -m "chore: project scaffold — dotenv, gitignore, openai deps"
```

---

### Task 2: `RunGuardian` class with tests

**Files:**
- Create: `tests/test_guardian.py`
- Modify: `categorize.py` (add `RunGuardian` class and `load_dotenv` call)

- [ ] **Step 1: Create the test file**

```bash
mkdir -p tests
```

Create `tests/test_guardian.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from categorize import RunGuardian


def make_guardian(**kwargs):
    defaults = dict(token_budget=10_000_000, max_unsorted_rate=0.5, max_skew_rate=0.8)
    defaults.update(kwargs)
    return RunGuardian(**defaults)


def test_ok_under_all_limits():
    g = make_guardian()
    g.record_usage(100)
    g.record_batch({f"f{i}.pdf": "Work" for i in range(20)})
    ok, _ = g.check()
    assert ok


def test_budget_exact_limit_triggers():
    g = make_guardian(token_budget=1000)
    g.record_usage(1000)
    ok, reason = g.check()
    assert not ok
    assert "token budget" in reason.lower()


def test_budget_initial_tokens_cumulative():
    g = make_guardian(token_budget=1000, initial_tokens=900)
    g.record_usage(100)
    ok, reason = g.check()
    assert not ok
    assert "token budget" in reason.lower()


def test_unsorted_rate_above_threshold():
    g = make_guardian()
    # 20 files: 11 _Unsorted = 55% > 50%
    batch = {f"f{i}.pdf": "_Unsorted" for i in range(11)}
    batch.update({f"g{i}.pdf": "Work" for i in range(9)})
    g.record_batch(batch)
    ok, reason = g.check()
    assert not ok
    assert "_Unsorted" in reason


def test_unsorted_rate_not_checked_below_20_files():
    g = make_guardian()
    # 19 files all _Unsorted — below the 20-file minimum, no check fires
    g.record_batch({f"f{i}.pdf": "_Unsorted" for i in range(19)})
    ok, _ = g.check()
    assert ok


def test_skew_triggers_for_dominant_real_category():
    g = make_guardian()
    # 25 files: 4 _Unsorted + 21 Work → Work is 84% of total > 80%
    batch = {f"f{i}.pdf": "_Unsorted" for i in range(4)}
    batch.update({f"g{i}.pdf": "Work" for i in range(21)})
    g.record_batch(batch)
    ok, reason = g.check()
    assert not ok
    assert "Work" in reason


def test_skew_does_not_trigger_for_unsorted():
    # _Unsorted is excluded from the skew calculation even when dominant.
    g = make_guardian(max_unsorted_rate=0.9)
    # 25 files: 21 _Unsorted (84% < 90% unsorted threshold), 4 Finance (16% < 80% skew threshold)
    batch = {f"f{i}.pdf": "_Unsorted" for i in range(21)}
    batch.update({f"g{i}.pdf": "Finance" for i in range(4)})
    g.record_batch(batch)
    ok, _ = g.check()
    assert ok


def test_total_classified_spans_batches():
    g = make_guardian()
    g.record_batch({"a.pdf": "Work", "b.pdf": "Finance"})
    g.record_batch({"c.pdf": "Work"})
    assert g.total_classified == 3
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
pytest tests/test_guardian.py -v
```

Expected: `ImportError` or `AttributeError` — `RunGuardian` doesn't exist yet.

- [ ] **Step 3: Add `load_dotenv` and `RunGuardian` to `categorize.py`**

At the top of `categorize.py`, after the existing imports, add:

```python
from dotenv import load_dotenv

load_dotenv()
```

Then add the `RunGuardian` class after the `# Configuration` block (around line 43, after `MODEL = ...`):

```python
# ---------------------------------------------------------------------------
# Guardian
# ---------------------------------------------------------------------------

class RunGuardian:
    """Monitors token spend, unsorted rate, and category skew. Pauses on breach."""

    def __init__(
        self,
        token_budget: int,
        max_unsorted_rate: float,
        max_skew_rate: float,
        initial_tokens: int = 0,
    ) -> None:
        self.token_budget = token_budget
        self.max_unsorted_rate = max_unsorted_rate
        self.max_skew_rate = max_skew_rate
        self.tokens_used = initial_tokens
        self._category_counts: dict[str, int] = {}

    @property
    def total_classified(self) -> int:
        return sum(self._category_counts.values())

    def record_usage(self, total_tokens: int) -> None:
        self.tokens_used += total_tokens

    def record_batch(self, classifications: dict[str, str]) -> None:
        for cat in classifications.values():
            self._category_counts[cat] = self._category_counts.get(cat, 0) + 1

    def check(self) -> tuple[bool, str]:
        """Return (ok, reason). ok=False means pause the run."""
        if self.tokens_used >= self.token_budget:
            return False, (
                f"token budget reached: {self.tokens_used:,}/{self.token_budget:,} tokens used"
            )

        if self.total_classified >= 20:
            unsorted = self._category_counts.get("_Unsorted", 0)
            unsorted_rate = unsorted / self.total_classified
            if unsorted_rate > self.max_unsorted_rate:
                return False, (
                    f"_Unsorted rate {unsorted_rate:.1%} exceeds limit {self.max_unsorted_rate:.1%} "
                    f"— categories may not match file content"
                )

            non_unsorted = {k: v for k, v in self._category_counts.items() if k != "_Unsorted"}
            if non_unsorted:
                max_cat = max(non_unsorted, key=non_unsorted.__getitem__)
                skew = non_unsorted[max_cat] / self.total_classified
                if skew > self.max_skew_rate:
                    return False, (
                        f"category '{max_cat}' has {skew:.1%} of files "
                        f"(limit {self.max_skew_rate:.1%}) — taxonomy may be too narrow"
                    )

        return True, ""

    def print_stats(self) -> None:
        est_cost = (self.tokens_used * 0.15) / 1_000_000
        print(f"\n  Tokens used : {self.tokens_used:,} / {self.token_budget:,}")
        print(f"  Est. cost   : ${est_cost:.4f}")
        if self._category_counts:
            print(f"  Distribution ({self.total_classified} files):")
            for cat, count in sorted(self._category_counts.items(), key=lambda x: -x[1]):
                pct = count / self.total_classified * 100
                print(f"    {cat:<22} {count:>5}  ({pct:.1f}%)")
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
pytest tests/test_guardian.py -v
```

Expected: all 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add categorize.py tests/test_guardian.py
git commit -m "feat: add RunGuardian with token/unsorted/skew monitoring"
```

---

### Task 3: Extend progress tracking to persist token spend

**Files:**
- Modify: `categorize.py` — update `load_progress` and `save_progress`

- [ ] **Step 1: Replace `load_progress` and `save_progress`**

Find the existing functions (around line 156–163) and replace both with:

```python
def load_progress() -> tuple[set[str], int]:
    """Returns (processed_paths, cumulative_tokens_used)."""
    if PROGRESS_FILE.exists():
        data = json.loads(PROGRESS_FILE.read_text())
        if isinstance(data, list):
            # migrate old format (plain list of paths)
            return set(data), 0
        return set(data.get("processed", [])), int(data.get("tokens_used", 0))
    return set(), 0


def save_progress(processed: set[str], tokens_used: int) -> None:
    PROGRESS_FILE.write_text(json.dumps({
        "processed": list(processed),
        "tokens_used": tokens_used,
    }))
```

- [ ] **Step 2: Run tests — confirm they still pass**

```bash
pytest tests/test_guardian.py -v
```

Expected: all 8 tests pass (guardian tests don't use progress functions).

- [ ] **Step 3: Commit**

```bash
git add categorize.py
git commit -m "feat: persist cumulative token spend in progress.json"
```

---

### Task 4: Swap Anthropic → OpenAI across all API calls

**Files:**
- Modify: `categorize.py` — imports, `sample_command`, `classify_batch`

- [ ] **Step 1: Swap the import**

In `categorize.py`, replace:

```python
import anthropic
```

with:

```python
import openai
```

- [ ] **Step 2: Update the `MODEL` constant**

Replace:

```python
MODEL = "claude-haiku-4-5-20251001"
```

with:

```python
MODEL = "gpt-4o-mini"
```

- [ ] **Step 3: Rewrite `sample_command` to use OpenAI**

Replace the entire `sample_command` function with:

```python
def sample_command() -> None:
    client = openai.OpenAI()

    print(f"Walking {DRIVE_PATH} ...")
    all_files = walk_files(DRIVE_PATH, skip_dirs={"_Organized"})
    doc_files = [f for f in all_files if is_document(f)]
    print(f"Found {len(doc_files)} document files. Sampling {min(SAMPLE_SIZE, len(doc_files))}.")

    sample = random.sample(doc_files, min(SAMPLE_SIZE, len(doc_files)))

    snippets = []
    for path in sample:
        text = extract_text(path)
        if text.strip():
            snippets.append(f"File: {path.name}\nContent: {text[:300]}")

    print(f"Extracted text from {len(snippets)} files. Sending to model in batches...")

    raw_categories: list[str] = []
    total_batches = (len(snippets) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(snippets), BATCH_SIZE):
        batch = snippets[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        print(f"  Batch {batch_num}/{total_batches} ...")

        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": (
                    "You are analyzing a sample of files from a personal archive to suggest a category taxonomy.\n\n"
                    f"Here are {len(batch)} file samples:\n\n"
                    + "\n\n---\n\n".join(batch)
                    + "\n\nBased on these files, suggest broad category names suitable for organizing this archive. "
                    "Reply with ONLY a JSON array of category name strings, nothing else. "
                    'Example: ["Finance", "Contracts", "Personal", "Work"]'
                ),
            }],
        )
        raw_categories.extend(parse_json_array(response.choices[0].message.content))

    print("\nConsolidating categories...")
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": (
                "Here is a raw list of document category names from multiple batches. "
                "Some may be duplicates or near-duplicates.\n\n"
                + json.dumps(list(set(raw_categories)))
                + "\n\nConsolidate into a clean final list of 5-15 broad categories "
                "suitable for a personal file archive. Reply with ONLY a JSON array of strings."
            ),
        }],
    )
    final_categories = parse_json_array(response.choices[0].message.content)

    if not final_categories:
        final_categories = ["Finance", "Personal", "Work", "Legal", "Medical", "Travel"]

    lines = [
        "# Edit this list before running: python categorize.py run",
        "# One category per line. Lines starting with # are ignored.",
        "",
    ] + final_categories

    CATEGORIES_FILE.write_text("\n".join(lines) + "\n")

    print(f"\nProposed categories written to: {CATEGORIES_FILE}")
    print("\nCategories:")
    for cat in final_categories:
        print(f"  - {cat}")
    print(f"\nEdit {CATEGORIES_FILE.name} if needed, then run:")
    print("  python categorize.py run --dry-run")
```

- [ ] **Step 4: Rewrite `classify_batch` to use OpenAI and return token count**

Replace the entire `classify_batch` function with:

```python
def classify_batch(
    client: openai.OpenAI,
    batch: list[tuple[Path, str]],
    categories: list[str],
) -> tuple[dict[str, str], int]:
    """Returns (classifications, total_tokens_used)."""
    cat_list = ", ".join(f'"{c}"' for c in categories)
    file_blocks = [
        f"File: {path.name}\nContent: {(snippet or '(no text)')[:300]}"
        for path, snippet in batch
    ]
    prompt = (
        f"Classify each file into exactly one of these categories: {cat_list}\n\n"
        'If a file does not fit any category, use "_Unsorted".\n\n'
        "Files to classify:\n\n"
        + "\n\n---\n\n".join(file_blocks)
        + "\n\nReply with ONLY a JSON object mapping each filename to its category. "
        'Example: {"report.pdf": "Finance", "letter.docx": "Personal"}'
    )

    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    result = parse_json_object(response.choices[0].message.content)
    if not result:
        result = {path.name: "_Unsorted" for path, _ in batch}
    return result, response.usage.total_tokens
```

- [ ] **Step 5: Run the guardian tests to confirm nothing regressed**

```bash
pytest tests/test_guardian.py -v
```

Expected: all 8 tests pass.

- [ ] **Step 6: Commit**

```bash
git add categorize.py
git commit -m "feat: migrate API client from Anthropic to OpenAI gpt-4o-mini"
```

---

### Task 5: Add pre-flight estimate

**Files:**
- Modify: `categorize.py` — add `import math` and `pre_flight_estimate` function

- [ ] **Step 1: Add `import math` to the imports block**

In `categorize.py`, add `import math` alongside the existing stdlib imports:

```python
import math
```

- [ ] **Step 2: Add `pre_flight_estimate` after the `# Destination helpers` section**

Insert the following function after `unique_dest` and before `# Progress tracking`:

```python
# ---------------------------------------------------------------------------
# Pre-flight estimate
# ---------------------------------------------------------------------------

def pre_flight_estimate(
    doc_files: list[Path],
    other_files: list[Path],
    guardian: RunGuardian,
) -> bool:
    """Print cost/token estimate and ask user to confirm. Returns True to proceed."""
    batch_count = math.ceil(len(doc_files) / BATCH_SIZE) if doc_files else 0
    est_input_tokens = int(len(doc_files) * SNIPPET_CHARS / 4) + batch_count * 200
    est_output_tokens = batch_count * 200
    est_total = est_input_tokens + est_output_tokens
    # gpt-4o-mini: $0.15/1M input, $0.60/1M output
    est_cost = (est_input_tokens * 0.15 + est_output_tokens * 0.60) / 1_000_000
    tokens_remaining = guardian.token_budget - guardian.tokens_used

    print("Pre-flight estimate")
    print(f"  Documents to classify : {len(doc_files):,}")
    print(f"  Other files (_Other)  : {len(other_files):,}")
    print(f"  API batches           : {batch_count:,}")
    print(f"  Est. tokens           : ~{est_total:,}")
    print(f"  Est. cost             : ~${est_cost:.4f}")
    print(f"  Budget remaining      : {tokens_remaining:,} tokens")
    if est_total > tokens_remaining:
        print()
        print("  Warning: estimated usage exceeds remaining budget.")
        print("  The run will process files until the budget is reached, then pause.")
        print("  Raise TOKEN_BUDGET in .env to increase the cap.")
    print()
    answer = input("Proceed? [y/N] ").strip().lower()
    return answer == "y"
```

- [ ] **Step 3: Run tests to confirm nothing regressed**

```bash
pytest tests/test_guardian.py -v
```

Expected: all 8 tests pass.

- [ ] **Step 4: Commit**

```bash
git add categorize.py
git commit -m "feat: add pre-flight cost estimate before live run"
```

---

### Task 6: Wire `RunGuardian` into `run_command`

**Files:**
- Modify: `categorize.py` — rewrite `run_command`

- [ ] **Step 1: Replace `run_command` entirely**

```python
def run_command(dry_run: bool) -> None:
    categories = load_categories()
    valid_categories = set(categories) | {"_Unsorted", "_Other"}
    client = openai.OpenAI()
    processed, tokens_used = load_progress()

    token_budget = int(os.getenv("TOKEN_BUDGET", "2000000"))
    max_unsorted_rate = float(os.getenv("MAX_UNSORTED_RATE", "0.50"))
    max_skew_rate = float(os.getenv("MAX_SKEW_RATE", "0.80"))
    guardian = RunGuardian(token_budget, max_unsorted_rate, max_skew_rate, initial_tokens=tokens_used)

    label = "DRY RUN — no files will be moved" if dry_run else "LIVE RUN — files will be moved"
    print(f"{label}")
    print(f"Categories : {', '.join(categories)}")
    print(f"Output     : {ORGANIZED_PATH}\n")

    all_files = walk_files(DRIVE_PATH, skip_dirs={"_Organized"})
    remaining = [f for f in all_files if str(f) not in processed]
    print(f"Total files: {len(all_files)}  |  Already processed: {len(processed)}  |  Remaining: {len(remaining)}\n")

    doc_files = [f for f in remaining if is_document(f)]
    other_files = [f for f in remaining if not is_document(f)]

    if not dry_run:
        if not pre_flight_estimate(doc_files, other_files, guardian):
            print("Aborted.")
            return
        for cat in categories:
            (ORGANIZED_PATH / cat).mkdir(parents=True, exist_ok=True)
        (ORGANIZED_PATH / "_Unsorted").mkdir(parents=True, exist_ok=True)
        (ORGANIZED_PATH / "_Other").mkdir(parents=True, exist_ok=True)

    moved = errors = 0

    # Non-documents → _Other
    for path in other_files:
        dest = ORGANIZED_PATH / "_Other" / path.name
        if dry_run:
            print(f"  [_Other]       {path.relative_to(DRIVE_PATH)}")
        else:
            try:
                shutil.move(str(path), str(unique_dest(dest)))
                processed.add(str(path))
                moved += 1
            except Exception as e:
                print(f"  ERROR {path}: {e}")
                errors += 1

    # Documents → classified
    total_batches = (len(doc_files) + BATCH_SIZE - 1) // BATCH_SIZE
    batch: list[tuple[Path, str]] = []

    for idx, path in enumerate(doc_files):
        batch.append((path, extract_text(path)))

        if len(batch) == BATCH_SIZE or idx == len(doc_files) - 1:
            batch_num = idx // BATCH_SIZE + 1
            print(f"Classifying batch {batch_num}/{total_batches} ({len(batch)} files)...")

            try:
                classifications, batch_tokens = classify_batch(client, batch, categories)
            except Exception as e:
                print(f"  API error: {e} — marking batch as _Unsorted")
                classifications = {p.name: "_Unsorted" for p, _ in batch}
                batch_tokens = 0

            if not dry_run:
                guardian.record_usage(batch_tokens)
                guardian.record_batch(classifications)

            for path, _ in batch:
                category = classifications.get(path.name, "_Unsorted")
                if category not in valid_categories:
                    category = "_Unsorted"

                dest = ORGANIZED_PATH / category / path.name
                if dry_run:
                    print(f"  [{category:<20}] {path.relative_to(DRIVE_PATH)}")
                else:
                    try:
                        shutil.move(str(path), str(unique_dest(dest)))
                        processed.add(str(path))
                        moved += 1
                    except Exception as e:
                        print(f"  ERROR {path}: {e}")
                        errors += 1

            if not dry_run:
                save_progress(processed, guardian.tokens_used)

                ok, reason = guardian.check()
                if not ok:
                    print(f"\nGuardian: pausing run — {reason}")
                    guardian.print_stats()
                    print(f"\nProgress saved to {PROGRESS_FILE.name}.")
                    print("Resume with:\n  python categorize.py run")
                    sys.exit(0)

            batch = []

    summary = "Would move" if dry_run else "Moved"
    count = moved + len(other_files) if dry_run else moved
    print(f"\n{summary}: {count} files | Errors: {errors}")

    if not dry_run and errors == 0:
        PROGRESS_FILE.unlink(missing_ok=True)
        print("Progress file cleaned up.")
```

- [ ] **Step 2: Run tests to confirm nothing regressed**

```bash
pytest tests/test_guardian.py -v
```

Expected: all 8 tests pass.

- [ ] **Step 3: Smoke-test with `--dry-run` (no API calls, no cost)**

```bash
OPENAI_API_KEY=test python categorize.py run --dry-run
```

Expected: prints `DRY RUN`, category list, file counts, then classification output. No API calls are made in dry-run mode (guardian is not active in dry-run).

- [ ] **Step 4: Commit**

```bash
git add categorize.py
git commit -m "feat: wire RunGuardian into run command with pre-flight estimate"
```

---

### Task 7: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace the `README.md` content**

Replace the entire file with:

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update README for OpenAI migration and guardian"
```

---

## Spec Coverage Check

| Spec requirement | Task |
|---|---|
| `.env` file with API key | Task 1 |
| `.env.example` template | Task 1 |
| `.gitignore` excludes `.env` | Task 1 |
| Swap `anthropic` → `openai` | Task 4 |
| Model: `gpt-4o-mini` | Task 4 |
| `TOKEN_BUDGET` in `.env` | Tasks 1 + 6 |
| `MAX_UNSORTED_RATE` in `.env` | Tasks 1 + 6 |
| `MAX_SKEW_RATE` in `.env` | Tasks 1 + 6 |
| `RunGuardian` class | Task 2 |
| Token budget is cumulative across runs | Tasks 3 + 6 |
| Guardian pauses (saves progress) on breach | Task 6 |
| Pre-flight estimate with `Proceed? [y/N]` | Tasks 5 + 6 |
| README updated | Task 7 |
