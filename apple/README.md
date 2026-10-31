# WolfBox for macOS

A native SwiftUI demo client for macOS 14 or later. It uses system sidebars,
toolbars, sheets, menus, and sharing; there is no embedded web UI and no Swift
package dependency. Open `apple/Package.swift` in Xcode for previews.

From the repository root:

```sh
swift build --package-path apple
swift run --package-path apple WolfBox --demo-fixtures
```

`--demo-fixtures` loads bundled, labeled sample records without a server. The
Account menu previews Student, TA, and Instructor roles. You can also choose
“Explore a sample workspace” on sign-in. Sign out to leave sample mode.

Build a launchable, ad-hoc-signed application bundle:

```sh
apple/scripts/build-app.sh
open apple/build/WolfBox.app --args --demo-fixtures
```

For the live client, omit `--demo-fixtures`:

```sh
open apple/build/WolfBox.app
```

Quit with Command-Q. Server settings default to `http://127.0.0.1:8000`.
Changing the server signs you out. The app stores only the server URL in
UserDefaults; session tokens go into a server-specific Keychain entry.
Every authenticated request sends `Authorization: Bearer <token>`. A 401 clears
the session and returns to sign-in. Signup displays progress while the server
provisions the student's box. There is no unauthenticated live-login shortcut.

## Verification

```sh
swift test --package-path apple
python3.11 -m venv apple/.venv
apple/.venv/bin/pip install -r box/requirements.txt -r orchestrator/requirements.txt
apple/scripts/live-check.sh
```

The live-check script starts fake-Gemma local boxes and an orchestrator on
18300/18301/18302, copies the course into its own temporary directory, runs the
Swift API contract test, and shuts down only the processes it started. It never
changes the repository's course manifest or an existing dev stack. Override
`WOLFBOX_LIVE_PORT` to choose another base port. Python 3.11+ is required by the
backend's `datetime.UTC` import.

The regular test suite skips the opt-in live test. See `test-results.txt`,
`build-results.txt`, `live-results.txt`, and `VERIFICATION.md` for this run's
results and the exact limits of the evidence.

Regenerate fixture screenshots from the actual app window (no server):

```sh
apple/build/WolfBox.app/Contents/MacOS/WolfBox --demo-fixtures \
  --capture-screenshots "$PWD/apple/screenshots"
```

The process exits when capture finishes. Main light screens include native window
chrome; dark, signup, document and section-detail captures use native hosting views.

## Flows

- **Learn:** assignment-specific editor drafts, four-space tabs, Command-Return
  to run tests, per-test results and excerpts, hint polling, links to past
  patterns, tutor questions, mistake counts, and a reviewable TA message.
  “Send…” opens macOS sharing so the user can choose a recipient. The backend
  does not provide an office-hours queue API, so the app never claims delivery.
- **Course:** bounded sync polling, new/changed document summaries and change
  notes, seven-day deadlines, all-upcoming disclosure, and a native Markdown
  reader. Document IDs are encoded as one path segment, including `/`.
- **Plan:** save preferences, inspect their echo, then solve. All returned
  options are selectable. Every scheduled meeting uses its actual start and
  end; early, late, and weekend meetings extend the calendar. Every section is
  listed with instructor, rating and source, optional rating URL, and seats.
  Catalog provenance and remaining/courses-needed counts come from the API.
- **TA:** roster with nudge badges, selected-student Markdown handoff, and
  expandable run history.
- **Instructor:** publish hw5, update hw4, confirm course reset, and count
  visualizations for mistake tags and failing tests.
- **Moodle:** instructor only; explicit local authorization is required to
  start an action. Defaults are course `csc116`, staged item `hw5`. The client
  sends `{course}` for open/list and `{course,item}` for publish, handles the
  202 task ID, polls status, lists history, labels `mode=fake` as simulated, and
  exposes watch/takeover links only when safe, non-null URLs are present.
  Server-side instructor authorization remains authoritative.

Polling is sequential, every second after the preceding response, and bounded
at 75 seconds. A slow individual poll uses the remaining time budget. Leaving
an account invalidates in-flight responses. Errors appear inline and do not
terminate the app. Failed state reloads preserve the editor's current draft.

## Platform and limits

Built for arm64 macOS with a macOS 14 deployment target using Swift 6.4.2,
Swift language mode 5, and Xcode 27.2. iOS was not added: the native AppKit editor
and window-capture harness keep this implementation focused on the presenter's
Mac. The serial desk light and editor line numbers are omitted. Drafts survive
navigation in the current session; the server owns submitted-code persistence.

The bundle allows HTTP for the local demo server. It is ad-hoc signed for local
use, not notarized or prepared for distribution.
