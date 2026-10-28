"""Shared paths, env loading, config and a tiny background job runner."""
import io, json, os, sys, threading, time, traceback, uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, 'lib')
DESIGNS = os.path.join(ROOT, 'designs')
ON_MODEL = os.path.join(ROOT, 'on_model')
PERSONAS = os.path.join(ROOT, 'personas')
PACKS = os.path.join(ROOT, 'packs')
for d in (PERSONAS, PACKS, DESIGNS, ON_MODEL):
    os.makedirs(d, exist_ok=True)
sys.path.insert(0, LIB)
sys.path.insert(0, os.path.join(ROOT, 'tools'))


def load_env():
    """.env wins over .env.example; real environment wins over both. The key is never printed."""
    for name in ('.env', '.env.example'):
        p = os.path.join(ROOT, name)
        if not os.path.exists(p):
            continue
        for line in open(p, encoding='utf-8'):
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()
CONFIG = json.load(open(os.path.join(ROOT, 'app', 'config.json'), encoding='utf-8'))


def read_json(p, default=None):
    try:
        return json.load(open(p, encoding='utf-8'))
    except (OSError, ValueError):
        return default


def write_json(p, data):
    tmp = p + '.tmp'
    json.dump(data, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def file_url(path):
    """/files/<relative path>?v=<mtime> so the browser refetches regenerated images."""
    rel = os.path.relpath(path, ROOT).replace(os.sep, '/')
    v = int(os.path.getmtime(path)) if os.path.exists(path) else 0
    return f'/files/{rel}?v={v}'


# ---------- Gemini ----------
_client = None


def gemini():
    global _client
    if _client is None:
        from gemini_gen import make_client   # same relay / proxy settings as the design pipeline
        _client = make_client()
    return _client


IMAGE_MODEL = os.environ.get('GEMINI_IMAGE_MODEL', 'gemini-3-pro-image')
TEXT_MODELS = (os.environ.get('GEMINI_TEXT_MODEL', 'gemini-3.5-flash'), 'gemini-3-flash-preview', 'gemini-3.6-flash')


def gen_image(prompt, refs=(), aspect='3:4', tries=2, size=None):
    """refs: PIL images. Returns PIL RGB image."""
    from google.genai import types
    from PIL import Image
    err = 'no image in response'
    for _ in range(tries):
        try:
            r = gemini().models.generate_content(
                model=IMAGE_MODEL, contents=[prompt, *refs],
                config=types.GenerateContentConfig(response_modalities=['IMAGE'],
                                                   image_config=types.ImageConfig(aspect_ratio=aspect, **({'image_size': size} if size else {}))))
            for part in (r.candidates[0].content.parts or []):
                if part.inline_data is not None:
                    return Image.open(io.BytesIO(part.inline_data.data)).convert('RGB')
            err = f'no image in response (finish: {r.candidates[0].finish_reason})'
        except Exception as e:  # overloaded / safety / network: retry once
            err = str(e)[:300]
    raise RuntimeError(err)


def gen_json(prompt, temperature=0.8, images=()):
    from google.genai import types
    last = None
    for model in TEXT_MODELS:
        try:
            r = gemini().models.generate_content(
                model=model, contents=[prompt, *images] if images else prompt,
                config=types.GenerateContentConfig(response_mime_type='application/json', temperature=temperature))
            return json.loads(r.text)
        except Exception as e:
            last = e
    raise last


# ---------- jobs ----------
JOBS = {}


class Job:
    def __init__(self, kind, title):
        self.id = uuid.uuid4().hex[:10]
        self.kind, self.title = kind, title
        self.status, self.log, self.result = 'running', [], None
        self.started = time.time()
        JOBS[self.id] = self

    def say(self, msg):
        self.log.append(f'{time.strftime("%H:%M:%S")} {msg}')
        self.log = self.log[-400:]

    def dict(self):
        return dict(id=self.id, kind=self.kind, title=self.title, status=self.status,
                    log=self.log, result=self.result, started=self.started)


def run_job(kind, title, fn, *args):
    """fn(job, *args) runs in a thread; its return value becomes job.result."""
    job = Job(kind, title)

    def work():
        try:
            job.result = fn(job, *args)
            job.status = 'done'
        except Exception as e:
            job.say('ОШИБКА: ' + str(e)[:500])
            traceback.print_exc()
            job.status = 'error'
    threading.Thread(target=work, daemon=True).start()
    return job
