#!/usr/bin/env python3
import json
import sys
import time
import random
import urllib.request
import urllib.error

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
code, _ = req('GET', '/collections/', headers=AH)
results['GET /collections/'] = code
code, _ = req('POST', '/collections/', headers=AH,
              data={'name': 'Test Collection', 'visibility': 'public'})
results['POST /collections/'] = code

# DMs
code, _ = req('GET', '/dms/requests', headers=AH)
results['GET /dms/requests'] = code
code, _ = req('GET', '/dms/inbox', headers=AH)
results['GET /dms/inbox'] = code

# Uploads unauthenticated
code, _ = req('POST', '/users/me/avatar', headers={}, data={})
results['POST /users/me/avatar (unauth)'] = code

# Places search (public)
code, _ = req('GET', '/places/search?limit=1&offset=0')
results['GET /places/search'] = code

print(json.dumps(results, indent=2))
