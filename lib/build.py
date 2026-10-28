"""Export pipeline: for each design -> print SVG/PNG (transparent), per-ink stencils, layout sheet, mockups, spec."""
import os, json, sys
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(__file__))
from core import *

OUT = os.path.join(os.path.dirname(LIB), 'designs')
import shapes
BODY_PX = 1000                              # body width in template px (all templates)


def width_mm(D):
    """Flat body width of the main size in mm (supplier drawings, shapes.SIZES)."""
    return shapes.main_size(D['cap'], D.get('segment'))['w'] * 10
SIDE_LABEL = {'A': ("Side A (wearer's left, with logo)", 'A面（佩戴者左侧，带标志）'), 'B': ("Side B (wearer's right)", 'B面（佩戴者右侧）')}
FONT = "Arial, 'Microsoft YaHei', 'Noto Sans CJK SC', 'DejaVu Sans'"   # Latin + Chinese labels


def folders(od):
    """Design folder layout: mockup + spec in the root, vector files in SVG/, raster files in PNG/."""
    svg, png = os.path.join(od, 'SVG'), os.path.join(od, 'PNG')
    os.makedirs(svg, exist_ok=True)
    os.makedirs(png, exist_ok=True)
    return svg, png

class Ctx:
    def __init__(self, cap, side):
        d, g, W, H = load_cap(cap)
        self.W, self.H = W, H
        self.mirrored = (side == 'B' and cap in shapes.MIRROR_B)   # side B of an asymmetric cap: mirrored template
        self.cap = mirror_x(g, W) if self.mirrored else g
        if cap in shapes.KIDS:   # shaped kids caps: the print runs along the whole outline, moulded parts included
            self.margin = shapes.KIDS_MARGIN
            self.safe = self.cap.buffer(-self.margin)
        else:
            self.margin = MARGIN
            body = load_body(cap)
            self.safe = (mirror_x(body, W) if self.mirrored else body).buffer(-MARGIN)
        self.cap_d = geom_d(self.cap)
        self.side = side

def logo_layer(D, ctx):
    g, w, h = load_logo(D['logo'])
    x, y, lw = D['logo_pos']
    dx, dy = shapes.offset(D['cap'])   # logo position is given in body coordinates
    x, y = x + dx, y + dy
    s = lw / w
    return T(g, x, y, s=s, origin=(0, 0)), (lw, h*s)

def build_side(D, side):
    ctx = Ctx(D['cap'], side)
    layers = D['sides'][side](ctx)
    logo_g = None
    if side == 'A' and D.get('logo'):   # no engine logo: none, or BRAND lettering drawn inside the artwork
        logo_g, _ = logo_layer(D, ctx)
        layers = layers + [(None, logo_g.buffer(GAP))]
    cols = compose(layers, ctx.safe, len(D['inks']))
    if logo_g is not None:   # brand logo is added untouched (no sliver cleanup), only clipped to the print zone
        from shapely.ops import unary_union as _uu
        cols[D['logo_ink']] = _uu([cols[D['logo_ink']], logo_g.intersection(ctx.safe)])
    rep = checks(cols, ctx.safe, logo_g)
    return ctx, cols, rep

def mockup_cell(ctx, cols, cap_hex, inks, label, sheen=True):
    W, H = ctx.W, ctx.H
    body = f'<defs><radialGradient id="sh" cx="0.35" cy="0.18" r="0.75"><stop offset="0" stop-color="#fff" stop-opacity="0.22"/><stop offset="0.55" stop-color="#fff" stop-opacity="0.04"/><stop offset="1" stop-color="#000" stop-opacity="0.18"/></radialGradient></defs>'
    body += f'<path d="{ctx.cap_d}" fill="{cap_hex}"/>'
    for i, g in enumerate(cols):
        if not g.is_empty: body += f'<path d="{geom_d(g)}" fill="{inks[i]}" fill-rule="evenodd"/>'
    if sheen: body += f'<path d="{ctx.cap_d}" fill="url(#sh)"/>'
    return body

def esc(s): return s.replace('&', '&amp;').replace('<', '&lt;')

