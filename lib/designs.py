"""BRAND capsule: 3 women / 3 kids / 3 unisex designs. Ink tuple: (name_ru, HEX, nearest RAL note, file-slug)."""
import math, random
import numpy as np
from shapely.ops import transform, unary_union
from shapely.geometry import LineString, Polygon
from core import *

def bend(g, cx, cy, R, a0):
    """Wrap local geometry (x along spine, y across) around a circle: x -> arc length, y -> radial offset."""
    def f(x, y, z=None):
        x = np.asarray(x); y = np.asarray(y)
        th = a0 + x / R
        r = R - y
        return cx + r*np.cos(th), cy + r*np.sin(th)
    return transform(f, g)

# ============================== WOMEN (long-hair cap) ==============================
def jelly(cx, cy, bw, tent_len, ang, seed):
    rnd = random.Random(seed)
    rx, ry = bw/2, bw*0.56
    top = ellipse(0, 0, rx, ry).intersection(box(-rx-1, -ry-1, rx+1, 0))
    n = 5; sr = rx/n
    sc = unary_union([circle(-rx + sr*(2*i+1), 0, sr*1.02) for i in range(n)])
    bell = unary_union([top, sc.intersection(box(-rx, 0, rx, sr+1))])
    L = []
    L.append((0, bell))
    # inner arcs knocked out of the bell
    for k, f in enumerate([0.62, 0.36]):
        arc = [(rx*f*math.cos(t), -ry*f*math.sin(t)*1.05 - 4) for t in np.linspace(math.radians(18), math.radians(162), 20)]
        L.append((None, ribbon(arc, max(9, bw*0.035), smooth=False)))
    # oral arms (ink 0) and tentacles (ink 1)
    arms = []
    for k, x0 in enumerate([-bw*0.12, bw*0.12]):
        pts = [(x0, sr*0.6)] + [(x0 + (bw*0.09)*math.sin(i*1.3 + k*2), sr + tent_len*0.62*i/5) for i in range(1, 6)]
        arms.append(taper(pts, bw*0.13, 10))
    tents = []
    for k in range(5):
        x0 = -rx*0.75 + k*rx*0.375
        ph = rnd.uniform(0, 6.28); amp = bw*rnd.uniform(0.05, 0.09)
        pts = [(x0 + amp*math.sin(ph + i*0.9), sr*1.2 + tent_len*i/7*rnd.uniform(0.85, 1.0)) for i in range(8)]
        tents.append(taper(pts, 13, 9))
    out = L + [(1, unary_union(tents))] + [(0, unary_union(arms))]
    return [(c, T(g, cx, cy, rot=ang, origin=(0, 0))) for c, g in out]

def w1_a(ctx):
    L = []
    L += jelly(0, 0, 270, 330, 12, 1); L = [(c, T(g, 640, 215)) for c, g in L]
    M = jelly(0, 0, 180, 240, -10, 2);  L += [(c, T(g, 315, 215)) for c, g in M]
    S = jelly(0, 0, 100, 130, 20, 3);   L += [(c, T(g, 830, 470)) for c, g in S]
    # rising bubbles
    for x, y, r in [(480, 120, 12), (505, 85, 8), (470, 62, 6.5), (250, 95, 9), (860, 330, 9), (880, 295, 6.5)]:
        L.append((1, circle(x, y, r)))
    return L

