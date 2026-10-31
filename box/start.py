"""Start the box with the same entry point locally and in Maritime."""

import os
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == "__main__":
    uvicorn.run(
        "wolfbox.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8080"))
    )
