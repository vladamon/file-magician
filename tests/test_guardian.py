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
    # 61 files: 35 _Unsorted = 57% > 50% (must exceed 60-file minimum)
    batch = {f"f{i}.pdf": "_Unsorted" for i in range(35)}
    batch.update({f"g{i}.pdf": "Work" for i in range(26)})
    g.record_batch(batch)
    ok, reason = g.check()
    assert not ok
    assert "_Unsorted" in reason


def test_unsorted_rate_not_checked_below_60_files():
    g = make_guardian()
    # 59 files all _Unsorted — below the 60-file minimum, no check fires
    g.record_batch({f"f{i}.pdf": "_Unsorted" for i in range(59)})
    ok, _ = g.check()
    assert ok


def test_skew_triggers_for_dominant_real_category():
    g = make_guardian()
    # 62 files: 10 _Unsorted + 52 Work → Work is 84% of total > 80% (must exceed 60-file minimum)
    batch = {f"f{i}.pdf": "_Unsorted" for i in range(10)}
    batch.update({f"g{i}.pdf": "Work" for i in range(52)})
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


def test_skew_not_checked_when_no_unsorted_files():
    # When zero files land in _Unsorted, the skew check is skipped entirely
    # — a single dominant real category with perfect classification is fine.
    g = make_guardian()
    # 25 files, all Work — 100% skew — but unsorted == 0, so no check fires
    g.record_batch({f"f{i}.pdf": "Work" for i in range(25)})
    ok, _ = g.check()
    assert ok


def test_total_classified_spans_batches():
    g = make_guardian()
    g.record_batch({"a.pdf": "Work", "b.pdf": "Finance"})
    g.record_batch({"c.pdf": "Work"})
    assert g.total_classified == 3
