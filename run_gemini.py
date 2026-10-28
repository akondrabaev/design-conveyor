"""Full Gemini -> stencil pipeline for one design.

python3 run_gemini.py --theme "<тема>" [--sides AB]          # Gemini palette + Gemini image(s)
python3 run_gemini.py --spec spec.json --raw-A a.png [--raw-B b.png]   # reuse a saved spec / image
Outputs: designs/<slug>/: <slug>_mockup.png + <slug>_spec.xlsx (EN/ZH, RAL), SVG/ and PNG/ (print, stencils, layout),
_gemini/ (sources).
"""
import argparse, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'lib'))
from PIL import Image
import gemini_gen as gg
import gemini_design as gd
import build as B
import finalize as F

ap = argparse.ArgumentParser()
ap.add_argument('--theme'); ap.add_argument('--spec'); ap.add_argument('--sides', default='A')
ap.add_argument('--raw-A'); ap.add_argument('--raw-B')
ap.add_argument('--refs', nargs='*', default=[], help='liked example images, style reference for Gemini')
a = ap.parse_args()

spec = json.load(open(a.spec)) if a.spec else gg.art_direction(a.theme)
gdir = os.path.join(B.OUT, spec['slug'], '_gemini'); os.makedirs(gdir, exist_ok=True)
json.dump(spec, open(f'{gdir}/spec.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
import spec_xlsx
spec_xlsx.translations(spec['slug'], spec)   # EN/ZH name for the mockup and the spec (cached in spec.json)
refs = [Image.open(p).convert('RGB') for p in a.refs]

idx, qrep = {}, {}
for s in a.sides:
    raw_path = getattr(a, f'raw_{s}')
    if raw_path:
        raw = Image.open(raw_path).convert('RGB')
    else:
        if s == 'B':
            spec = dict(spec, image_prompt=spec['image_prompt'] + ' Second side of the same cap: same motif family, different arrangement, lighter density.')
        raw = gg.render_print(spec, refs)
    raw.save(f'{gdir}/side-{s}_raw.png')
    idx[s], qrep[s] = gg.quantize(raw, spec)
    gg.render_index(idx[s], spec).save(f'{gdir}/side-{s}_quantized.png')
json.dump(qrep, open(f'{gdir}/quantize_report.json', 'w'), ensure_ascii=False, indent=1)

D = gd.make_design(spec, idx)
checks = B.build(D)
F.DESC[D['slug']] = (spec['concept'], f"{D['segment']} линейка.", 'Рисунок и палитра от Gemini, сведены к ≤3 краскам и переведены в вектор конвейером BRAND.')
F.write_spec(D)
print(json.dumps({'slug': D['slug'], 'checks': checks, 'quantize': qrep}, ensure_ascii=False, indent=1))
