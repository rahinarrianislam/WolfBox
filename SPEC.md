# WolfBox — Product Spec

> **AI tutors forget you. WolfBox remembers, and so does your TA.**

Hacktoberfest Hack Day Raleigh · Oct 31, 2026 · Hacking 10:30 AM → projects due 2:45 PM.
Pitch deck: [`wolfbox-proposal.html`](wolfbox-proposal.html). Build plan: [`IMPLEMENTATION.md`](IMPLEMENTATION.md).

---

## 1. Problem

Every CS student starts from zero, every time. Their tools forget everything between sessions:

| Pain | What gets forgotten |
|---|---|
| "Works on my laptop, fails the autograder." Day 1 setup hell. | the environment |
| The same off-by-one bug on every assignment | the student's mistakes |
| A general chatbot doesn't know your code, attempts, or course rules | the context |
| Office hours: the first 10 minutes go to explaining what you tried | the story so far |
| Stuck for 2 days but never asks for help | how long they've struggled |
| Registration: dozens of sections, time conflicts, surprise prereqs | degree progress and preferences |

## 2. Solution

**One persistent Maritime agent box per student.** It holds the student's coding environment, their full test-run history, a profile of their recurring mistakes, and their degree plan. It sleeps when idle and wakes in ~1s. Gemma 4 is the reasoning layer.

Four pillars, plus a desk light:

1. **LEARN: coding tutor.** Runs the student's code against the assignment tests inside the box and logs every run. When tests fail, it gives a Socratic hint that cites the student's own history ("this looks like your hw2 loop-bound bug").
2. **HELP: nudge + TA handoff.** Detects when a student is stuck and nudges them toward office hours with a drafted message. TAs get a one-page summary: what was tried, where they're stuck, recurring patterns.
3. **SYNC: course autopilot.** The box wakes on a schedule, downloads every assignment and doc the teacher posts, and processes them with Gemma 4: summaries, deadlines, "what changed" notes, and a ready-to-run workspace for each new assignment. In offline mode this all happens on local Gemma 4, so course material never leaves the laptop.
4. **PLAN: registration planner.** Remembers the transcript and preferences ("no 8 AMs", "I work Tue/Thu afternoons"). Generates three conflict-free schedules and shows remaining requirements.

## 3. Users

| User | Wants | Surface |
|---|---|---|
| **Student** (primary) | Get unstuck fast without being handed answers. Pick a schedule painlessly. | Student page |
| **TA** | Know a student's situation before helping them | TA page |
| **Instructor** (stretch) | See where the class is stuck | Instructor page |

## 4. Goals and non-goals (hackathon scope)

**Goals**
- A working end-to-end loop on real Maritime agent boxes with real Gemma 4 calls.
- Persistence that is *visible* in the demo: a seeded student vs. a fresh student give different answers to the same question.
- Qualifies for all three prize tracks (§9).

**Non-goals (future-work slide)**
- Real integrations: MyPack, Moodle, Gradescope/autograders, GitHub Classroom.
- Auth, real student data, FERPA compliance work. **Seeded fake students only.**
- In-browser IDE. A textarea editor is enough.
- Group-project boxes, exam prep, spaced repetition.
- Real LMS scraping (Moodle/Canvas logins). Sync reads a **mock course site** we host, with the same manifest format a real adapter would produce.

## 5. Features and acceptance criteria

Priority: **P0** = must ship for the demo, **P1** = should, **P2** = stretch.

### LEARN

