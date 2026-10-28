"""Print constructor: a new model from the stencils of an existing design - own cap shape and colours, no AI.

The "stencil" of a design is its ink index map (designs/<src>/_gemini/side-X_quantized.png: base + up to 3 inks).
It is fitted onto any cap template the same way the generator does it, so one drawing can be produced on another
shape and in any colourway. Saving builds the full set: SVG/PNG stencils, layout, mockup, spec.xlsx.

    python3 lib/compose.py '<json request>'      (used by the web app as a subprocess)
request: {"src": slug, "slug": new slug, "name": "...", "shape": "sym|long|kid_*", "sides": "A|mirror|AB",
          "base": "#hex", "inks": ["#hex", ...], "variants": [{"hex": "#hex", "inks": [...]}, ...]}
"""
import copy, json, os, shutil, sys
import numpy as np
from PIL import Image, ImageDraw

LIB = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, LIB)
OUT = os.path.join(os.path.dirname(LIB), 'designs')

import ral, shapes
from core import load_cap, load_body, MARGIN


def sources():
    """Designs whose stencils can be reused (screen-printed, with saved index maps)."""
    out = []
    for slug in sorted(os.listdir(OUT)):
        g = os.path.join(OUT, slug, '_gemini')
        p = os.path.join(g, 'spec.json')
        if not os.path.exists(p):
            continue
        spec = json.load(open(p, encoding='utf-8'))
        if spec.get('print') == 'full_colour':   # PU: the full-colour print stays, only cap colours change
            if os.path.exists(os.path.join(OUT, slug, 'PNG', f'{slug}_print.png')):
                out.append(dict(slug=slug, name=spec.get('name', slug), shape=spec['shape'], pu=True, side_b=None,
                                base=spec['base']['hex'], inks=[], variants=[dict(hex=v['hex'], inks=[]) for v in spec.get('variants', [])[:2]]))
            continue
        if not os.path.exists(os.path.join(g, 'side-A_quantized.png')):
            continue
        out.append(dict(slug=slug, name=spec.get('name', slug), shape=spec.get('shape') or _kind(spec),
                        side_b=spec.get('side_b') or ('own' if os.path.exists(os.path.join(g, 'side-B_quantized.png')) else None),
                        base=spec['base']['hex'], inks=[i['hex'] for i in spec['inks']],
                        variants=[dict(hex=v['hex'], inks=[i['hex'] if isinstance(i, dict) else i for i in v.get('inks', [])])
                                  for v in spec.get('variants', [])[:2]]))
    return out


def _kind(spec):
    from gemini_design import cap_kind
    return cap_kind(spec)


def index_map(src, side='A'):
    """Index map (0 = cap, 1..n = inks) from the saved quantized image of the source design."""
    g = os.path.join(OUT, src, '_gemini')
    spec = json.load(open(os.path.join(g, 'spec.json'), encoding='utf-8'))
    pal = np.array([[int(h.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)]
                    for h in [spec['base']['hex']] + [k['hex'] for k in spec['inks']]], dtype=np.int32)
    q = np.asarray(Image.open(os.path.join(g, f'side-{side}_quantized.png')).convert('RGB'), dtype=np.int32)
    idx = np.zeros(q.shape[:2], np.uint8)
    best = np.full(q.shape[:2], np.iinfo(np.int32).max, np.int32)
    for n, c in enumerate(pal):
        d = ((q - c) ** 2).sum(-1)
        idx[d < best] = n
        np.minimum(best, d, out=best)
    return idx


# ---------- fast preview (raster, no tracing) ----------
_MASKS = {}


def _masks(kind, scale):
    key = (kind, scale)
    if key not in _MASKS:
        _, outline, W, H = load_cap(kind)
        safe = outline.buffer(-shapes.KIDS_MARGIN) if kind in shapes.KIDS else load_body(kind).buffer(-MARGIN)
        size = (round(W * scale), round(H * scale))
        ms = []
        for g in (outline, safe):
            m = Image.new('L', size, 0)
            d = ImageDraw.Draw(m)
            for p in getattr(g, 'geoms', [g]):
                d.polygon([(x * scale, y * scale) for x, y in p.exterior.coords], fill=255)
                for r in p.interiors:
                    d.polygon([(x * scale, y * scale) for x, y in r.coords], fill=0)
            ms.append(np.asarray(m) > 127)
        _MASKS[key] = (ms[0], ms[1], W, H)
    return _MASKS[key]


