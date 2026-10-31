# Maritime Native Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Configure WolfBox to default to Maritime cloud agent boxes, provide launch-time prompt in the native macOS SwiftUI app to enter/upload the Maritime API key to the environment (replacing manual WS0 setup), update frontend client architecture, and deprecate the web UI in favor of SwiftUI only.

**Architecture:** The FastAPI orchestrator exposes `/api/config` and `/api/config/maritime-key` to manage Maritime credentials and backend configuration, persisting keys to `.env` and `os.environ`. The native macOS SwiftUI app queries config on launch, displays an onboarding/key sheet if unconfigured, securely persists credentials in Keychain and uploads them to the orchestrator environment. The static web UI receives deprecation notices directing users to the SwiftUI app.

**Tech Stack:** Python 3.12 (FastAPI, pytest, maritime 0.9.0 SDK), Swift 5.9 (SwiftUI, Observation, AppKit, XCTest).

**Spec:** User request: "(pull and make the branch main first) it should ask for a maritime api key upon app launch if there is one, and auto-upload to the env when needed (WS0 replacement). default config should use maritime. cant you start up the remote boxes? you have the api access. update the frontend client architecture, too, then. also, deprecate the web ui. this is swift ui only."

## Global Constraints

- Never commit real secret keys into git. Sample data must remain clearly labeled.
- Default `BOX_BACKEND` must be `"maritime"`.
- Test suite must pass with `GEMMA_BACKEND=fake` without requiring live external network.
- The web UI must be clearly marked as deprecated in favor of the native macOS SwiftUI app.
- SwiftUI client must compile cleanly via `apple/scripts/build-app.sh` and pass `swift test --package-path apple`.

## Review Focus

- Unset `MARITIME_API_KEY`: Calling a Maritime box when unconfigured returns a graceful `BoxUnavailable` (503) error rather than a crash.
- Empty key submission: `POST /api/config/maritime-key` rejects whitespace/empty keys with HTTP 400.
- Key persistence: Uploaded Maritime key persists in `.env` and updates runtime `os.environ` and `box_client`.
- Offline/Fixture mode: When launched in demo fixture mode, SwiftUI app does not block or error if backend is unreachable.
- Secure key entry: Maritime API key input in SwiftUI uses `SecureField` and does not leak into logs.

---

### Task 1: Backend & Dev Environment — Maritime Default & Config Endpoints

**Files:**
- Modify: `orchestrator/wolfhub/boxes.py`
- Modify: `orchestrator/wolfhub/main.py`
- Modify: `scripts/dev.sh`
- Modify: `scripts/seed.py`
- Modify: `scripts/demo_reset.py`
- Test: `orchestrator/tests/test_ws4_main.py`

**Interfaces:**
- Consumes: `os.getenv("MARITIME_API_KEY")`, `os.getenv("BOX_BACKEND", "maritime")`
- Produces: `GET /api/config` returning `{"backend": str, "has_maritime_key": bool, "maritime_key_preview": str | None}`, `POST /api/config/maritime-key` accepting `{"key": str}`.

- [ ] **Step 1: Write tests for config and key upload in `orchestrator/tests/test_ws4_main.py`**
- [ ] **Step 2: Run pytest to verify tests pass**
  Run: `GEMMA_BACKEND=fake .venv/bin/pytest orchestrator/tests/test_ws4_main.py -v`
- [ ] **Step 3: Commit backend changes**
  Run: `git commit -m "feat(orchestrator): default BOX_BACKEND to maritime and add config endpoints"`

---

### Task 2: Deprecate Web UI in Favor of Native macOS SwiftUI

**Files:**
- Modify: `orchestrator/static/index.html`
- Modify: `orchestrator/static/student.html`
- Modify: `orchestrator/static/instructor.html`
- Modify: `orchestrator/static/ta.html`
- Modify: `README.md`

**Interfaces:**
- Consumes: None
- Produces: Prominent visual deprecation notices on all HTML pages pointing users to `apple/build/WolfBox.app`.

- [ ] **Step 1: Add deprecation banners to `index.html`, `student.html`, `instructor.html`, `ta.html`**
- [ ] **Step 2: Update `README.md` to document that the Web UI is deprecated and SwiftUI is the sole supported client**
- [ ] **Step 3: Verify static files render correctly and commit**
  Run: `git commit -m "docs: deprecate web ui in favor of native macOS SwiftUI client"`

---

### Task 3: Frontend Architecture — Config Models and API Client

**Files:**
- Modify: `apple/Sources/WolfBoxCore/Models.swift`
- Modify: `apple/Sources/WolfBoxCore/APIClient.swift`
- Test: `apple/Tests/WolfBoxCoreTests/APITests.swift`

**Interfaces:**
- Consumes: `GET /api/config`, `POST /api/config/maritime-key`
- Produces: `ConfigResponse` struct, `APIClient.fetchConfig() async throws -> ConfigResponse`, `APIClient.uploadMaritimeKey(_ key: String) async throws -> ConfigResponse`.

- [ ] **Step 1: Add `ConfigResponse` to `apple/Sources/WolfBoxCore/Models.swift`**
- [ ] **Step 2: Add `fetchConfig` and `uploadMaritimeKey` to `apple/Sources/WolfBoxCore/APIClient.swift`**
- [ ] **Step 3: Add unit tests in `apple/Tests/WolfBoxCoreTests/APITests.swift`**
- [ ] **Step 4: Run Swift tests to verify**
  Run: `swift test --package-path apple --filter APITests`
- [ ] **Step 5: Commit core changes**
  Run: `git commit -m "feat(apple): add config response model and maritime key upload client methods"`

---

### Task 4: Frontend Architecture — AppModel & Launch Modal Key Prompt

**Files:**
- Modify: `apple/Sources/WolfBox/AppModel.swift`
- Modify: `apple/Sources/WolfBox/RootView.swift`
- Test: `apple/Tests/WolfBoxAppTests/AppModelTests.swift`

**Interfaces:**
- Consumes: `ConfigResponse`, `APIClient.fetchConfig()`, `APIClient.uploadMaritimeKey()`
- Produces: `MaritimeKeySheet` view, `AppModel.showMaritimePrompt`, `AppModel.checkMaritimeConfig()`, `AppModel.saveMaritimeKey(_ key: String) async`.

- [ ] **Step 1: Update `AppModel.swift` with Maritime state, config check on launch/auth, and key upload handler**
- [ ] **Step 2: Implement `MaritimeKeySheet` in `RootView.swift` with key prompt and status indicators**
- [ ] **Step 3: Add tests in `apple/Tests/WolfBoxAppTests/AppModelTests.swift`**
- [ ] **Step 4: Build app and verify test suite**
  Run: `swift test --package-path apple` and `./apple/scripts/build-app.sh`
- [ ] **Step 5: Commit SwiftUI app changes**
  Run: `git commit -m "feat(apple): prompt for maritime api key on launch and auto-upload to env"`
