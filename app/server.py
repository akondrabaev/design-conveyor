"""BRAND design pipeline MVP: local web UI over both pipelines.

Run:  start.bat   (or: .venv\\Scripts\\python -X utf8 -m uvicorn server:app --app-dir app --port 8765)
Open: http://localhost:8765
"""
import io, os, time
from fastapi import FastAPI, HTTPException, UploadFile, File, Body
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from common import ROOT, CONFIG, JOBS, DESIGNS, ON_MODEL, PERSONAS, PACKS, run_job, file_url
import catalog, content

app = FastAPI(title='Design Conveyor')
STATIC = os.path.join(ROOT, 'app', 'static')


@app.get('/')
def index():
    """Static links get ?v=<mtime>, so the browser never runs an old app.js / style.css after an update."""
    html = open(os.path.join(STATIC, 'index.html'), encoding='utf-8').read()
    for f in ('app.js', 'style.css'):
        html = html.replace(f'/static/{f}"', f'/static/{f}?v={int(os.path.getmtime(os.path.join(STATIC, f)))}"')
    return HTMLResponse(html, headers={'Cache-Control': 'no-store'})


@app.get('/api/config')
def config():
    from presets import PRESETS
    import shapes
    import brand
    return dict(CONFIG, presets=list(PRESETS), brand=brand.NAME, key_set=bool(os.environ.get('GEMINI_API_KEY')),
                shapes=[dict(id=k, label=v['ru'], panel=shapes.panel(k), pu=bool(v.get('pu'))) for k, v in shapes.SHAPES.items()])


# ---------- jobs ----------
@app.get('/api/jobs')
def jobs():
    return sorted((j.dict() for j in JOBS.values()), key=lambda j: -j['started'])[:30]


@app.get('/api/jobs/{jid}')
def job(jid: str):
    if jid not in JOBS:
        raise HTTPException(404, 'нет такой задачи (сервер перезапускался?)')
    return JOBS[jid].dict()


# ---------- pipeline 1: designs ----------
@app.get('/api/designs')
def designs():
    return catalog.list_designs()


@app.post('/api/designs/generate')
def design_generate(body: dict = Body(...)):
    theme = (body.get('theme') or '').strip()
    if not theme:
        raise HTTPException(400, 'нужна тема')
    refs = [os.path.join(REFS, os.path.basename(r)) for r in body.get('refs', [])]   # ids from /api/refs only
    j = run_job('design', f'Новинка: {theme[:60]}', catalog.generate_design, theme,
                body.get('preset', 'free'), body.get('slug', ''), body.get('sides', 'A'), body.get('shape', ''), body.get('logo', ''), refs, body.get('pu_layout', 'placement'))
    return j.dict()


REFS = os.path.join(ROOT, 'uploads', 'refs')


@app.post('/api/refs')
async def upload_ref(file: UploadFile = File(...)):
    """A reference image for a new design; returns its id for /api/designs/generate."""
    import uuid
    os.makedirs(REFS, exist_ok=True)
    try:
        im = Image.open(io.BytesIO(await file.read()))
        im.load()
    except Exception:
        raise HTTPException(400, 'это не картинка')
    im.thumbnail((2048, 2048))
    rid = uuid.uuid4().hex[:12] + '.png'
    (im.convert('RGBA') if im.mode in ('RGBA', 'LA', 'P') else im.convert('RGB')).save(os.path.join(REFS, rid))
    return dict(id=rid)


@app.get('/api/designs/{slug}/usage')
def design_usage(slug: str):
    return dict(packs=len(content.packs_using(slug)),
                running=any(j.status == 'running' and slug in (j.title + ' '.join(j.log)) for j in JOBS.values()))


@app.delete('/api/designs/{slug}')
def design_delete(slug: str):
    if not catalog.design_info(slug) and not os.path.isdir(os.path.join(DESIGNS, slug)):
        raise HTTPException(404, 'нет такого дизайна')
    if design_usage(slug)['running']:
        raise HTTPException(409, 'по этому дизайну сейчас идёт задача, дождитесь окончания')
    try:
        catalog.delete_design(slug)
    except FileNotFoundError:
        raise HTTPException(404, 'нет такого дизайна')
    return dict(ok=True)


@app.post('/api/designs/{slug}/mirror')
def design_mirror(slug: str):
    if not catalog.design_info(slug):
        raise HTTPException(404)
    return run_job('design', f'Симметричная B: {slug}', catalog.mirror_design, slug).dict()


@app.get('/api/designs/{slug}/guides')
def design_guides(slug: str):
    """Placement preview of the design for every pose (cached renders)."""
    if not catalog.design_info(slug):
        raise HTTPException(404)
    return {p['id']: file_url(content.guide_image(slug, p['id'], 600)) for p in CONFIG['poses']}


# ---------- personas and pose sheets ----------
@app.get('/api/personas')
def personas():
    return content.list_personas()