def _fit(idx, w, h):
    s = max(w / idx.shape[1], h / idx.shape[0])
    im = Image.fromarray(idx).resize((int(np.ceil(idx.shape[1] * s)), int(np.ceil(idx.shape[0] * s))), Image.NEAREST)
    x0, y0 = (im.width - w) // 2, (im.height - h) // 2
    return np.asarray(im.crop((x0, y0, x0 + w, y0 + h)))


def _rgb(h):
    h = h.lstrip('#')
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


_ART = {}


UPLOADS = os.path.join(os.path.dirname(LIB), 'uploads', 'refs')
LOGOS = os.path.join(os.path.dirname(LIB), 'uploads', 'logos')


def resolve_logo(logo):
    """Styled logos travel as an id of uploads/logos/; the drawing code needs the file path."""
    if logo and logo.get('kind') == 'styled':
        p = os.path.join(LOGOS, os.path.basename(str(logo.get('id', ''))))
        return dict(logo, path=p) if os.path.isfile(p) else None
    return logo


STYLED_PROMPT = """The attached image is a full-colour print for a swim cap. Draw ONLY the word BRAND (exactly the letters B-R-A-N-D)
as a cartoon logo lettering in the SAME style as this artwork - the same colours, outline thickness, shading and mood - so it looks
like a part of it. Pure plain white background (#FFFFFF), no character, no other elements, no shadow on the background, no frame.
Letters with a clean outline, bold and readable, centred with generous margins, wide landscape composition."""


def styled_logo(src):
    """Generate BRAND lettering in the style of the print of `src` (Gemini), cut from white; returns the new logo id."""
    import io, uuid
    import gemini_gen as gg
    from google.genai import types
    art, _ = _pu_art(src)
    ref = Image.new('RGB', art.size, 'white')
    ref.paste(art, mask=art.split()[3])
    r = gg.client().models.generate_content(
        model=gg.IMAGE_MODEL, contents=[STYLED_PROMPT, ref],
        config=types.GenerateContentConfig(response_modalities=['IMAGE'], image_config=types.ImageConfig(aspect_ratio='16:9')))
    part = next(p for p in r.candidates[0].content.parts if p.inline_data is not None)
    logo = _gp().cut_background(Image.open(io.BytesIO(part.inline_data.data)).convert('RGB'))
    os.makedirs(LOGOS, exist_ok=True)
    lid = uuid.uuid4().hex[:12] + '.png'
    logo.save(os.path.join(LOGOS, lid))
    return lid
_GP = []


def _gp():
    """tools/generate_pu.py as a module (cut-out helpers)."""
    if not _GP:
        import importlib.util
        sp = importlib.util.spec_from_file_location('generate_pu', os.path.join(os.path.dirname(LIB), 'tools', 'generate_pu.py'))
        gp = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(gp)
        _GP.append(gp)
    return _GP[0]


def upload_path(src):
    """'upload:<id>' -> the uploaded file (ids from /api/refs only)."""
    name = os.path.basename(src.split(':', 1)[1])
    p = os.path.join(UPLOADS, name)
    if not name or not os.path.isfile(p):
        raise FileNotFoundError('загруженный принт не найден, загрузите его снова')
    return p


def _pu_art(src):
    """The print before placement: an uploaded image as is, or the generated character / all-over elements."""
    if src not in _ART:
        if src.startswith('upload:'):
            _ART[src] = (_gp().upload_art(Image.open(upload_path(src))), 'placement')
        else:
            spec = json.load(open(os.path.join(OUT, src, '_gemini', 'spec.json'), encoding='utf-8'))
            raw = Image.open(os.path.join(OUT, src, '_gemini', 'raw.png')).convert('RGB')
            _ART[src] = (_gp().make_art(raw, spec), spec.get('pu_layout', 'placement'))
    return _ART[src]


def pu_preview(src, shape, base, width=520, place=None, logo=None):
    """PU cap: outline in the cap colour + the source's print placed by lib/pu.py (with the constructor's move / scale)."""
    import pu
    outline, _, W, H = _masks(shape, width / 1000)
    h, w = outline.shape
    art, layout = _pu_art(src)
    img = Image.fromarray(np.where(outline[..., None], np.array(_rgb(base), np.uint8), 255).astype(np.uint8))
    fr = pu.frame(art, shape, layout, place, w, resolve_logo(logo))
    img.paste(fr.resize((w, h)), (0, 0), fr.resize((w, h)))
    plain = Image.fromarray(np.where(outline[:, ::-1][..., None], np.array(_rgb(base), np.uint8), 255).astype(np.uint8))
    return {'A': img, 'B': plain}


