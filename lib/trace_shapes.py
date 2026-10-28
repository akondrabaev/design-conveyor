"""Kids cap templates traced from the supplier's pictures (lib/shape_src/<kind>.png), replacing the drawn approximations.

  kid_horns   2-D drawing: outer line = cap outline (the black fill is only the drawing style, not the print area)
  kid_dragon  2-D drawing (COD10_02): outline only; front is on the right in the drawing -> mirrored (template: front left)
  kid_fish    photo of the flat cap on white (front already on the left: eye and mouth left, fin and tail right)
  kid_cat     photo of the flat cap on white
The printable body is the standard cap body (cap_sym, the same moulded dome) fitted to the traced outline by its width
low on the cap, where there are no moulded parts, and its bottom edge; body = fitted standard body ∩ outline. Normalised like every template: body width = 1000 px.

python3 lib/trace_shapes.py   -> lib/cap_<kind>.txt, lib/cap_<kind>_body.txt, offsets in lib/shapes.json
"""
import json, os, sys
import numpy as np
import cv2
from PIL import Image, ImageOps
from scipy import ndimage
from shapely.geometry import Polygon
from shapely import affinity

LIB = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, LIB)
PAD = 12
MARGIN = 36   # core.MARGIN: the print area of the horns drawing is grown by it, so the engine's inset lands on the drawn border

# kind: (source kind, mirror, opening radius as a share of the body width)
SOURCES = {'kid_horns': ('drawing', False, 0.09), 'kid_dragon': ('drawing', True, 0.075),
           'kid_fish': ('photo', False, 0.075), 'kid_cat': ('photo', False, 0.06)}


def _disk(r):
    r = max(1, int(round(r)))
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def _largest(mask):
    lab, n = ndimage.label(mask)
    if n == 0:
        return mask
    sizes = ndimage.sum(mask, lab, range(1, n + 1))
    return lab == (1 + int(np.argmax(sizes)))


def masks(kind):
    src, mirror, r_open = SOURCES[kind]
    im = Image.open(os.path.join(LIB, 'shape_src', f'{kind}.png')).convert('RGB')
    if mirror:
        im = ImageOps.mirror(im)
    a = np.asarray(im).astype(np.int16)
    gray = a.mean(-1)
    if src in ('drawing', 'drawing_fill'):
        h = a.shape[0]
        dark = gray < 128
        if kind == 'kid_dragon':
            dark[int(h * 0.9):] = False                   # caption "COD10_02" under the drawing
        # everything not reachable from the image border is the cap: robust to small gaps in the line
        closed = cv2.dilate(dark.astype(np.uint8), _disk(6)).astype(bool)
        lab, _ = ndimage.label(~closed)
        border = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
        inside = ~np.isin(lab, border[border > 0])
        outline = _largest(cv2.erode(inside.astype(np.uint8), _disk(6)).astype(bool))
    else:
        ink = (255 - a.min(-1)) > 35                       # anything clearly not white paper
        outline = _largest(ndimage.binary_fill_holes(cv2.morphologyEx(ink.astype(np.uint8), cv2.MORPH_CLOSE, _disk(3)).astype(bool)))
    return outline


def _row_width(g, y):
    from shapely.geometry import LineString
    i = g.intersection(LineString([(g.bounds[0] - 10, y), (g.bounds[2] + 10, y)]))
    return i.bounds[0], i.bounds[2]


def fit_body(outline, clip=True):
    """Standard body scaled and placed so that its width low on the cap and its bottom match the outline."""
    import core
    sym = core.load_cap('sym')[1].buffer(0)
    h_rel = 0.2                                       # measuring row: 0.2 body widths above the bottom (no moulded parts there)
    sx0, sx1 = _row_width(sym, sym.bounds[3] - h_rel * (sym.bounds[2] - sym.bounds[0]))
    ratio = (sx1 - sx0) / (sym.bounds[2] - sym.bounds[0])
    W = outline.bounds[2] - outline.bounds[0]
    for _ in range(3):                                # body width estimate -> measuring row -> body width
        x0, x1 = _row_width(outline, outline.bounds[3] - h_rel * W)
        W = (x1 - x0) / ratio
    k = W / (sym.bounds[2] - sym.bounds[0])
    body = affinity.scale(sym, k, k, origin=(0, 0))
    bx0, bx1 = _row_width(body, body.bounds[3] - h_rel * W)
    body = affinity.translate(body, (x0 + x1) / 2 - (bx0 + bx1) / 2, outline.bounds[3] - body.bounds[3])
    return body.intersection(outline).buffer(0) if clip else body


