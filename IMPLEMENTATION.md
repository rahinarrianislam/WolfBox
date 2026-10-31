# WolfBox: Implementation Plan

Companion to [`SPEC.md`](SPEC.md). This doc is written so workstreams can be built **in parallel by different people or agents**. The contracts in §3–§5 are the source of truth. Change them only by editing this file and telling everyone.

---

## 1. Architecture

```
Browser (student / TA / instructor pages, vanilla HTML+JS)
   │  REST (JSON)
   ▼
Orchestrator  (FastAPI, runs on a laptop)
   │  BoxClient interface: LocalBoxClient | MaritimeBoxClient
   │  - provisions one box per student (idempotent)
   │  - sends envelope messages to the box's POST /chat
   ▼
WolfBox  (FastAPI in a Maritime agent box, one per student)
   ├─ GET /health, POST /chat   (Maritime container contract)
   ├─ router  → dispatches envelope types
   ├─ store   → all state under $DATA_DIR (= /data on Maritime)
   ├─ runner  → pytest in a subprocess, background thread
   ├─ tutor   → Gemma 4: tags, hints, answers, TA summary, nudge draft
   └─ planner → deterministic solver + Gemma pref parsing / explanation
                    │
                    ▼
              Gemini API (Gemma 4)
```

**Offline mode.** With no internet, Maritime and the Gemini API are both unreachable, so offline means *everything on one laptop*: `BOX_BACKEND=local` (boxes are local processes, `DATA_DIR=./.data/<id>`) + `GEMMA_BACKEND=ollama` (Gemma 4 served by Ollama at `OLLAMA_URL`, default `http://127.0.0.1:11434`). The code is identical; only env changes. `scripts/offline.sh` starts it.

```
Online:   Browser → Orchestrator → Maritime boxes → Gemini API (Gemma 4)
Offline:  Browser → Orchestrator → local boxes    → Ollama (Gemma 4, local)
Auto:     … → boxes → Gemini API, and on network failure → Ollama
```

**Rule:** the box owns all student state. The orchestrator is stateless apart from a `students.json` registry that maps student id to box id.

## 2. Repo layout

```
Dockerfile                  # builds the BOX (Maritime repo builds need it at root)
box/
  start.py                  # reads $PORT, runs uvicorn (Maritime: no shell-string CMD)
  requirements.txt          # fastapi, uvicorn, google-genai, pytest
  wolfbox/
    main.py                 # FastAPI app: /health, /chat; first-boot init
    protocol.py             # envelope parsing + response helpers (§3)
    router.py               # type → handler
    store.py                # DATA_DIR I/O: runs, profile, plan, snapshots
    runner.py               # run pytest, parse results, background jobs
    tutor.py                # tagging, hints, ask, ta_summary, nudge
    nudge.py                # pure rule: is the student stuck?
    gemma.py                # Gemini client wrapper + FakeGemma
    sync/
      manifest.py           # fetch + validate course.json
      fetch.py              # download items, sha256, keep previous version for diffing
      extract.py            # pdf (pypdf) / md / html → text
      process.py            # Gemma: summarize, deadlines, change note; create workspaces
      index.py              # keyword index for ask citations (P2)
      jobs.py               # background sync job state
    planner/
      solver.py             # pure: catalog + prefs + transcript → options
      prefs.py              # Gemma: text → Prefs JSON; explain options
  assignments/hw4/          # template copied to $DATA_DIR/repo on first boot
    hw4.py                  # starter code (stubs)
    test_hw4.py
    README.md               # the assignment prompt
  data/
    catalog.json            # SAMPLE sections (label in UI: "sample data")
    requirements.json       # SAMPLE degree requirements
  tests/                    # pytest for box modules (Gemma faked)
orchestrator/
  requirements.txt          # fastapi, uvicorn, httpx, maritime
  wolfhub/
    main.py                 # REST API for the UI (§4) + serves static/
    boxes.py                # BoxClient protocol + Local/Maritime impls
    registry.py             # students.json: id → {name, box_id, backend}
    aggregate.py            # instructor heatmap (P2)
  course_site/              # MOCK course site, served at /course/<course>/
    csc116/
      course.json           # manifest (§5)
      published/…           # hw4/, syllabus.md, lecture slides (pdf/md), announcements
      staged/…              # hw5/, hw4-v2/ — moved into the manifest by "Publish"
  static/
    serial.js               # Web Serial desk-light driver (WS7)
    index.html              # pick a student / role
    student.html            # editor, run results, hint, ask, nudge banner, Plan tab
    ta.html                 # student list + handoff summary
    instructor.html         # heatmap (P2)
    app.js, style.css       # shared; Hacktoberfest palette from the deck
firmware/
  desk_light/desk_light.ino # built-in LED only (WS7)
seed/
  alex/                     # runs.jsonl, profile.json, plan.json, snapshots/
  sam/                      # empty/fresh (for the contrast demo)
scripts/
  dev.sh                    # run 2 local boxes + orchestrator
  offline.sh                # dev.sh + GEMMA_BACKEND=ollama; checks Ollama is up and the model is pulled
  seed.py                   # push seed/<id>/ into a box (via `seed` envelope)
  provision.py              # create boxes on Maritime for alex, sam, …
  demo_reset.py             # reset demo state between rehearsals
```

