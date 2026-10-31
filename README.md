# WolfBox

> **AI tutors forget you. WolfBox remembers, and so does your TA.**

WolfBox is a hackathon prototype for a persistent coding tutor and course companion. Each student has an isolated box that remembers test runs and recurring mistakes, syncs course materials, and can help plan a schedule. The demo includes a deterministic sample registration planner and a mock course site.

## Sample data notice

**The bundled demo records are fake sample data.** Live Canvas imports use the connected account’s actual course records. The course site, assignments, catalog, degree requirements, transcript, and students are synthetic and are not real NC State data or real student records. Alex Rivera and Sam Chen are fictional demo students.

## Architecture

```text
macOS SwiftUI Client (apple/build/WolfBox.app)  [Authoritative Client]
   │ (Note: the static browser UI at orchestrator/static/ is deprecated)
   │ REST (JSON)
   ▼
Orchestrator (FastAPI, laptop; stateless except student-to-box registry)
   │ BoxClient: Maritime agent (default) or local process
   ▼
WolfBox (FastAPI, one persistent box per student)
   ├─ Router → envelope handlers
   ├─ Store → runs, snapshots, profile, plan, course documents
   ├─ Runner → pytest in a background subprocess
   ├─ Tutor → Gemma 4: tags, history-aware hints, TA summary
   ├─ Sync → sample course manifest, documents, deadlines, workspaces
   └─ Planner → deterministic section solver + Gemma preference parsing
        │
        ├─ Gemini API (online)
        └─ Ollama / Gemma 4 (local or offline)
```

Student state stays in the box. The orchestrator routes requests and stores the student-to-box mapping. Maritime is the default box backend for cloud agent boxes.

## Native macOS SwiftUI Client

WolfBox is a native macOS application built with SwiftUI and AppKit. Build and launch:

```sh
apple/scripts/build-app.sh
open apple/build/WolfBox.app
```

On launch, the app connects to the orchestrator at `http://127.0.0.1:8000`. If unconfigured, it prompts for your `MARITIME_API_KEY` and automatically uploads it to the backend environment, persisting it for all future runs.

*(Note: The static web UI in `orchestrator/static/` is deprecated).*

## Quick start

Install Python 3.12 dependencies:

```sh
uv venv -p 3.12 .venv
uv pip install -p .venv -r box/requirements.txt -r orchestrator/requirements.txt maritime
```

Start the local demo stack with the deterministic fake Gemma backend:

```sh
COURSE_SOURCE=mock GEMMA_BACKEND=fake scripts/dev.sh
```

In another terminal, reset both boxes, restore the sample course, seed Alex, and sync both boxes:

```sh
.venv/bin/python scripts/demo_reset.py
```

Launch the native SwiftUI app: `open apple/build/WolfBox.app`. The script is safe to run again between demos. `scripts/dev.sh` stops its child processes when you press Ctrl-C.

Seed a single student's current box with `python scripts/seed.py alex`; add `--backend local` or `--backend maritime` to select a backend explicitly. Seed and reset envelopes require `ALLOW_SEED=1` on each box. The local dev script sets this for its demo boxes.

## Online Gemma mode

Put your Gemini key in the ignored `.env` file (never commit it):

```sh
GEMINI_API_KEY=your-key
GEMMA_BACKEND=auto
```

Then start `scripts/dev.sh` as above. `auto` uses Gemini when available and can fall back to local Ollama when configured. To require the Gemini API directly, use `GEMMA_BACKEND=gemini`.

## Offline mode

Install and start Ollama separately, then pull the small Gemma 4 model:

```sh
ollama pull gemma4:e4b
scripts/offline.sh
```

The offline script checks the local Ollama service and starts the stack with local boxes and Gemma 4. The first model response may take longer while Ollama loads the model.

## Configuration

