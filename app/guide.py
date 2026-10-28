"""Cap placement guide: the flat print wrapped onto a grey mannequin head, rendered at a pose's head angle.

Cap construction (BRAND): one moulded silicone cap, printed flat on two sides; the sides meet at the head midline
(forehead -> crown -> nape), where there is only a faint moulding line, not a seam.
  side A (with logo) = the wearer's LEFT half. Flat image as seen from the wearer's left: left edge = forehead,
                       right edge = nape, bottom edge = rim over the ear, top arc = the seam.
  side B (optional)  = the wearer's RIGHT half, seen from the wearer's right: right edge = forehead.
                       No side B print -> plain base silicone.
Kids caps with ears / horns (panel='front') are made the other way: front half (side A, the face) and back half
(side B), joined over the crown from ear to ear; flat image of the front: left edge = wearer's right ear, right edge =
wearer's left ear, top arc = the ear-to-ear line over the crown, bottom edge = rim over the forehead.
Each half is unrolled: angle along the join line -> image column, angle away from it -> image row.

Head frame: x = wearer's right, y = forward (face), z = up. yaw rotates the head about z:
0 = facing the camera, -90 = wearer's left side to the camera (face points to frame left), +90 = right side, 180 = back.
"""
import math
import numpy as np
from PIL import Image

AX, AY, AZ = 0.80, 1.00, 1.08          # head ellipsoid semi-axes
NOSE = (0.0, 0.98, -0.28, 0.17)       # small sphere that shows where the face points
AY_LONG_BACK = 1.38                    # long cap: the back half of the head is a longer half-ellipsoid = smooth volume for hair


def ay_of(y, long):
    return np.where(y >= 0, AY, AY_LONG_BACK if long else AY)
SKIN = np.array([196, 199, 204], np.float32)


def rim_z(y, long=False):
    """Cap edge height: above the eyebrows at the front, low at the nape (lower still for the long cap)."""
    nape = -0.68 if long else -0.55
    return np.where(y > 0, -0.14 + 0.44 * y, -0.14 + (-0.14 - nape) * y)


def _columns(mask):
    """Per image column: top and bottom row of the cap silhouette."""
    H, W = mask.shape
    rows = np.arange(H)[:, None]
    has = mask.any(0)
    top = np.where(has, np.where(mask, rows, H).min(0), 0)
    bot = np.where(has, np.where(mask, rows, -1).max(0), H - 1)
    # fill empty edge columns from neighbours
    idx = np.where(has)[0]
    top = np.interp(np.arange(W), idx, top[idx])
    bot = np.interp(np.arange(W), idx, bot[idx])
    return top, bot


class Flat:
    def __init__(self, img, front_left, mode='side'):
        a = np.asarray(img.convert('RGBA'), dtype=np.float32)
        self.rgb, self.mask = a[..., :3], a[..., 3] > 127
        self.rgb[~self.mask] = np.median(self.rgb[self.mask], axis=0)   # edge samples fall back to the cap colour, not black
        self.H, self.W = self.mask.shape
        self.top, self.bot = _columns(self.mask)
        self.front_left = front_left
        self.mode = mode   # 'side' (left/right halves), 'front' or 'back' (front/back halves)

    def sample(self, x, y, z, long):
        """Unrolled cap coordinates instead of a side projection (which squeezes the front of the cap):
        alpha = angle along the midline (front -> crown -> nape), beta = angle away from the midline toward the ear.
        Flat image: alpha -> column (forehead..nape), beta / beta_rim(alpha) -> row (top arc..rim)."""
        if self.mode == 'side':
            al = np.arctan2(z / AZ, y / ay_of(y, long))
            be = np.arcsin(np.clip(np.abs(x) / AX, 0, 1))
        else:   # front/back halves: the join runs from the right ear (alpha 0) over the crown to the left ear (pi)
            al = np.arctan2(z / AZ, x / AX)
            be = np.arcsin(np.clip(np.abs(y) / ay_of(y, long), 0, 1))
        al = np.where(al < -np.pi / 2, al + 2 * np.pi, al)   # below the horizontal at the far end: keep alpha continuous
        a0, a1, al_grid, br_grid = _rim_table(long, self.mode)
        u = np.clip((al - a0) / (a1 - a0), 0, 1)
        if not self.front_left:
            u = 1 - u
        v = np.clip(be / np.maximum(np.interp(al, al_grid, br_grid), 1e-3), 0, 1)
        ci = np.clip(u * (self.W - 1), 0, self.W - 1).astype(int)
        r = np.clip(self.top[ci] + v * (self.bot[ci] - self.top[ci]), 0, self.H - 1).astype(int)
        return self.rgb[r, ci]


_RIM = {}


def _rim_table(long, mode='side'):
    """For each alpha along the join line: the largest beta still above the rim (bisection), and the alpha range
    where the join line is on the cap (the two points where it meets the rim)."""
    key = (long, mode)
    if key in _RIM:
        return _RIM[key]
    al = np.linspace(-np.pi / 2, 3 * np.pi / 2, 2001)

    def above(a, b):
        if mode == 'side':
            y = ay_of(np.cos(a), long) * np.cos(b) * np.cos(a)
        else:
            sgn = 1 if mode == 'front' else -1
            y = sgn * ay_of(np.full_like(a, sgn), long) * np.sin(b)
        z = AZ * np.cos(b) * np.sin(a)
        return z > rim_z(y, long)
    lo, hi = np.zeros_like(al), np.full_like(al, np.pi / 2)
    for _ in range(30):
        mid = (lo + hi) / 2
        ok = above(al, mid)
        lo, hi = np.where(ok, mid, lo), np.where(ok, hi, mid)
    on = above(al, np.zeros_like(al))
    a0, a1 = al[on].min(), al[on].max()
    _RIM[key] = (a0, a1, al, np.where(on, lo, 0))
    return _RIM[key]


