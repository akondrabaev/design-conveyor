"""Pipeline 1 (new designs): list designs, launch generation, render a clean cap image for cards."""
import base64, glob, os, re, subprocess, sys, threading, time
from common import ROOT, DESIGNS, ON_MODEL, read_json, file_url

def cap_kind(spec):
    from gemini_design import cap_kind as _k   # one rule for the whole pipeline: spec['shape'] or by segment
    return _k(spec)
SIDES = ('A', 'B')
RENDER_LOCK = threading.RLock()  # shots render in parallel threads and share these caches


def design_file(slug, name):
    """Production files live in PNG/ and SVG/ (older designs: in the design root)."""
    d = os.path.join(DESIGNS, slug)
    sub = 'SVG' if name.endswith('.svg') else 'PNG'
    p = os.path.join(d, sub, f'{slug}_{name}')
    return p if os.path.exists(p) else os.path.join(d, f'{slug}_{name}')


def _with_ral(c):
    import ral   # lib/ral.py: nearest RAL Classic by CIEDE2000
    r = ral.nearest(c['hex'])
    return dict(c, ral=r['code'], ral_name=r['name_en'], ral_hex=r['hex'], de=r['de'])


def design_info(slug):
    d = os.path.join(DESIGNS, slug)
    spec = read_json(os.path.join(d, '_gemini', 'spec.json'))
    if not spec:
        return None
    sides = [s for s in SIDES if os.path.exists(design_file(slug, f'side-{s}_print_transparent.png'))]
    files = sorted(os.path.relpath(p, d).replace(os.sep, '/') for p in
                   glob.glob(f'{d}/{slug}_*') + glob.glob(f'{d}/SVG/*') + glob.glob(f'{d}/PNG/*'))
    layout = design_file(slug, 'side-A_layout.png')
    xlsx = f'{d}/{slug}_spec.xlsx'
    om = os.path.join(ON_MODEL, f'{slug}_on_model.jpg')
    hero = os.path.join(d, '_hero.png')
    return dict(
        slug=slug, name=spec.get('name', slug), concept=spec.get('concept', ''), segment=spec.get('segment', ''),
        base=_with_ral(spec['base']), inks=[_with_ral(i) for i in spec.get('inks', [])],
        variants=[_with_ral(v) for v in spec.get('variants', [])], spec_xlsx=file_url(xlsx) if os.path.exists(xlsx) else None,
        image_prompt=spec.get('image_prompt', ''), sides=sides, shape=cap_kind(spec), print=spec.get('print', 'screen'),
        type=_type(spec), side_b=spec.get('side_b', 'own' if 'B' in sides else None),
        checks=read_json(os.path.join(d, '_checks.json'), {}),
        mockup=file_url(f'{d}/{slug}_mockup.png') if os.path.exists(f'{d}/{slug}_mockup.png') else None,
        layout=file_url(layout) if os.path.exists(layout) else None,
        hero=file_url(hero) if os.path.exists(hero) else None,
        on_model=file_url(om) if os.path.exists(om) else None,
        refs=[file_url(p) for p in sorted(glob.glob(f'{d}/_gemini/refs/*'))],
        files=[dict(name=f, url=file_url(os.path.join(d, f))) for f in files],
        mtime=os.path.getmtime(d),
    )


def _type(spec):
    import export_xlsx
    return export_xlsx.cap_type(spec)


def list_designs():
    out = []
    for slug in os.listdir(DESIGNS):
        if os.path.isdir(os.path.join(DESIGNS, slug)):
            info = design_info(slug)
            if info:
                out.append(info)
    return sorted(out, key=lambda x: -x['mtime'])


def colorways(slug):
    """Every colourway of a design: [{'cap': hex, 'inks': [hex...]}]; 0 = main. Inks of variants as in the spec
    (or computed for contrast, lib/colorways.py). PU caps: full-colour print, only the cap colour changes."""
    import colorways as cw, copy
    spec = read_json(os.path.join(DESIGNS, slug, '_gemini', 'spec.json'))
    pu = spec.get('print') == 'full_colour'
    if not pu:
        spec = cw.ensure(copy.deepcopy(spec))
    main = [i['hex'] for i in spec['inks']] if not pu else []
    out = [dict(cap=spec['base']['hex'], inks=main)]
    for v in spec.get('variants', [])[:2]:
        out.append(dict(cap=v['hex'], inks=[i['hex'] for i in v.get('inks', [])] if not pu else []))
    return out