Values shown are defaults where applicable. `.env` is loaded by `scripts/dev.sh`.

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Gemini API credential; keep it in `.env` or the box's secret environment. |
| `GEMMA_BACKEND` | `auto`, `gemini`, `ollama`, or `fake`; local dev defaults to `fake`. |
| `GEMMA_MODEL` | Gemini model id; defaults to `gemma-4-26b-a4b-it`. |
| `OLLAMA_URL` | Ollama API base URL; defaults to `http://127.0.0.1:11434`. |
| `OLLAMA_MODEL` | Local model tag; defaults to `gemma4:e4b`. |
| `OLLAMA_TIMEOUT` | Maximum seconds for local model calls; defaults to 20. |
| `BOX_BACKEND` | `local` or `maritime`; local is the dev default. |
| `MARITIME_API_KEY` | Maritime credential, if required by the installed SDK/environment. |
| `COURSE_URL` | Optional initial manifest URL. App-selected Canvas courses override this for later syncs. |
| `COURSE_SOURCE` | `canvas` (dev default) or `mock` for the offline sample demo. |
| `CANVAS_URL` / `CANVAS_API_TOKEN` | Canvas host and access token; keep in `.env`. |
| `STUCK_MINUTES` | Minutes before a student is considered stuck; local dev sets 2 for the demo. |
| `ALLOW_SEED` | Must be `1` to accept seed and reset envelopes. |
| `LOCAL_BOXES` | Comma-separated `student_id=http://host:port` mappings; dev defaults Alex to `8101` and Sam to `8102`. |

## Maritime deployment

