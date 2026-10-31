CANVAS LED — WCPSS / Arduino UNO Q

The live CanvasDisplay sketch replaces the alternating demonstration. It shows Waiting for Canvas key until actual Canvas information arrives from your Mac over USB. Your token stays on the
Mac and is sent only to https://wcpss.instructure.com.

Start:
1. Connect UNO Q with USB. Close Arduino IDE's Serial Monitor.
2. Double-click Start Canvas.command. Keep its window open and your Mac awake.
3. On first run, create a personal token under Canvas Account > Settings >
   Approved Integrations > New Access Token. Name it Canvas LED and set an expiry.
4. Paste the token into the Terminal prompt and press Return. Input is hidden.

The updater reads all active student courses, but displays only the single
next unsubmitted assignment with an upcoming due date. It refreshes every five
minutes. Past-due and undated items are excluded from this next-due view.
Submitted, graded, and excused assignments are excluded. It makes no Canvas
changes. The display shows the course, assignment name, and due date in Eastern
time. With no eligible future assignment it says Next assignment due: N/A.
On-paper tasks may need manual verification until completion is recorded.

Closing the updater or removing its saved token shows Waiting for Canvas key. A USB
disconnection or updater crash shows Waiting for Canvas key after 20 seconds without a
heartbeat. If Canvas rejects the token (401/403), the next five-minute check
returns the board to Waiting for Canvas key. Temporary Canvas failures keep the last result,
marked outdated after 15 minutes, while the updater is still connected.

Token is saved in a file readable only by your Mac account:
~/Library/Application Support/Canvas LED/token
To replace it, remove that file and restart. Revoke it in Canvas to disable access.

Requires Python 3 (already available on the Mac used for this setup).
To restore the standalone animation demo, upload AssignmentDemo.ino instead.
