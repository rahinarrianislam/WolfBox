"""Serve an isolated copy of the course for the native client's contract test."""
import os
from pathlib import Path
import uvicorn
import wolfhub.main as main
import wolfhub.course as course

main.ROOT = Path(os.environ['WOLFBOX_LIVE_ROOT'])
course.SITE_DIR = main.ROOT / 'course_site'
uvicorn.run(main.create_app(), host='127.0.0.1', port=int(os.environ['WOLFBOX_LIVE_PORT']))