def _persona_or_404(pid):
    try:
        return content.persona(pid)
    except RuntimeError:
        raise HTTPException(404, 'нет такой модели')


@app.post('/api/personas')
def persona_create(body: dict = Body(...)):
    if body.get('group') not in content.BY_ID['groups']:
        raise HTTPException(400, 'неизвестная группа')
    if not (body.get('look') or '').strip():
        raise HTTPException(400, 'опишите внешность')
    return content.create_persona(body['group'], body.get('name', ''), body['look'], body.get('wear', ''))


@app.put('/api/personas/{pid}')
def persona_update(pid: str, body: dict = Body(...)):
    _persona_or_404(pid)
    return content.update_persona(pid, body)


@app.delete('/api/personas/{pid}')
def persona_delete(pid: str):
    _persona_or_404(pid)
    content.delete_persona(pid)
    return dict(ok=True)


@app.post('/api/personas/{pid}/generate')
def persona_generate(pid: str):
    p = _persona_or_404(pid)
    return run_job('persona', f'Эталон: {p["label"]} ({p["name"]})', content.generate_persona, pid).dict()


@app.post('/api/personas/{pid}/upload')
async def persona_upload(pid: str, file: UploadFile = File(...)):
    _persona_or_404(pid)
    content.save_persona(pid, Image.open(io.BytesIO(await file.read())))
    return dict(ok=True)


@app.get('/api/poses')
def poses():
    return content.list_pose_sheets()


@app.post('/api/poses/{group}/generate')
def pose_generate(group: str):
    if group not in content.BY_ID['groups']:
        raise HTTPException(404)
    return run_job('poses', f'Ракурсы: {content.BY_ID["groups"][group]["label"]}', content.generate_pose_sheet, group).dict()


@app.post('/api/poses/{group}/{pose_id}/flip')
def pose_flip(group: str, pose_id: str):
    if group not in content.BY_ID['groups'] or pose_id not in content.BY_ID['poses']:
        raise HTTPException(404)
    content.flip_pose(group, pose_id)
    return dict(ok=True)


# ---------- pipeline 2: packs ----------
@app.get('/api/packs')
def packs():
    return content.list_packs()


@app.post('/api/packs')
def pack_create(body: dict = Body(...)):
    if not body.get('shots'):
        raise HTTPException(400, 'нет кадров')
    for s in body['shots']:
        if s.get('kind', 'model') != 'model':
            continue
        p = _persona_or_404(s['persona'])
        if not content.persona_ref_path(s['persona']):
            raise HTTPException(400, f'нет эталона модели «{p["label"]}»')
        if content.is_head_pose(s['pose']) and not os.path.exists(content.pose_path(p['group'], s['pose'])):
            raise HTTPException(400, f'нет листа ракурсов «{content.BY_ID["groups"][p["group"]]["label"]}»')
    pack = content.create_pack(body)
    j = run_job('pack', f'Фото: {pack["design"]}', content.run_pack, pack['id'])
    return dict(id=pack['id'], job=j.id)


@app.get('/api/packs/{pid}')
def pack_get(pid: str):
    p = content.load_pack(pid)
    if not p:
        raise HTTPException(404)
    return content.pack_view(p)


@app.delete('/api/packs/{pid}')
def pack_delete(pid: str):
    if not content.load_pack(pid):
        raise HTTPException(404)
    try:
        content.delete_pack(pid)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return dict(ok=True)


@app.delete('/api/packs/{pid}/shots/{n}')
def shot_delete(pid: str, n: int):
    p = content.load_pack(pid)
    if not p or not (0 <= n < len(p['shots'])):
        raise HTTPException(404)
    try:
        return content.pack_view(content.delete_shot(pid, n))
    except RuntimeError as e:
        raise HTTPException(409, str(e))


@app.get('/api/storage')
def storage():
    return content.storage()


@app.post('/api/packs/{pid}/shots/{n}/regen')
def shot_regen(pid: str, n: int, body: dict = Body(default={})):
    p = content.load_pack(pid)
    if not p or not (0 <= n < len(p['shots'])):
        raise HTTPException(404)
    return run_job('shot', f'Кадр {n + 1}: {p["design"]}', content.regen_shot, pid, n, body.get('note')).dict()