| ID | Pri | Story | Acceptance |
|---|---|---|---|
| L1 | P0 | As a student I get my own box | Provisioning a student is idempotent (same student → same box). On first boot the box copies the `hw4` assignment template into `/data/repo/`. |
| L2 | P0 | I can submit code and see test results | Submitting `hw4.py` writes it to `/data/repo/`, runs pytest in the box, and returns pass/fail per test plus a short error excerpt. The UI never blocks for more than 30s. |
| L3 | P0 | Every run is remembered | Each run appends a record to `/data/runs.jsonl` and snapshots the submitted code to `/data/snapshots/<run_id>/`. History survives sleep/wake. |
| L4 | P0 | I get a hint that knows my history | On failure the hint (a) never contains a full solution, (b) is ≤ 80 words and ends with a question, (c) cites a past mistake when one matches. |
| L5 | P0 | My mistake patterns are tracked | Each failing run is tagged with one or more tags from a fixed list (see IMPLEMENTATION §5). Counts accumulate in `/data/profile.json`. |
| L6 | P1 | I can ask free-form questions | "Why does test_empty fail?" returns a history-aware answer within 30s. |
| L8 | P1 | WolfBox works with no internet | **Offline mode:** the whole stack (boxes, orchestrator, UI) runs on one laptop with Gemma 4 served locally by Ollama. In `auto` mode, if the Gemini API is unreachable, calls fall back to local Gemma 4 within ~3s with no user-visible error. The UI shows a badge: `Gemma 4 · cloud` or `Gemma 4 · local (offline)`. Tests, the planner solver, and all `/data` history are unaffected. |
| L7 | P2 | Roll back in plain English | "Show my code from before Tuesday" returns the matching snapshot. |

### HELP

| ID | Pri | Story | Acceptance |
|---|---|---|---|
| H1 | P1 | I get nudged when I'm stuck | The nudge activates when the same test has failed on ≥ 5 consecutive runs **or** a test has failed continuously for ≥ `STUCK_MINUTES` (default 30; set to 2 for the demo). It shows the reason and a drafted message to the TA. |
| H2 | P1 | TAs get a handoff summary | The TA page lists students. Clicking one shows a Gemma-written summary: current assignment, failing tests, what they've tried (from run diffs), recurring patterns, and a suggested starting question. ≤ 200 words. |
| H3 | P2 | Instructors see class-wide blind spots | A heatmap of tests × students, or mistake tags × count, aggregated across all boxes. Anonymized. |

### SYNC

| ID | Pri | Story | Acceptance |
|---|---|---|---|
| S1 | P1 | My box mirrors everything the teacher posts | `sync` fetches the course manifest, downloads new or changed items (by content hash) into `/data/courses/<course>/`, and reports `{new, changed, unchanged, errors}`. Re-running with no changes is a no-op. |
| S2 | P1 | I get a summary and deadlines for each doc | Each new or changed doc gets a ≤ 3-line summary. Due dates are extracted into `deadlines.json` and shown in a "This week" panel. |
| S3 | P1 | I'm told what changed | When a doc's hash changes, a ≤ 2-sentence "what changed" note is generated from the old and new text and shown as an alert. |
| S4 | P1 | New assignments are ready to run | An assignment item that ships tests gets a workspace at `/data/repo/<assignment>/` and appears in the assignment picker. LEARN works on it with no manual setup. |
| S5 | P2 | Answers cite course material | `ask` retrieves the top matching doc chunks (keyword search) and cites them by title. |
| S6 | P2 | Sync happens while I'm away | The box exposes `GET /schedules`. Maritime wakes it to sync, then it goes back to sleep. |

### DESK LIGHT (Arduino, built-in LED only)

| ID | Pri | Story | Acceptance |
|---|---|---|---|
| D1 | P2 | My Arduino shows my status | The student page's "Connect desk light" button (Web Serial, Chrome) drives the board's built-in LED: slow pulse = running, solid = all pass, fast blink = failing, double-blink = stuck, 3 quick flashes = new doc synced. Works offline. No extra parts. |

### PLAN

| ID | Pri | Story | Acceptance |
|---|---|---|---|
| PL1 | P1* | I can state preferences in plain English | "No 8 AMs, I work Tue/Thu after noon, 15 credits max" is parsed by Gemma into structured prefs (schema in IMPLEMENTATION §5), stored in `/data/plan.json`, and echoed back so the student can confirm. |
| PL2 | P1* | I get 3 conflict-free schedules | A deterministic solver over the sample catalog returns ≤ 3 distinct options. Every option has no time conflicts, meets prereqs from the transcript, respects hard prefs, and is ranked by soft prefs. **Gemma never invents sections.** It only explains the options. |
| PL3 | P1* | I see what's left for my degree | Remaining requirements are computed from `requirements.json` minus completed courses. |
| PL4 | P2 | Section full → swap | Marking a section full re-solves while keeping the other sections fixed when possible. |

\* Build PLAN **after** SYNC. If time runs short, PLAN falls back to the static mock-up.

## 6. Demo script (~3 min)