## 3. Box protocol (WolfBox ⇄ Orchestrator)

Maritime only routes `POST /chat` with body `{"message": "<string>", "source": "..."}` and must reply within **30s**. The reply is taken from the JSON field `response`.

So:

- **Request:** `message` is a JSON string, the *envelope*: `{"v": 1, "type": "<type>", ...payload}`. A plain non-JSON message is treated as `{"type": "ask", "text": message}`, so `maritime chat alex "hi"` still works.
- **Response:** `{"response": "<JSON string>"}`. The inner JSON is always `{"ok": true, ...}` or `{"ok": false, "error": "<msg>"}`.
- Every handler must return in **< 25s**. Anything slower is started in a background thread and polled.
- `submit_code`, `get_state`, `list_runs`, and `ta_summary` take an optional `assignment` (default: the most recently due assignment with tests). Workspaces live at `repo/<assignment>/`.
- The box also serves `GET /schedules` → `[{"id": "sync", "cron": "*/15 * * * *", "prompt": "{\"v\":1,\"type\":\"sync\"}"}]`. Maritime delivers that prompt to `/chat` with `source: "scheduled"`. Verify the schedule entry format in WS0.

| type | payload | returns (inner JSON, besides `ok`) |
|---|---|---|
| `init` | `{student_id, name}` | `{created: bool}`. Writes `profile.json` if missing and copies the assignment template. Idempotent. |
| `get_state` | `{}` | `{student_id, name, assignment, code, last_run: Run\|null, nudge: Nudge, profile: ProfileSummary, llm: LlmStatus}` |
| `submit_code` | `{files: {"hw4.py": "<src>"}}` | `{run_id, status: "running"}` |
| `get_run` | `{run_id}` | `{run: Run}`. `run.status` is `running`, `done`, or `error`. `run.hint` is null until generated (`hint_status`: `pending\|ready\|failed`). |
| `list_runs` | `{limit?: 20}` | `{runs: [Run]}`, newest first, without code |
| `ask` | `{text}` | `{reply}` (Gemma, history-aware, 25s timeout → canned fallback) |
| `ta_summary` | `{}` | `{markdown}` (Gemma; cached by last run_id) |
| `plan_get` | `{}` | `{plan: Plan, remaining: [Requirement], options: [Option]}` |
| `plan_set_prefs` | `{text}` | `{prefs: Prefs, echo: "<one-line restatement>"}` |
| `plan_solve` | `{full_sections?: [section_id]}` | `{options: [Option]}` (≤ 3, each with `explanation`) |
| `sync` | `{course_url?}` (defaults to env `COURSE_URL`) | `{job_id, status: "running"}` |
| `get_sync` | `{job_id}` | `{job: SyncJob}` |
| `list_docs` | `{course?}` | `{docs: [DocMeta]}` (no text) |
| `get_doc` | `{doc_id}` | `{doc: DocMeta, text}` |
| `deadlines` | `{days?: 14}` | `{deadlines: [Deadline]}` sorted by `due` |
| `list_assignments` | `{}` | `{assignments: [{id, title, due, has_tests, source: "sync"\|"template"}]}` |
| `seed` | `{files: {"<relpath>": "<content>"}}` | `{written: n}`. **Only if env `ALLOW_SEED=1`.** Paths must stay inside `DATA_DIR`. |
| `reset` | `{}` | Wipes `DATA_DIR` and re-inits. **Only if `ALLOW_SEED=1`.** |

