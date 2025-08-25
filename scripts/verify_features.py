#!/usr/bin/env python3
import json
import sys
import time
import random
import urllib.request
import urllib.error
import subprocess
from pathlib import Path

BASE = 'http://localhost:8000'
TIMEOUT = 6

results = {}


def req(method: str, path: str, headers=None, data=None, timeout=TIMEOUT):
    if headers is None:
        headers = {}
    body = None
    if data is not None:
        headers = {**headers, 'Content-Type': 'application/json'}
        body = json.dumps(data).encode()
    try:
        r = urllib.request.Request(
            BASE + path, data=body, headers=headers, method=method)
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            code = resp.getcode()
            content = resp.read()
            return code, content
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception:
        return 0, b''


# Core endpoints
for path in ('/health', '/docs', '/openapi.json', '/metrics'):
    code, _ = req('GET', path)
    results[f'GET {path}'] = code

# Phone OTP → token (randomized phone to avoid throttling collisions)
rand_suffix = f"{int(time.time()) % 10000:04d}{random.randint(1000, 9999)}"
phone = '+1550' + rand_suffix  # dummy valid-looking E.164
code, body = req('POST', '/onboarding/request-otp', data={'phone': phone})
results['POST /onboarding/request-otp'] = code
otp = ''
try:
    m = json.loads(body or b'{}')
    otp = m.get('otp') or ''
except Exception:
    otp = ''

token = ''
if otp and code == 200:
    code2, body2 = req('POST', '/onboarding/verify-otp',
                       data={'phone': phone, 'otp_code': otp})
    results['POST /onboarding/verify-otp'] = code2
    try:
        v = json.loads(body2 or b'{}')
        token = v.get('access_token') or ''
        if token:
            # persist token for follow-up manual tests
            try:
                Path('/app/token_jwt').write_text(token)
            except Exception:
                pass
    except Exception:
        token = ''
else:
    results['POST /onboarding/verify-otp'] = 0

# Protected checks (only if token present)
AH = {'Authorization': f'Bearer {token}'} if token else {}

code, _ = req('GET', '/auth/me', headers=AH)
results['GET /auth/me'] = code

code, _ = req('GET', '/places/me/check-ins', headers=AH)
results['GET /places/me/check-ins'] = code

# Collections
code, body = req('GET', '/collections/', headers=AH)
results['GET /collections/'] = code
# Create a collection and capture id
code, body = req('POST', '/collections/', headers=AH,
                 data={'name': 'Test Collection', 'visibility': 'public'})
results['POST /collections/'] = code
collection_id = None
try:
    if code == 200:
        j = json.loads(body or b'{}')
        collection_id = j.get('id')
except Exception:
    collection_id = None
# Fallback: fetch first collection id
if not collection_id:
    code_c, body_c = req('GET', '/collections/', headers=AH)
    try:
        j = json.loads(body_c or b'{}')
        items = j.get('items') or []
        if items:
            collection_id = items[0].get('id')
    except Exception:
        collection_id = None

# DMs basic requests/inbox
results['GET /dms/requests'], _ = req('GET', '/dms/requests', headers=AH)
results['GET /dms/inbox'], _ = req('GET', '/dms/inbox', headers=AH)

# Uploads unauthenticated
code, _ = req('POST', '/users/me/avatar', headers={}, data={})
results['POST /users/me/avatar (unauth)'] = code

# Places search (public) and capture first place id
code, body = req('GET', '/places/search?limit=1&offset=0')
results['GET /places/search'] = code
place_id = None
try:
    j = json.loads(body or b'{}')
    items = j.get('items') or []
    if items:
        place_id = items[0].get('id')
except Exception:
    place_id = None

# Create a check-in (if place exists)
checkin_id = None
if place_id and token:
    code, body = req('POST', '/places/check-ins', headers=AH, data={
        'place_id': place_id,
        'note': 'verifier',
        'latitude': 24.7,
        'longitude': 46.7,
        'visibility': 'public'
    })
    results['POST /places/check-ins'] = code
    try:
        j = json.loads(body or b'{}')
        checkin_id = j.get('id')
    except Exception:
        checkin_id = None
else:
    results['POST /places/check-ins'] = 0