# ---------- export: Excel with mockups of the selected designs ----------
@app.post('/api/export/mockups')
def export_mockups(body: dict = Body(...)):
    from fastapi.responses import Response
    from urllib.parse import quote
    import export_xlsx
    slugs = [s for s in body.get('slugs', []) if catalog.design_info(s)]
    if not slugs:
        raise HTTPException(400, 'ничего не выбрано')
    data, name = export_xlsx.build(slugs, catalog.design_info, catalog.cap_image, catalog.colorways)
    return Response(data, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': f"attachment; filename*=UTF-8''{quote(name)}"})


EXPORTS = os.path.join(ROOT, 'uploads', 'exports')


@app.post('/api/export/package')
def export_package(body: dict = Body(...)):
    """Files for "save as": Excel in the root + a folder per model. Returns the manifest with download URLs."""
    import export_xlsx, uuid, shutil
    slugs = [s for s in body.get('slugs', []) if catalog.design_info(s)]
    if not slugs:
        raise HTTPException(400, 'ничего не выбрано')
    if os.path.isdir(EXPORTS):   # keep only the latest few packages
        for old in sorted(os.listdir(EXPORTS))[:-3]:
            shutil.rmtree(os.path.join(EXPORTS, old), ignore_errors=True)
    pid = time.strftime('%Y%m%d_%H%M%S_') + uuid.uuid4().hex[:6]
    files = export_xlsx.package(slugs, catalog.design_info, catalog.cap_image, catalog.colorways, os.path.join(EXPORTS, pid))
    return dict(id=pid, files=[dict(path=f['path'], url=f"/api/export/file?p={quote_path(f['file'])}") for f in files])


def quote_path(p):
    from urllib.parse import quote
    return quote(os.path.relpath(p, ROOT).replace(os.sep, '/'))


@app.get('/api/export/file')
def export_file(p: str):
    full = os.path.realpath(os.path.join(ROOT, p))
    allowed = [os.path.realpath(d) + os.sep for d in (DESIGNS, EXPORTS)]
    if not any(full.startswith(a) for a in allowed) or not os.path.isfile(full):   # only design files and export packages
        raise HTTPException(404)
    return FileResponse(full)


@app.post('/api/export/zip')
def export_zip(body: dict = Body(...)):
    """Same package as one ZIP (browsers without a folder picker)."""
    import zipfile
    from fastapi.responses import Response
    from urllib.parse import quote
    pkg = export_package(body)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_STORED) as z:
        for f in pkg['files']:
            z.write(os.path.join(ROOT, __import__('urllib.parse').parse.unquote(f['url'].split('p=', 1)[1])), f['path'])
    name = f"{__import__('brand').NAME}_export_{time.strftime('%Y-%m-%d')}.zip"
    return Response(buf.getvalue(), media_type='application/zip', headers={'Content-Disposition': f"attachment; filename*=UTF-8''{quote(name)}"})


# ---------- constructor: new models from existing stencils ----------
@app.get('/api/constructor/sources')
def constructor_sources():
    import compose
    return compose.sources()


@app.get('/api/ral')
def ral_table():
    import ral
    return [dict(code=r['code'], en=r['name_en'], zh=r['name_zh'], hex=r['hex']) for r in ral.table()]


@app.post('/api/constructor/preview')
def constructor_preview(body: dict = Body(...)):
    import base64, compose, colorways
    ways = body.get('ways') or [dict(cap=body['base'], inks=body.get('inks', []))]
    try:
        sets = compose.preview_ways(body['src'], body['shape'], ways, body.get('sides', 'mirror'), place=body.get('place'), logo=body.get('logo'))
    except Exception as e:
        raise HTTPException(400, str(e)[:300])

    def url(im):
        buf = io.BytesIO()
        im.save(buf, 'PNG')
        return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()
    return {'ways': [dict(A=url(s['A']), B=url(s['B']), contrast=colorways.contrast_report(w['cap'], w['inks']) if w['inks'] else [])
                     for s, w in zip(sets, ways)]}


@app.post('/api/constructor/styled_logo')
def constructor_styled_logo(body: dict = Body(...)):
    """BRAND lettering in the style of the selected PU print (Gemini); only the lettering is generated, the print is untouched."""
    import compose
    try:
        lid = compose.styled_logo(body['src'])
    except Exception as e:
        raise HTTPException(502, f'Gemini: {str(e)[:300]}')
    return dict(id=lid, url=f'/api/logos/{lid}')


@app.get('/api/logos/{lid}')
def logo_file(lid: str):
    import compose
    p = os.path.join(compose.LOGOS, os.path.basename(lid))
    if not os.path.isfile(p):
        raise HTTPException(404)
    return FileResponse(p)


@app.post('/api/colorways/fix')
def colorways_fix(body: dict = Body(...)):
    import colorways
    return colorways.fix_inks(body['cap'], body['inks'], prefer=tuple(body.get('prefer', [])))


@app.post('/api/constructor/save')
def constructor_save(body: dict = Body(...)):
    for k in ('src', 'shape', 'base'):
        if not body.get(k):
            raise HTTPException(400, f'нет поля {k}')
    return run_job('design', f"Конструктор: {body.get('name') or body['src']}", catalog.compose_design, body).dict()


# only output folders are served: the project root holds .env / .env.example with the API key
for _d in (DESIGNS, ON_MODEL, PERSONAS, PACKS, content.POSES_DIR):
    app.mount(f'/files/{os.path.basename(_d)}', StaticFiles(directory=_d), name=os.path.basename(_d))
app.mount('/static', StaticFiles(directory=STATIC), name='static')
app.mount('/assets', StaticFiles(directory=os.path.join(ROOT, 'app', 'assets')), name='assets')