def koi(L):
    body = blob([(x*L, y*L) for x, y in [(0.5, 0), (0.44, -0.08), (0.3, -0.135), (0.1, -0.14), (-0.1, -0.11), (-0.28, -0.06), (-0.37, -0.03),
                                         (-0.37, 0.03), (-0.28, 0.06), (-0.1, 0.11), (0.1, 0.14), (0.3, 0.135), (0.44, 0.08)]])
    tail = blob([(x*L, y*L) for x, y in [(-0.33, 0), (-0.45, -0.1), (-0.62, -0.19), (-0.56, -0.06), (-0.5, 0), (-0.56, 0.06), (-0.62, 0.19), (-0.45, 0.1)]])
    fins = unary_union([blob([(x*L, s*y*L) for x, y in [(0.24, 0.1), (0.16, 0.25), (0.06, 0.29), (0.1, 0.2), (0.13, 0.11)]]) for s in (1, -1)])
    dorsal = blob([(x*L, y*L) for x, y in [(0.12, -0.012), (-0.02, -0.03), (-0.2, -0.012), (-0.02, 0.006)]])
    patches = unary_union([blob([(x*L, y*L) for x, y in pts]) for pts in [
        [(0.47, -0.01), (0.42, -0.07), (0.34, -0.06), (0.33, 0.02), (0.39, 0.07), (0.45, 0.05)],
        [(0.18, -0.12), (0.06, -0.13), (-0.04, -0.06), (0.02, 0.05), (0.14, 0.04), (0.22, -0.03)],
        [(-0.1, 0.1), (-0.2, 0.07), (-0.24, 0.0), (-0.16, -0.03), (-0.08, 0.02)]]]).intersection(body.buffer(-GAP-5))
    eyes = unary_union([circle(0.4*L, s*0.065*L, 0.022*L) for s in (1, -1)])
    return [(1, unary_union([tail, fins])), (0, body), (None, dorsal.buffer(0)), (2, patches), (None, eyes)]

def w2_a(ctx):
    cx, cy, R = 520, 335, 175
    L = []
    for a0 in (0, math.pi):
        L += [(c, bend(T(g, 0, 0), cx, cy, R, a0 + math.pi/2)) for c, g in koi(520)]
    # thin gold ripple arcs around the pair
    for r, a1, a2 in [(300, 200, 250), (330, 210, 240), (300, 20, 75), (330, 30, 62)]:
        L.append((1, ribbon([(cx + r*math.cos(math.radians(t)), cy + r*math.sin(math.radians(t))) for t in np.linspace(a1, a2, 30)], 9, smooth=False)))
    return L

def w2_b(ctx):
    cx, cy = 600, 370
    L = []
    for k, r in enumerate((95, 140, 185, 230)):
        g0 = 150 + k*55
        L.append((1, ribbon([(cx + r*math.cos(math.radians(t)), cy + r*math.sin(math.radians(t))) for t in np.linspace(g0 + 28, g0 + 360 - 28, 90)], 10, smooth=False)))
    L += [(c, bend(g, cx, cy, 162, math.radians(150))) for c, g in koi(330)]
    return L

def monstera(L):
    w = 0.82*L
    half = [(0, -L), (0.2*w, -0.93*L), (0.4*w, -0.78*L), (0.5*w, -0.55*L), (0.47*w, -0.32*L), (0.34*w, -0.1*L), (0.16*w, 0.0), (0.04*w, -0.05*L)]
    out = blob(half + [(-x, y) for x, y in half[::-1][1:-1]] + [(0, -0.07*L)])
    cuts = []
    for s_ in (1, -1):
        for k in range(5):
            y0 = -L*(0.2 + 0.15*k) + (0.03*L if s_ < 0 else 0)
            x0 = s_*0.13*w
            ang = math.radians(-18 - 6*k)
            p2 = (x0 + s_*0.7*w*math.cos(ang), y0 + 0.7*w*math.sin(ang))
            cuts.append(taper([(x0, y0), ((x0+p2[0])/2, (y0+p2[1])/2 - 6), p2], 7, 20))
            if k < 4:
                cuts.append(ellipse(s_*0.2*w, y0 - 0.075*L, 0.06*w, 0.018*L, math.degrees(ang)*s_ * -1 if s_ < 0 else math.degrees(ang)))
    mid = taper([(0, -0.02*L), (0, -0.5*L), (0, -0.86*L)], 11, 8)
    leaf = out.difference(unary_union(cuts)).difference(mid)
    stem = taper([(0, -0.04*L), (-4, 0.25*L), (-18, 0.6*L)], 20, 16)
    return unary_union([leaf, stem])

