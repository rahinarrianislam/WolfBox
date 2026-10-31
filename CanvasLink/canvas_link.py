#!/usr/bin/env python3
"""WCPSS Canvas -> UNO Q over USB. Only uses Python's standard library."""
import datetime as dt
import getpass
import glob
import json
import os
from pathlib import Path
import re
import queue
import threading
import select
import ssl
import sys
import termios
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

BASE = 'https://wcpss.instructure.com'
TZ = ZoneInfo('America/New_York')
PRIVATE = Path.home() / 'Library' / 'Application Support' / 'Canvas LED'
TOKEN = PRIVATE / 'token'

class SameOrigin(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl)[:2] != urllib.parse.urlsplit(BASE)[:2]:
            raise RuntimeError('Canvas redirected to sign-in. Check or replace the API token.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def tls_context():
    context = ssl.create_default_context()
    # python.org macOS builds can lack their optional CA installation.
    # Add the macOS system CA bundle while preserving certificate/hostname checks.
    system_ca = Path('/etc/ssl/cert.pem')
    if sys.platform == 'darwin' and system_ca.is_file():
        context.load_verify_locations(cafile=str(system_ca))
    return context

class Canvas:
    def __init__(self, token):
        self.token = token
        self.opener = urllib.request.build_opener(SameOrigin(), urllib.request.HTTPSHandler(context=tls_context()))

    def pages(self, path, params):
        url = BASE + '/api/v1' + path + '?' + urllib.parse.urlencode(params, doseq=True)
        seen = set()
        while url:
            if urllib.parse.urlsplit(url)[:2] != urllib.parse.urlsplit(BASE)[:2] or url in seen:
                raise RuntimeError('Unexpected Canvas pagination link.')
            seen.add(url)
            req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + self.token, 'Accept': 'application/json'})
            with self.opener.open(req, timeout=30) as response:
                rows = json.load(response)
                if not isinstance(rows, list):
                    raise RuntimeError('Canvas returned an unexpected response.')
                yield from rows
                links = response.headers.get('Link', '')
                match = re.search(r'<([^>]+)>;\s*rel="next"', links)
                url = urllib.parse.urljoin(url, match.group(1)) if match else None

    def assignments(self):
        courses = list(self.pages('/courses', {'enrollment_state': 'active', 'enrollment_type': 'student', 'state[]': 'available', 'per_page': 100}))
        results = []
        for course in courses:
            if course.get('workflow_state') != 'available':
                continue
            for assignment in self.pages('/courses/' + str(int(course['id'])) + '/assignments', {'include[]': 'submission', 'per_page': 100}):
                assignment = dict(assignment)
                assignment['course_label'] = course.get('course_code') or course.get('name', 'Course')
                results.append(assignment)
        return results, len(courses)

def date(value):
    return dt.datetime.fromisoformat(value.replace('Z', '+00:00')) if value else None

def clean(text, limit=330):
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    return ' '.join(text.split())[:limit]

def outstanding(a):
    s = a.get('submission')
    if not isinstance(s, dict):
        raise RuntimeError('Canvas did not include submission status; refusing to assume work is complete.')
    if s.get('excused') or s.get('workflow_state') in ('submitted', 'pending_review', 'graded') or s.get('submitted_at'):
        return False
    if a.get('published') is False:
        return False
    # Ignore informational ungraded items. On-paper work remains visible for
    # review until Canvas records a grade or excused/submitted status.
    kinds = a.get('submission_types', [])
    if kinds and set(kinds) <= {'none', 'not_graded'} and not s.get('missing'):
        return False
    return True

