"""RAL Classic palette: nearest RAL colour for any HEX by CIEDE2000.

Data: lib/ral_classic.json (code, English name, Chinese name, sRGB HEX), from the npm package ral-colors 1.0.1 (MIT),
without pearl and luminous colours (not available as silicone print inks). Screen HEX values are approximations of
the physical RAL cards: final colours are approved on physical samples.
"""
import json, math, os

_TABLE = None
# ΔE2000 grades used in the spec
EXACT, CLOSE = 1.0, 3.0


def table():
    global _TABLE
    if _TABLE is None:
        rows = json.load(open(os.path.join(os.path.dirname(__file__), 'ral_classic.json'), encoding='utf-8'))
        for r in rows:
            r['lab'] = hex_to_lab(r['hex'])
        _TABLE = rows
    return _TABLE


def hex_to_lab(h):
    h = h.lstrip('#')
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    x = (0.4124564 * lin[0] + 0.3575761 * lin[1] + 0.1804375 * lin[2]) / 0.95047
    y = (0.2126729 * lin[0] + 0.7151522 * lin[1] + 0.0721750 * lin[2]) / 1.0
    z = (0.0193339 * lin[0] + 0.1191920 * lin[1] + 0.9503041 * lin[2]) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e2000(lab1, lab2):
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    C1, C2 = math.hypot(a1, b1), math.hypot(a2, b2)
    Cm = (C1 + C2) / 2
    G = 0.5 * (1 - math.sqrt(Cm ** 7 / (Cm ** 7 + 25 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360
    h2p = math.degrees(math.atan2(b2, a2p)) % 360
    dLp, dCp = L2 - L1, C2p - C1p
    if C1p * C2p == 0:
        dhp = 0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    else:
        dhp = h2p - h1p - 360 if h2p > h1p else h2p - h1p + 360
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2))
    Lpm, Cpm = (L1 + L2) / 2, (C1p + C2p) / 2
    if C1p * C2p == 0:
        hpm = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hpm = (h1p + h2p) / 2
    else:
        hpm = (h1p + h2p + 360) / 2 if h1p + h2p < 360 else (h1p + h2p - 360) / 2
    T = (1 - 0.17 * math.cos(math.radians(hpm - 30)) + 0.24 * math.cos(math.radians(2 * hpm))
         + 0.32 * math.cos(math.radians(3 * hpm + 6)) - 0.20 * math.cos(math.radians(4 * hpm - 63)))
    dtheta = 30 * math.exp(-((hpm - 275) / 25) ** 2)
    Rc = 2 * math.sqrt(Cpm ** 7 / (Cpm ** 7 + 25 ** 7))
    Sl = 1 + 0.015 * (Lpm - 50) ** 2 / math.sqrt(20 + (Lpm - 50) ** 2)
    Sc, Sh = 1 + 0.045 * Cpm, 1 + 0.015 * Cpm * T
    Rt = -math.sin(math.radians(2 * dtheta)) * Rc
    return math.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh))


def nearest(hex_, exclude=()):
    """-> dict(code, name_en, name_zh, hex, de) of the closest RAL Classic colour, skipping codes in exclude."""
    lab = hex_to_lab(hex_)
    best = min((r for r in table() if r['code'] not in exclude), key=lambda r: delta_e2000(lab, r['lab']))
    return dict(code=best['code'], name_en=best['name_en'], name_zh=best['name_zh'], hex=best['hex'],
                de=round(delta_e2000(lab, best['lab']), 1))


def snap_spec(spec):
    """Move the design palette onto RAL Classic: base, inks and cap variants get the nearest RAL colour,
    the inks of one design never share a RAL code. Keeps the original HEX in 'hex_src'. Changes spec in place."""
    used = set()
    for c in [spec['base']] + list(spec['inks']):
        r = nearest(c['hex'], exclude=used)
        used.add(r['code'])
        c.update(hex_src=c['hex'], hex=r['hex'], ral=r['code'])
    for v in spec.get('variants', []):
        r = nearest(v['hex'], exclude={spec['base']['ral']})
        v.update(hex_src=v['hex'], hex=r['hex'], ral=r['code'])
        if v.get('inks'):   # the model gives plain hex strings per ink
            v['inks'] = [dict(hex=(i['hex'] if isinstance(i, dict) else i)) for i in v['inks']]
    import colorways
    colorways.ensure(spec)   # every cap colour gets inks that read on it
    spec['palette'] = 'RAL Classic'
    return spec


def grade(de):
    return 'exact' if de <= EXACT else 'close' if de <= CLOSE else 'approx'