def _recolor(png, src_inks, dst_inks):
    """Flat print with the main ink colours -> the same print in another colourway (nearest main ink per pixel, alpha kept)."""
    import numpy as np
    from PIL import Image
    a = np.asarray(Image.open(png).convert('RGBA')).copy()
    rgb = a[..., :3].astype(np.int32)
    pal = np.array([[int(h.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)] for h in src_inks], np.int32)
    best = np.full(rgb.shape[:2], np.iinfo(np.int32).max, np.int32)
    idx = np.zeros(rgb.shape[:2], np.uint8)
    for n, c in enumerate(pal):
        d = ((rgb - c) ** 2).sum(-1)
        idx[d < best] = n
        np.minimum(best, d, out=best)
    new = np.array([[int(h.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)] for h in dst_inks], np.uint8)
    a[..., :3] = np.where(a[..., 3:4] > 0, new[idx], a[..., :3])
    return Image.fromarray(a)


def cap_image(slug, side='A', scale=1.6, sheen=True, way=0):
    """Clean cap render (silhouette in the cap colour + print + sheen), transparent background, for colourway `way`.
    Built from the engine's print_transparent.png, so it works for every existing design. Cached."""
    with RENDER_LOCK:
        return _cap_image(slug, side, scale, sheen, way)


def _cap_image(slug, side, scale, sheen, way=0):
    from PIL import Image
    import core, io
    d = os.path.join(DESIGNS, slug)
    tag = '' if not way else f'_w{way}'
    out = (f'{d}/_cap_{side}{tag}.png' if sheen else f'{d}/_flat_{side}{tag}.png')
    src = design_file(slug, f'side-{side}_print_transparent.png')
    spec_p = f'{d}/_gemini/spec.json'
    if os.path.exists(out) and os.path.getmtime(out) >= max(os.path.getmtime(src), os.path.getmtime(spec_p)):
        return Image.open(out)
    spec = read_json(spec_p)
    ways = colorways(slug)
    cw = ways[min(way, len(ways) - 1)]
    cap_hex = cw['cap']
    kind = cap_kind(spec)
    cap_d, _, W, H = core.load_cap(kind)
    if side == 'B':  # side B uses the mirrored template
        cap_d = f'<g transform="translate({W:.1f},0) scale(-1,1)"><path d="{cap_d}" fill="{{fill}}"/></g>'
    else:
        cap_d = f'<path d="{cap_d}" fill="{{fill}}"/>'
    if way and cw['inks'] and cw['inks'] != ways[0]['inks']:   # screen print in another colourway: recolour the inks
        buf = io.BytesIO()
        _recolor(src, ways[0]['inks'], cw['inks']).save(buf, 'PNG')
        png64 = base64.b64encode(buf.getvalue()).decode()
    else:
        png64 = base64.b64encode(open(src, 'rb').read()).decode()
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{W:.0f}" height="{H:.0f}">'
           '<defs><radialGradient id="sh" cx="0.35" cy="0.18" r="0.75"><stop offset="0" stop-color="#fff" stop-opacity="0.22"/>'
           '<stop offset="0.55" stop-color="#fff" stop-opacity="0.04"/><stop offset="1" stop-color="#000" stop-opacity="0.18"/></radialGradient></defs>'
           + cap_d.replace('{fill}', cap_hex)
           + f'<image x="0" y="0" width="{W:.0f}" height="{H:.0f}" xlink:href="data:image/png;base64,{png64}"/>'
           + (cap_d.replace('{fill}', 'url(#sh)') if sheen else '') + '</svg>')
    tmp = out + '.tmp.png'
    core.render(svg, tmp, scale=scale)
    os.replace(tmp, out)
    return Image.open(out)


def is_long(slug):
    spec = read_json(os.path.join(DESIGNS, slug, '_gemini', 'spec.json')) or {}
    return cap_kind(spec) == 'long'


def shape_of(slug):
    return cap_kind(read_json(os.path.join(DESIGNS, slug, '_gemini', 'spec.json')) or {})


def slugify(s):
    s = re.sub(r'[^a-z0-9]+', '_', s.lower()).strip('_')
    return s[:40]


