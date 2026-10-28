"""BRAND swim-cap print engine: geometry helpers, layer compositing, checks and file export.
Coordinates: cap frame, 1000 px = flat cap width."""
import math, os, re, json
import numpy as np
try:
    import cairosvg
except OSError:  # no libcairo (Windows): render with resvg instead
    cairosvg = None
from shapely.geometry import Polygon, MultiPolygon, LineString, Point, box
from shapely.ops import unary_union
from shapely import affinity

LIB = os.path.dirname(os.path.abspath(__file__))
GAP = 6        # min gap between different print colours (px)
MINW = 8       # min line / feature width (px)
MARGIN = 36    # no-print band along cap edge (px)

# ---------- path parsing ----------
def _cubic(p0, p1, p2, p3, n=14):
    t = np.linspace(0, 1, n)[1:, None]
    return list(map(tuple, (1-t)**3*p0 + 3*(1-t)**2*t*p1 + 3*(1-t)*t**2*p2 + t**3*p3))

def parse_path(d):
    toks = re.findall(r'[MLCZ]|-?\d+\.?\d*', d)
    rings, cur, i, cmd = [], [], 0, None
    num = lambda: float(toks[i])
    while i < len(toks):
        t = toks[i]
        if t in 'MLCZ':
            cmd = t; i += 1
            if t == 'Z':
                if len(cur) > 2: rings.append(cur)
                cur = []
            continue
        if cmd == 'M':
            cur = [(float(toks[i]), float(toks[i+1]))]; i += 2; cmd = 'L'
        elif cmd == 'L':
            cur.append((float(toks[i]), float(toks[i+1]))); i += 2
        elif cmd == 'C':
            v = [float(x) for x in toks[i:i+6]]; i += 6
            p0 = np.array(cur[-1]); cur += _cubic(p0, np.array(v[0:2]), np.array(v[2:4]), np.array(v[4:6]))
    if len(cur) > 2: rings.append(cur)
    g = Polygon()
    for r in rings:
        g = g.symmetric_difference(Polygon(r).buffer(0))
    return g

def load_cap(kind):
    """Outline of the flat cap (with horns / ears / fin / crest for the kids shapes) and its frame size."""
    d = open(f'{LIB}/cap_{kind}.txt').read()
    g = parse_path(d)
    minx, miny, maxx, maxy = g.bounds
    if os.path.exists(f'{LIB}/cap_{kind}_body.txt'):   # shaped caps: frame includes the moulded parts
        maxx, maxy = maxx + 12, maxy + 12
    return d, g, maxx, maxy

def load_body(kind):
    """The printable body of the cap: the outline without moulded parts (same as the outline for sym / long)."""
    p = f'{LIB}/cap_{kind}_body.txt'
    return parse_path(open(p).read()).buffer(0) if os.path.exists(p) else load_cap(kind)[1]

def load_logo(kind):
    """kind: 'adult' / 'kids' (lib/logo_<kind>.txt) or a path to a design's own logo file (styled lettering)."""
    p = kind if kind.endswith('.txt') else f'{LIB}/logo_{kind}.txt'
    head, d = open(p).read().split('\n', 1)
    w, h = map(float, head.split())
    return parse_path(d), w, h

# ---------- shape helpers ----------
def catmull(pts, closed=True, n=16):
    P = [np.array(p, float) for p in pts]
    if closed: P = [P[-1]] + P + [P[0], P[1]]
    else: P = [P[0]] + P + [P[-1]]
    out = []
    for i in range(1, len(P)-2):
        p0, p1, p2, p3 = P[i-1], P[i], P[i+1], P[i+2]
        for t in np.linspace(0, 1, n, endpoint=False):
            t2, t3 = t*t, t*t*t
            out.append(tuple(0.5*((2*p1) + (-p0+p2)*t + (2*p0-5*p1+4*p2-p3)*t2 + (-p0+3*p1-3*p2+p3)*t3)))
    if not closed: out.append(tuple(P[-2]))
    return out

def blob(pts):            return Polygon(catmull(pts)).buffer(0)
def poly(pts):            return Polygon(pts).buffer(0)
def circle(x, y, r):      return Point(x, y).buffer(r, quad_segs=32)
def ellipse(x, y, rx, ry, ang=0):
    e = affinity.scale(Point(0, 0).buffer(1, quad_segs=32), rx, ry, origin=(0, 0))
    return affinity.translate(affinity.rotate(e, ang, origin=(0, 0)), x, y)
def ribbon(pts, w, smooth=True, cap='round'):
    line = catmull(pts, closed=False) if smooth and len(pts) > 2 else pts
    return LineString(line).buffer(w/2, cap_style={'round': 1, 'flat': 2, 'square': 3}[cap], join_style=1)
