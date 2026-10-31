# Native design direction

Skills read, in requested order: `apple-design`, then
`design-taste-frontend`. The latter's HTML draw/inspection scripts are not
app-screen tools; its restraint, subject specificity, typography, grouping,
substance, and screenshot critique informed this native app instead.

The subject inventory: one persistent box per student; Alex's three weeks of
history; fresh-student Sam; the HW2 loop-bound pattern reappearing on HW4;
test_last_index; a drafted office-hours message; updated empty-list behavior;
HW5 appearing after sync; Tuesday/Thursday work afternoons; deterministic
schedule options with real sections; and Gemma's visible active backend.

The idea: **the student's remembered attempts become the context beside the
work itself**. The code editor and history-aware hint share the primary view;
the same history becomes a compact TA briefing. The product's useful output
provides the visual substance.

| Surface | Claim | Visible proof / action |
| --- | --- | --- |
| Sign-in | This workspace carries your work forward | Local account form and the original brand promise |
| Learn | An attempt is part of a longer story | Per-test results, HW2 reference, mistake counts, tutor, TA draft |
| Course | The box catches you up | New HW5, changed HW4, summaries, reader, due dates |
| Plan | Your classes fit your actual week | Preference echo, time-positioned calendars, all section details |
| TA | Office hours start with context | Prior attempts, recurring pattern, suggested starting question |
| Instructor | Class patterns guide the next explanation | Count charts beside concrete course publishing controls |
| Moodle | Delegation stays observable and authorized | Instructor gate, consent, steps, simulated badge, takeover links |

The palette reinterprets the proposal's warm paper and forest green. Paper is
content ground; green identifies the primary action and remembered context;
gold marks help and changed material; red is reserved for failures. The planner
uses muted blue, gold, and pink to distinguish actual courses. Semantic colors
adapt for dark appearance. System chrome keeps native macOS materials.

SF is the interface typeface, with a 30-point semibold page heading and native
body/callout hierarchy. Only the code editor uses monospace. Native control
feedback is immediate; navigation uses a critically damped 0.3-second spring
when motion is allowed and no added transition when Reduce Motion is on.
No decorative glass, gradients, emoji, eyebrow labels, card grids, or resting
content shadows were introduced.

Accessibility uses standard keyboard-operable controls, text selection,
VoiceOver test outcomes and calendar meeting descriptions, system semantic
text colors, and a labeled native code editor. This is not a full VoiceOver
user study; the visual review covers light and dark screenshots.

# Screenshot critique

ROUND 1
Seen in one second: code and the remembered hint.
Idea (one sentence): an attempt stays connected to the student's history.
Live thing: run tests or ask about the current code.
Layout words by section: auth=split / learn=workbench / course=library / plan=calendar / ta=briefing / instructor=counts.
Scores: design 7.5 · usability 7.5 · creativity 7 · content 8 → overall 7.5
Caps applied: native app exceptions replace web imagery and motion requirements.
Top three problems (most visible first), each with the screenshot it shows in and the fix:
1. sign-in.png: the brand column's intrinsic content is centered inside its half; align its content to the leading margin.
2. sign-in.png: a command-line fixture flag appears in the user flow; replace it with an actual sample-workspace button.
3. moodle.png: raw description/status dictionaries read as implementation details; use readable step descriptions and a secondary status label.

ROUND 2
Seen in one second: the green workbench, now with native chrome.
Idea (one sentence): remembered context remains beside the student's work.
Live thing: a real native editor and native run action.
Layout words by section: auth=split / learn=workbench / course=library / plan=calendar / ta=briefing / instructor=counts.
Scores: design 6.5 · usability 6.5 · creativity 7 · content 8 → overall 6.8
Caps applied: dark-mode contrast limited usability.
Top three problems (most visible first), each with the screenshot it shows in and the fix:
1. learn-dark.png: fixed dark green and red statuses lose contrast on a dark ground; use adaptive sage and salmon semantic colors.
2. plan-dark.png: white text sits on pale blue/pink meeting fills; use darker appearance-specific calendar fills.
3. learn.png: initial hosting-view captures omit real toolbar state; capture the actual scene window with a regular activation policy and an explicitly visible Gemma caption.

ROUND 3
Seen in one second: a calm native workbench with one obvious run action.
Idea (one sentence): the same stored history informs student hints and the TA handoff.
Live thing: code, test results, tutor questions, calendar selection, and authorized task progress.
Layout words by section: auth=split / learn=workbench / course=library / plan=calendar / ta=briefing / instructor=counts / moodle=task log.
Scores: design 8 · usability 8 · creativity 7.5 · content 8 → overall 7.9
Caps applied: web-specific caps are inapplicable to this native app.
Top three problems (most visible first), each with the screenshot it shows in and the fix:
1. plan.png: the full real-time calendar pushes section details below the fold on smaller screens; retain vertical scrolling and supply plan-sections.png to show every detail in review evidence.
2. learn-dark.png: sidebar symbols must be resolved in the intended appearance; use adaptive green symbols in the native sidebar and explicitly dark hosting views for dark snapshots.
3. moodle.png: the clarified server contract makes all delegation instructor-only and distinguishes fake tasks; update navigation, request bodies, defaults, and the simulated badge before final capture.

The third round is the final visual pass. Calendar whitespace represents actual
free hours. Section rows remain present below the calendar; nothing is discarded
to produce a more compact picture. No external pictures or invented proof were
needed for the app workspace.
