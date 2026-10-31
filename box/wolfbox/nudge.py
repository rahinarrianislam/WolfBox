"""Pure stuck detection; callers filter runs to the current assignment."""

from datetime import UTC, datetime


def _time(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if isinstance(value, (int, float)):
        value = datetime.fromtimestamp(value, UTC)
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def compute(runs, now, stuck_minutes):
    completed = [r for r in runs if r.get("status", "done") != "running"]
    completed.sort(key=lambda r: _time(r["ts"]), reverse=True)
    if completed:
        for test in sorted({f["test"] for f in completed[0].get("failed", [])}):
            streak = []
            for run in completed:
                if test not in {f["test"] for f in run.get("failed", [])}:
                    break
                streak.append(run)
            if len(streak) >= 5:
                return {
                    "active": True,
                    "reason": f"{test} failed {len(streak)} runs in a row",
                }
            minutes = (_time(now) - _time(streak[-1]["ts"])).total_seconds() / 60
            if minutes >= stuck_minutes:
                return {
                    "active": True,
                    "reason": f"{test} has been failing for {int(minutes)} minutes",
                }
    return {"active": False, "reason": None}