def taper(pts, w0, w1, smooth=True):
    line = catmull(pts, closed=False) if smooth and len(pts) > 2 else pts
    L = np.cumsum([0] + [math.dist(line[i], line[i+1]) for i in range(len(line)-1)]); L = L / L[-1]
    parts = []
    for i in range(len(line)-1):
        r0 = (w0 + (w1-w0)*L[i]) / 2; r1 = (w0 + (w1-w0)*L[i+1]) / 2
        parts.append(unary_union([Point(line[i]).buffer(r0, 16), Point(line[i+1]).buffer(r1, 16)]).convex_hull)
    return unary_union(parts)
def wave_line(x0, x1, y, amp, period, w, phase=0):
    xs = np.linspace(x0, x1, int((x1-x0)/4)+2)
    return LineString([(x, y + amp*math.sin(2*math.pi*(x-x0)/period + phase)) for x in xs]).buffer(w/2, cap_style=1)
def T(g, dx=0, dy=0, s=1, rot=0, origin=(0, 0)):
    if s != 1: g = affinity.scale(g, s, s, origin=origin)
    if rot: g = affinity.rotate(g, rot, origin=origin)
    return affinity.translate(g, dx, dy)
def mirror_x(g, W=1000): return affinity.scale(g, -1, 1, origin=(W/2, 0))

# ---------- compositing ----------
def compose(layers, safe, ncol):
    """layers: list of (colour_index | None, geom) in paint order. None = knockout (cap colour shows).
    Upper layers knock out lower layers of other colours with a GAP, so stencils never overlap."""
    acc = [Polygon() for _ in range(ncol)]
    for ci, g in layers:
        g = g.buffer(0)
        if g.is_empty: continue
        if ci is None:
            acc = [a.difference(g) for a in acc]; continue
        for j in range(ncol):
            if j != ci and not acc[j].is_empty:
                acc[j] = acc[j].difference(g.buffer(GAP))
        acc[ci] = unary_union([acc[ci], g])
    out = []
    for a in acc:
        a = a.intersection(safe)
        # drop slivers created by knockouts
        a = a.buffer(-1.5).buffer(1.5)
        polys = [p for p in getattr(a, 'geoms', [a]) if not p.is_empty and p.area > (MINW*1.6)**2]
        out.append(unary_union(polys) if polys else Polygon())
    return out

# ---------- SVG ----------
def geom_d(g):
    def ring(r):
        c = list(r.coords)
        return 'M' + ' L'.join(f'{x:.2f},{y:.2f}' for x, y in c[:-1]) + ' Z'
    d = []
    for p in getattr(g, 'geoms', [g]):
        if p.is_empty or p.geom_type != 'Polygon': continue
        d.append(ring(p.exterior)); d += [ring(i) for i in p.interiors]
    return ' '.join(d)

def svg_doc(W, H, body, bg=None):
    b = f'<rect width="{W:.0f}" height="{H:.0f}" fill="{bg}"/>' if bg else ''
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" viewBox="0 0 {W:.0f} {H:.0f}">{b}{body}</svg>'

def print_svg(cols, palette, names, W, H):
    body = ''
    for i, g in enumerate(cols):
        if g.is_empty: continue
        body += f'<g id="ink{i+1}_{names[i]}_{palette[i].lstrip("#")}"><path d="{geom_d(g)}" fill="{palette[i]}" fill-rule="evenodd"/></g>'
    return svg_doc(W, H, body)

def render(svg, path, scale=1.0):
    if cairosvg:
        cairosvg.svg2png(bytestring=svg.encode(), write_to=path, scale=scale)
        return
    import resvg_py
    png = resvg_py.svg_to_bytes(svg_string=svg, zoom=scale, font_family='Arial', sans_serif_family='Arial')
    with open(path, 'wb') as f:
        f.write(bytes(png))

# ---------- checks ----------
def checks(cols, safe, logo_geom):
    rep = {}
    used = [i for i, g in enumerate(cols) if not g.is_empty]
    rep['inks_used'] = len(used)
    rep['inks_ok'] = len(used) <= 3
    union = unary_union([g for g in cols if not g.is_empty])
    rep['outside_safe_px2'] = round(union.difference(safe.buffer(0.5)).area, 2)
    rep['inside_safe_ok'] = rep['outside_safe_px2'] < 1
    thin = {}
    for i in used:
        g = cols[i].difference(logo_geom.buffer(2)) if logo_geom is not None else cols[i]
        if g.is_empty: thin[i+1] = 0; continue
        opened = g.buffer(-MINW/2 + 0.5).buffer(MINW/2 - 0.5)
        thin[i+1] = round(100 * g.difference(opened).area / g.area, 2)
    rep['thin_area_pct_by_ink'] = thin
    gaps = []
    for a in used:
        for b in used:
            if a < b: gaps.append(round(cols[a].distance(cols[b]), 2))
    rep['min_gap_between_inks_px'] = min(gaps) if gaps else None
    rep['gap_ok'] = (min(gaps) >= GAP - 0.6) if gaps else True
    return rep
