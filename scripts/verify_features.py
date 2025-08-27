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


def check_core(results: dict) -> None:
    for path in ('/health', '/docs', '/openapi.json', '/metrics'):
        code, _ = req('GET', path)
        results[f'GET {path}'] = code


def check_openapi(results: dict) -> None:
    code_oai, body_oai = req('GET', '/openapi.json')
    if code_oai != 200:
        return
    try:
        oai = json.loads(body_oai or b'{}')
        paths = oai.get('paths', {}) or {}

        def has(path: str, method: str | None = None) -> bool:
            p = paths.get(path)
            if p is None:
                return False
            if method is None:
                return True
            return method.lower() in (p or {})

        results['OA /settings/privacy'] = 1 if has(
            '/settings/privacy', 'get') and has('/settings/privacy', 'put') else 0
        results['OA /settings/notifications'] = 1 if has(
            '/settings/notifications', 'get') and has('/settings/notifications', 'put') else 0
        results['OA /follow endpoints'] = 1 if has('/follow/{user_id}', 'post') and has(
            '/follow/{user_id}', 'delete') and has('/follow/followers', 'get') and has('/follow/following', 'get') else 0
        results['OA /dms endpoints'] = 1 if has(
            '/dms/requests') and has('/dms/inbox') else 0
        results['OA /collections endpoints'] = 1 if has(
            '/collections/', 'get') and has('/collections/', 'post') else 0
        results['OA /places endpoints'] = 1 if has(
            '/places/search', 'get') and has('/places/check-ins', 'post') else 0
        results['OA /support endpoints'] = 1 if has(
            '/support/tickets', 'get') and has('/support/tickets', 'post') else 0
    except Exception:
        return


def login_via_phone(results: dict) -> str:
    rand_suffix = f"{int(time.time()) % 10000:04d}{random.randint(1000, 9999)}"
    phone = '+1550' + rand_suffix
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
                try:
                    Path('/app/token_jwt').write_text(token)
                except Exception:
                    pass
        except Exception:
            token = ''
    else:
        results['POST /onboarding/verify-otp'] = 0
    return token


def protected_smoke(results: dict, headers: dict) -> None:
    code, _ = req('GET', '/auth/me', headers=headers)
    results['GET /auth/me'] = code
    code, _ = req('GET', '/places/me/check-ins', headers=headers)
    results['GET /places/me/check-ins'] = code


def ensure_collection(results: dict, headers: dict) -> int | None:
    code, body = req('GET', '/collections/', headers=headers)
    results['GET /collections/'] = code
    code, body = req('POST', '/collections/', headers=headers,
                     data={'name': 'Test Collection', 'visibility': 'public'})
    results['POST /collections/'] = code
    collection_id = None
    try:
        if code == 200:
            j = json.loads(body or b'{}')
            collection_id = j.get('id')
    except Exception:
        collection_id = None
    if not collection_id:
        code_c, body_c = req('GET', '/collections/', headers=headers)
        try:
            j = json.loads(body_c or b'{}')
            items = j.get('items') or []
            if items:
                collection_id = items[0].get('id')
        except Exception:
            collection_id = None
    return collection_id


def dms_smoke(results: dict, headers: dict) -> None:
    results['GET /dms/requests'], _ = req('GET',
                                          '/dms/requests', headers=headers)
    results['GET /dms/inbox'], _ = req('GET', '/dms/inbox', headers=headers)


def check_unauth_upload(results: dict) -> None:
    code, _ = req('POST', '/users/me/avatar', headers={}, data={})
    results['POST /users/me/avatar (unauth)'] = code


def pick_place(results: dict) -> int | None:
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
    return place_id


def create_checkin(results: dict, headers: dict, place_id: int | None) -> int | None:
    if not place_id:
        results['POST /places/check-ins'] = 0
        return None
    code, body = req('POST', '/places/check-ins', headers=headers, data={
                     'place_id': place_id, 'note': 'verifier', 'latitude': 24.7, 'longitude': 46.7, 'visibility': 'public'})
    results['POST /places/check-ins'] = code
    try:
        j = json.loads(body or b'{}')
        return j.get('id')
    except Exception:
        return None


