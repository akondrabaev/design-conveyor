"""Make a symmetric two-sided version of an existing design: side B = side A mirrored, no logo on B. No Gemini call.

python3 tools/mirror_b.py SRC_SLUG [NEW_SLUG]      # default NEW_SLUG = SRC_SLUG + '_ab'
Uses designs/<src>/_gemini/side-A_quantized.png (already in the design's own palette, so recoloured designs work too).
"""
import sys, json, copy, os, shutil
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'lib'))
import numpy as np
from PIL import Image
import gemini_design as gd, build as B, finalize as F

src = sys.argv[1]
slug = sys.argv[2] if len(sys.argv) > 2 else src + '_ab'
g = os.path.join(ROOT, 'designs', src, '_gemini')
spec = json.load(open(f'{g}/spec.json', encoding='utf-8'))

# quantized image -> ink index map (0 = base, 1..n = inks), nearest palette colour
pal = np.array([[int(h.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)]
                for h in [spec['base']['hex']] + [k['hex'] for k in spec['inks']]], dtype=np.int32)
q = np.asarray(Image.open(f'{g}/side-A_quantized.png').convert('RGB'), dtype=np.int32)
idx = np.zeros(q.shape[:2], np.uint8)
best = np.full(q.shape[:2], 1 << 30)
for n, c in enumerate(pal):
    d = ((q - c) ** 2).sum(-1)
    idx[d < best] = n
    best = np.minimum(best, d)

new = copy.deepcopy(spec)
new.update(slug=slug, name=spec['name'] + ' (2 стороны)', side_b='mirror')
od = os.path.join(ROOT, 'designs', slug, '_gemini')
os.makedirs(od, exist_ok=True)
json.dump(new, open(f'{od}/spec.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
for f in ('side-A_raw.png', 'side-A_quantized.png', 'quantize_report.json'):
    if os.path.exists(f'{g}/{f}'):
        shutil.copy(f'{g}/{f}', f'{od}/{f}')
D = gd.make_design(new, {'A': idx})
checks = B.build(D)
F.DESC[slug] = (new['concept'], f"{D['segment']} линейка.",
                f'Симметричная двусторонняя версия «{spec["name"]}»: сторона B — зеркало стороны A без логотипа.')
F.write_spec(D)
print(slug, json.dumps(checks, ensure_ascii=False))
