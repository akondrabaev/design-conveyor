"""Generate one design with a segment preset (Gemini art direction + image + BRAND engine).

python3 tools/generate.py --preset kids --slug kids_boy_dino_surf --theme "dinosaurs surfing and diving in big waves, for boys"
Presets: kids | unisex_sport | female | free  (see presets.py). Output: designs/<slug>/
--shape kid_horns | kid_fish | kid_cat | kid_bear | kid_dragon: kids cap with moulded parts (lib/shapes.py);
the art director then designs a character that fits the shape.
"""
import argparse, json, os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'lib')); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gemini_gen as gg
import ral
from presets import PRESETS

ap = argparse.ArgumentParser()
ap.add_argument('--preset', default='free', choices=PRESETS); ap.add_argument('--slug', required=True)
ap.add_argument('--theme', required=True); ap.add_argument('--sides', default='A')
ap.add_argument('--mirror-b', action='store_true', help='two-sided symmetric cap: side B = side A mirrored, no logo')
ap.add_argument('--refs', nargs='*', default=[], help='reference images: what the client roughly means')
ap.add_argument('--shape', default='', help='cap template: sym | long | kid_horns | kid_fish | kid_cat | kid_bear | kid_dragon')
ap.add_argument('--logo', default='', choices=['', 'small', 'styled', 'none'], help='shaped kids caps: small wordmark (default), lettering drawn in the artwork, or none')
a = ap.parse_args()
pr = PRESETS[a.preset]
extra = pr['extra']
if a.shape.startswith('kid_'):
    import shapes
    sh = shapes.SHAPES[a.shape]
    extra += (f"\nCAP SHAPE: {sh['en']} - {sh['hint']}. The cap itself IS the character (like the classic moulded animal caps): "
              "choose the cap colour as the character's skin colour; the inks are only its features (eyes, mouth, teeth, cheeks, "
              "gills, spots, stripes, belly), placed along the cap outline; most of the cap stays plain cap colour. "
              + ("The print is the character's FACE front-on on the front of the cap." if a.shape in shapes.FRONT else
                 "The print is one side of the head: the character in profile looking toward the forehead; the other side is the "
                 "mirror image, so both sides form one head. In image_prompt describe paired features once (one eye, one set of "
                 "gills) and centre objects as HALVES cut by the front edge (half of the glasses = one lens, half of the mouth).")
              + " The image_prompt must describe only the character's features and their placement, no scene or background, "
              "no text. Segment MUST be \"Детская\".")
from PIL import Image as _Image
ref_imgs = [_Image.open(r).convert('RGB') for r in a.refs]
spec = gg.art_direction(a.theme, extra, ref_imgs)
if pr['segment']: spec['segment'] = pr['segment']   # the model sometimes ignores the segment, so force it
spec['slug'] = a.slug
if a.shape:
    spec['shape'] = a.shape
    if a.shape.startswith('kid_'):
        spec['logo'] = a.logo or 'small'
    if a.shape.startswith('kid_'):
        spec['segment'] = 'Детская'
for i in spec['inks']: i['file'] = i['file'].replace('.svg', '')  # model occasionally adds an extension
ral.snap_spec(spec)   # palette on RAL Classic before the image is drawn: print files = specification colours
if a.mirror_b:
    spec['side_b'] = 'mirror'; a.sides = 'A'   # B is derived from A, no second Gemini image
os.makedirs(os.path.join(ROOT, 'designs', a.slug, '_gemini'), exist_ok=True)
p = os.path.join(ROOT, 'designs', a.slug, '_gemini', 'spec.json')
json.dump(spec, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
if spec.get('logo') == 'styled':   # BRAND lettering drawn separately: placed on side A only, never mirrored to B
    import shape_canvas
    from google.genai import types
    print('styled logo:', shape_canvas.styled_logo(spec, a.slug, gg.client(), gg.IMAGE_MODEL, types, os.path.dirname(p)), flush=True)
saved = []
if a.refs:   # keep the references with the design: what it was based on
    import shutil
    rd = os.path.join(os.path.dirname(p), 'refs')
    os.makedirs(rd, exist_ok=True)
    for n, r in enumerate(a.refs, 1):
        saved.append(os.path.join(rd, f'ref_{n}{os.path.splitext(r)[1].lower() or ".png"}'))
        shutil.copy(r, saved[-1])
subprocess.run([sys.executable, os.path.join(ROOT, 'run_gemini.py'), '--spec', p, '--sides', a.sides]
               + (['--refs', *saved] if saved else []), check=True)
