import httpx
import pytest

from wolfhub.canvas import CanvasRest
from wolfhub.moodle.manifest import course_url


def test_canvas_import_paginates_and_syncs_without_secret(tmp_path):
    def respond(request):
        assert request.headers['authorization'] == 'Bearer secret'
        if request.url.path == '/api/v1/courses/42':
            return httpx.Response(200, json={'id': 42, 'name': 'Programming'})
        if request.url.params.get('page') == '2':
            return httpx.Response(200, json=[{'id': 2, 'name': 'Hidden', 'published': False}])
        return httpx.Response(200, headers={'Link': '<https://canvas.test/api/v1/courses/42/assignments?page=2>; rel="next"'}, json=[
            {'id': 1, 'name': 'Loops', 'description': '<p>Write a loop &amp; test it.</p>', 'due_at': '2026-11-01T23:59:00Z', 'updated_at': '2026-10-31T12:00:00Z'}])
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = CanvasRest('https://canvas.test', 'secret', client).import_course('csc116', '42', tmp_path, 'task_test')
    assert result['source'] == 'canvas' and not result['sample']
    assert len(result['items']) == 1
    item = result['items'][0]
    assert item['due'] == '2026-11-01T23:59:00Z'
    assert item['description'].startswith('Write a loop & test it.')
    assert item['version'] > 1
    manifest = tmp_path / 'csc116/course.canvas.json'
    assert 'secret' not in manifest.read_text()
    from wolfbox.sync.manifest import load_manifest
    loaded = load_manifest('https://wolfbox.test/course/csc116/course.canvas.json', lambda _: manifest.read_bytes())
    path = tmp_path / loaded['items'][0]['files'][0]['url'].removeprefix('/course/')
    assert path.read_text().startswith('# Loops')
    assert not (tmp_path / 'csc116/course.json').exists()


def test_cross_origin_pagination_never_receives_token():
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=[], headers={'Link': '<https://evil.test/next>; rel="next"'})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ValueError, match='Cross-origin'):
            CanvasRest('https://canvas.test', 'secret', client).pages('/api/v1/courses')
    assert len(requests) == 1


def test_permission_error_does_not_expose_token():
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(403, text='secret'))) as client:
        with pytest.raises(ValueError, match='HTTP 403') as err:
            CanvasRest('https://canvas.test', 'secret', client).course('42')
    assert 'secret' not in str(err.value)


def test_canvas_configuration_and_manifest_selection(monkeypatch):
    monkeypatch.delenv('CANVAS_API_TOKEN', raising=False)
    with pytest.raises(ValueError, match='CANVAS_API_TOKEN'):
        CanvasRest('https://canvas.test')
    assert course_url(source='canvas') == '/course/csc116/course.canvas.json'
    assert course_url(source='mock') == '/course/csc116/course.json'


def test_course_picker_selection_persists_and_controls_sync(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from wolfhub.main import create_app
    from wolfhub.registry import Registry
    import wolfhub.canvas as canvas

    imports, calls = [], []
    class FakeCanvas:
        def __init__(self, **kwargs): pass
        def courses(self): return [{'id': '42', 'name': 'Programming', 'code': 'CS'}]
        def import_course(self, course, query, site_dir, task_id):
            imports.append((course, query))
            return {'items': []}
    class Box:
        def call(self, box_id, envelope):
            calls.append(envelope)
            return {'ok': True, 'job_id': 'sync_test'}
    monkeypatch.setattr(canvas, 'CanvasRest', FakeCanvas)
    monkeypatch.setenv('COURSE_SOURCE', 'canvas')
    registry = Registry(tmp_path / 'students.json')
    registry.set('alex', 'Alex', 'box:alex', 'local')
    with TestClient(create_app(Box(), registry)) as client:
        assert client.post('/api/students/alex/sync').status_code == 400
        courses = client.get('/api/students/alex/canvas/courses').json()
        assert courses['courses'][0]['name'] == 'Programming'
        assert courses['selected_course_id'] is None
        response = client.post('/api/students/alex/sync', json={'canvas_course_id': '42'})
        assert response.status_code == 200
        assert imports == [('canvas-42', '42')]
        assert calls[-1]['course_url'] == 'http://testserver/course/canvas-42/course.canvas.json'
        registry.set('alex', 'Alex', 'box:alex', 'local')
        assert Registry(registry.path).get('alex')['canvas_course_id'] == '42'
        assert client.get('/api/students/alex/canvas/courses').json()['selected_course_id'] == '42'
        assert client.post('/api/students/alex/sync').status_code == 200
        assert imports[-1] == ('canvas-42', '42')
        before = len(imports)
        assert client.post('/api/students/alex/sync', json={'canvas_course_id': '../bad'}).status_code == 422
        assert len(imports) == before
