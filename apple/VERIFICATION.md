# Verification evidence

Verified October 31, 2026 on the current Mac. Source ownership is `apple/` plus
Swift/Xcode ignore entries in `.gitignore`. No backend, web UI, firmware, or
course content was modified. No pushes or PRs were made.

## Build

```sh
swift build --package-path apple
apple/scripts/build-app.sh
codesign --verify --strict apple/build/WolfBox.app
```

Debug build passed. Final release build and bundle signing passed (exit 0):

```text
Building for production...
Build complete!
.../apple/build/WolfBox.app
```

The full release compiler output is in `build-results.txt`. The produced binary
is Mach-O arm64. Tooling: Xcode 27.2 (27B52), Swift 6.4.2. Deployment target:
macOS 14. iOS was not built. Available iOS 26.5/27.0 simulators were inventoried;
no device was launched or changed.

## Automated checks

```sh
swift test --package-path apple
```

15 checks passed, 0 failures; the opt-in live test was skipped in the default
suite. `test-results.txt` contains the complete output. Coverage includes URL
validation and encoded path segments, bearer transport, unauthorized vs offline
errors, recoverable response errors, numeric/object ratings, delegation payload
shapes, both heatmap student representations, complete run/hint state, actual
calendar minutes and meeting preservation, fixture content, instructor-only
Moodle authorization, no request for a non-instructor, draft preservation when
the server is down, and sign-out/data clearing after a 401.

The heatmap list shape and the stricter Moodle role boundary were each observed
failing a regression test before their decoder/policy fixes.

## Live local backend

```sh
apple/scripts/live-check.sh
```

One live Swift API integration test passed with 0 failures. Full output is in
`live-results.txt`. The isolated instance used `GEMMA_BACKEND=fake`, local boxes,
ports 18300/18301/18302, a temporary registry, and a copied course site. Its
processes and temporary course/data directory were cleaned up afterward.
The existing stack on 8000/8101/8102 was left alone. `scripts/dev.sh` could not
be launched safely on its fixed occupied ports; the isolated script uses the
same box entry point and orchestrator app with separate state.

Exercised live through the Swift APIClient and production Codable models:

- Health, student provisioning, state, and assignment listing.
- Python submission, per-test result decoding, and polling through hint completion.
- Tutor answer, TA Markdown summary, and run history.
- Publish hw5, update hw4-v2, sync creation/polling, document listing, reader
  fetch with `csc116%2Fhw4`, and deadlines.
- Plan retrieval, preference save/echo, deterministic solve and catalog source.
- Instructor heatmap and course reset on the disposable copy.

The local checkout returns 404 for `/api/auth/me`. Login/signup/logout/Keychain
persistence were compiled and their relevant transport/session-error boundaries
were tested, but were not exercised end-to-end against real auth endpoints.
The live integration test does not authenticate and is not an app sign-in
bypass. The app itself still requires an authenticated live account.

Moodle UI and task models use the clarified contract: instructor only, bearer
auth, `{course}` or `{course,item}`, a 202 task ID, task polling and task-list
retrieval, nullable watch/takeover links, string steps, result/status/mode, and
an explicit `mode=fake` badge. Only bundled fixtures and authorization/error
checks were exercised here. Real Moodle actions, credentials, task links and
server-side authorization await the parent's corrected backend integration.

## Visual evidence

```sh
apple/build/WolfBox.app/Contents/MacOS/WolfBox --demo-fixtures \
  --capture-screenshots "$PWD/apple/screenshots"
```

The release executable rendered and captured these PNGs, then exited. Every
main view was opened and visually inspected. `design-notes.md` records the
three critique rounds and fixes. Main light screens capture the app's actual
native scene window. Dark views, signup, the document reader and section detail
use native hosting views with explicit appearance for reproducibility. Window
captures may be constrained to the host display width; the layout remains
scrollable at the Mac's actual size.

- `screenshots/sign-in.png`
- `screenshots/sign-up.png`
- `screenshots/learn.png`
- `screenshots/course.png`
- `screenshots/plan.png`
- `screenshots/plan-option-2.png`
- `screenshots/plan-option-3.png`
- `screenshots/plan-sections.png`
- `screenshots/ta.png`
- `screenshots/instructor.png`
- `screenshots/moodle.png`
- `screenshots/document.png`
- `screenshots/learn-dark.png`
- `screenshots/plan-dark.png`

Screenshots are fixture evidence, not live-backend UI evidence. Native code
editing was rendered; a full manual keyboard/VoiceOver/Reduce Motion test pass
was not performed. Code implements four-space Tab handling, accessible labels,
semantic text colors, native controls, and a reduced-motion fallback.

## Deliberate omissions

Optional iOS, USB desk-light integration, and code line numbers are omitted.
The TA Send action uses native sharing; no nonexistent queue delivery is claimed.
The local app is ad-hoc signed, not notarized for distribution. Auth and Moodle
must be checked again after backend integration before a live signed-in demo.