## 4. Orchestrator REST API (UI ⇄ Orchestrator)

All JSON. Mostly thin pass-throughs to the box.

```
GET  /api/students                       → [{id, name, backend, box_id}]
POST /api/students {id, name}            → provision + init (idempotent)
GET  /api/students/{id}/state            → box get_state
POST /api/students/{id}/submit {code}    → box submit_code → {run_id}
GET  /api/students/{id}/runs/{run_id}    → box get_run          (UI polls every 1s)
GET  /api/students/{id}/runs             → box list_runs
POST /api/students/{id}/ask {text}       → box ask
GET  /api/students/{id}/ta-summary       → box ta_summary
GET  /api/students/{id}/plan             → box plan_get
POST /api/students/{id}/plan/prefs {text}→ box plan_set_prefs
POST /api/students/{id}/plan/solve {full_sections?} → box plan_solve
POST /api/students/{id}/sync             → box sync → {job_id}
GET  /api/students/{id}/sync/{job_id}    → box get_sync           (UI polls)
GET  /api/students/{id}/docs             → box list_docs
GET  /api/students/{id}/docs/{doc_id}    → box get_doc
GET  /api/students/{id}/deadlines        → box deadlines
GET  /api/students/{id}/assignments      → box list_assignments
GET  /course/{course}/...                → static mock course site (course_site/)
POST /api/instructor/publish {item}      → move a staged item into course.json (e.g. "hw5", "hw4-v2")
POST /api/instructor/reset-course        → restore course.json to the original published set
GET  /api/instructor/heatmap             → aggregate over all students (P2)
```

### BoxClient interface (`orchestrator/wolfhub/boxes.py`)

```python
class BoxClient(Protocol):
    def ensure(self, student_id: str, name: str) -> str: ...      # returns box_id, idempotent
    def call(self, box_id: str, envelope: dict) -> dict: ...      # returns inner JSON
```

- **LocalBoxClient:** `box_id` = base URL (e.g. `http://127.0.0.1:8101`). `call` = `httpx.post(f"{url}/chat", json={"message": json.dumps(env), "source": "cli"})`. Mapping comes from `LOCAL_BOXES="alex=http://127.0.0.1:8101,sam=http://127.0.0.1:8102"`.
- **MaritimeBoxClient:** `ensure` creates the box per §7 (verified by WS0). `call` uses `client.agents.chat(box_id, json.dumps(env))` and parses the `response` string. Set `GEMINI_API_KEY` (secret), `ALLOW_SEED=1`, and `GEMMA_MODEL` with `set_env` + `reload_env`.
- Select with `BOX_BACKEND=local|maritime`.

## 5. Data schemas (`$DATA_DIR`)

```
$DATA_DIR/
  profile.json
  plan.json
  runs.jsonl                 # append-only, one Run per line (status updates rewrite via runs/<id>.json)
  runs/<run_id>.json         # latest state of each run (source of truth for get_run)
  snapshots/<run_id>/hw4.py
  repo/                      # working copy: hw4.py, test_hw4.py, README.md
```