def preview_ways(src, shape, ways, sides='mirror', width=420, place=None, logo=None):
    """All colourways: [{cap, inks}] -> [{'A': img, 'B': img}], same stencils, each in its own colours."""
    pu = shape in shapes.PU
    return [pu_preview(src, shape, w['cap'], width, place, logo) if pu else preview(src, shape, w['cap'], w['inks'], sides, width)
            for w in ways]


def preview(src, shape, base, inks, sides='mirror', width=520):
    """PNG images (side A, side B) of the source stencils on `shape` in the given colours."""
    outline, safe, W, H = _masks(shape, width / 1000)
    h, w = outline.shape
    pal = np.array([_rgb(base)] + [_rgb(c) for c in inks], np.uint8)
    def paint(idx):
        idx = _fit(idx, w, h).copy()
        idx[idx >= len(pal)] = 0
        idx[~safe] = 0
        return np.where(outline[..., None], pal[idx], 255).astype(np.uint8)
    a = paint(index_map(src, 'A'))
    if sides == 'A':
        b = np.where(outline[..., None], pal[0], 255).astype(np.uint8)
    elif sides == 'AB':
        b = paint(index_map(src, 'B'))
    else:
        b = a
    if sides == 'mirror' or shape in shapes.MIRROR_B:   # side B on the head = the mirrored view
        b = b[:, ::-1]
    return {'A': Image.fromarray(a), 'B': Image.fromarray(np.ascontiguousarray(b))}


# ---------- save: full design ----------