# Authenticated avatar upload (tiny PNG via curl) using saved token
if token:
    png_path = '/tmp/1.png'
    Path(png_path).write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0bIDATx\x9cc``\x00\x00\x00\x02\x00\x01r\x0b\xe6\x84\x00\x00\x00\x00IEND\xaeB`\x82")
    curl = ['curl', '--max-time', '8', '-s', '-o', '/dev/null', '-w',
            '%{http_code}\n', '-H', f'Authorization: Bearer {token}', '-F', f'file=@{png_path};type=image/png', f'{BASE}/users/me/avatar']
    proc = subprocess.run(curl, capture_output=True, text=True)
    try:
        results['POST /users/me/avatar (auth)'] = int(
            (proc.stdout or '').strip() or '0')
    except Exception:
        results['POST /users/me/avatar (auth)'] = 0
else:
    results['POST /users/me/avatar (auth)'] = 0

# Upload a check-in photo (if we have a check-in id)
if checkin_id and token:
    png_path = '/tmp/2.png'
    Path(png_path).write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0bIDATx\x9cc``\x00\x00\x00\x02\x00\x01r\x0b\xe6\x84\x00\x00\x00\x00IEND\xaeB`\x82")
    curl = ['curl', '--max-time', '8', '-s', '-o', '/dev/null', '-w',
            '%{http_code}\n', '-H', f'Authorization: Bearer {token}', '-F', f'file=@{png_path};type=image/png', f'{BASE}/places/check-ins/{checkin_id}/photo']
    proc = subprocess.run(curl, capture_output=True, text=True)
    try:
        results['POST /places/check-ins/{id}/photo'] = int(
            (proc.stdout or '').strip() or '0')
    except Exception:
        results['POST /places/check-ins/{id}/photo'] = 0
else:
    results['POST /places/check-ins/{id}/photo'] = 0

# Add check-in to collection (if ids available)
if collection_id and checkin_id and token:
    code, _ = req(
        'POST', f'/collections/{collection_id}/items/{checkin_id}', headers=AH)
    results['POST /collections/{id}/items/{checkin_id}'] = code
else:
    results['POST /collections/{id}/items/{checkin_id}'] = 0

# Minimal DM request to a new email user (to exercise POST /dms/requests)
# Create recipient via email OTP
recipient = f'recipient{int(time.time()) % 100000}@test.com'
code_m, body_m = req('POST', '/auth/request-otp', data={'email': recipient})
# Extract OTP digits from message
rec_otp = ''
try:
    msg = json.loads(body_m or b'{}').get('message', '')
    import re
    m = re.search(r'(\d{6})', msg)
    rec_otp = m.group(1) if m else ''
except Exception:
    rec_otp = ''
if code_m == 200 and rec_otp and token:
    _code_v, _ = req('POST', '/auth/verify-otp',
                     data={'email': recipient, 'otp_code': rec_otp})
    # Send DM request from current token user to recipient
    code_dm, _ = req('POST', '/dms/requests', headers=AH,
                     data={'recipient_email': recipient, 'text': 'hi'})
    results['POST /dms/requests (send)'] = code_dm
else:
    results['POST /dms/requests (send)'] = 0

# Activity feed (requires following someone; expect 200 even if empty)
code, _ = req('GET', '/activity/feed', headers=AH)
results['GET /activity/feed'] = code
# Support tickets: create then list
code, body = req('POST', '/support/tickets', headers=AH,
                 data={'subject': 'Test', 'body': 'From verifier'})
results['POST /support/tickets'] = code
code, _ = req('GET', '/support/tickets', headers=AH)
results['GET /support/tickets'] = code

print(json.dumps(results, indent=2))

# Validation: expected codes
expected_200 = [
    'GET /health',
    'GET /docs',
    'GET /openapi.json',
    'GET /metrics',
    'POST /onboarding/request-otp',
    'POST /onboarding/verify-otp',
    'GET /auth/me',
    'GET /places/me/check-ins',
    'GET /collections/',
    'POST /collections/',
    'GET /dms/requests',
    'GET /dms/inbox',
    'GET /places/search',
    'POST /users/me/avatar (auth)',
    'GET /activity/feed',
    'POST /support/tickets',
    'GET /support/tickets'
]
# These are optional based on dynamic data; don't fail build if zero
optional_ok_or_zero = [
    'POST /places/check-ins',
    'POST /places/check-ins/{id}/photo',
    'POST /collections/{id}/items/{checkin_id}',
    'POST /dms/requests (send)'
]
expected_403 = ['POST /users/me/avatar (unauth)']

ok = True
for k in expected_200:
    if results.get(k) != 200:
        ok = False
for k in expected_403:
    if results.get(k) != 403:
        ok = False
# optional checks if present should be 200
for k in optional_ok_or_zero:
    v = results.get(k)
    if v not in (0, 200):
        ok = False

sys.exit(0 if ok else 1)
