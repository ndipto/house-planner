# ai_activity.py
# Visible log of live Meta model calls (demo transparency).
#
# What this file does: times every real runtime call to a Meta model
# (Muse Spark / Muse Image / Muse Voice Transcribe) and keeps the
# last 12 in st.session_state["ai_activity"] so the "AI activity"
# card can show viewers what ran. Only metadata is stored: model id,
# friendly label, task, duration, status, time. NEVER prompts,
# responses, or API keys.
#
# Outside a Streamlit run (plain `python` tests) every helper below
# is a silent no-op: it never touches session state and never raises.

import time

MAX_ENTRIES = 12

ENTRY_KEYS = ("model", "label", "task", "seconds", "status", "time")


def _store():
    """st.session_state inside a run, else None (never raises)."""
    try:
        import streamlit as st
        try:
            from streamlit.runtime.scriptrunner_utils.script_run_context import (
                get_script_run_ctx)
            if get_script_run_ctx() is None:
                return None
        except Exception:
            return None
        return st.session_state
    except Exception:
        return None


def _entry(model_id, label, task, seconds, status):
    """One metadata-only activity entry (no prompts, keys, replies)."""
    return {
        "model": str(model_id),
        "label": str(label),
        "task": str(task),
        "seconds": round(float(seconds), 1),
        "status": str(status),
        "time": time.strftime("%H:%M:%S"),
    }


def _append(entries, entry):
    """Pure: entries plus one, newest last, capped at MAX_ENTRIES."""
    return (list(entries or []) + [entry])[-MAX_ENTRIES:]


def record(model_id, label, task, seconds, status, _state=None):
    """Append one call entry; silent no-op outside Streamlit.

    _state injects a plain dict for tests (None = session state).
    """
    try:
        state = _state if _state is not None else _store()
        if state is None:
            return
        state["ai_activity"] = _append(state.get("ai_activity"),
                                       _entry(model_id, label, task,
                                              seconds, status))
    except Exception:
        pass


class timed:
    """Time one model call; record done/failed (or a retry mark).

    Use as `with timed(MODEL_ID, "Muse Spark", "Room program"):`
    around the client call. Success records `mark` ("done", or
    "retried" for later attempts); an exception records "failed"
    and propagates unchanged.
    """

    def __init__(self, model_id, label, task, mark="done",
                 _state=None):
        self.model_id = model_id
        self.label = label
        self.task = task
        self.mark = mark
        self._state = _state
        self.start = 0.0

    def __enter__(self):
        self.start = time.monotonic()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        record(self.model_id, self.label, self.task,
               time.monotonic() - self.start,
               "failed" if exc_type is not None else self.mark,
               _state=self._state)
        return False