def upload_avatar(results: dict, headers: dict) -> None:
    if not headers:
        results['POST /users/me/avatar (auth)'] = 0
        return
    import base64
    png_path = '/tmp/avatar.png'
    # Valid 1x1 PNG (black)
    png_b64_small = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/6X8D8IAAAAASUVORK5CYII='
    try:
        Path(png_path).write_bytes(base64.b64decode(png_b64_small))
    except Exception:
        Path(png_path).write_bytes(b'')
    curl = ['curl', '--max-time', '8', '-s', '-o', '/dev/null', '-w',
            '%{http_code}\n', '-H', f'Authorization: Bearer {headers["Authorization"].replace("Bearer ", "")}', '-F', f'file=@{png_path};type=image/png', f'{BASE}/users/me/avatar']
    proc = subprocess.run(curl, capture_output=True, text=True)
    code_avatar = 0
    try:
        code_avatar = int((proc.stdout or '').strip() or '0')
    except Exception:
        code_avatar = 0
    # Fallback with Pillow JPEG if PNG fails
    if code_avatar != 200:
        try:
            from PIL import Image
            jpg_path_fb = '/tmp/avatar_fallback.jpg'
            img = Image.new('RGB', (10, 10), color=(255, 255, 255))
            img.save(jpg_path_fb, format='JPEG')
            curl_fb = ['curl', '--max-time', '8', '-s', '-o', '/dev/null', '-w',
                       '%{http_code}\n', '-H', f'Authorization: Bearer {headers["Authorization"].replace("Bearer ", "")}', '-F', f'file=@{jpg_path_fb};type=image/jpeg', f'{BASE}/users/me/avatar']
            proc_fb = subprocess.run(curl_fb, capture_output=True, text=True)
            code_avatar = int((proc_fb.stdout or '').strip() or '0')
        except Exception:
            pass
    results['POST /users/me/avatar (auth)'] = code_avatar
    # Cleanup temp files
    try:
        Path(png_path).unlink(missing_ok=True)
    except Exception:
        pass
    try:
        Path('/tmp/avatar_fallback.jpg').unlink(missing_ok=True)
    except Exception:
        pass
    # Best-effort cleanup of uploaded avatar file on disk
    if code_avatar == 200:
        try:
            code_me, body_me = req('GET', '/auth/me', headers=headers)
            if code_me == 200:
                data = json.loads(body_me or b'{}')
                avatar_url = data.get('avatar_url') or ''
                if isinstance(avatar_url, str) and avatar_url.startswith('/media/'):
                    local_path = Path(avatar_url.lstrip('/'))
                    try:
                        local_path.unlink(missing_ok=True)
                    except Exception:
                        pass
        except Exception:
            pass


def upload_checkin_photo(results: dict, headers: dict, checkin_id: int | None) -> None:
    if not (headers and checkin_id):
        results['POST /places/check-ins/{id}/photo'] = 0
        return
    import base64
    png_path2 = '/tmp/checkin.png'
    png_b64_small2 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/6X8D8IAAAAASUVORK5CYII='
    try:
        Path(png_path2).write_bytes(base64.b64decode(png_b64_small2))
    except Exception:
        Path(png_path2).write_bytes(b'')
    curl = ['curl', '--max-time', '8', '-s', '-o', '/dev/null', '-w',
            '%{http_code}\n', '-H', f'Authorization: Bearer {headers["Authorization"].replace("Bearer ", "")}', '-F', f'file=@{png_path2};type=image/png', f'{BASE}/places/check-ins/{checkin_id}/photo']
    proc = subprocess.run(curl, capture_output=True, text=True)
    code_ci_photo = 0
    try:
        code_ci_photo = int((proc.stdout or '').strip() or '0')
    except Exception:
        code_ci_photo = 0
    if code_ci_photo != 200:
        try:
            from PIL import Image
            jpg_path2_fb = '/tmp/checkin_fallback.jpg'
            img2 = Image.new('RGB', (10, 10), color=(200, 200, 200))
            img2.save(jpg_path2_fb, format='JPEG')
            curl_fb2 = ['curl', '--max-time', '8', '-s', '-o', '/dev/null', '-w',
                        '%{http_code}\n', '-H', f'Authorization: Bearer {headers["Authorization"].replace("Bearer ", "")}', '-F', f'file=@{jpg_path2_fb};type=image/jpeg', f'{BASE}/places/check-ins/{checkin_id}/photo']
            proc_fb2 = subprocess.run(curl_fb2, capture_output=True, text=True)
            code_ci_photo = int((proc_fb2.stdout or '').strip() or '0')
        except Exception:
            pass
    results['POST /places/check-ins/{id}/photo'] = code_ci_photo
    # Cleanup temp files
    try:
        Path(png_path2).unlink(missing_ok=True)
    except Exception:
        pass
    try:
        Path('/tmp/checkin_fallback.jpg').unlink(missing_ok=True)
    except Exception:
        pass
    # Best-effort cleanup of uploaded check-in photos via API
    if code_ci_photo == 200 and checkin_id:
        try:
            req('DELETE',
                f'/places/check-ins/{checkin_id}/photo', headers=headers)
        except Exception:
            pass