def palm(spine, n, lw):
    pts = catmull(spine, closed=False)
    idx = np.linspace(4, len(pts)-3, n).astype(int)
    blades = [ribbon(spine, 12)]
    for k, i in enumerate(idx):
        (x0, y0), (x1, y1) = pts[i-2], pts[i+2]
        a = math.atan2(y1-y0, x1-x0)
        ln = lw*(0.55 + 0.45*math.sin(math.pi*(k+1)/(n+1)))
        for s in (1, -1):
            b = a + s*math.radians(58)
            tip = (pts[i][0] + ln*math.cos(b), pts[i][1] + ln*math.sin(b))
            mid = (pts[i][0] + 0.55*ln*math.cos(b - s*0.12), pts[i][1] + 0.55*ln*math.sin(b - s*0.12))
            blades.append(taper([pts[i], mid, tip], 24, 8))
    return unary_union(blades)

def w3_a(ctx):
    L = []
    big = T(monstera(430), 735, 650, rot=18, origin=(0, 0))
    small = T(monstera(310), 525, 665, rot=-30, origin=(0, 0))
    L += [(1, small), (0, big)]
    # caustic ripples: the lower part of the leaves is "under water", sliced by wavy gaps
    for k, y in enumerate(range(500, 760, 50)):
        L.append((None, wave_line(-50, 1050, y, 7, 170 + k*8, 9, phase=k*0.9)))
    return L

# ============================== KIDS (symmetric cap) ==============================
def k1_a(ctx):
    L = []
    belly = blob([(300, 610), (470, 570), (690, 505), (870, 440), (935, 470), (925, 590), (820, 680), (600, 715), (400, 705), (300, 670)])
    L.append((0, belly))
    mouth = blob([(555, 572), (640, 632), (770, 640), (870, 595), (915, 525), (880, 548), (780, 590), (665, 600)])
    L.append((1, mouth))
    tongue = ellipse(740, 624, 54, 13, -6)
    L.append((2, tongue))
    eye = circle(745, 335, 66)
    L += [(0, eye), (1, circle(758, 340, 33)), (0, circle(768, 326, 10))]
    for k in range(3):
        x = 520 + k*48
        L.append((1, taper([(x, 330 + k*8), (x - 22, 400 + k*6), (x - 12, 470)], 16, 14)))
    L.append((2, ellipse(655, 455, 38, 22, -10)))
    for x, y, r in [(910, 330, 16), (935, 270, 11), (918, 220, 8)]:
        L.append((0, circle(x, y, r)))
    return L

def k1_teeth(L):
    # white triangle teeth hanging from the upper lip of the mouth (drawn after mouth so gaps are cut)
    pts = [(590, 586), (652, 603), (716, 606), (780, 596), (840, 572), (888, 538)]
    teeth = []
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        mx, my = (x0+x1)/2, (y0+y1)/2
        nx, ny = -(y1-y0), (x1-x0); n = math.hypot(nx, ny); nx, ny = nx/n, ny/n
        teeth.append(poly([(x0 + (x1-x0)*0.12, y0 + (y1-y0)*0.12 - 2), (x1 - (x1-x0)*0.12, y1 - (y1-y0)*0.12 - 2), (mx, my + 34)]))
    return unary_union(teeth)

def k1_a_full(ctx):
    L = k1_a(ctx)
    mouth_i = [i for i, (c, g) in enumerate(L) if c == 1][0]
    mouth = L[mouth_i][1]
    teeth = k1_teeth(None).intersection(mouth.buffer(-4))
    L.insert(mouth_i + 2, (0, teeth))
    return L

def k1_b(ctx):
    return [(c, mirror_x(g, ctx.W)) for c, g in k1_a_full(ctx)]