def build(D):
    slug = D['slug']; od = os.path.join(OUT, slug); os.makedirs(od, exist_ok=True)
    svgd, pngd = folders(od)
    inks = [i[1] for i in D['inks']]; names = [i[3] for i in D['inks']]
    sides = list(D['sides'].keys())
    res = {}
    for side in sides:
        ctx, cols, rep = build_side(D, side)
        res[side] = (ctx, cols, rep)
        tag = f'side-{side}'
        W, H = ctx.W, ctx.H
        # 02/03 print: positioned in cap frame, transparent background, print only
        svg = print_svg(cols, inks, names, W, H)
        open(f'{svgd}/{slug}_{tag}_print_vector.svg', 'w', encoding='utf-8').write(svg)
        render(svg, f'{pngd}/{slug}_{tag}_print_transparent.png', scale=3)
        # stencils: one per ink, black, transparent bg
        for i, g in enumerate(cols):
            if g.is_empty: continue
            s = svg_doc(W, H, f'<path d="{geom_d(g)}" fill="#000" fill-rule="evenodd"/>')
            open(f'{svgd}/{slug}_{tag}_stencil{i+1}_{names[i]}.svg', 'w', encoding='utf-8').write(s)
            render(s, f'{pngd}/{slug}_{tag}_stencil{i+1}_{names[i]}.png', scale=3)
        # production layout sheet: template + safe zone + print (not a mockup)
        mm = width_mm(D) / BODY_PX
        lay = f'<path d="{ctx.cap_d}" fill="{D["variants"][0]["cap_hex"]}" stroke="#9aa3ad" stroke-width="2"/>'
        lay += f'<path d="{geom_d(ctx.safe)}" fill="none" stroke="#FF4D4F" stroke-width="2.5" stroke-dasharray="10 7"/>'
        for i, g in enumerate(cols):
            if not g.is_empty: lay += f'<path d="{geom_d(g)}" fill="{inks[i]}" fill-rule="evenodd"/>'
        PAD = 70
        sh = shapes.SHAPES[D['cap']]
        tpl = (f"{sh['en'].lower()}, mirrored template", f"{sh['zh']}，镜像模板") if ctx.mirrored else (f"{sh['en'].lower()} template", f"{sh['zh']}模板")
        lbl = ({'A': ('Side A = front (face)', 'A面=正面（脸部）'), 'B': ('Side B = back of the head', 'B面=背面')}[side]
               if D['cap'] in shapes.FRONT else SIDE_LABEL[side])
        top = [f'{esc(slug)} · {lbl[0]} · {tpl[0]}', f'{lbl[1]} · {tpl[1]}']
        notes = ['Outline = edge of the flat cap; red dashed line = border of the print area' + ('; the print covers the moulded parts too.' if D['cap'] in shapes.KIDS else '.'),
                 '轮廓为平放泳帽边缘；红色虚线为印刷区域边界' + ('；立体造型部分同样印刷。' if D['cap'] in shapes.KIDS else '。'),
                 f'Flat width {width_mm(D):.0f} mm ({shapes.main_size(D["cap"], D.get("segment"))["en"]}); print margin {ctx.margin*mm:.1f} mm. Check against the physical sample.',
                 f'平放宽度{width_mm(D):.0f}毫米（{shapes.main_size(D["cap"], D.get("segment"))["g"]}克）；印刷边距{ctx.margin*mm:.1f}毫米。请以实物样品核对。']
        PT = PAD + 40   # room for two title lines
        sheet = f'<svg xmlns="http://www.w3.org/2000/svg" width="{W+2*PAD:.0f}" height="{H+PT+PAD+120:.0f}"><rect width="100%" height="100%" fill="#fff"/><g transform="translate({PAD},{PT})">{lay}</g>' + \
                ''.join(f'<text x="{PAD}" y="{30 + 28*i}" font-family="{FONT}" font-size="20" fill="#333">{t}</text>' for i, t in enumerate(top)) + \
                ''.join(f'<text x="{PAD}" y="{H+PT+35 + 26*i:.0f}" font-family="{FONT}" font-size="17" fill="#666">{t}</text>' for i, t in enumerate(notes)) + '</svg>'
        render(sheet, f'{pngd}/{slug}_{tag}_layout.png')
    # 01 mockup grid: rows = cap colour variants, cols = sides
    cw, chh = 1000, max(r[0].H for r in res.values())
    PAD, LBL = 50, 110
    Wt = len(sides)*(cw+PAD)+PAD; Ht = len(D['variants'])*(chh+LBL+PAD)+PAD+70
    body = f'<rect width="100%" height="100%" fill="#DADDE1"/><text x="{PAD}" y="62" font-family="{FONT}" font-weight="bold" font-size="40" fill="#1d1d1d">{esc(D.get("title_en") or slug)} - mockup / 效果图</text>'
    for r, V in enumerate(D['variants']):
        vinks = V.get('inks', inks)
        for c, side in enumerate(sides):
            ctx, cols, _ = res[side]
            x = PAD + c*(cw+PAD); y = 100 + r*(chh+LBL+PAD)
            body += f'<g transform="translate({x},{y})">{mockup_cell(ctx, cols, V["cap_hex"], vinks, "")}</g>'
            body += f'<text x="{x+cw/2}" y="{y+chh+45}" text-anchor="middle" font-family="{FONT}" font-size="30" fill="#222">{esc(V.get("cap_ral") or V["cap_name"])}{" · " + side if len(sides) > 1 else ""}</text>'
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{Wt}" height="{Ht}">{body}</svg>'
    render(svg, f'{od}/{slug}_mockup.png', scale=0.6)
    # hero (first variant, side A) for lookbook
    ctx, cols, _ = res['A']
    V = D['variants'][0]
    hero = f'<svg xmlns="http://www.w3.org/2000/svg" width="{ctx.W:.0f}" height="{ctx.H:.0f}">{mockup_cell(ctx, cols, V["cap_hex"], V.get("inks", inks), "")}</svg>'
    render(hero, f'{od}/_hero.png', scale=0.5)
    reps = {s: res[s][2] for s in sides}
    json.dump(reps, open(f'{od}/_checks.json', 'w'), indent=1, ensure_ascii=False)
    return reps
