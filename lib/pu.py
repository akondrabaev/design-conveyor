"""PU caps: where the full-colour print sits on the side panel - one rule for the generator, the constructor preview and save.

layout 'placement': the character box (shapes.PU_PRINT_BOX); 'allover': the whole side.
place = {'x': dx, 'y': dy, 's': scale}: the user's move (fractions of the cap width / height) and scale (1 = default).
Everything closer than GAP to the cap outline is cut off (the manufacturer needs a small gap along the edge).
"""
import numpy as np
from PIL import Image, ImageDraw

import shapes
from core import load_cap

GAP = 14   # px of the 1000 px wide template (~3.3 mm on a 235 mm cap)


def box(kind, layout='placement', place=None):
    """(cx, cy, bw, bh) of the print in template px."""
    _, _, W, H = load_cap(kind)
    if layout == 'allover':
        cx, cy, bw, bh = W / 2, H / 2, W, H
    else:
        fx, fy, fw, fh = shapes.PU_PRINT_BOX
        cx, cy, bw, bh = fx * W, fy * H, fw * W, fh * H
    p = place or {}
    s = float(p.get('s', 1) or 1)
    return cx + float(p.get('x', 0)) * W, cy + float(p.get('y', 0)) * H, bw * s, bh * s


def mask(kind, width_px):
    """L mask of the printable area (outline minus GAP) at a frame width of width_px."""
    _, outline, W, H = load_cap(kind)
    k = width_px / W
    m = Image.new('L', (round(W * k), round(H * k)), 0)
    d = ImageDraw.Draw(m)
    safe = outline.buffer(-GAP)
    for g in getattr(safe, 'geoms', [safe]):
        d.polygon([(x * k, y * k) for x, y in g.exterior.coords], fill=255)
    return m


LOGO_KINDS = {'adult': 'wordmark', 'kids': 'wordmark with waves'}


def logo_image(kind, hex_, width_px):
    """BRAND logo (lib/logo_<kind>.txt vector) as RGBA in one colour, width_px wide, antialiased."""
    from core import load_logo
    g, w, h = load_logo(kind)
    ss = 3
    k = width_px * ss / w
    m = Image.new('L', (max(1, round(w * k)), max(1, round(h * k))), 0)
    d = ImageDraw.Draw(m)
    for p in getattr(g, 'geoms', [g]):
        d.polygon([(x * k, y * k) for x, y in p.exterior.coords], fill=255)
        for r in p.interiors:
            d.polygon([(x * k, y * k) for x, y in r.coords], fill=0)
    m = m.resize((max(1, round(w * k / ss)), max(1, round(h * k / ss))), Image.LANCZOS)
    rgb = tuple(int(hex_.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4))
    out = Image.new('RGBA', m.size, rgb + (0,))
    out.putalpha(m)
    return out


def frame(art, kind, layout='placement', place=None, width_px=1000, logo=None):
    """The print placed on the cap frame (RGBA, transparent outside the print), cut to the printable area.
    logo = {'kind': 'adult'|'kids'|'none', 'hex', 'x', 'y' (centre, fractions of the cap), 's' (width, fraction of the cap)}."""
    _, _, W, H = load_cap(kind)
    k = width_px / W
    cx, cy, bw, bh = box(kind, layout, place)
    s = min(bw / art.width, bh / art.height) * k
    a = art.resize((max(1, round(art.width * s)), max(1, round(art.height * s))), Image.LANCZOS)
    out = Image.new('RGBA', (round(W * k), round(H * k)), (0, 0, 0, 0))
    out.paste(a, (round(cx * k - a.width / 2), round(cy * k - a.height / 2)), a)
    li = None
    lw = max(8, round(float((logo or {}).get('s', 0.2)) * W * k))
    if logo and logo.get('kind') in LOGO_KINDS:
        li = logo_image(logo['kind'], logo.get('hex', '#FFFFFF'), lw)
    elif logo and logo.get('kind') == 'styled' and logo.get('path'):   # BRAND lettering drawn in the style of the print
        im = Image.open(logo['path']).convert('RGBA')
        li = im.resize((lw, max(1, round(im.height * lw / im.width))), Image.LANCZOS)
    if li is not None:
        lx, ly = float(logo.get('x', 0.25)) * W * k, float(logo.get('y', 0.8)) * H * k
        out.alpha_composite(li, (round(lx - li.width / 2), round(ly - li.height / 2)))
    alpha = np.minimum(np.asarray(out.split()[3]), np.asarray(mask(kind, width_px)))
    out.putalpha(Image.fromarray(alpha))
    return out


def remove_cap_background(img, base_hex, kind, tol=42):
    """'All-over without background': the model paints elements on the cap colour; pixels of the cap colour (or the white
    outside) that form large areas or touch the outline become transparent, small cap-coloured details inside elements stay."""
    from scipy import ndimage
    _, outline, W, H = load_cap(kind)
    a = np.asarray(img.convert('RGB')).astype(np.int16)
    base = np.array([int(base_hex.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)])
    near = (np.abs(a - base).sum(-1) < tol * 1.7) | (a.min(-1) > 238)
    lab, n = ndimage.label(near)
    sizes = np.bincount(lab.ravel())
    k = img.width / W
    m = Image.new('L', img.size, 0)
    ImageDraw.Draw(m).polygon([(x * k, y * k) for x, y in outline.buffer(-GAP * 2).exterior.coords], fill=255)
    inner = np.asarray(m) > 0
    edge_labels = np.unique(lab[~inner & near])                 # touches the edge band or lies outside
    big = np.where(sizes > 0.004 * near.size)[0]
    bg = np.isin(lab, np.union1d(edge_labels, big)) & (lab > 0)
    fg = ndimage.binary_opening(~bg, iterations=2)          # thin leftovers of the template edge
    lab2, _ = ndimage.label(fg)
    s2 = np.bincount(lab2.ravel())
    fg &= np.isin(lab2, np.where(s2 > 0.0002 * fg.size)[0]) & (lab2 > 0)   # specks
    out = img.convert('RGBA')
    out.putalpha(Image.fromarray((fg * 255).astype(np.uint8)))
    return out