def tentacle(base, ang, length, w0, curl, sucker_side=1):
    pts = []; x, y = base; a = math.radians(ang)
    n = 22
    for i in range(n):
        pts.append((x, y))
        k = i/n
        a += math.radians(curl * (k**2.2) * 9)
        step = length/n*(1 - 0.35*k)
        x += step*math.cos(a); y += step*math.sin(a)
    g = taper(pts, w0, 10, smooth=True)
    suck = []
    sm = catmull(pts, closed=False)
    for j in range(6, len(sm) - 40, 26):
        (x0, y0), (x1, y1) = sm[j], sm[j+2]
        nx, ny = -(y1-y0), (x1-x0); nn = math.hypot(nx, ny) or 1
        prog = j/len(sm); ww = w0 + (10-w0)*prog
        if ww < 26: continue
        suck.append(circle(x0 + sucker_side*nx/nn*ww*0.18, y0 + sucker_side*ny/nn*ww*0.18, ww*0.16))
    return g, unary_union(suck) if suck else Polygon()

def k2_a(ctx):
    L = []
    head = blob([(640, 90), (760, 120), (820, 230), (800, 360), (720, 420), (600, 420), (520, 350), (520, 220), (560, 130)])
    tents, sucks = [], []
    for base, ang, ln, curl in [((560, 400), 175, 380, -1.6), ((610, 420), 140, 330, 1.7), ((680, 425), 95, 260, -1.8), ((750, 410), 60, 230, 1.8), ((800, 360), 20, 170, -2.4)]:
        g, s = tentacle(base, ang, ln, 62, curl, 1 if curl > 0 else -1)
        tents.append(g); sucks.append(s)
    L.append((0, unary_union([head] + tents)))
    L.append((None, unary_union(sucks)))
    for ex in (615, 725):
        L += [(1, ellipse(ex, 265, 40, 50)), (2, circle(ex + 8, 278, 24)), (1, circle(ex + 15, 268, 8))]
    L.append((2, ribbon([(640, 345), (670, 362), (700, 345)], 13)))
    for x, y, r in [(400, 150, 22), (350, 95, 14), (430, 80, 10), (880, 150, 12)]:
        L.append((1, circle(x, y, r).difference(circle(x - r*0.25, y - r*0.25, r*0.35))))
    return L

def k2_b(ctx):
    L = []
    tents, sucks = [], []
    for base, ang, ln, curl in [((330, 10), 95, 470, -3.2), ((560, -10), 80, 420, 3.0), ((790, 30), 110, 330, -3.4)]:
        g, s = tentacle(base, ang, ln, 70, curl, 1 if curl > 0 else -1)
        tents.append(g); sucks.append(s)
    L.append((0, unary_union(tents)))
    L.append((None, unary_union(sucks)))
    for x, y, r in [(200, 300, 20), (160, 240, 13), (850, 520, 22), (890, 455, 14), (230, 520, 10)]:
        L.append((1, circle(x, y, r).difference(circle(x - r*0.25, y - r*0.25, r*0.35))))
    # little navy fish
    for x, y, s in [(700, 560, 1), (610, 610, 0.75)]:
        f = unary_union([ellipse(0, 0, 40, 22), poly([(-30, 0), (-62, -20), (-62, 20)])])
        L.append((2, T(f, x, y, s=s)))
        L.append((None, circle(x + 20*s, y - 5*s, 5)))
    return L