def polygon(mask, eps=0.6):
    cs, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cs, key=cv2.contourArea)
    c = cv2.approxPolyDP(c, eps, True)[:, 0, :].astype(float)
    return Polygon(c).buffer(0)


def clean_parts(outline, body, kind):
    """Outline = the smooth fitted body + each moulded part as a clean rounded polygon (convex hull of the traced part,
    reduced to its corners). Removes the jagged edge of a small photo while keeping the part's size and position."""
    from shapely.ops import unary_union
    from shapely.geometry import box
    rest = outline.difference(body.buffer(3))
    x0, y0, x1, y1 = body.bounds
    if kind in ('kid_cat',):                          # two ears: only the left and right thirds, never the strip between them
        w = x1 - x0
        top = y0 + (y1 - y0) * 0.3                    # ears sit on the upper corners only
        rest = unary_union([rest.intersection(box(x0 - w, y0 - w, x0 + w * 0.33, top)),
                            rest.intersection(box(x1 - w * 0.33, y0 - w, x1 + w, top))])
    parts = []
    for g in getattr(rest, 'geoms', [rest]):
        thin = 9 if kind == 'kid_cat' else 6
        if g.area < 300 or g.buffer(-thin).is_empty:     # specks and thin slivers where the photo edge is wider than the body
            continue
        r = 18 if kind == 'kid_cat' else 5            # drop the thin strip along the body edge (photo perspective), keep the part
        g = g.buffer(-r).buffer(r)
        if g.is_empty:
            continue
        g = max(getattr(g, 'geoms', [g]), key=lambda x: x.area)
        if kind == 'kid_cat':                         # pointed ear: the smallest triangle around the traced ear
            import cv2
            _, tri = cv2.minEnclosingTriangle(np.array(g.convex_hull.exterior.coords, np.float32).reshape(-1, 1, 2))
            hull = Polygon(tri.reshape(-1, 2)).buffer(0)
        else:
            hull = g.convex_hull.simplify(14)         # a few corner points
        parts.append(hull.buffer(-10, join_style=1).buffer(10, join_style=1).buffer(14))   # rounded corners, overlaps the body
    return unary_union([body] + parts).buffer(18, join_style=1).buffer(-18, join_style=1).simplify(0.5)   # soft joints


def trace(kind):
    import core
    outline = polygon(masks(kind))
    photo = SOURCES[kind][0] == 'photo'
    body = fit_body(outline, clip=not photo)          # photos: the smooth standard body as is, not the jagged traced edge
    k = 1000 / (body.bounds[2] - body.bounds[0])              # body width -> 1000 px
    outline = affinity.scale(outline, k, k, origin=(0, 0))
    body = affinity.scale(body, k, k, origin=(0, 0))
    if SOURCES[kind][0] == 'photo':
        outline = clean_parts(outline, body, kind)          # small jpeg photos: rebuild a smooth outline from the parts' key points
    else:
        outline = outline.buffer(2).buffer(-4).buffer(2).simplify(0.8)
    body = body.buffer(2).buffer(-2).simplify(0.6).intersection(outline)
    dx, dy = PAD - outline.bounds[0], PAD - outline.bounds[1]
    outline, body = affinity.translate(outline, dx, dy), affinity.translate(body, dx, dy)
    open(f'{LIB}/cap_{kind}.txt', 'w').write(core.geom_d(outline))
    open(f'{LIB}/cap_{kind}_body.txt', 'w').write(core.geom_d(body))
    return [round(body.bounds[0], 2), round(body.bounds[1], 2)]


def main():
    p = f'{LIB}/shapes.json'
    meta = json.load(open(p)) if os.path.exists(p) else {}
    for kind in SOURCES:
        if not os.path.exists(f'{LIB}/shape_src/{kind}.png'):   # no source image: keep the shipped outline
            continue
        meta[kind] = dict(offset=trace(kind), source=f'shape_src/{kind}.png')
    json.dump(meta, open(p, 'w'), indent=1)
    return meta


if __name__ == '__main__':
    print(main())
