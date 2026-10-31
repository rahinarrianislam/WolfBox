"""Canvas REST assignment import; credentials stay on the orchestrator."""
import html
import os
from datetime import datetime
from urllib.parse import urljoin, urlsplit

import httpx

from .moodle.agent import MoodleDelegate
from .moodle.manifest import save_manifest
from .moodle.models import web_url
from .moodle.rest import plain_text


class CanvasRest:
    def __init__(self, base_url=None, token=None, client=None):
        self.base = web_url(base_url or os.environ['CANVAS_URL']).rstrip('/')
        self.token = token or os.getenv('CANVAS_API_TOKEN')
        if not self.token:
            raise ValueError('Set CANVAS_API_TOKEN on the server')
        self.client = client or httpx.Client(timeout=20, follow_redirects=False)

    def request(self, method, path, **kwargs):
        url = urljoin(self.base + '/', path)
        if urlsplit(url).netloc != urlsplit(self.base).netloc or urlsplit(url).scheme != 'https':
            raise ValueError('Cross-origin Canvas API request refused')
        response = self.client.request(method, url, headers={'Authorization': f'Bearer {self.token}'}, **kwargs)
        if response.status_code >= 300:
            # Never include request URLs, response bodies, or credentials in task logs.
            raise ValueError(f'Canvas API returned HTTP {response.status_code}; check token and course permissions')
        return response

    def pages(self, path):
        rows, seen = [], set()
        while path:
            if path in seen or len(seen) >= 100:
                raise ValueError('Canvas pagination exceeded its limit')
            seen.add(path)
            response = self.request('GET', path)
            data = response.json()
            if not isinstance(data, list):
                raise ValueError('Expected a Canvas list response')
            rows.extend(data)
            path = response.links.get('next', {}).get('url')
        return rows

    def courses(self):
        return [{'id': str(c['id']), 'name': c.get('name') or c.get('course_code') or str(c['id']),
                 'code': c.get('course_code', '')}
                for c in self.pages('/api/v1/courses?per_page=100') if c.get('name') or c.get('course_code')]

    def course(self, query):
        if str(query).isdigit():
            return self.request('GET', f'/api/v1/courses/{query}').json()
        courses = self.pages('/api/v1/courses?per_page=100')
        exact = [c for c in courses if str(query).casefold() in {
            str(c['id']), c.get('course_code', '').casefold(), c.get('name', '').casefold()}]
        if len(exact) != 1:
            raise ValueError('Set CANVAS_COURSE_ID to a Canvas course ID or exact course name/code')
        return exact[0]

    def import_course(self, course, query, site_dir, task_id):
        selected = self.course(query)
        rows = self.pages(f"/api/v1/courses/{selected['id']}/assignments?per_page=100")
        items = []
        for row in rows:
            if row.get('published') is False:
                continue
            # Descriptions and deadlines are synced locally; Canvas links stay in the instructions.
            item = {'id': f"canvas-{row['id']}", 'type': 'assignment', 'title': row['name'],
                    'description': plain_text(row.get('description')) + f"\n\n[Open in Canvas]({self.base}/courses/{selected['id']}/assignments/{row['id']})",
                    'version': max(1, int(datetime.fromisoformat(row['updated_at'].replace('Z', '+00:00')).timestamp())) if row.get('updated_at') else 1,
                    'files': []}
            if row.get('due_at'):
                item['due'] = row['due_at']
            items.append(item)
        return save_manifest({'course': course, 'title': selected['name'], 'source': 'canvas',
                              'sample': False, 'items': items}, site_dir, task_id)


class CanvasDelegate(MoodleDelegate):
    """Reuse task storage and validation, with direct Canvas operations."""
    def __init__(self, site_dir=None, **kwargs):
        super().__init__(site_dir=site_dir, mode='real', **kwargs)

    def _run_task(self, task_id):
        task = self.tasks[task_id]
        task['status'] = 'running'
        task['mode'] = 'real'
        try:
            with httpx.Client(timeout=20, follow_redirects=False) as client:
                rest = CanvasRest(token=task.get('ws_token'), client=client)
                query = task['params'].get('canvas_course_id') or os.getenv('CANVAS_COURSE_ID')
                if not query:
                    raise ValueError('Select a Canvas course first')
                task['steps'].append('Connecting to Canvas')
                if task['kind'] == 'list_assignments':
                    task['result'] = rest.import_course(task['course'], query, self.site_dir, task_id)
                    task['steps'].append(f"Imported {len(task['result']['items'])} Canvas assignments")
                else:
                    course = rest.course(query)
                    url = f"{rest.base}/courses/{course['id']}"
                    if task['kind'] == 'publish_assignment':
                        staged = self._load_staged_assignment(task['course'], task['params']['item'])
                        assignment = {'name': staged['title'], 'description': '<pre>' + html.escape(staged['description']) + '</pre>',
                                      'submission_types': ['online_upload'], 'published': True}
                        if staged['due']:
                            assignment['due_at'] = staged['due']
                        result = rest.request('POST', f"/api/v1/courses/{course['id']}/assignments", json={'assignment': assignment}).json()
                        url = f"{url}/assignments/{result['id']}"
                    task['result'] = {'canvas_url': url}
                    task['steps'].append('Canvas operation completed')
            task['status'] = 'done'
        except Exception as exc:
            task['status'] = 'error'
            task['steps'].append(str(exc) if isinstance(exc, ValueError) else 'Canvas request failed; check server configuration and connectivity')

    def resume_task(self, task_id, token=None):
        raise ValueError('Configure CANVAS_API_TOKEN on the server and start a new task')