```jsonc
// Run
{
  "run_id": "r_20261031T113205_ab12",
  "ts": "2026-10-31T11:32:05Z",
  "assignment": "hw4",
  "status": "running|done|error",
  "passed": ["test_sum_basic", "..."],
  "failed": [{"test": "test_last_index", "message": "<≤400 chars of assertion/traceback>"}],
  "duration_ms": 812,
  "tags": ["off_by_one"],              // from tutor.classify, may be []
  "hint": "…≤80 words, ends with a question…",
  "hint_status": "pending|ready|failed",
  "related_past": [{"run_id": "…", "assignment": "hw2", "tag": "off_by_one"}],
  "llm": {"backend": "gemini|ollama|fake", "model": "gemma-4-26b-a4b-it"}   // who wrote the hint
}

// profile.json
{
  "student_id": "alex", "name": "Alex Rivera", "course": "CSC 116",
  "mistake_counts": {"off_by_one": 4, "empty_input": 2},
  "examples": {"off_by_one": [{"run_id": "…", "assignment": "hw2", "note": "range(len(xs)+1) indexed past end"}]},
  "updated_at": "…"
}

// Nudge (computed, not stored)
{"active": true, "reason": "test_last_index failed 5 runs in a row", "draft": "Hi! I'm stuck on hw4 …"}

// plan.json
{
  "completed": ["CSC 116", "MA 141", "MA 241"],
  "prefs_text": "no 8 AMs, I work Tue/Thu after noon, max 15 credits",
  "prefs": Prefs,
  "last_options": [Option]
}

// Prefs (hard constraints filter, soft ones score)
{
  "earliest_start": "09:00",            // hard, nullable
  "blocked": [{"days": ["Tue","Thu"], "start": "12:00", "end": "23:59"}],  // hard
  "min_credits": 12, "max_credits": 15, // hard
  "prefer_days_off": ["Fri"],           // soft
  "prefer_compact": true,               // soft: minimize gaps
  "must_take": ["CSC 316"]              // hard, nullable
}

// catalog.json (SAMPLE)
{"courses": [{"code": "CSC 316", "title": "Data Structures", "credits": 3,
  "prereqs": ["CSC 216"], "satisfies": ["CSC_CORE"],
  "sections": [{"id": "CSC316-001", "days": ["Mon","Wed","Fri"], "start": "09:35", "end": "10:25"}]}]}

// requirements.json (SAMPLE)
{"program": "CS BS (sample)", "requirements": [{"id": "CSC_CORE", "name": "CS core", "courses_needed": 6}]}

// course.json (manifest, served by the mock course site)
{"course": "csc116", "title": "CSC 116 (sample)", "sample": true,
 "items": [{"id": "hw4", "type": "assignment|doc|announcement", "title": "HW4: list utilities",
            "version": 1, "published_at": "…", "due": "2026-11-06T23:59:00-05:00",
            "files": [{"path": "hw4/README.md", "url": "/course/csc116/published/hw4/README.md"},
                      {"path": "hw4/hw4.py", "url": "…", "role": "starter"},
                      {"path": "hw4/test_hw4.py", "url": "…", "role": "tests"}]}]}

// DocMeta  ($DATA_DIR/courses/<course>/docs/<item_id>/meta.json; raw files + text.md + prev/ alongside)
{"doc_id": "csc116/hw4", "course": "csc116", "item_id": "hw4", "type": "assignment", "title": "…",
 "version": 2, "sha256": "…", "fetched_at": "…", "summary": "≤3 lines", "change_note": "…|null",
 "deadlines": [Deadline], "workspace": "repo/hw4|null", "llm": {"backend": "…", "model": "…"}}

// Deadline  ($DATA_DIR/courses/<course>/deadlines.json, merged across docs)
{"what": "HW4 due", "due": "2026-11-06T23:59:00-05:00", "source_doc": "csc116/hw4"}

// SyncJob
{"job_id": "s_…", "status": "running|done|error", "started": "…", "finished": "…|null",
 "new": ["csc116/hw5"], "changed": ["csc116/hw4"], "unchanged": 6, "errors": [{"item": "…", "error": "…"}]}

// Option
{"sections": [{"course": "CSC 316", "section_id": "CSC316-001", "days": [...], "start": "...", "end": "..."}],
 "credits": 15, "score": 0.87, "satisfies": ["CSC_CORE", "STATS"], "explanation": "…Gemma, ≤50 words…"}

// LlmStatus (computed)
{"mode": "auto|gemini|ollama|fake", "active_backend": "gemini|ollama|fake", "model": "gemma4:e4b", "online": false}
```

**Mistake tags (fixed list, `tutor.TAGS`):** `off_by_one`, `empty_input`, `none_handling`, `mutation_aliasing`, `wrong_return`, `type_confusion`, `infinite_loop`, `other`.

## 6. Gemma (`box/wolfbox/gemma.py`)

- SDK: `google-genai`. Env: `GEMINI_API_KEY`, `GEMMA_MODEL` (default `gemma-4-26b-a4b-it`, MoE for speed; alternative `gemma-4-31b-it`). Use minimal thinking. Verify the parameter name against the docs in WS0.
- `GEMMA_FAKE=1` → `FakeGemma` returns deterministic canned outputs. **All tests and UI dev use this.**

### Backends and offline mode

`GEMMA_BACKEND` = `gemini` | `ollama` | `auto` (default) | `fake` (`GEMMA_FAKE=1` is an alias for `fake`).