def add_checkin_to_collection(results: dict, headers: dict, collection_id: int | None, checkin_id: int | None) -> None:
    if collection_id and checkin_id and headers:
        code, _ = req(
            'POST', f'/collections/{collection_id}/items/{checkin_id}', headers=headers)
        results['POST /collections/{id}/items/{checkin_id}'] = code
    else:
        results['POST /collections/{id}/items/{checkin_id}'] = 0


def dm_request(results: dict, headers: dict) -> None:
    # Create a second user via phone onboarding
    import random
    import time
    phone2 = '+1551' + \
        f"{int(time.time()) % 10000:04d}{random.randint(1000, 9999)}"
    code_m, body_m = req('POST', '/onboarding/request-otp',
                         data={'phone': phone2})
    otp2 = ''
    try:
        m = json.loads(body_m or b'{}')
        otp2 = m.get('otp') or ''
    except Exception:
        otp2 = ''
    if code_m == 200 and otp2 and headers:
        _code_v, body_v = req('POST', '/onboarding/verify-otp',
                              data={'phone': phone2, 'otp_code': otp2})
        try:
            user2 = json.loads(body_v or b'{}').get('user') or {}
            recipient_id = user2.get('id')
        except Exception:
            recipient_id = None
        if recipient_id:
            code_dm, _ = req('POST', '/dms/requests', headers=headers,
                             data={'recipient_id': recipient_id, 'text': 'hi'})
            results['POST /dms/requests (send)'] = code_dm
            return
    results['POST /dms/requests (send)'] = 0


def activity_and_support(results: dict, headers: dict) -> None:
    code, _ = req('GET', '/activity/feed', headers=headers)
    results['GET /activity/feed'] = code
    code, _ = req('POST', '/support/tickets', headers=headers,
                  data={'subject': 'Test', 'body': 'From verifier'})
    results['POST /support/tickets'] = code
    code, _ = req('GET', '/support/tickets', headers=headers)
    results['GET /support/tickets'] = code