def k3_a(ctx):
    L = []
    hull = LineString([(330, 430), (720, 430)]).buffer(95, cap_style=1)
    nose = ellipse(720, 430, 140, 95).intersection(box(720, 300, 900, 560))
    body = unary_union([hull, nose])
    tower = LineString([(470, 300), (590, 300)]).buffer(48, cap_style=1).intersection(box(400, 240, 700, 345))
    peri = ribbon([(560, 260), (560, 175), (610, 175)], 20, smooth=False, cap='square')
    lens = poly([(605, 160), (640, 160), (640, 192), (605, 192)])
    fin = poly([(255, 430), (190, 360), (165, 360), (205, 430), (165, 500), (190, 500)])
    L.append((0, unary_union([body, tower, peri, lens, fin])))
    for x in (450, 570, 690):
        L.append((None, circle(x, 430, 45)))
        L.append((1, circle(x, 430, 38).difference(circle(x, 430, 23))))
    L.append((None, ribbon([(330, 505), (760, 505)], 9, smooth=False)))
    # propeller
    L.append((0, ribbon([(225, 430), (165, 430)], 16, smooth=False)))
    for dy in (-38, 38):
        L.append((0, ellipse(152, 430 + dy, 15, 30)))
    for x, y, r in [(140, 340, 18), (178, 282, 12), (205, 225, 19), (255, 182, 10), (840, 250, 13), (868, 212, 9)]:
        L.append((1, circle(x, y, r).difference(circle(x - r*0.28, y - r*0.28, r*0.32)) if r > 14 else circle(x, y, r)))
    for x, y, s in [(760, 640, 1), (850, 600, 0.8), (670, 680, 0.7)]:
        f = unary_union([ellipse(0, 0, 36, 18), poly([(-26, 0), (-54, -18), (-54, 18)])])
        L.append((1, T(f, x, y, s=s)))
        L.append((None, circle(x + 16*s, y - 4*s, 4.5)))
    return L

# ============================== UNISEX (symmetric cap) ==============================
def u1_letters():
    def r(x, y, w, h): return box(x, y, x+w, y+h)
    S = unary_union([r(0, 0, 190, 52), r(0, 0, 56, 130), r(0, 104, 190, 52), r(134, 104, 56, 156), r(0, 208, 190, 52)])
    Wl = poly([(0, 0), (54, 0), (78, 165), (105, 60), (145, 60), (172, 165), (196, 0), (250, 0), (208, 260), (150, 260), (125, 155), (100, 260), (42, 260)])
    I = r(0, 0, 56, 260)
    M = poly([(0, 260), (0, 0), (56, 0), (125, 115), (194, 0), (250, 0), (250, 260), (194, 260), (194, 105), (140, 195), (110, 195), (56, 105), (56, 260)])
    gs = [T(S, 0), T(Wl, 230), T(I, 520), T(M, 616)]
    return [g.buffer(-5).buffer(5) for g in gs]

def u1_a(ctx):
    L = []
    sc, WL = 0.8, 136
    ox, oy = 500 - 0.8*433, 240
    up_box = box(-100, -100, 1000, WL - 7); dn_box = box(-100, WL + 7, 1000, 400)
    for g in u1_letters():
        L.append((0, T(g.intersection(up_box), ox, oy, s=sc, origin=(0, 0))))
        L.append((1, T(T(g.intersection(dn_box), 34, 6), ox, oy, s=sc, origin=(0, 0))))
    wy = oy + sc*WL
    L.append((1, wave_line(70, ox - 30, wy, 7, 110, 11)))
    L.append((1, wave_line(ox + sc*900, 935, wy + 4, 7, 110, 11, phase=1.2)))
    for k, y in enumerate([wy + 140, wy + 190]):
        L.append((1, wave_line(330 + k*60, 700 - k*60, y, 6, 90, 10, phase=k)))
    return L

def depth_field(xs, ys, seed, basin):
    rng = np.random.default_rng(seed)
    X, Y = np.meshgrid(xs, ys)
    bx, by, ang = basin
    c, sn = math.cos(ang), math.sin(ang)
    U = (X-bx)*c + (Y-by)*sn; V = -(X-bx)*sn + (Y-by)*c
    F = 1.3*np.exp(-(U**2/(2*260**2) + V**2/(2*120**2)))          # main trench
    for _ in range(7):                                            # secondary relief
        cx, cy = rng.uniform(-100, 1100), rng.uniform(-50, 900)
        s = rng.uniform(90, 200); a = rng.uniform(-0.45, 0.45)
        F += a*np.exp(-((X-cx)**2 + (Y-cy)**2)/(2*s*s))
    F += 0.12*np.sin(X/150 + Y/310)
    return F