def display(assignments, course_count, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    if not course_count:
        return 'I', 'Canvas connected. No active student courses found.'
    upcoming = []
    for assignment in assignments:
        due = date(assignment.get('due_at'))
        if due is not None and due >= now and outstanding(assignment):
            upcoming.append((due, assignment))
    if not upcoming:
        return 'H', 'Next assignment due: N/A. No upcoming dated assignments.'
    due, assignment = min(upcoming, key=lambda pair: pair[0])
    label = clean(assignment['course_label'], 45) + ': ' + clean(assignment.get('name', 'Assignment'), 100)
    when = due.astimezone(TZ).strftime('%b %d %I:%M %p')
    return 'S', clean(f'Next assignment: {label}. Due {when} Eastern')

class Board:
    def __init__(self):
        ports = glob.glob('/dev/cu.usbmodem*')
        if len(ports) != 1:
            raise RuntimeError('Connect only your UNO Q by USB, then try again.')
        self.fd = os.open(ports[0], os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        attrs = termios.tcgetattr(self.fd)
        attrs[0] = attrs[1] = attrs[3] = 0
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        attrs[4] = attrs[5] = termios.B115200
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(self.fd, termios.TCSANOW, attrs)

    def send(self, mood, message):
        payload = (mood + '\t' + clean(message) + '\n').encode('ascii')
        return self.exchange(payload)

    def command(self, command):
        return self.exchange((command + '\n').encode('ascii'))

    def exchange(self, payload):
        offset = 0
        while offset < len(payload):
            if select.select([], [self.fd], [], 5)[1]:
                offset += os.write(self.fd, payload[offset:])
            else:
                raise RuntimeError('USB write timed out.')
        received = b''
        until = time.monotonic() + 90
        while time.monotonic() < until:
            if select.select([self.fd], [], [], 1)[0]:
                received += os.read(self.fd, 4096)
                if b'CANVAS_OK' in received:
                    return received.decode('ascii', errors='replace')
        raise RuntimeError('No acknowledgement from the board. Upload CanvasDisplay.ino and close Serial Monitor.')

    def close(self):
        os.close(self.fd)

def token():
    if '--reset-token' in sys.argv or not TOKEN.exists():
        print('Create a token at https://wcpss.instructure.com/profile/settings')
        print('Use New Access Token, name it Canvas LED, and choose an expiration date.')
        print('Paste it below. Your entry stays hidden and is sent only to WCPSS Canvas.')
        value = getpass.getpass('Canvas token: ').strip()
        if not value:
            raise RuntimeError('No token entered.')
        # Validate the token before saving; the token never goes to the board.
        list(Canvas(value).pages('/courses', {'enrollment_state': 'active', 'per_page': 100}))
        PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(PRIVATE, 0o700)
        fd = os.open(TOKEN, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(value)
        return value
    return TOKEN.read_text().strip()

def main():
    if '--device-test' in sys.argv:
        board = Board()
        try:
            board.send('I', 'USB connection test - waiting for Canvas setup')
            print('UNO Q acknowledged the USB update.')
        finally:
            board.close()
        return
    api = Canvas(token())
    print('Canvas LED is running. Keep this window open and your Mac awake.')
    print('Checks all active student courses every five minutes. Press Control-C to stop.')
    print('Closing this updater or removing its saved token shows Waiting for Canvas key.')
    results = queue.Queue()
    board = None
    last_sent = None
    next_fetch = 0
    next_heartbeat = 0
    fetching = False

    def fetch():
        try:
            results.put((True, api.assignments()))
        except Exception as error:
            results.put((False, error))

    try:
        while True:
            if not TOKEN.exists():
                print('Saved token removed. Showing Waiting for Canvas key.')
                break
            now = time.monotonic()
            if not fetching and now >= next_fetch:
                fetching = True
                threading.Thread(target=fetch, daemon=True).start()
            try:
                success, value = results.get_nowait()
            except queue.Empty:
                success = None
            if success is not None:
                fetching = False
                next_fetch = time.monotonic() + 300
                if success:
                    assignments, courses = value
                    last_sent = display(assignments, courses)
                    try:
                        if board is None:
                            board = Board()
                        board.send(*last_sent)
                        next_heartbeat = time.monotonic() + 5
                        print(dt.datetime.now(TZ).strftime('%I:%M %p') + f' - Updated UNO Q from {courses} courses.')
                    except Exception as error:
                        print('USB update failed: ' + str(error))
                        if board:
                            board.close()
                            board = None
                        next_fetch = time.monotonic() + 5
                elif isinstance(value, urllib.error.HTTPError) and value.code in (401, 403):
                    print('Canvas access rejected. Showing Waiting for Canvas key. Replace the token to reconnect.')
                    break
                else:
                    print('Canvas update failed: ' + str(value))
                    print('Last saved information becomes marked outdated after 15 minutes.')
                if '--once' in sys.argv:
                    break
            if last_sent and time.monotonic() >= next_heartbeat:
                try:
                    if board is None:
                        board = Board()
                        # Reconnection requires a fresh Canvas response, rather than
                        # re-stamping stale data as newly fetched.
                        next_fetch = 0
                    else:
                        board.command('K')
                except Exception as error:
                    print('USB disconnected: ' + str(error))
                    if board:
                        board.close()
                        board = None
                next_heartbeat = time.monotonic() + 5
            time.sleep(0.25)
    finally:
        if board:
            try:
                board.command('D')
            except Exception:
                pass  # Hardware timeout handles abrupt disconnects too.
            board.close()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nStopped. The board shows Waiting for Canvas key automatically.')
    except urllib.error.HTTPError as e:
        print(f'Canvas rejected access ({e.code}). Check the token and try again.')
        sys.exit(1)
    except Exception as e:
        print('Setup unsuccessful: ' + str(e))
        sys.exit(1)
