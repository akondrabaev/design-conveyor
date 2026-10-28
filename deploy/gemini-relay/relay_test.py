"""Speed and reachability test of the Gemini relay, run on the server (Python 3.8+, standard library only).

    GEMINI_API_KEY=... GEMINI_BASE_URL=https://gemini-relay.<account>.workers.dev RELAY_SECRET=... \
        python3 relay_test.py [ref1.png ref2.png ...]

1. /__where       - where the worker runs (colo) and what IP it leaves from
2. text request    - small JSON round trip through the relay (latency)
3. image request   - the real workload: reference images up (several MB) + a 2K image down
Without GEMINI_BASE_URL it calls Google directly (to compare / to show the location block).
"""
import base64, json, os, sys, time, urllib.error, urllib.request

KEY = os.environ['GEMINI_API_KEY']
BASE = os.environ.get('GEMINI_BASE_URL', 'https://generativelanguage.googleapis.com').rstrip('/')
SECRET = os.environ.get('RELAY_SECRET', '')
TEXT_MODEL = os.environ.get('GEMINI_TEXT_MODEL', 'gemini-3.5-flash')
IMAGE_MODEL = os.environ.get('GEMINI_IMAGE_MODEL', 'gemini-3-pro-image')


def call(path, body=None, timeout=300):
    headers = {'x-goog-api-key': KEY, 'Content-Type': 'application/json'}
    if SECRET:
        headers['X-Relay-Secret'] = SECRET
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method='POST' if data else 'GET')
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read(), e.code
    return status, raw, time.time() - t, len(data or b'')


def mb(n):
    return f'{n / 2 ** 20:.2f} MB'


if 'GEMINI_BASE_URL' in os.environ:
    s, raw, dt, _ = call('/__where', timeout=30)
    print(f'[where] http {s}, {dt:.2f}s')
    print('   ' + raw.decode(errors='replace').replace('\n', '\n   ')[:600])

s, raw, dt, up = call(f'/v1beta/models/{TEXT_MODEL}:generateContent',
                      {'contents': [{'parts': [{'text': 'Reply with one word: ok'}]}]})
print(f'[text]  http {s}, {dt:.2f}s, answer {raw[:160].decode(errors="replace")!r}' if s != 200 else
      f'[text]  http 200, {dt:.2f}s')

refs = sys.argv[1:]
parts = [{'text': 'Photorealistic product photo of a silicone swim cap with exactly the print from the attached image, '
                  'lying on white tiles by a pool. Vertical 3:4.'}]
for p in refs:
    parts.append({'inline_data': {'mime_type': 'image/png' if p.endswith('.png') else 'image/jpeg',
                                  'data': base64.b64encode(open(p, 'rb').read()).decode()}})
body = {'contents': [{'parts': parts}],
        'generationConfig': {'responseModalities': ['IMAGE'], 'imageConfig': {'aspectRatio': '3:4', 'imageSize': '2K'}}}
s, raw, dt, up = call(f'/v1beta/models/{IMAGE_MODEL}:generateContent', body)
if s == 200:
    out = json.loads(raw)
    img = next((p['inlineData']['data'] for p in out['candidates'][0]['content']['parts'] if 'inlineData' in p), '')
    open('relay_test_out.png', 'wb').write(base64.b64decode(img))
    print(f'[image] http 200, {dt:.1f}s total, sent {mb(up)}, received {mb(len(raw))} (image {mb(len(img) * 3 / 4)}) -> relay_test_out.png')
else:
    print(f'[image] http {s}, {dt:.1f}s, sent {mb(up)}: {raw[:300].decode(errors="replace")}')