1. **Hook (15s):** "AI tutors forget you. Every session starts from zero."
2. **Persistence (45s):** Alex's box is asleep and seeded with 3 weeks of history. Submit buggy `hw4.py`. The box wakes and runs the tests. The hint says *"this looks like the loop-bound issue from hw2. What does your loop do on the last index?"*
3. **Contrast (20s):** Fresh student Sam submits the identical code and gets a generic hint. *That's the product.*
4. **Help (40s):** Alex fails again and the nudge appears. Switch to the TA page and show Alex's handoff summary.
5. **Sync (30s):** On the instructor page, click **Publish hw5** and **Update hw4 spec**. Hit "Sync now" on Alex's page (or wait for the schedule): "New: hw5, due Fri" with a summary and a ready workspace, plus "hw4 changed: `safe_max([])` now returns `None`". The Arduino LED flashes 3 times.
6. **Plan (30s):** Type "no 8 AMs, I work Tue/Thu afternoons". Show 3 schedules plus remaining requirements.
7. **Close (20s):** Maritime makes this ~$1/student/month and isolated per student. Gemma 4 is open-weight, so schools could self-host. Future work.

## 7. Success criteria (mapped to judging)

| Judging criterion | How we hit it |
|---|---|
| Relevance (Y/N) | Uses Gemma 4 via the Gemini API, open-weight AI, and Maritime agent boxes. Each is load-bearing, not decorative. |
| Impact & Value | Every judge was a student. TA time saved and silent strugglers caught are concrete. |
| Innovation | Memory is the differentiator. The side-by-side contrast proves it. |
| Feasibility & Scalability | ~$1/student/month per box. Sleep/wake. Template-provisioned. |
| Technical Execution | Real per-student VMs, real test execution, deterministic solver + LLM split. |
| Demo & Communication | Scripted 3-min demo with seeded data. Every teammate can explain the architecture. |

## 8. Risks

| Risk | Mitigation |
|---|---|
| Maritime custom-image deploy takes longer than expected | 30-min spike first (IMPLEMENTATION WS0). Everyone develops against `BOX_BACKEND=local` in the meantime. Fallback: one shared box with per-student dirs under `/data/students/<id>/` (still persistent, weaker story). |
| Gemma latency vs. the 30s `/chat` limit | Hints are generated in the background after a run and fetched by polling. Use the faster MoE model by default and a 25s timeout with a canned fallback. |
| Gemma gives away solutions | System prompt rules plus a post-check that rejects replies containing code blocks longer than 3 lines. |
| Live wifi or API failure during the demo | **Offline mode (L8):** switch to local boxes + local Gemma 4 with one command. Rehearse it once. Also pre-record a backup video at 2:15 and keep the seeded state. |
| Local Gemma too slow or too big for a laptop | Default offline model is the small `gemma4:e4b`. Use `gemma4:26b` only on machines with ≥ 32 GB RAM. **Pull the model before the venue wifi gets busy** (~10 GB). Hints already run in the background. |
| Scope creep | Feature freeze at 1:45. PLAN is cuttable to a static mock-up. |

## 9. Prize tracks

- **Best Use of Maritime:** one persistent agent box per student. Scheduled wake-ups sync the course while the student is away. `/data` is the student's memory. Untrusted student code is isolated per VM. Sleep/wake.
- **Best Use of Gemma 4:** `gemma-4-26b-a4b-it` / `gemma-4-31b-it` via the Gemini API for hints, mistake tagging, TA summaries, and preference parsing.
- **Best Open-Source AI Project:** Gemma 4 is open-weight. Repo is open source. Offline mode runs the open weights locally, so a school could self-host WolfBox with no cloud LLM at all.

## 10. Decisions (defaults, change if the team disagrees)

| Question | Decision |
|---|---|
| Stack | **Python everywhere.** FastAPI for box and orchestrator. Vanilla HTML/JS UI served by the orchestrator, no build step. |
| Assignment | A small Python `hw4` (list utilities) with ~6 pytest tests and a planted off-by-one opportunity. |
| Where the orchestrator runs | A laptop for the demo. Deploying it is P2. |
| Offline LLM runtime | **Ollama** serving `gemma4:e4b` (or `gemma4:26b` on big machines). Reached over HTTP from the box. No new Python dependency. |
| Planner data | Small sample catalog and requirements, **clearly labeled as sample data**, not real NC State sections. |