| Backend | Transport | Model env | Default model |
|---|---|---|---|
| `gemini` | `google-genai` SDK, `GEMINI_API_KEY` | `GEMMA_MODEL` | `gemma-4-26b-a4b-it` |
| `ollama` | `httpx` → `POST {OLLAMA_URL}/api/chat`, `stream: false`. Use `format: "json"` (or a JSON schema) for JSON tasks. No API key. | `OLLAMA_MODEL` | `gemma4:e4b` (`gemma4:26b` on ≥ 32 GB RAM) |
| `fake` | none | n/a | n/a |

- `gemma.py` exposes one internal `_generate(system, user, json_mode, timeout) -> (text, backend, model)`. Every task function in the table below goes through it, so tasks are backend-agnostic.
- **`auto`**: try Gemini with a 3s connect timeout. On a connection error, DNS failure, timeout, or 5xx, retry the same prompt on Ollama and **open a circuit for 60s** (skip Gemini entirely, so offline calls don't each pay the 3s penalty). After 60s, probe Gemini again. Don't fall back on 4xx (bad key/prompt). Surface that error instead.
- If neither backend answers, task functions raise and callers use their canned fallback strings (§10).
- Record `backend` and `model` on every Run (`run.llm`) and expose `LlmStatus` in `get_state`, so the UI can show the badge.
- Local models are weaker and slower: keep prompts small (the history cap below already does), keep the JSON outputs flat, and validate them strictly. Allow `OLLAMA_TIMEOUT` (default 20s) for background work like hints and TA summaries.
- Thinking: send Ollama's `think: false` for speed if the model accepts it. Verify in WS0.
- Warm-up: on box start in `ollama`/`auto` mode, fire one tiny request in the background with `keep_alive: "30m"` so the first real hint doesn't pay the model load time.
- A box running in local Docker reaches Ollama on the host at `OLLAMA_URL=http://host.docker.internal:11434`.
- One function per task. Each returns validated output or raises → caller falls back.

| fn | input | output | notes |
|---|---|---|---|
| `classify(code, failures)` | code + failed tests | `list[tag]` | JSON output, filtered to `TAGS` |
| `hint(code, failures, tags, history)` | + profile examples | `str` | Rules: no solution code, ≤ 80 words, end with a question, cite the matching past example if any. Post-check rejects any code block > 3 lines and retries once. |
| `answer(question, code, last_run, history)` | | `str` | Same no-solution rules |
| `ta_summary(profile, recent_runs, code)` | | markdown ≤ 200 words | Sections: Where they are · What they tried · Patterns · Suggested opener |
| `nudge_draft(reason, last_run)` | | `str` ≤ 60 words | message from student to TA |
| `summarize_doc(title, text)` | | `str` ≤ 3 lines | truncate input to ~6k chars |
| `extract_deadlines(title, text, manifest_due)` | | `list[Deadline]` JSON | manifest `due` wins over model output if both exist |
| `change_note(title, old_text, new_text)` | unified diff, truncated | `str` ≤ 2 sentences | |
| `parse_prefs(text)` | | `Prefs` JSON | validate; unknown fields dropped |
| `explain_options(options, prefs)` | | `list[str]` | one ≤ 50-word explanation per option |

**History passed to prompts:** the top 3 profile tags with counts and up to 2 `examples` per tag. Keep prompts small for speed.

## 7. Maritime deployment (verify in WS0, then fill in the exact commands)

What the docs say (as of today):
- Container contract: listen on `0.0.0.0:$PORT`, `GET /health` → 2xx, `POST /chat` ≤ 30s, persist only under `/data`. `HOME=/data`. On slim images, install `ca-certificates`. CMD must be a real program (`["python", "start.py"]`).
- Build from repo: `maritime create <name> --repo <github url>` (Dockerfile at repo root). Or a public pre-built image: REST `POST https://api.maritime.sh/api/agents` with `name` + `imageName`, `framework: "custom"`.
- Python SDK (`pip install maritime`): `client.agents.chat(id, msg)`, `.exec`, `.files.write/download`, `.set_env(id, k, v, secret=True)`, `.reload_env`, `.sleep`, `.delete`, `.list`. `provision(external_id=…)` is idempotent but the docs only show it with built-in templates.
- CLI: `npm i -g maritime-cli`, `maritime login`, `maritime status|chat|logs|sleep|env set`.

**Plan A:** build once from the repo (or push to `ghcr.io/<org>/wolfbox-box`, public) and create one agent per student (`wolfbox-alex`, `wolfbox-sam`, …) via CLI/REST. Store the box ids in `students.json`.
**Plan B (if per-student custom boxes fail):** one box. Box code namespaces by student: `DATA_DIR=/data/students/<id>`, and the envelope carries `student_id`. Keep this cheap to switch: `store.py` takes `data_dir` as a parameter and never reads a global.

## 8. Workstreams

Each workstream has an owner, the files it owns, what it depends on, and a definition of done (DoD). **Only edit files you own.** Request changes to shared contracts by editing §3–§5.

### WS0: Maritime spike (human, first 30 min) · *blocks WS6 only*
- Sign up and redeem `HACKNCSTATE`. Install the CLI. Deploy a hello-world FastAPI that follows the contract, using the repo or image path.
- Confirm and record in §7: the create command, how to get the box id, `agents.chat` round-trip, `set_env`, `files.download`, sleep → wake latency, and whether `provision` accepts a custom image.
- Confirm the Gemma model id and the thinking parameter with a single `google-genai` call.
- **Offline prep:** install Ollama on the demo laptop and run `ollama pull gemma4:e4b` *now* (~10 GB; also `gemma4:26b` if the laptop has ≥ 32 GB). Confirm the exact tags on the Ollama registry, that `format: "json"` works, and whether `think: false` is accepted. Record the time to first token.
- **DoD:** §7 updated with exact working commands. `GEMINI_API_KEY` shared with the team privately (not committed).

### WS1: Box core · owns `Dockerfile`, `box/start.py`, `box/wolfbox/{main,protocol,router,store,runner,nudge}.py`, `box/assignments/`
- FastAPI app, envelope parsing (§3), first-boot `init`, store with `data_dir` injection, and a runner (`pytest -q --json-report` or parse junit XML) in a background thread with a 20s subprocess timeout.
- After a run finishes, call `tutor.on_run_complete(store, run)`. Stub it until WS2 lands.
- `nudge.py`: pure function `compute(runs, now, stuck_minutes) -> Nudge` (without draft text).
- `hw4` assignment: e.g. `last_n(xs, n)`, `pairwise_sums(xs)`, `chunk(xs, size)`, `safe_max(xs)`, about 6 tests, including `test_last_index` and `test_empty`. Stubs return wrong values so tests start red.
- **DoD:** `DATA_DIR=./.data/alex GEMMA_FAKE=1 python box/start.py` works. `curl` submit → get_run shows a correct pass/fail split. Unit tests for store, runner, nudge, and protocol pass. Docker image builds and `/health` is 200.

### WS2: Tutor and Gemma · owns `box/wolfbox/{gemma,tutor}.py`
- Everything in §6 except `parse_prefs` and `explain_options`, plus `FakeGemma`.
- The three backends + `auto` fallback with the circuit breaker (§6, "Backends and offline mode"). Unit-test the fallback by pointing `GEMINI` at an unroutable address and `OLLAMA_URL` at a stub server.
- `tutor.on_run_complete`: classify → update the profile counts and examples → find `related_past` → generate the hint → write the run with `hint_status`.
- Handlers for `ask`, `ta_summary` (cached), and the nudge `draft` used by `get_state`.
- **DoD:** tests with FakeGemma pass. Fallback tests pass. With wifi off, `GEMMA_BACKEND=auto` produces a hint from local Gemma 4 and reports `active_backend: "ollama"`. A manual script with the real key against the seeded Alex profile produces a hint that cites hw2 for an off-by-one failure, in < 10s.

### WS3: Planner · owns `box/wolfbox/planner/`, `box/data/`
- `solver.solve(catalog, requirements, completed, prefs, full_sections=[]) -> list[Option]`: eligible courses (prereqs met, not completed), course sets within the credit bounds that include `must_take`, then sections without conflicts that pass the hard prefs, scored by soft prefs and requirement coverage. Return the top 3 distinct course sets. Pure code with no Gemma.
- `prefs.parse(text) -> Prefs` and `prefs.explain(options, prefs)` via `gemma.py` (add the two functions there in coordination with WS2, or keep them local in `prefs.py`).
- Sample data: about 12 courses, 2–3 sections each, about 4 requirements, and a transcript for Alex. Every file says `"sample": true`.
- Handlers for `plan_get`, `plan_set_prefs`, and `plan_solve`.
- **DoD:** solver unit tests (no conflicts, prereqs respected, hard prefs respected, ≤ 3 options, deterministic). "no 8 AMs, Tue/Thu afternoons off" returns 3 options with FakeGemma.

### WS4: Orchestrator · owns `orchestrator/wolfhub/*.py`, `scripts/{dev.sh,provision.py}`
- REST API (§4), `BoxClient` with Local and Maritime implementations, and the registry. Mount `course_site/` at `/course/` and include WS8's `course.py` router. Local boxes get `COURSE_URL=http://127.0.0.1:8000/course/csc116/course.json`. Maritime boxes need a public URL for the course site (WS0: tunnel, or deploy the static site as a Maritime public web app).
- `dev.sh` starts 2 local boxes (ports 8101/8102, `GEMMA_BACKEND` configurable) and the orchestrator on 8000.
- `offline.sh`: checks `curl $OLLAMA_URL/api/tags` lists the model (prints the `ollama pull` command if not), then runs `dev.sh` with `BOX_BACKEND=local GEMMA_BACKEND=ollama`.
- **DoD:** with `BOX_BACKEND=local`, every §4 endpoint works against the local boxes. The Maritime client is written to the WS0 findings.

### WS5: UI · owns `orchestrator/static/`
- `student.html`:
  - Code textarea (monospace, tab inserts spaces) and a Submit button that polls the run until it finishes.
  - Test results list (✓/✗).
  - Hint card, which shows "thinking…" while `hint_status=pending`.
  - "Related: hw2 · off_by_one" chip from `related_past`.
  - Ask box.
  - Nudge banner with the draft and a "Send to TA" button (fake send).
  - Plan tab: prefs input, echo, 3 option cards with a week grid (reuse the deck's mock-up), and the remaining requirements list.
- Sync UI on `student.html`: assignment picker (from `list_assignments`), a "This week" deadlines panel, "Sync now" button with job polling, alert cards for new and changed docs (summary + change note), and a doc viewer.
- `instructor.html`: **Publish hw5**, **Update hw4 spec**, and **Reset course** buttons (WS8 endpoints). Heatmap is P2.
- Desk light: "Connect desk light" button wired to `serial.js` (WS7). Hidden if Web Serial is unsupported.
- `ta.html`: student list with stuck badges. The selected student shows the rendered markdown summary and recent runs.
- `index.html`: role/student picker. Style follows the deck palette (`wolfbox-proposal.html`).
- LLM badge in the header from `get_state.llm`: `Gemma 4 · cloud` (green) or `Gemma 4 · local (offline)` (yellow). On each hint, show a small `via gemma4:e4b` caption from `run.llm`.
- **DoD:** the full demo script (SPEC §6) clicks through against local boxes with FakeGemma.

### WS6: Seed, deploy, demo · owns `seed/`, `scripts/{seed.py,demo_reset.py}`, `README.md`
- `seed/alex`: about 15 runs across hw2 and hw3 (with snapshots), a profile with `off_by_one: 4`, and `plan.json` with completed courses. `seed/sam`: nothing.
- `seed.py <student> [--backend]` pushes files via the `seed` envelope. `demo_reset.py` resets both students.
- Deploy to Maritime per §7 and set env on each box. Rehearse. Record a backup video.
- Rehearse the **offline fallback** once: wifi off → `scripts/offline.sh` → seed Alex locally → run the demo script. Write the switch steps on a sticky note for the presenter.
- Optional demo beat (10s): turn wifi off on stage and show the hint still arrives, now with the `local (offline)` badge.
- README: what it is, the architecture diagram, how to run locally, the tracks, and the sample-data disclaimer.
- **DoD:** the demo script runs end-to-end on Maritime boxes with real Gemma, twice in a row after `demo_reset.py`.

### WS7: Arduino desk light · owns `firmware/`, `orchestrator/static/serial.js`
- **Built-in LED only** (the board is all we have). Use `LED_BUILTIN` so it works on any board. Serial at 115200 baud. Commands are newline-terminated: `STATE running|pass|fail|stuck|offline|idle` and `FLASH 3`.
- Patterns (non-blocking, `millis()`-based): running = slow 1 Hz pulse, pass = solid on, fail = fast 5 Hz blink, stuck = double-blink every 1.5s, offline = short blip every 3s, idle = off. `FLASH n` overlays n quick flashes, then returns to the current state. Reply `OK <cmd>` for each command, for debugging.
- `serial.js`: `connectDeskLight()` (Web Serial `navigator.serial.requestPort()`, Chrome only, must be triggered by a click), `setDeskState(state)`, `flashDesk(n)`. No-op if not connected or unsupported. WS5 calls these on run status, nudge, LLM offline, and sync results.
- **DoD:** sketch compiles with `arduino-cli compile --fqbn <board>`. Flashing it and clicking "Connect desk light" in Chrome changes the LED pattern as tests run. If no board is present, the UI hides the button gracefully.

### WS8: Course sync · owns `box/wolfbox/sync/`, `orchestrator/course_site/`, the instructor publish/reset endpoints in `orchestrator/wolfhub/course.py`
- Mock course site for `csc116` (**sample data**):
  - **Published:** syllabus (md) with deadlines, 2 lecture notes (one PDF, one md), hw2, hw3, hw4 (README + starter + tests; hw4 matches WS1's template), 1 announcement.
  - **Staged:** `hw5` (new assignment with tests) and `hw4-v2` (README changed: `safe_max([])` must return `None`; tests updated).
- `sync` job: manifest → for each item, fetch files → sha256 → if new or changed, keep `prev/`, extract text, run `summarize_doc` / `extract_deadlines` / `change_note` (if changed), create or update the workspace for items with `role: tests` (never overwrite the student's own edited code: put new starter code at `hw4.py.new` and note it), write DocMeta, and merge `deadlines.json`. Gemma failures don't fail the sync: the doc is stored with `summary: null`.
- `GET /schedules` on the box (add the route in `main.py` in coordination with WS1).
- Tutor hook (P2): `index.py` keyword index; `tutor.answer` gets the top 2 chunks with titles.
- **DoD:** fresh box → `sync` → 7 docs, deadlines populated, hw2–hw4 workspaces exist. `publish hw5` + `hw4-v2` → `sync` → `new: [hw5]`, `changed: [hw4]` with a sensible change note. A second `sync` is a no-op. Works with `GEMMA_BACKEND=fake` and `ollama`.

### Dependency graph

```
WS0 ───────────────────────────────┐
WS1 ──┬─> WS2 (needs store/run shape; can start from §5 immediately)
      └─> WS3 handlers (solver itself has no deps)
WS4 (against §3 contract; can use a fake box early) ─> WS5
WS8 (sync) needs WS1 store + WS2 gemma._generate (can stub); WS7 is independent
WS1+WS2+WS4+WS5+WS8 ─> WS6 integration  (WS3, WS7 join when ready)
```

Everything except WS6 can start **now** from the contracts in this file.

## 9. Timeline

| Time | Milestone |
|---|---|
| 10:30–11:00 | WS0 spike in parallel with WS1/WS3/WS4 scaffolds. Contracts frozen. |
| 11:00–11:45 | Box runs tests locally. Solver passes tests. Orchestrator proxies to local boxes. |
| 11:45–12:15 | Lunch. Merge to `wolfbox`. |
| 12:15–1:00 | Real Gemma hints. UI student page. Sync end-to-end against the mock course. First box on Maritime. |
| 1:00–1:45 | Nudge, TA page, sync UI (This week, alerts, Publish). Plan tab if on track. Desk light. Seed Alex. Both boxes on Maritime. |
| **1:45** | **Feature freeze.** Only bug fixes and demo polish from here. |
| 1:45–2:30 | Rehearse ×2, backup video, README, MLH submission draft. |
| 2:30–2:45 | Submit. |

## 10. Conventions

- Python 3.12. Format with `ruff format`. No new dependencies without saying so in chat.
- Branches: `wolfbox` is integration. Workstreams use `wolfbox/ws<N>-<slug>` and merge to `wolfbox` often (small PRs or direct merges, whatever is fastest).
- Never commit secrets. `.env` is gitignored. Keys live in Maritime env (`secret=True`) and local `.env`.
- Tests: `pytest box/tests orchestrator/tests` must pass with `GEMMA_FAKE=1` before merging.
- Every Gemma call has a timeout and a fallback string. The demo must never hang.
- Never assume internet inside the box beyond the Gemini call. No CDN assets in the UI either: vendor any JS/CSS into `static/` so offline mode renders.
