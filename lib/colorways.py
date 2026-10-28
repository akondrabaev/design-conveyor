"""Colourways: the same stencils printed in different colours. Every cap colour gets ink colours that stay readable on it.

spec['variants'][i]['inks'] = [{'hex', 'ral'}, ...]  (same order as spec['inks'], i.e. stencil 1, 2, 3)
An ink is kept from the main colourway when it contrasts with the variant cap (ΔE2000 >= MIN_CAP); otherwise it is
replaced: first by the main cap colour (a dark cap colour reads well on a light cap and vice versa), then by the RAL
Classic colour closest to the original ink that is far enough from the cap and from the other inks.
"""
import ral

MIN_CAP = 30    # ink vs cap colour
MIN_INK = 18    # inks of one colourway between themselves


def de(a, b):
    return ral.delta_e2000(ral.hex_to_lab(a), ral.hex_to_lab(b))


def fix_inks(cap_hex, inks_hex, prefer=()):
    """inks_hex: wanted ink colours (stencil order). Returns RAL-snapped colours that read on cap_hex."""
    out = []
    for h in inks_hex:
        ok = de(h, cap_hex) >= MIN_CAP and all(de(h, o) >= MIN_INK for o in out)
        if ok:
            out.append(ral.nearest(h)['hex'])
            continue
        cands = [p for p in prefer] + [r['hex'] for r in ral.table()]
        good = [c for c in cands if de(c, cap_hex) >= MIN_CAP + 5 and all(de(c, o) >= MIN_INK for o in out)]
        pref = [c for c in good if c in prefer]
        out.append(pref[0] if pref else min(good, key=lambda c: de(c, h)) if good else h)
    return out


def contrast_report(cap_hex, inks_hex):
    return [round(de(h, cap_hex), 1) for h in inks_hex]


def ensure(spec):
    """Fill / repair the ink colours of every cap variant (in place)."""
    main_inks = [i['hex'] for i in spec['inks']]
    for v in spec.get('variants', []):
        wanted = [c['hex'] for c in v['inks']] if v.get('inks') and len(v['inks']) == len(main_inks) else main_inks
        fixed = fix_inks(v['hex'], wanted, prefer=(spec['base']['hex'],))
        v['inks'] = [dict(hex=h, ral=ral.nearest(h)['code']) for h in fixed]
    return spec
