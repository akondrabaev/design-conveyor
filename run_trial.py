"""One trial design: Gemini art direction -> Gemini image -> quantized inks -> preview sheet.
Usage: python3 run_trial.py "<theme>" <slug>
"""
import json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import gemini_gen as gg

theme, slug = sys.argv[1], sys.argv[2]
out = os.path.join(os.path.dirname(__file__), "trials", slug)
os.makedirs(out, exist_ok=True)

spec = gg.art_direction(theme)
json.dump(spec, open(f"{out}/spec.json", "w"), ensure_ascii=False, indent=2)
raw = gg.render_print(spec)
raw.save(f"{out}/gemini_raw.png")
idx, rep = gg.quantize(raw, spec)
np.save(f"{out}/ink_index.npy", idx)
flat = gg.render_index(idx, spec)
flat.save(f"{out}/print_flat.png")
for n, m in enumerate(gg.ink_masks(idx, len(spec["inks"])), 1):
    m.save(f"{out}/ink{n}_mask.png")
json.dump(rep, open(f"{out}/report.json", "w"), ensure_ascii=False, indent=2)

# provisional cap mockup: generic dome until the real silhouettes from the archive are back
W, H = 1200, 900
cap = Image.new("L", (W, H), 0)
d = ImageDraw.Draw(cap)
d.chord([60, 60, W - 60, 2 * H - 260], 180, 360, fill=255)
d.rectangle([60, H - 200, W - 60, H - 130], fill=255)
cap = cap.filter(ImageFilter.GaussianBlur(2))
print_img = flat.resize((W, H))
yy, xx = np.mgrid[0:H, 0:W]
shade = 0.82 + 0.18 * np.clip(1 - (((xx - W * 0.38) / W) ** 2 + ((yy - H * 0.3) / H) ** 2) * 2.2, 0, 1)
arr = (np.asarray(print_img).astype(np.float32) * shade[..., None]).clip(0, 255).astype(np.uint8)
bg = Image.new("RGB", (W, H), (242, 240, 236))
mock = Image.composite(Image.fromarray(arr), bg, cap)
mock.save(f"{out}/mockup.png")

# preview sheet
font_p = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
f1 = ImageFont.truetype(font_p, 34) if os.path.exists(font_p) else ImageFont.load_default()
f2 = ImageFont.truetype(font_p, 24) if os.path.exists(font_p) else ImageFont.load_default()
sheet = Image.new("RGB", (2460, 1300), (250, 249, 246))
sd = ImageDraw.Draw(sheet)
sd.text((40, 30), f"{spec['name']} — {spec['concept']}", fill=(20, 20, 20), font=f1)
for i, (im, label) in enumerate([(raw, "Gemini, исходник"), (flat, "После сведения к краскам"), (mock, "Мокап (временный силуэт)")]):
    t = im.copy(); t.thumbnail((780, 600))
    x = 40 + i * 800
    sheet.paste(t, (x, 110)); sd.text((x, 720), label, fill=(90, 90, 90), font=f2)
sw = [("Основа: " + spec["base"]["name"], spec["base"]["hex"], None)] + [
    (f"Краска {n}: {k['name']}", k["hex"], rep["inks"][n]) for n, k in enumerate(spec["inks"], 1)]
for i, (name, hx, r) in enumerate(sw):
    x = 40 + i * 600
    sd.rectangle([x, 790, x + 120, 910], fill=hx, outline=(180, 180, 180))
    sd.text((x + 140, 800), name, fill=(20, 20, 20), font=f2)
    sd.text((x + 140, 840), hx, fill=(90, 90, 90), font=f2)
    if r:
        sd.text((x + 140, 875), f"покрытие {r['coverage_pct']}%, тонкое убрано {r['thin_removed_pct']}%", fill=(90, 90, 90), font=f2)
sd.text((40, 960), f"Красок: {rep['ink_count']} (≤3)  ·  размер {rep['size'][0]}×{rep['size'][1]}  ·  мин. толщина {gg.MIN_STROKE_PX} px", fill=(20, 20, 20), font=f2)
sheet.save(f"{out}/preview.png")
print(json.dumps({"spec": spec, "report": rep}, ensure_ascii=False, indent=1))
