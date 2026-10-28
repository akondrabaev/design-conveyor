"""Recolour an existing design (same Gemini drawing, new cap + ink colours), e.g. light-cap versions.

python3 tools/recolor.py SRC_SLUG NEW_SLUG "Name" '<base json>' '<inks json [[hex,name,ral],...]>' '<variants json>'
Example (used for fem_peony_waves_light):
python3 tools/recolor.py fem_peony_waves fem_peony_waves_light "Шёлковые пионы (светлая)" \\
 '{"hex":"#F4E9E2","name":"Сливочный","ral":"RAL 9001 (≈)"}' \\
 '[["#E08A76","Персиковый коралл","RAL 3022 (≈)"],["#A8475F","Глубокая роза","RAL 3027 (≈)"],["#6B8A68","Шалфей","RAL 6021 (≈)"]]' \\
 '[{"hex":"#DCE7EE","name":"Пудрово-голубой","ral":"RAL 9002 (≈)"},{"hex":"#F1DCE0","name":"Пудрово-розовый","ral":"RAL 3015 (≈)"}]'
Ink order follows the source spec (ink 1 replaces ink 1, ...).
"""
import sys, json, copy, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'lib'))
from PIL import Image
import gemini_gen as gg, gemini_design as gd, build as B, finalize as F, ral
src, slug, name, base, inks, variants = sys.argv[1], sys.argv[2], sys.argv[3], json.loads(sys.argv[4]), json.loads(sys.argv[5]), json.loads(sys.argv[6])
g = os.path.join(ROOT, 'designs', src, '_gemini')
old = json.load(open(f'{g}/spec.json'))
idx, rep = gg.quantize(Image.open(f'{g}/side-A_raw.png').convert('RGB'), old)   # quantize against the ORIGINAL palette
new = copy.deepcopy(old); new.update(slug=slug, name=name, base=base, variants=variants)
for i, (h, n, r) in enumerate(inks): new['inks'][i].update(hex=h, name=n, ral=r)
ral.snap_spec(new)   # new colours on RAL Classic
new.pop('i18n', None)
od = os.path.join(ROOT, 'designs', slug, '_gemini'); os.makedirs(od, exist_ok=True)
json.dump(new, open(f'{od}/spec.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
gg.render_index(idx, new).save(f'{od}/side-A_quantized.png')
D = gd.make_design(new, {'A': idx}); checks = B.build(D)
F.DESC[slug] = (new['concept'], f"{D['segment']} линейка.", 'Перекрашенная версия: тот же рисунок Gemini, новые цвета шапочки и красок.')
F.write_spec(D); print(slug, checks)
