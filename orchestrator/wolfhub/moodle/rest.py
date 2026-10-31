"""Token-based read adapter; institutional password/SSO login stays human-only."""
import html
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

from .manifest import save_manifest
from .models import web_url


DEMO_HOSTS = {"school.moodledemo.net", "sandbox.moodledemo.net"}


def plain_text(value):
    return html.unescape(re.sub(r"<[^>]+>", " ", value or "")).strip()


class MoodleRest:
    def __init__(self, base_url, token=None, client=None):
        self.base = web_url(base_url).rstrip("/")
        self.token = token or os.getenv("MOODLE_WS_TOKEN")
        self.client = client or httpx.Client(timeout=20, follow_redirects=False)

    def authenticate(self):
        if self.token:
            return
        if urlsplit(self.base).hostname not in DEMO_HOSTS:
            raise ValueError("Use MOODLE_WS_TOKEN or human takeover for institutional Moodle")
        username, password = os.getenv("MOODLE_USERNAME"), os.getenv("MOODLE_PASSWORD")
        if not username or not password:
            page = self.client.get(self.base + "/login/index.php")
            page.raise_for_status()
            text = plain_text(page.text)
            match = re.search(r"username\s+(teacher)\s+and password\s+(\S+)", text)
            if not match:
                raise ValueError("Set public demo MOODLE_USERNAME/MOODLE_PASSWORD")
            username, password = match.groups()
        response = self.client.post(self.base + "/login/token.php", data={"username": username, "password": password, "service": "moodle_mobile_app"})
        response.raise_for_status()
        self.token = response.json().get("token")
        if not self.token:
            raise ValueError("Moodle web-service token unavailable; use browser import")

    def call(self, function, **params):
        self.authenticate()
        response = self.client.post(self.base + "/webservice/rest/server.php", data={"wstoken": self.token, "wsfunction": function, "moodlewsrestformat": "json", **params})
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and (data.get("exception") or data.get("errorcode")):
            raise ValueError(f"Moodle API refused {function}")
        return data

    def import_course(self, course, query, site_dir, task_id):
        courses = self.call("core_course_search_courses", criterianame="search", criteriavalue=query)["courses"]
        exact = [c for c in courses if query.casefold().strip() in {str(c["id"]), c["shortname"].casefold().strip(), plain_text(c["fullname"]).casefold().strip()}]
        if len(exact) != 1:
            raise ValueError("MOODLE_COURSE must exactly match one course short name, full name, or id")
        selected = exact[0]
        sections = self.call("core_course_get_contents", courseid=selected["id"])
        assignments = self.call("mod_assign_get_assignments", **{"courseids[0]": selected["id"]})
        if assignments.get("warnings"):
            raise ValueError("Moodle refused assignment access; use browser import")
        by_module = {a["cmid"]: a for c in assignments["courses"] for a in c["assignments"]}
        manifest = {"course": course, "title": plain_text(selected["fullname"]), "source": "moodle", "sample": urlsplit(self.base).hostname in DEMO_HOSTS, "items": []}
        exports = {}
        for section in sections:
            for module in section.get("modules", []):
                if module.get("modname") not in {"assign", "resource", "folder", "page", "url", "book"}:
                    continue
                assignment = by_module.get(module["id"], {})
                item_id = f"moodle-{module['id']}"
                item = {"id": item_id, "type": "assignment" if module["modname"] == "assign" else "doc", "title": plain_text(module["name"]), "version": 1, "description": plain_text(assignment.get("intro") or module.get("description")), "files": []}
                if assignment.get("duedate"):
                    item["due"] = datetime.fromtimestamp(assignment["duedate"], timezone.utc).isoformat()
                contents = module.get("contents", []) + assignment.get("introattachments", [])
                for attachment in contents:
                    if attachment.get("type", "file") != "file":
                        continue
                    filename = attachment["filename"]
                    url = attachment["fileurl"]
                    # Do not forward a Moodle bearer token to an attachment-controlled host.
                    if urlsplit(url).netloc != urlsplit(self.base).netloc or urlsplit(url).scheme != "https":
                        raise ValueError("Cross-origin Moodle attachment refused")
                    path = f"{item_id}/{filename}"
                    if path in exports:
                        continue
                    remote = f"/rest/{task_id}/exports/{path}"
                    item["files"].append({"path": path, "url": url.split("?")[0], "agent_path": remote})
                    exports[path] = url
                manifest["items"].append(item)

        def download(path):
            relative = path.removeprefix(f"/rest/{task_id}/exports/")
            response = self.client.get(exports[relative], params={"token": self.token})
            response.raise_for_status()
            if response.is_redirect or "text/html" in response.headers.get("content-type", ""):
                raise ValueError("Moodle attachment requires browser authentication")
            return response.content

        return save_manifest(manifest, site_dir, task_id, f"/rest/{task_id}", download)