def _run_tool(job, args):
    # one BLAS thread: numpy's OpenBLAS otherwise reserves buffers per CPU core and can fail to start under memory pressure
    env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
    p = subprocess.Popen([sys.executable, *args], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding='utf-8', errors='replace')
    for line in p.stdout:
        line = line.rstrip()
        if line and not line.startswith((' ', '{', '}', '"')):  # skip the big JSON report, keep messages/tracebacks
            job.say(line[:300])
    if p.wait() != 0:
        raise RuntimeError(f'{os.path.basename(args[0])} завершился с кодом {p.returncode}')


def compose_design(job, req):
    """Constructor: new model from an existing design's stencils, own shape and colours, no AI (lib/compose.py)."""
    base = 'pu_own' if req['src'].startswith('upload:') else req['src'][:24]
    req = dict(req, slug=slugify(req.get('slug', '')) or f"{base}_{time.strftime('%m%d_%H%M%S')}")
    if os.path.exists(os.path.join(DESIGNS, req['slug'])):
        raise RuntimeError(f"дизайн {req['slug']} уже есть, задайте другое имя")
    job.say(f"Сборка {req['slug']} из {req['src']}: форма {req['shape']}" + (", принт PU, мокап, ТЗ" if req['shape'].startswith('pu_') else ", трафареты, раскладка, мокап, ТЗ"))
    import json as _json
    _run_tool(job, [os.path.join(ROOT, 'lib', 'compose.py'), _json.dumps(req, ensure_ascii=False)])
    job.say('Готово')
    return dict(slug=req['slug'])


def delete_design(slug):
    """Remove a design for good: its folder (stencils, spec, mockups, caches) and its old on-model photo."""
    import shutil
    d = os.path.realpath(os.path.join(DESIGNS, slug))
    if os.path.dirname(d) != os.path.realpath(DESIGNS) or not os.path.isdir(d):   # only a direct sub-folder of designs/
        raise FileNotFoundError(slug)
    shutil.rmtree(d)
    om = os.path.join(ON_MODEL, f'{slug}_on_model.jpg')
    if os.path.exists(om):
        os.remove(om)


def mirror_design(job, src):
    """Symmetric two-sided copy of an existing design: B = A mirrored, no logo, no Gemini call."""
    slug = src + '_ab'
    if os.path.exists(os.path.join(DESIGNS, slug)):
        raise RuntimeError(f'дизайн {slug} уже есть')
    job.say(f'Сторона B = зеркало A: {slug}')
    _run_tool(job, [os.path.join(ROOT, 'tools', 'mirror_b.py'), src, slug])
    job.say('Готово')
    return dict(slug=slug)


def generate_design(job, theme, preset, slug, sides, shape='', logo='', refs=(), pu_layout='placement'):
    """Runs tools/generate.py (Gemini art direction + image + BRAND engine) as a subprocess, streams its log."""
    slug = slugify(slug) or f'{preset}_{time.strftime("%m%d_%H%M%S")}'
    if os.path.exists(os.path.join(DESIGNS, slug)):
        raise RuntimeError(f'дизайн {slug} уже есть, задайте другой slug')
    job.say(f'Старт: {slug}, пресет {preset}, стороны {sides}')
    job.say('Шаг 1/3: арт-дирекция Gemini (палитра, концепция)… шаг 2/3: картинка… шаг 3/3: трафареты и мокап')
    refs = [p for p in refs if os.path.exists(p)]
    if refs:
        job.say(f'Референсов: {len(refs)}')
    ref_args = ['--refs', *refs] if refs else []
    if shape.startswith('pu_'):   # PU caps: full-colour print, own pipeline
        _run_tool(job, [os.path.join(ROOT, 'tools', 'generate_pu.py'), '--shape', shape, '--slug', slug, '--theme', theme,
                        '--preset', preset, '--layout', pu_layout or 'placement'] + ref_args)
        job.say('Готово')
        return dict(slug=slug)
    args = [os.path.join(ROOT, 'tools', 'generate.py'), '--preset', preset, '--slug', slug, '--theme', theme]
    args += ['--sides', 'A', '--mirror-b'] if sides == 'ABm' else ['--sides', sides]
    if shape:
        args += ['--shape', shape]
    if logo:
        args += ['--logo', logo]
    args += ref_args
    _run_tool(job, args)
    job.say('Готово')
    return dict(slug=slug)
