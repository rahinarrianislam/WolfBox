import json
from urllib.parse import urljoin, urlparse

from .fetch import fetch


def load_manifest(course_url, fetcher=None):
    raw = (fetcher or fetch)(course_url)
    data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
    if not isinstance(data, dict) or not isinstance(data.get("items"), list) or not data.get("course"):
        raise ValueError("invalid course manifest")
    origin = f"{urlparse(course_url).scheme}://{urlparse(course_url).netloc}"
    for item in data["items"]:
        if not item.get("id") or not isinstance(item.get("files"), list):
            raise ValueError("invalid manifest item")
        for file in item["files"]:
            file["resolved_url"] = urljoin(origin, file.get("url") or file.get("path", ""))
    return data
