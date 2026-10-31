"""Envelope type -> handler. WS1 owns this file.

HANDLER CONVENTION (shared): a handler is `fn(store: Store, payload: dict) -> dict`. It returns the inner JSON
WITHOUT "ok"; the router adds {"ok": true}. Raise any exception for {"ok": false, "error": str(e)}.
Each feature module exposes a module-level dict `HANDLERS = {"<type>": fn}`; the router merges:
    wolfbox.router (core: init, get_state, submit_code, get_run, list_runs, list_assignments, seed, reset)
    wolfbox.tutor.HANDLERS            (WS2: ask, ta_summary)
    wolfbox.planner.handlers.HANDLERS (WS3: plan_get, plan_set_prefs, plan_solve)
    wolfbox.sync.handlers.HANDLERS    (WS8: sync, get_sync, list_docs, get_doc, deadlines)
Feature imports are wrapped in try/except ImportError so a missing workstream doesn't break the box.
"""
