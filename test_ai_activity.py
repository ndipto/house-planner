# test_ai_activity.py
# AI activity helper tests: metadata-only entries, cap, bare-mode safety.
# Run: python test_ai_activity.py

from ai_activity import ENTRY_KEYS, MAX_ENTRIES, record, timed


def test_records_entries():
    """record() stores model, label, task, duration, status, time."""
    state = {}
    record("muse-spark-1.3", "Muse Spark", "Room program", 2.44,
           "done", _state=state)
    entries = state["ai_activity"]
    assert len(entries) == 1, "one entry stored"
    row = entries[0]
    assert row["model"] == "muse-spark-1.3", "real model id kept"
    assert row["label"] == "Muse Spark", row
    assert row["task"] == "Room program", row
    assert row["seconds"] == 2.4, "duration to 1 decimal"
    assert row["status"] == "done", row
    assert row["time"], "timestamped"
    print("PASS test_records_entries")


def test_caps_at_twelve():
    """Only the last 12 entries survive."""
    state = {}
    for index in range(20):
        record("m", "L", "T%d" % index, 0.1, "done", _state=state)
    entries = state["ai_activity"]
    assert len(entries) == MAX_ENTRIES == 12, len(entries)
    assert entries[0]["task"] == "T8", "oldest dropped"
    assert entries[-1]["task"] == "T19", "newest kept"
    print("PASS test_caps_at_twelve")


def test_never_stores_keys_or_prompts():
    """Entries carry metadata only; block data never leaks in."""
    import ai_activity

    row = ai_activity._entry("m", "L", "T", 1.0, "done")
    assert set(row) == set(ENTRY_KEYS), sorted(row)
    blob = repr(row)
    for token in ("key", "prompt", "response", "Bearer", "sk-"):
        assert token not in blob, token
    state = {}
    secret = "sk-live-primrose-moth-12345"
    with timed("m", "L", "T", _state=state):
        _ = secret
    assert secret not in repr(state), "block data never recorded"
    print("PASS test_never_stores_keys_or_prompts")


def test_safe_outside_streamlit():
    """Bare mode (tests): record/timed do nothing and never crash."""
    record("m", "L", "T", 1.0, "done")
    with timed("m", "L", "T"):
        pass
    try:
        with timed("m", "L", "T"):
            raise ValueError("boom")
    except ValueError:
        pass
    else:
        raise AssertionError("timed must not swallow exceptions")
    print("PASS test_safe_outside_streamlit")


def test_failed_and_retried_marks():
    """Exceptions record failed; later attempts record retried."""
    state = {}
    try:
        with timed("m", "L", "T", _state=state):
            raise RuntimeError("nope")
    except RuntimeError:
        pass
    with timed("m", "L", "T", mark="retried", _state=state):
        pass
    assert [row["status"] for row in state["ai_activity"]] == [
        "failed", "retried"], state["ai_activity"]
    print("PASS test_failed_and_retried_marks")


if __name__ == "__main__":
    test_records_entries()
    test_caps_at_twelve()
    test_never_stores_keys_or_prompts()
    test_safe_outside_streamlit()
    test_failed_and_retried_marks()
    print("ALL AI-ACTIVITY TESTS PASSED")