def save_pu(req, spec, slug, src, g):
    """PU: same print (raw image copied), new cap colours / PU size; rebuilt by tools/generate_pu.py --rebuild."""
    import subprocess
    capr = ral.nearest(req['base'])
    spec.update(slug=slug, shape=req['shape'], source=src)
    spec['name'] = req.get('name') or f"{spec['name']} · {capr['code']}"
    spec['base'] = dict(hex=capr['hex'], name=capr['name_en'], ral=capr['code'])
    spec['variants'] = [dict(hex=ral.nearest(v['hex'])['hex'], name=ral.nearest(v['hex'])['name_en'], ral=ral.nearest(v['hex'])['code'])
                        for v in req.get('variants', [])[:2]]
    spec['segment'] = 'Детская' if req['shape'] == 'pu_kids' else spec.get('segment', 'Унисекс')
    if req.get('place'):   # the constructor's move / scale of the print
        spec['pu_place'] = {k: float(req['place'].get(k, d)) for k, d in (('x', 0), ('y', 0), ('s', 1))}
    if _logo(req, g):
        spec['pu_logo'] = _logo(req, g)
    tr = spec.get('i18n') or {}
    for lang in ('en', 'zh'):
        if lang in tr:
            tr[lang]['name'] = f"{tr[lang]['name']} · {capr['code']}"
    json.dump(spec, open(os.path.join(g, 'spec.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    subprocess.run([sys.executable, os.path.join(os.path.dirname(LIB), 'tools', 'generate_pu.py'), '--shape', req['shape'],
                    '--slug', slug, '--rebuild'], check=True, stdout=subprocess.DEVNULL)
    return dict(slug=slug)


def _logo(req, g=None):
    lg = req.get('logo') or {}
    if lg.get('kind') == 'styled':   # copy the generated lettering into the design
        r = resolve_logo(lg)
        if not r or not g:
            return None
        shutil.copy(r['path'], os.path.join(g, 'logo_pu.png'))
        return dict(kind='styled', file='logo_pu.png', **{k: float(lg.get(k, d)) for k, d in (('x', 0.25), ('y', 0.8), ('s', 0.2))})
    if lg.get('kind') not in ('adult', 'kids'):
        return None
    return dict(kind=lg['kind'], hex=ral.nearest(lg.get('hex', '#FFFFFF'))['hex'],
                **{k: float(lg.get(k, d)) for k, d in (('x', 0.25), ('y', 0.8), ('s', 0.2))})


def save_upload(req):
    """PU model from the user's own print: the image as is (no AI) + optional BRAND logo layer."""
    import subprocess
    slug = req['slug']
    g = os.path.join(OUT, slug, '_gemini')
    os.makedirs(g)
    Image.open(upload_path(req['src'])).convert('RGBA').save(os.path.join(g, 'raw.png'))
    capr = ral.nearest(req['base'])
    spec = dict(slug=slug, name=req.get('name') or 'Свой принт PU', concept='', image_prompt='', shape=req['shape'],
                print='full_colour', upload=True, pu_layout='placement', segment='Детская' if req['shape'] == 'pu_kids' else 'Унисекс',
                base=dict(hex=capr['hex'], name=capr['name_en'], ral=capr['code']),
                variants=[dict(hex=ral.nearest(v['hex'])['hex'], name=ral.nearest(v['hex'])['name_en'], ral=ral.nearest(v['hex'])['code'])
                          for v in req.get('variants', [])[:2]], inks=[])
    if req.get('place'):
        spec['pu_place'] = {k: float(req['place'].get(k, d)) for k, d in (('x', 0), ('y', 0), ('s', 1))}
    spec['pu_logo'] = _logo(req, g)
    spec['logo'] = 'overlay' if spec['pu_logo'] else 'none'
    json.dump(spec, open(os.path.join(g, 'spec.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    subprocess.run([sys.executable, os.path.join(os.path.dirname(LIB), 'tools', 'generate_pu.py'), '--shape', req['shape'],
                    '--slug', slug, '--rebuild'], check=True, stdout=subprocess.DEVNULL)
    return dict(slug=slug)


def save(req):
    src, slug = req['src'], req['slug']
    if os.path.exists(os.path.join(OUT, slug)):
        raise SystemExit(f'design {slug} already exists')
    if src.startswith('upload:'):
        return save_upload(req)
    sg = os.path.join(OUT, src, '_gemini')
    od = os.path.join(OUT, slug)
    if os.path.exists(od):
        raise SystemExit(f'design {slug} already exists')
    g = os.path.join(od, '_gemini')
    os.makedirs(g)
    for f in os.listdir(sg):   # stencil sources (index maps, original image, styled logo) travel with the new model
        if f.endswith(('.png', '.txt', '.json')) and f != 'spec.json':
            shutil.copy(os.path.join(sg, f), os.path.join(g, f))
    spec = copy.deepcopy(json.load(open(os.path.join(sg, 'spec.json'), encoding='utf-8')))
    if spec.get('print') == 'full_colour':
        return save_pu(req, spec, slug, src, g)
    n = len(spec['inks'])
    inks = list(req['inks'])[:n]
    capr = ral.nearest(req['base'])
    spec.update(slug=slug, shape=req['shape'], source=src, palette='RAL Classic')
    spec['name'] = req.get('name') or f"{spec['name']} · {capr['code']}"
    spec['base'] = dict(hex=capr['hex'], name=capr['name_en'], ral=capr['code'])
    for k, h in zip(spec['inks'], inks):
        r = ral.nearest(h)
        k.update(hex=r['hex'], ral=r['code'], name=r['name_en'])
    spec['variants'] = []
    for v in req.get('variants', [])[:2]:
        r = ral.nearest(v['hex'])
        spec['variants'].append(dict(hex=r['hex'], name=r['name_en'], ral=r['code'],
                                     inks=[dict(hex=ral.nearest(c)['hex']) for c in v.get('inks', [])[:n]]))
    spec.pop('side_b', None)
    sides = req.get('sides', 'mirror')
    if sides == 'mirror':
        spec['side_b'] = 'mirror'
    if shapes.SHAPES.get(req['shape'], {}).get('kids'):
        spec['segment'] = 'Детская'
        spec.setdefault('logo', 'small')
    elif spec.get('logo') in ('small', 'styled', 'none'):
        spec.pop('logo')
    tr = spec.get('i18n') or {}
    if tr.get('en'):   # no AI: the source's translated name + the colourway code
        for lang in ('en', 'zh'):
            if lang in tr:
                tr[lang]['name'] = f"{tr[lang]['name']} · {capr['code']}"
        spec['i18n'] = tr
    json.dump(spec, open(os.path.join(g, 'spec.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    import gemini_design as gd, build as B, finalize as F
    idx = {'A': index_map(src, 'A')}   # decoded with the SOURCE palette (the quantized images are in its colours)
    if sides == 'AB' and os.path.exists(os.path.join(sg, 'side-B_quantized.png')):
        idx['B'] = index_map(src, 'B')
    D = gd.make_design(spec, idx)
    checks = B.build(D)
    F.write_spec(D)
    return dict(slug=slug, checks=checks)


if __name__ == '__main__':
    print(json.dumps(save(json.loads(sys.argv[1])), ensure_ascii=False, default=str))
