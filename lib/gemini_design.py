"""Bridge: Gemini spec + quantized ink index map -> design dict D for build.py.

The raster is cover-fitted onto the flat cap frame (1000 px wide), each ink mask is traced
with potrace into vector polygons, and build() then clips to the print zone, knocks out
the logo, enforces gaps and exports print/stencils/layout/mockups as for hand-drawn designs.
"""
import os
import numpy as np
import potrace
from PIL import Image
from core import load_cap, parse_path, T, mirror_x
import ral

CAP_BY_SEGMENT = {'Женская': 'long', 'Детская': 'sym', 'Унисекс': 'sym'}
LOGO = {'long': ('adult', (120, 590, 190)), 'sym': ('adult', (130, 610, 175))}
KIDS_LOGO = ('kids', (120, 575, 150))
SUPERSAMPLE = 3   # trace at 3000 px across the cap, then scale back to the 1000 px frame


def _lum(h):
    h = h.lstrip('#'); r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _trace(mask):
    bm = potrace.Bitmap(~np.pad(mask, 4))  # potracer traces False pixels
    pl = bm.trace(turdsize=60, alphamax=1.0, opticurve=True, opttolerance=0.3)
    P = lambda p: (lambda x, y: f'{(x - 4) / SUPERSAMPLE:.2f},{(y - 4) / SUPERSAMPLE:.2f}')(*((p.x, p.y) if hasattr(p, 'x') else p))
    d = ''
    for c in pl:
        d += f'M{P(c.start_point)} '
        for seg in c.segments:
            d += f'L{P(seg.c)} L{P(seg.end_point)} ' if seg.is_corner else f'C{P(seg.c1)} {P(seg.c2)} {P(seg.end_point)} '
        d += 'Z '
    return parse_path(d) if d else None


def fit_index(idx, W, H):
    """Cover-fit the index map onto a W x H cap frame at SUPERSAMPLE resolution (nearest, keeps inks crisp)."""
    tw, th = int(round(W * SUPERSAMPLE)), int(round(H * SUPERSAMPLE))
    s = max(tw / idx.shape[1], th / idx.shape[0])
    im = Image.fromarray(idx).resize((int(np.ceil(idx.shape[1] * s)), int(np.ceil(idx.shape[0] * s))), Image.NEAREST)
    x0, y0 = (im.width - tw) // 2, (im.height - th) // 2
    return np.asarray(im.crop((x0, y0, x0 + tw, y0 + th)))


def ink_geoms(idx, n_inks, W, H):
    fitted = fit_index(idx, W, H)
    return [_trace(fitted == n) for n in range(1, n_inks + 1)]


SMALL_LOGO = {'side': (770, 650, 110),    # lower back corner of the side (as on the crest / fish caps), inside the print area
              'front': (445, 725, 110)}   # under the face, bottom centre


def logo_mode(spec):
    """'standard' (wave logo / wordmark), shaped kids caps: 'small' (default), 'styled' (lettering drawn in the artwork), 'none'."""
    import shapes
    return spec.get('logo') or ('small' if cap_kind(spec) in shapes.KIDS else 'standard')


def cap_kind(spec):
    """Template of the design: explicit spec['shape'] (kids shapes, see shapes.py) or by segment."""
    return spec.get('shape') or CAP_BY_SEGMENT.get(spec.get('segment'), 'sym')


def make_design(spec, idx_by_side):
    """idx_by_side: {'A': index map, 'B': index map (optional)}."""
    import shapes
    cap = cap_kind(spec)
    logo, pos = KIDS_LOGO if spec.get('segment') == 'Детская' else LOGO.get(cap, LOGO['sym'])
    if cap in shapes.KIDS:   # shaped kids caps: small plain wordmark, drawn in the artwork, or none (spec['logo'])
        mode = logo_mode(spec)
        corner = SMALL_LOGO['front' if cap in shapes.FRONT else 'side']
        styled = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'designs', spec['slug'], '_gemini', 'logo_styled.txt')
        if mode == 'small':
            logo, pos = 'adult', corner
        elif mode == 'styled' and os.path.exists(styled):   # BRAND lettering in the character's style, side A only
            logo, pos = styled, (corner[0] - 15, corner[1] - 15, 140)
        else:
            logo, pos = None, None
    _, _, W, H = load_cap(cap)
    inks = spec['inks']
    geoms = {s: ink_geoms(idx, len(inks), W, H) for s, idx in idx_by_side.items()}
    if spec.get('side_b') == 'mirror':
        # symmetric cap: side B (wearer's right) is side A mirrored, so motifs face forward on both sides; no logo on B.
        # build() already mirrors the long template for side B, so the long cap reuses A's geometry as is.
        geoms['B'] = geoms['A'] if cap in shapes.MIRROR_B else [None if g is None else mirror_x(g, W) for g in geoms['A']]

    def side_fn(s):
        return lambda ctx: [(i, T(g, 0, 0) if not ctx.mirrored else __import__('core').mirror_x(g, ctx.W))
                            for i, g in enumerate(geoms[s]) if g is not None and not g.is_empty]

    base_l = _lum(spec['base']['hex'])
    logo_ink = max(range(len(inks)), key=lambda i: abs(_lum(inks[i]['hex']) - base_l))   # unused when logo is None
    # RAL is always the computed nearest RAL Classic colour (ΔE2000), never the text model's guess
    import colorways, copy
    spec = colorways.ensure(copy.deepcopy(spec))   # older designs: per-cap ink colours computed on the fly
    variants = [dict(cap_name=spec['base']['name'], cap_hex=spec['base']['hex'], cap_ral=ral.nearest(spec['base']['hex'])['code'])]
    variants += [dict(cap_name=v['name'], cap_hex=v['hex'], cap_ral=ral.nearest(v['hex'])['code'], inks=[i['hex'] for i in v['inks']])
                 for v in spec.get('variants', [])[:2]]
    return dict(slug=spec['slug'], title=spec['name'], title_en=spec.get('i18n', {}).get('en', {}).get('name'), segment=spec.get('segment', 'Унисекс'), cap=cap,
                logo=logo, logo_pos=pos, logo_ink=logo_ink,
                inks=[(k['name'], k['hex'], k.get('ral', ''), k.get('file', f'ink{i + 1}')) for i, k in enumerate(inks)],
                variants=variants, sides={s: side_fn(s) for s in geoms})
