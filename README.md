# WolfBox

> **AI tutors forget you. WolfBox remembers, and so does your TA.**

WolfBox is a hackathon prototype for a persistent coding tutor and course companion. Each student has an isolated box that remembers test runs and recurring mistakes, syncs course materials, and can help plan a schedule. The demo includes a deterministic sample registration planner and a mock course site.

## Sample data notice

**Everything in this repository is fake sample data.** The course site, assignments, catalog, degree requirements, transcript, and students are synthetic and are not real NC State data or real student records. Alex Rivera and Sam Chen are fictional demo students.

## Architecture

```text
Browser (student / TA / instructor pages)
   │ REST (JSON)
   ▼
Orchestrator (FastAPI, laptop; stateless except student-to-box registry)
   │ BoxClient: local process or Maritime agent
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

Student state stays in the box. The orchestrator routes requests and stores the student-to-box mapping. In offline mode, the orchestrator and boxes run locally and each box reaches Gemma 4 through Ollama.

## Quick start

Install Python 3.12 dependencies:

```sh
uv venv -p 3.12 .venv
uv pip install -p .venv -r box/requirements.txt -r orchestrator/requirements.txt
```

Start the local demo stack with the deterministic fake Gemma backend:

```sh
GEMMA_BACKEND=fake scripts/dev.sh
```

In another terminal, reset both boxes, restore the sample course, seed Alex, and sync both boxes:

```sh
.venv/bin/python scripts/demo_reset.py
```

Open <http://127.0.0.1:8000>. The script is safe to run again between demos. `scripts/dev.sh` stops its child processes when you press Ctrl-C.

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
| `COURSE_URL` | Course manifest URL fetched by a box; local dev sets the mock CSC 116 manifest. |
| `STUCK_MINUTES` | Minutes before a student is considered stuck; local dev sets 2 for the demo. |
| `ALLOW_SEED` | Must be `1` to accept seed and reset envelopes. |
| `LOCAL_BOXES` | Comma-separated `student_id=http://host:port` mappings; dev defaults Alex to `8101` and Sam to `8102`. |

## Maritime deployment

The current outline provisions one agent per student, builds or selects the WolfBox image, sets `ALLOW_SEED=1`, `GEMINI_API_KEY`, `GEMMA_MODEL`, and a publicly reachable `COURSE_URL`, then records each agent id in the orchestrator registry. Use the `maritime` CLI or Python SDK path described in [IMPLEMENTATION.md §7](IMPLEMENTATION.md#7-maritime-deployment-verify-in-ws0-then-fill-in-the-exact-commands). **Verify every provisioning, custom image, environment, and wake/sleep step per WS0 before relying on it; those provider details are not yet confirmed in this repository.**

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