def contours_layers(ctx, seed, basin):
    from skimage import measure
    st = 4.0
    xs = np.arange(-20, 1021, st); ys = np.arange(-20, ctx.H + 21, st)
    F = depth_field(xs, ys, seed, basin)
    inner = ctx.safe.buffer(-10)
    vals = [F[int((y+20)/st), int((x+20)/st)] for x in range(40, 980, 20) for y in range(40, int(ctx.H)-40, 20) if inner.contains(Point(x, y))]
    lo, hi = np.quantile(vals, [0.02, 0.995])
    lv = np.linspace(lo, hi, 16)
    lines = []
    for v in lv[:-1]:
        for c in measure.find_contours(F, v):
            pts = [(xs[0] + p[1]*st, ys[0] + p[0]*st) for p in c]
            if len(pts) > 6: lines.append(LineString(pts).simplify(0.8).buffer(4.5, cap_style=1))
    deep = Polygon()
    Fp = np.pad(F, 1, constant_values=F.min() - 1)
    for c in measure.find_contours(Fp, lv[-1]):
        pts = [(xs[0] + (p[1]-1)*st, ys[0] + (p[0]-1)*st) for p in c]
        if len(pts) > 6: deep = deep.symmetric_difference(Polygon(pts).buffer(0))
    deep = unary_union([p for p in getattr(deep, 'geoms', [deep]) if inner.contains(p)]) if not deep.is_empty else deep
    return [(0, unary_union(lines)), (1, deep)]

def u2_a(ctx): return contours_layers(ctx, 7, (600, 330, 0.5))
def u2_b(ctx): return contours_layers(ctx, 11, (420, 360, -0.4))

def manta2():
    half = [(0, -120), (60, -116), (140, -100), (230, -62), (318, -8), (342, 16), (300, 18), (230, 32), (160, 60), (100, 100), (50, 140), (16, 160)]
    pts = half + [(-x, y) for x, y in half[::-1][:-1]]
    body = blob(pts)
    horns = unary_union([taper([(s*30, -110), (s*42, -140), (s*38, -158)], 30, 20) for s in (1, -1)])
    tail = taper([(0, 140), (6, 280), (-4, 400)], 18, 8)
    whole = unary_union([body, horns])
    band = whole.difference(T(whole, 0, 52)).difference(box(-24, -400, 24, 400))
    ribs = []
    for s in (1, -1):
        for k, (a, b) in enumerate([((24, -40), (300, 10)), ((24, 20), (200, 46)), ((24, 70), (110, 92))]):
            ribs.append(ribbon([(s*a[0], a[1]), (s*(a[0]+b[0])/2, (a[1]+b[1])/2 - 14), (s*b[0], b[1])], 9))
    spine = ribbon([(0, -100), (0, 150)], 9, smooth=False)
    eyes = unary_union([circle(s*48, -92, 8) for s in (1, -1)])
    return [(0, unary_union([whole, tail])), (1, band), (None, unary_union(ribs + [spine, eyes]))]

def u3_a(ctx):
    L = []
    for c, g in manta2(): L.append((c, T(g, 460, 440, s=0.92, rot=-38, origin=(0, 0))))
    for (x, y, s) in [(790, 250, 0.3), (840, 400, 0.24)]:
        for c, g in manta2(): L.append((c, T(g, x, y, s=s, rot=-38, origin=(0, 0))))
    return L