def screens_checks(results: dict, headers: dict, place_id: int | None, user_id: int | None) -> None:
    # Recommendations (auth)
    code, _ = req(
        'GET', '/places/recommendations?limit=5&offset=0', headers=headers)
    results['GET /places/recommendations'] = code
    # Trending variants (public)
    code, _ = req('GET', '/places/trending?limit=5&offset=0')
    results['GET /places/trending'] = code
    code, _ = req('GET', '/places/trending/global?limit=5&offset=0')
    results['GET /places/trending/global'] = code
    # Search suggestions
    code, _ = req('GET', '/places/search/suggestions?q=caf')
    results['GET /places/search/suggestions'] = code
    # External suggestions (public)
    code, _ = req(
        'GET', '/places/external/suggestions?query=cafe&lat=24.7&lon=46.7')
    results['GET /places/external/suggestions'] = code
    # Who's here endpoints (auth; require a place)
    if place_id:
        code, _ = req('GET', f'/places/{place_id}/whos-here', headers=headers)
        results['GET /places/{id}/whos-here'] = code
        code, _ = req(
            'GET', f'/places/{place_id}/whos-here-count', headers=headers)
        results['GET /places/{id}/whos-here-count'] = code
    else:
        results['GET /places/{id}/whos-here'] = 0
        results['GET /places/{id}/whos-here-count'] = 0
    # User profile screens (auth)
    if user_id:
        code, _ = req(
            'GET', f'/users/{user_id}/media?limit=10&offset=0', headers=headers)
        results['GET /users/{id}/media'] = code
        code, _ = req('GET', f'/users/{user_id}/collections', headers=headers)
        results['GET /users/{id}/collections'] = code
        code, _ = req(
            'GET', f'/users/{user_id}/profile-stats', headers=headers)
        results['GET /users/{id}/profile-stats'] = code
    else:
        results['GET /users/{id}/media'] = 0
        results['GET /users/{id}/collections'] = 0
        results['GET /users/{id}/profile-stats'] = 0


def main() -> int:
    results: dict[str, int] = {}
    check_core(results)
    check_openapi(results)
    token = login_via_phone(results)
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    protected_smoke(results, headers)
    # Determine current user_id from /auth/me for profile checks
    user_id = None
    try:
        code_me, body_me = req('GET', '/auth/me', headers=headers)
        if code_me == 200:
            user_id = (json.loads(body_me or b'{}') or {}).get('id')
    except Exception:
        user_id = None
    collection_id = ensure_collection(results, headers)
    dms_smoke(results, headers)
    check_unauth_upload(results)
    place_id = pick_place(results)
    checkin_id = create_checkin(
        results, headers, place_id) if place_id else None
    upload_avatar(results, headers)
    upload_checkin_photo(results, headers, checkin_id)
    add_checkin_to_collection(results, headers, collection_id, checkin_id)
    dm_request(results, headers)
    activity_and_support(results, headers)
    screens_checks(results, headers, place_id, user_id)
    print(json.dumps(results, indent=2))

    expected_200 = [
        'GET /health', 'GET /docs', 'GET /openapi.json', 'GET /metrics',
        'POST /onboarding/request-otp', 'POST /onboarding/verify-otp', 'GET /auth/me',
        'GET /places/me/check-ins', 'GET /collections/', 'POST /collections/', 'GET /dms/requests',
        'GET /dms/inbox', 'GET /places/search', 'POST /users/me/avatar (auth)', 'GET /activity/feed',
        'POST /support/tickets', 'GET /support/tickets'
    ]
    # Screen endpoints expected 200 (auth if needed)
    expected_200 += [
        'GET /places/recommendations',
        'GET /places/trending',
        'GET /places/trending/global',
        'GET /places/search/suggestions',
        'GET /places/external/suggestions',
    ]
    # Auth + data dependent
    optional_ok_or_zero = [
        'POST /places/check-ins', 'POST /places/check-ins/{id}/photo',
        'POST /collections/{id}/items/{checkin_id}', 'POST /dms/requests (send)'
    ]
    optional_ok_or_zero += [
        'GET /places/{id}/whos-here',
        'GET /places/{id}/whos-here-count',
        'GET /users/{id}/media',
        'GET /users/{id}/collections',
        'GET /users/{id}/profile-stats',
    ]
    expected_403 = ['POST /users/me/avatar (unauth)']
    ok = True
    for k in expected_200:
        if results.get(k) != 200:
            ok = False
    for k in expected_403:
        if results.get(k) != 403:
            ok = False
    for k in optional_ok_or_zero:
        v = results.get(k)
        if v not in (0, 200):
            ok = False
    oa_expected = [
        'OA /settings/privacy', 'OA /settings/notifications', 'OA /follow endpoints',
        'OA /dms endpoints', 'OA /collections endpoints', 'OA /places endpoints', 'OA /support endpoints'
    ]
    for k in oa_expected:
        if results.get(k) != 1:
            ok = False
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
