# file-magician v2 — Design Spec

**Date:** 2026-06-05  
**Status:** Approved

---

## Goals

1. Replace the machine-level `ANTHROPIC_API_KEY` env var with a project-local `.env` file so credentials stay scoped to this project.
2. Switch the AI provider from Anthropic (Claude Haiku) to OpenAI (`gpt-4o-mini`) — cheaper, sufficient for classification.
3. Add a `RunGuardian` that monitors token spend, unsorted rate, and category skew — auto-pausing (with progress saved) when any threshold is breached.
4. Add a pre-flight estimate before any live run so the user can abort before spending money.
5. Update README to document the new setup and guardian configuration.

---

## File Structure

```
file-magician/
├── .env              # gitignored — API key + guardian thresholds
├── .env.example      # committed — placeholder values, all options documented
├── .gitignore        # adds .env (categories.txt + progress.json already excluded)
├── requirements.txt  # swap anthropic → openai, add python-dotenv
├── categorize.py     # all changes live here
├── dedup.py          # unchanged
└── README.md         # updated setup + guardian docs
```

No new files beyond `.env`, `.env.example`, `.gitignore`, and the spec directory.

---

## Model

**`gpt-4o-mini`** (OpenAI)

| Metric | Value |
|---|---|
| Input price | $0.15 / 1M tokens |
| Output price | $0.60 / 1M tokens |
| Typical run (5,000 docs) | ~$0.20–0.40 |

Rationale: the task is pure text classification against a fixed label set — one of the simplest things you can ask an LLM to do. `gpt-4o-mini` is the cheapest OpenAI model that reliably returns valid JSON, which is all that's needed here.

---

## `.env` File

```dotenv
OPENAI_API_KEY=sk-...

# Guardian thresholds — tune to taste
TOKEN_BUDGET=2000000      # cumulative tokens across all runs; pause when reached
MAX_UNSORTED_RATE=0.50    # pause if >50% of classified files land in _Unsorted
MAX_SKEW_RATE=0.80        # pause if any single category exceeds 80% of classified files
```

All three guardian values are optional — the script falls back to the defaults above if not set.

---

## Dependency Changes (`requirements.txt`)

Remove:
- `anthropic`

Add:
- `openai`
- `python-dotenv`

Keep:
- `pypdf`, `python-docx`, `openpyxl`, `python-pptx`

---

## `categorize.py` Changes

### Startup

```python
from dotenv import load_dotenv
load_dotenv()  # loads .env from script directory
```

Called before anything else so `os.environ["OPENAI_API_KEY"]` is populated. The `openai.OpenAI()` client picks it up automatically.

### API Client Swap

| Before (Anthropic) | After (OpenAI) |
|---|---|
| `anthropic.Anthropic()` | `openai.OpenAI()` |
| `client.messages.create(model=..., messages=...)` | `client.chat.completions.create(model=..., messages=...)` |
| `response.content[0].text` | `response.choices[0].message.content` |
| no usage tracking | `response.usage.total_tokens` |

The prompt strings are unchanged — both APIs use the same `{"role": "user", "content": "..."}` message format.

### `progress.json` Schema Extension

Adds one field to track cumulative token spend:

```json
{
  "processed": ["path1", "path2", ...],
  "tokens_used": 45000
}
```

`tokens_used` persists across runs so the `TOKEN_BUDGET` is a **cumulative cap for the whole job**, not a per-session limit. To continue after a budget pause: raise `TOKEN_BUDGET` in `.env` and re-run.

### `RunGuardian` Class

```
RunGuardian(token_budget, max_unsorted_rate, max_skew_rate, initial_tokens=0)
```

**Methods:**

- `record_usage(total_tokens: int)` — add tokens from one API response
- `record_batch(classifications: dict[str, str])` — update category distribution counts
- `check() -> (ok: bool, reason: str)` — evaluate all thresholds; returns `(False, reason)` on breach
- `print_stats()` — prints tokens used, estimated cost, and category distribution table

**Checks (in order):**

1. `tokens_used >= token_budget` → pause (budget reached)
2. `_Unsorted / total > max_unsorted_rate` (only after ≥20 files classified) → pause (model drift)
3. `max_category / total > max_skew_rate`, excluding `_Unsorted` (only after ≥20 files) → pause (taxonomy skew)

**On breach:**

```
Guardian: pausing run — <reason>

  Tokens used:  1,234,567 / 2,000,000
  Est. cost:    $0.19
  Category distribution (450 files):
    Work                  210 (46.7%)
    Finance                80 (17.8%)
    _Unsorted              70 (15.6%)
    ...

Progress saved. Resume with:
  python categorize.py run
```

Then `sys.exit(0)`.

### Pre-Flight Estimate (`run` command, live run only)

Before any API call:

1. Walk drive and count remaining doc/non-doc files
2. Estimate tokens: `doc_count × (SNIPPET_CHARS ÷ 4) + batch_count × 200`
3. Compute cost using gpt-4o-mini pricing
4. Compare against remaining budget (`TOKEN_BUDGET - tokens_used_from_progress`)
5. Print summary and prompt `Proceed? [y/N]`

If the estimate exceeds the remaining budget, a warning is shown (but the user can still proceed — the guardian will pause mid-run when the budget is actually hit).

Skipped for `--dry-run` (no API calls, no cost).

### `sample` Command

Gains guardian token tracking (no thresholds — sampling is bounded by design at 200 files). Tokens from sampling are **not** counted toward the `TOKEN_BUDGET` since sampling is a one-time discovery step. Guardian only applies to `run`.

---

## README Updates

- Replace Anthropic API key setup with `.env` setup
- Document all `.env` options including guardian thresholds
- Add "Guardian / kill switch" section explaining what each threshold does and how to resume after a pause
- Update file structure table

---

## Out of Scope

- No changes to `dedup.py`
- No changes to text extraction logic
- No changes to file-walking or destination logic
- No UI, web interface, or background daemon
- No support for providers other than OpenAI (in this iteration)