# ============================== registry ==============================
WHITE = ('белый', '#F7F5F0', 'RAL 9016 Traffic white (≈)', 'white')
DESIGNS = [
 dict(slug='w1_jelly_waltz', title='Вальс медуз', segment='Женская', cap='long', logo='adult', logo_pos=(120, 590, 190), logo_ink=1,
      inks=[('лаванда', '#C9B8FF', 'точного RAL нет; ближе всего RAL 4011 Pearl violet (≈, приблизительно)', 'lavender'), WHITE],
      variants=[dict(cap_name='Тёмно-синий', cap_hex='#1F2A4D', cap_ral='RAL 5013 Cobalt blue (≈)'),
                dict(cap_name='Чёрный', cap_hex='#151515', cap_ral='RAL 9005 Jet black'),
                dict(cap_name='Морская волна', cap_hex='#1D5C66', cap_ral='RAL 5021 Water blue (≈, темнее)')],
      sides={'A': w1_a}),
 dict(slug='w2_koi_circle', title='Круг кои', segment='Женская', cap='long', logo='adult', logo_pos=(120, 590, 190), logo_ink=0,
      inks=[('молочно-белый', '#F5F1E6', 'RAL 9010 Pure white (≈)', 'white'), ('золотая охра', '#D9A441', 'RAL 1032 Broom yellow (≈) / RAL 1005 (≈)', 'gold'),
            ('коралл', '#FF6B57', 'RAL 3024 Luminous red (≈, светлее) — проверять по образцу', 'coral')],
      variants=[dict(cap_name='Чёрный', cap_hex='#141414', cap_ral='RAL 9005 Jet black'),
                dict(cap_name='Тёмно-синий', cap_hex='#1B2440', cap_ral='RAL 5011 Steel blue (≈)'),
                dict(cap_name='Изумруд', cap_hex='#11564A', cap_ral='RAL 6016 Turquoise green (≈)')],
      sides={'A': w2_a, 'B': w2_b}),
 dict(slug='w3_ripple_leaves', title='Листья в ряби', segment='Женская', cap='long', logo='adult', logo_pos=(120, 590, 190), logo_ink=1,
      inks=[('мята', '#A8E6CF', 'RAL 6019 Pastel green (≈)', 'mint'), WHITE],
      variants=[dict(cap_name='Хвойный', cap_hex='#20392F', cap_ral='RAL 6009 Fir green (≈)'),
                dict(cap_name='Чёрный', cap_hex='#141414', cap_ral='RAL 9005 Jet black'),
                dict(cap_name='Песочный', cap_hex='#E6DCC4', cap_ral='RAL 1013 Oyster white (≈)', inks=['#2F5D50', '#C8654A'],
                     note='на светлой шапочке краски меняются: зелёный #2F5D50 + терракота #C8654A')],
      sides={'A': w3_a}),
 dict(slug='k1_shark_pup', title='Акулёнок', segment='Детская', cap='sym', logo='kids', logo_pos=(120, 575, 150), logo_ink=1,
      inks=[WHITE, ('тёмно-синий', '#1B2340', 'RAL 5004 Black blue (≈)', 'navy'), ('розовый коралл', '#FF7E79', 'RAL 3015 Light pink (≈, насыщеннее)', 'coral')],
      variants=[dict(cap_name='Акулий серо-голубой', cap_hex='#7A93A8', cap_ral='RAL 5014 Pigeon blue (≈)'),
                dict(cap_name='Голубой', cap_hex='#2F86D1', cap_ral='RAL 5015 Sky blue (≈)'),
                dict(cap_name='Мятный', cap_hex='#7FD6C8', cap_ral='RAL 6027 Light green (≈)')],
      sides={'A': k1_a_full, 'B': k1_b}),
 dict(slug='k2_octo_hug', title='Осьминог Окто', segment='Детская', cap='sym', logo='kids', logo_pos=(120, 575, 150), logo_ink=1,
      inks=[('коралл', '#FF6F61', 'RAL 3022 Salmon pink (≈, ярче)', 'coral'), WHITE, ('тёмно-синий', '#1B2340', 'RAL 5004 Black blue (≈)', 'navy')],
      variants=[dict(cap_name='Бирюзовый', cap_hex='#2EB8C4', cap_ral='RAL 5018 Turquoise blue (≈, светлее)'),
                dict(cap_name='Солнечный жёлтый', cap_hex='#FFD23F', cap_ral='RAL 1023 Traffic yellow (≈)'),
                dict(cap_name='Сиреневый', cap_hex='#B7A5E0', cap_ral='близкого RAL нет — подбор по физическому образцу')],
      sides={'A': k2_a, 'B': k2_b}),
 dict(slug='k3_yellow_sub', title='Жёлтая подлодка', segment='Детская', cap='sym', logo='kids', logo_pos=(120, 575, 150), logo_ink=1,
      inks=[('жёлтый', '#FFD23F', 'RAL 1023 Traffic yellow (≈)', 'yellow'), WHITE],
      variants=[dict(cap_name='Тёмно-синий', cap_hex='#1B2A4A', cap_ral='RAL 5011 Steel blue (≈)'),
                dict(cap_name='Красный', cap_hex='#D7263D', cap_ral='RAL 3020 Traffic red (≈)'),
                dict(cap_name='Королевский синий', cap_hex='#1F5BB5', cap_ral='RAL 5017 Traffic blue (≈)')],
      sides={'A': k3_a}),
 dict(slug='u1_refraction', title='Преломление', segment='Унисекс', cap='sym', logo='adult', logo_pos=(130, 610, 175), logo_ink=0,
      inks=[('белый', '#FFFFFF', 'RAL 9016 Traffic white (≈)', 'white'), ('неоновый лайм', '#E4FF3A', 'флуоресцентного RAL-аналога нет; ближе RAL 1026 Luminous yellow (≈)', 'lime')],
      variants=[dict(cap_name='Чёрный', cap_hex='#121212', cap_ral='RAL 9005 Jet black'),
                dict(cap_name='Антрацит', cap_hex='#2B3035', cap_ral='RAL 7016 Anthracite grey (≈)'),
                dict(cap_name='Ультрамарин', cap_hex='#24379A', cap_ral='RAL 5002 Ultramarine blue (≈, светлее)')],
      sides={'A': u1_a}),
 dict(slug='u2_bathymetry', title='Батиметрия', segment='Унисекс', cap='sym', logo='adult', logo_pos=(130, 610, 175), logo_ink=1,
      inks=[('ледяной голубой', '#8FD3E8', 'RAL 5024 Pastel blue (≈, светлее)', 'ice'), ('белый', '#FFFFFF', 'RAL 9016 Traffic white (≈)', 'white')],
      variants=[dict(cap_name='Глубокий синий', cap_hex='#14213D', cap_ral='RAL 5011 Steel blue (≈)'),
                dict(cap_name='Чёрный', cap_hex='#121212', cap_ral='RAL 9005 Jet black'),
                dict(cap_name='Песочный', cap_hex='#E7DCC6', cap_ral='RAL 1013 Oyster white (≈)', inks=['#1F2A44', '#E8613A'],
                     note='на светлой шапочке: тёмно-синий #1F2A44 + оранжевый #E8613A')],
      sides={'A': u2_a, 'B': u2_b}),
 dict(slug='u3_manta_glide', title='Скат', segment='Унисекс', cap='sym', logo='adult', logo_pos=(130, 610, 175), logo_ink=0,
      inks=[('белый', '#F2F2EE', 'RAL 9016 Traffic white (≈)', 'white'), ('бирюза', '#3FC1C9', 'RAL 5018 Turquoise blue (≈, светлее)', 'turquoise')],
      variants=[dict(cap_name='Тёмно-синий', cap_hex='#0B1F3A', cap_ral='RAL 5011 Steel blue (≈)'),
                dict(cap_name='Чёрный', cap_hex='#121212', cap_ral='RAL 9005 Jet black'),
                dict(cap_name='Антрацит', cap_hex='#2B3035', cap_ral='RAL 7016 Anthracite grey (≈)')],
      sides={'A': u3_a}),
]
