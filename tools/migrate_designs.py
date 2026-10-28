"""Rebuild existing designs in the current output format without calling the image model:
SVG/ and PNG/ folders, mockup + <slug>_spec.xlsx (EN/ZH, RAL) in the root, old root files and *_spec.md removed.

python3 tools/migrate_designs.py            # all designs
python3 tools/migrate_designs.py slug ...   # selected designs
Source: designs/<slug>/_gemini/side-*_quantized.png (already in the design's own palette). Colours are kept;
the spec shows the nearest RAL Classic colour and ΔE2000 for each of them.
"""
import glob, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'lib'))
import numpy as np
from PIL import Image
import gemini_design as gd, build as B, finalize as F


def index_from_quantized(path, spec):
    pal = np.array([[int(h.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)]
                    for h in [spec['base']['hex']] + [k['hex'] for k in spec['inks']]], dtype=np.int32)
    q = np.asarray(Image.open(path).convert('RGB'), dtype=np.int32)
    idx = np.zeros(q.shape[:2], np.uint8)
    best = np.full(q.shape[:2], np.iinfo(np.int32).max, np.int32)
    for n, c in enumerate(pal):   # one palette colour at a time: ~30 MB instead of a 300 MB 4-D array
        d = ((q - c) ** 2).sum(-1)
        idx[d < best] = n
        np.minimum(best, d, out=best)
    return idx


def migrate(slug):
    od = os.path.join(B.OUT, slug)
    g = os.path.join(od, '_gemini')
    spec = json.load(open(f'{g}/spec.json', encoding='utf-8'))
    if spec.get('print') == 'full_colour':   # PU caps: rebuilt by their own tool
        import subprocess
        subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'generate_pu.py'), '--shape', spec['shape'],
                        '--slug', slug, '--rebuild'], check=True, stdout=subprocess.DEVNULL)
        return {'A': {'gap_ok': True}}
    sides = ['A'] if spec.get('side_b') == 'mirror' else [s for s in 'AB' if os.path.exists(f'{g}/side-{s}_quantized.png')]
    idx = {s: index_from_quantized(f'{g}/side-{s}_quantized.png', spec) for s in sides}
    # old layout: production files in the root -> removed, rebuilt into SVG/ and PNG/
    for f in glob.glob(f'{od}/{slug}_side-*') + glob.glob(f'{od}/{slug}_spec.md'):
        os.remove(f)
    import spec_xlsx
    spec_xlsx.translations(slug, spec)   # EN name on the mockup
    D = gd.make_design(spec, idx)
    checks = B.build(D)
    F.write_spec(D)
    return checks


if __name__ == '__main__':
    slugs = sys.argv[1:] or sorted(d for d in os.listdir(B.OUT) if os.path.exists(os.path.join(B.OUT, d, '_gemini', 'spec.json')))
    for s in slugs:
        try:
            c = migrate(s)
            print(s, 'ok', {k: v.get('gap_ok') for k, v in c.items()}, flush=True)
        except Exception as e:
            print(s, 'FAILED', str(e)[:200], flush=True)
