"""Import the selected Canvas course before starting student sync."""
import os
from pathlib import Path
import secrets

import httpx

from wolfhub.canvas import CanvasRest


def main():
    query = os.getenv('CANVAS_COURSE_ID')
    if not query:
        raise SystemExit('Set CANVAS_COURSE_ID in .env to a course ID or exact Canvas name/code. Use COURSE_SOURCE=mock for the sample demo.')
    site_dir = Path(__file__).resolve().parents[1] / 'orchestrator/course_site'
    try:
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            result = CanvasRest(client=client).import_course('csc116', query, site_dir, 'task_' + secrets.token_hex(6))
        print(f"Canvas ready: {len(result['items'])} assignments imported")
    except (ValueError, KeyError, httpx.HTTPError):
        raise SystemExit('Canvas import failed. Check CANVAS_URL, CANVAS_API_TOKEN, CANVAS_COURSE_ID, and connectivity.')


if __name__ == '__main__':
    main()