The current outline provisions one agent per student, builds or selects the WolfBox image, sets `ALLOW_SEED=1`, `GEMINI_API_KEY`, `GEMMA_MODEL`, and a publicly reachable `COURSE_URL`, then records each agent id in the orchestrator registry. Use the `maritime` CLI or Python SDK path described in [IMPLEMENTATION.md §7](IMPLEMENTATION.md#7-maritime-deployment-verify-in-ws0-then-fill-in-the-exact-commands). **Verify every provisioning, custom image, environment, and wake/sleep step per WS0 before relying on it; those provider details are not yet confirmed in this repository.**

## Canvas assignments

The assignments integration uses Canvas REST directly. The web and macOS Course
screens include a Canvas course picker and a refresh button. Choose a course and
select **Sync now** to import its published assignment instructions, Canvas links,
and due dates. WolfBox remembers each student's selected course for later syncs.
Switching courses keeps previously imported documents available.

Configure the server in the ignored `.env` file:

```sh
CANVAS_URL=https://your-school.instructure.com
CANVAS_API_TOKEN=your-access-token
```

Run `scripts/dev.sh`, choose a course in the app, then sync. No course ID needs to
be configured in a file. The existing local course key `csc116` is used only by the
optional CLI import; app imports use `canvas-<course-id>`.

Instructor Canvas tasks also use a course picker. Opening a course verifies API
access and returns a Canvas link; publishing creates a staged assignment's title,
instructions, and due date. Publishing requires Canvas instructor permissions.
The existing instructor authentication boundary still applies to these routes;
without a configured `wolfhub.auth` provider, instructor routes return 503.
Student sync uses the existing prototype student routing boundary.

The Canvas integration imports instructions and due dates, rather than downloading
starter files, uploading staged attachments, or importing grades/submissions.
Canvas assignment imports do not automatically create executable test workspaces.
Credentials remain on the server, pagination is supported, and bearer tokens are
never forwarded across origins. Imported Canvas content is ignored by Git.
For remotely hosted boxes, set `COURSE_ORIGIN` to the orchestrator URL they can reach.

Optional CLI import: set `CANVAS_COURSE_ID` and run
`PYTHONPATH=orchestrator .venv/bin/python scripts/import_canvas.py`.
The implementation follows the [Canvas assignments API](https://developerdocs.instructure.com/services/canvas/resources/assignments).

## Demo flow

`python scripts/demo_reset.py` restores the original sample course, resets Alex and Sam, seeds Alex with three weeks of synthetic hw2/hw3 run history, and completes an initial course sync for both students. The intended three-minute walkthrough is:

1. Submit buggy hw4 as Alex; the hint can cite the off-by-one pattern from hw2.
2. Submit the same code as fresh student Sam; the hint has no prior history to cite.
3. Show Alex's repeated attempts, the TA handoff, and a nudge.
4. Publish hw5 and an updated hw4 spec from the instructor page, then sync again.
5. Set schedule preferences and show conflict-free options and remaining requirements.

The course publisher and student pages use synthetic content. See [SPEC.md §6](SPEC.md#6-demo-script-3-min) for the timed presenter script.

## Prize tracks

- **Best Use of Maritime:** isolated persistent boxes per student, with student state stored in each box.
- **Best Use of Gemma 4:** Gemma powers tutor hints, mistake tags, summaries, and preference parsing.
- **Best Open-Source AI Project:** local Ollama mode can run open Gemma weights without sending course material to a cloud model.

## Tests

Run the box and orchestrator suites with the fake backend:

```sh
GEMMA_BACKEND=fake .venv/bin/pytest box/tests orchestrator/tests
```

## Registration planner: public NC State schedules

The default `CATALOG_SOURCE=sample` keeps the demo deterministic and offline.
Set `CATALOG_SOURCE=ncsu` on the box to solve using
`$DATA_DIR/catalog_ncsu.json`; if that file is absent or contains invalid JSON, the box uses
the sample catalog and the Plan tab retains its sample-data banner. The sample
notice above describes the default demo: the saved NC State response fixtures
and an explicitly refreshed public schedule are real public course data.
Degree requirements, requirement mappings, and Alex's transcript remain synthetic.

`NCSU_TERM` defaults to `2271` (Spring 2027). To refresh a local box's data directory:

```sh
PYTHONPATH=box DATA_DIR=/path/to/student-data NCSU_TERM=2271 \
  .venv/bin/python -m wolfbox.planner.refresh
```

Use the same `DATA_DIR` as the target box. This command writes an atomic catalog
snapshot and prints the finished job, including course/section counts, missing
courses, and errors. Requests use the public
[NC State Class Search](https://webappprd.acs.ncsu.edu/php/coursecat/index.php),
a browser User-Agent, five-second HTTP timeouts, and a 250 ms pause between
courses. No login or new runtime dependency is needed.

Box envelopes (through the existing `/chat` protocol, not new orchestrator routes):

- `{"v":1,"type":"plan_refresh"}` returns `{job_id, status:"running"}` immediately.
- `{"v":1,"type":"plan_refresh_status","job_id":"c_…"}` returns `{job}` with
  `status: running|done|error`, term, timestamps, counts, missing courses, and errors.
- `plan_get` and `plan_solve` include `catalog: {source, term, fetched_at, sample}`.
  Solved sections additionally carry `seats: {open, capacity}` and
  `status: Open|Closed|Waitlist`; saved `plan.catalog` records their provenance.
- `GET /schedules` retains the 15-minute sync entry and adds a `catalog` refresh
  with cron `0 */6 * * *`. Maritime delivers its `plan_refresh` prompt while away.

The refresh keeps exactly the sample course list and its `satisfies` mappings.
Missing courses have **no sections**; synthetic sections never enter a live
snapshot. A request or parse error leaves the previous snapshot intact. Only
lecture components are used when lectures exist; otherwise timed components are
accepted. TBA/asynchronous sections and rows with multiple meeting time ranges
are omitted because the solver supports one time range per section. Closed,
waitlisted, zero-seat, and reserved sections are excluded (reserved is normalized
to Closed because eligibility for reserved seats is unknown).

Prerequisites are best-effort course-code extraction from prerequisite text.
**Shortcut:** OR expressions, including mixed AND/OR, are flattened and any one
listed course may satisfy them; grades, corequisites, restrictions, and linked
lab/recitation enrollment are not enforced. Use the official registration system
to confirm eligibility. Real instructor names use the existing ratings lookup;
unknown instructors show Unrated. Live RMP requests still require `RMP_LIVE=1`.

The Plan tab shows the live term, snapshot time, and open/capacity counts.
After a source, term, or snapshot change, saved options are hidden until the
student solves again. Refreshing is available through envelopes or the command
above; no refresh button or orchestrator route was added.