def render(flat_a, flat_b, base_hex, yaw, elev=10, long=False, size=900, panel='side'):
    """flat_a / flat_b: PIL RGBA flat caps (base colour + print, transparent outside). flat_b may be None.
    panel='front': side A is the front (face) half, side B the back half (kids caps with ears / horns)."""
    front = panel == 'front'
    A = Flat(flat_a, front_left=True, mode='front' if front else 'side')
    B = Flat(flat_b, front_left=False, mode='back' if front else 'side') if flat_b is not None else None
    base = np.array([int(base_hex.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)], np.float32)

    span = 1.55
    s = np.linspace(-span, span, size)
    S, T = np.meshgrid(s, -s + 0.25)                 # image right, image up (shifted so the cap sits higher)
    e = math.radians(elev)
    f = np.array([0, -math.cos(e), -math.sin(e)])    # camera forward (world), camera sits at +y
    r = np.array([-1.0, 0, 0])                       # image right = world -x
    u = np.array([0, -math.sin(e), math.cos(e)])
    O = S[..., None] * r + T[..., None] * u - 6 * f
    D = np.broadcast_to(f, O.shape)
    # world -> head: rotate by -yaw about z
    p = math.radians(yaw)
    c_, s_ = math.cos(-p), math.sin(-p)

    def rot(v):
        return np.stack([v[..., 0] * c_ - v[..., 1] * s_, v[..., 0] * s_ + v[..., 1] * c_, v[..., 2]], -1)
    o, d = rot(O), rot(D)

    def ellipsoid(o, d, cx, cy, cz, ax, ay, az):
        oc = (o - [cx, cy, cz]) / [ax, ay, az]
        dd = d / [ax, ay, az]
        a = (dd * dd).sum(-1); b = 2 * (oc * dd).sum(-1); c = (oc * oc).sum(-1) - 1
        disc = b * b - 4 * a * c
        t = np.where(disc >= 0, (-b - np.sqrt(np.maximum(disc, 0))) / (2 * a), np.inf)
        return t
    def half(ay, front):
        """Nearest hit on the front (y >= 0) or back (y < 0) half of an ellipsoid with semi-axis ay."""
        oc, dd = o / [AX, ay, AZ], d / [AX, ay, AZ]
        a = (dd * dd).sum(-1); b = 2 * (oc * dd).sum(-1); c = (oc * oc).sum(-1) - 1
        disc = b * b - 4 * a * c
        sq = np.sqrt(np.maximum(disc, 0))
        best = np.full(a.shape, np.inf)
        for tt in ((-b + sq) / (2 * a), (-b - sq) / (2 * a)):
            yy = o[..., 1] + d[..., 1] * tt
            ok = (disc >= 0) & ((yy >= 0) if front else (yy < 0))
            best = np.where(ok & (tt < best), tt, best)
        return best
    t_front, t_back = half(AY, True), half(AY_LONG_BACK if long else AY, False)
    t_head = np.minimum(t_front, t_back)
    nx, ny, nz, nr = NOSE
    t_nose = ellipsoid(o, d, nx, ny, nz, nr * 0.7, nr, nr)
    t_neck = ellipsoid(o, d, 0, -0.1, -1.25, 0.48, 0.5, 0.75)
    t = np.minimum(np.minimum(t_head, t_nose), t_neck)
    hit = np.isfinite(t)
    P = o + d * np.where(hit, t, 0)[..., None]

    # normals in head frame
    ayh = ay_of(P[..., 1], long)
    Nh = P / np.stack([np.full_like(ayh, AX ** 2), ayh ** 2, np.full_like(ayh, AZ ** 2)], -1)
    N = np.where((t == t_head)[..., None], Nh,
                 np.where((t == t_nose)[..., None], (P - [nx, ny, nz]) / [(nr * .7) ** 2, nr ** 2, nr ** 2],
                          (P - [0, -0.1, -1.25]) / [0.48 ** 2, 0.5 ** 2, 0.75 ** 2]))
    N /= np.linalg.norm(N, axis=-1, keepdims=True) + 1e-9
    # light from the camera side, upper left (in head frame)
    L = rot(np.array([[0.35, 0.75, 0.55]]))[0]; L = L / np.linalg.norm(L)
    V = -d[0, 0]
    diff = np.clip((N * L).sum(-1), 0, 1)
    Hh = (L + V); Hh /= np.linalg.norm(Hh)
    spec = np.clip((N * Hh).sum(-1), 0, 1) ** 40

    x, y, z = P[..., 0], P[..., 1], P[..., 2]
    on_cap = hit & (t == t_head) & (z > rim_z(y, long))
    col = np.broadcast_to(SKIN, P.shape).copy()
    left = on_cap & ((y >= 0) if front else (x < 0))    # the half printed with side A
    right = on_cap & ((y < 0) if front else (x >= 0))
    if left.any():
        col[left] = A.sample(x[left], y[left], z[left], long)
    if right.any():
        col[right] = B.sample(x[right], y[right], z[right], long) if B else base
    shade = 0.45 + 0.6 * diff
    out = col * shade[..., None] + (on_cap * spec * 45)[..., None]   # soft sheen: a hard highlight on the midline reads as a ridge
    out = np.where(hit[..., None], out, 255)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
