"""Print for a PU (polyurethane-coated fabric) swim cap: one full-colour illustration (heat transfer / DTF), no ink limit.

python3 tools/generate_pu.py --shape pu_kids --slug pu_kids_unicorn --theme "a cute pony with a rainbow"
python3 tools/generate_pu.py --shape pu_adult --slug pu_wave --theme "..."   [--preset kids|unisex_sport|female|free]
Output designs/<slug>/: <slug>_mockup.png, <slug>_spec.xlsx, PNG/<slug>_print.png (transparent, 300 dpi at print size),
PNG/<slug>_side-A_print_transparent.png (print placed in the cap frame), PNG/<slug>_side-A_layout.png, _gemini/.
The BRAND lettering is part of the artwork, drawn in its style (as in app/assets/pu_refs/).
"""
import argparse, base64, io, json, os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'lib')); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage
import gemini_gen as gg, ral, shapes
from core import load_cap, render, geom_d
from presets import PRESETS
from google.genai import types

OUT = os.path.join(ROOT, 'designs')
DPI = 300

BRIEF = """You are the art director for BRAND, a swim cap brand. This design is a FULL-COLOUR print (heat transfer) for a
{cap} - any number of colours, gradients and shading are allowed.
Theme: {theme}
{extra}
The print is one character / illustration placed on the side of the cap, with the brand word BRAND drawn under it as
stylized lettering in the same style (like a cartoon logo). Original characters only: no existing cartoon, film, game or
brand characters. Choose a cap colour that makes the print pop (PU caps: white, black, navy, light blue, pink, red, yellow...).
Return JSON only:
{{"slug": short latin snake_case id, "name": short design name in Russian, "concept": one sentence in Russian,
  "segment": "Детская" | "Унисекс" | "Женская",
  "base": {{"hex": cap colour, "name": Russian colour name}},
  "variants": [{{"hex":..., "name": Russian name}}] (1-2 more cap colours that work with the same print),
  "image_prompt": an English prompt for an image model describing the illustration only (character, pose, style, colours)}}"""

IMAGE = """Full-colour illustration for a heat-transfer print on a {cap}. {prompt}
Under the character, the word BRAND (exactly the letters B-R-A-N-D) as stylized lettering in the same style and palette,
like a cartoon logo. Nothing else written.
Pure plain white background (#FFFFFF): no scenery, no shadow on the ground, no frame. The whole illustration and the lettering
inside the frame with generous margins. Clean, bold outlines so the artwork separates cleanly from the white background.
Square 1:1. The attached images are style and composition references only (a character with BRAND lettering under it): do not copy them."""


def on_white(im):
    im = im.convert('RGBA')
    bg = Image.new('RGB', im.size, 'white')
    bg.paste(im, mask=im.split()[3])
    return bg


def cut_background(im, tol=18):
    """White background -> transparent: near-white pixels connected to the image border (the artwork is outlined,
    so white parts inside the character stay). Returns RGBA cropped to the artwork."""
    a = np.asarray(im.convert('RGB')).astype(np.int16)
    white = (a.min(-1) > 255 - tol) & ((a.max(-1) - a.min(-1)) < 14)
    lab, _ = ndimage.label(white)
    k = 10   # the image model sometimes draws a thin frame at the very edge: seed the background just inside it
    ring = np.concatenate([lab[k], lab[-k - 1], lab[:, k], lab[:, -k - 1]])
    seeds = np.unique(ring[ring > 0])
    bg = np.isin(lab, seeds)
    bg[:k], bg[-k:], bg[:, :k], bg[:, -k:] = True, True, True, True   # the edge band (and any frame line in it) is background
    bg = ndimage.binary_opening(bg, iterations=1)
    alpha = Image.fromarray(((~bg) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8))
    out = im.convert('RGBA')
    out.putalpha(alpha)
    ys, xs = np.where(~bg)
    pad = 8
    return out.crop((max(xs.min() - pad, 0), max(ys.min() - pad, 0), min(xs.max() + pad, a.shape[1]), min(ys.max() + pad, a.shape[0])))


def dominant_colours(art, n=6):
    """Main colours of the artwork (for the spec), largest first."""
    a = np.asarray(art.convert('RGBA').resize((200, round(200 * art.height / art.width))))
    px = a[a[..., 3] > 200][:, :3].astype(np.float32)
    q = Image.fromarray(px.reshape(-1, 1, 3).astype(np.uint8)).quantize(colors=n, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()[:n * 3]
    counts = np.bincount(np.asarray(q).ravel(), minlength=n)
    cols = [('#%02X%02X%02X' % tuple(pal[i * 3:i * 3 + 3]), int(c)) for i, c in enumerate(counts) if c]
    total = sum(c for _, c in cols)
    return [dict(hex=h, share=round(100 * c / total, 1)) for h, c in sorted(cols, key=lambda x: -x[1])]


def print_box(kind, W, H, layout='placement'):
    if layout == 'allover':   # the whole side of the cap, edge to edge
        return W / 2, H / 2, W, H
    cx, cy, bw, bh = shapes.PU_PRINT_BOX
    return cx * W, cy * H, bw * W, bh * H


IMAGE_ALLOVER = """The attached image is the flat template of one side of a {cap}: the silhouette in the cap colour {base}, everything
outside it white. Paint FULL-COLOUR illustration elements spread over the WHOLE silhouette (raster heat transfer: gradients, shading and
rich colours are fine) - it is printed across the full height and length of the cap side.
{prompt}
NO BACKGROUND: do not fill the silhouette with a scene, sky, water or texture. Paint only the elements (characters, objects, plants,
bubbles...), each with a clean outline, placed directly on the plain cap colour {base}, which stays visible between them.
Keep every element at least 4% of the width away from the outline of the silhouette.
Include the word BRAND (exactly the letters B-R-A-N-D) as stylized lettering in the same style, not too big, in the lower front
(left) part. Nothing else written. Do not change the outline, keep everything outside the silhouette pure white, no frame, no border."""


def upload_art(img):
    """A print uploaded by the user, used as is: its own transparency, or a white background cut away; cropped to the artwork."""
    im = img.convert('RGBA')
    if np.asarray(im.split()[3]).min() < 250:   # already transparent
        bb = im.split()[3].getbbox()
        return im.crop(bb) if bb else im
    return cut_background(im.convert('RGB'))


def make_art(raw, spec):
    """Print artwork (RGBA): placement - the character cut from the white background; allover - the image masked by the cap outline."""
    if spec.get('upload'):
        return upload_art(raw)
    if spec.get('pu_layout') != 'allover':
        return cut_background(raw.convert('RGB'))
    import pu   # all-over without background: the elements only, the cap colour shows between them
    return pu.remove_cap_background(raw, spec['base']['hex'], spec['shape'])


def fit(art, bw, bh):
    s = min(bw / art.width, bh / art.height)
    return art.resize((max(1, round(art.width * s)), max(1, round(art.height * s))), Image.LANCZOS)


def svg_img(im):
    buf = io.BytesIO()
    im.save(buf, 'PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()


def build(spec, art):
    """Print file, layout, mockup and hero of a PU design. The print is placed by lib/pu.py (layout + the user's move /
    scale from the constructor, spec['pu_place']) and cut to the outline minus a small gap."""
    import pu
    slug, kind = spec['slug'], spec['shape']
    od = os.path.join(OUT, slug)
    pngd = os.path.join(od, 'PNG')
    os.makedirs(pngd, exist_ok=True)
    cap_d, outline, W, H = load_cap(kind)
    size = shapes.main_size(kind)
    mm_per_px = size['w'] * 10 / 1000
    layout, place = spec.get('pu_layout', 'placement'), spec.get('pu_place')

    # 1. print file: the placed print at 300 dpi, cropped to the artwork; its position on the cap in mm
    full_px = round(W * mm_per_px / 25.4 * DPI)
    logo = spec.get('pu_logo')
    if logo and logo.get('kind') == 'styled':   # the lettering file lives in the design's _gemini/
        logo = dict(logo, path=os.path.join(OUT, slug, '_gemini', logo.get('file', 'logo_pu.png')))
    big = pu.frame(art, kind, layout, place, full_px, logo)
    bbox = big.split()[3].getbbox() or (0, 0, big.width, big.height)
    big.crop(bbox).save(f'{pngd}/{slug}_print.png', dpi=(DPI, DPI))
    k = W / full_px                                   # 300-dpi px -> template px
    x0, y0, x1, y1 = (v * k for v in bbox)
    print_mm = ((x1 - x0) * mm_per_px, (y1 - y0) * mm_per_px)
    px = (bbox[2] - bbox[0], bbox[3] - bbox[1])
    # 2. print in the cap frame (3000 px), the input of mockups, the 3-D guide and on-model photos
    pu.frame(art, kind, layout, place, 3000, logo).save(f'{pngd}/{slug}_side-A_print_transparent.png')
    href = svg_img(pu.frame(art, kind, layout, place, 2000, logo))
    img = f'<image x="0" y="0" width="{W:.0f}" height="{H:.0f}" xlink:href="{href}"/>'
    seams = (f'<path d="{geom_d(outline.buffer(-70))}" fill="none" stroke="#000" stroke-opacity="0.18" stroke-width="3" stroke-dasharray="9 7"/>'
             f'<line x1="30" y1="{H - 38:.0f}" x2="{W - 30}" y2="{H - 38:.0f}" stroke="#000" stroke-opacity="0.2" stroke-width="3" stroke-dasharray="9 7"/>')
    NS = 'xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"'
    FONT = "Arial, 'Microsoft YaHei', 'DejaVu Sans'"
    # 3. layout sheet: cap outline, print area (outline minus the gap), print, dimensions
    PAD, PT = 70, 110
    gap_mm = pu.GAP * mm_per_px
    lines_top = [f'{slug} · {shapes.SHAPES[kind]["en"]} {size["w"] * 10:.0f} x {size["h"] * 10:.0f} mm · side A (wearer\'s left)',
                 f'{shapes.SHAPES[kind]["zh"]} {size["w"] * 10:.0f}×{size["h"] * 10:.0f}毫米 · A面（佩戴者左侧）']
    notes = [f'Full-colour print {print_mm[0]:.0f} x {print_mm[1]:.0f} mm, {x0 * mm_per_px:.0f} mm from the front edge, {y0 * mm_per_px:.0f} mm from the top.',
             f'{gap_mm:.1f} mm gap to the cap edge (red dashed line). Grey dashed = seams.',
             f'全彩印刷 {print_mm[0]:.0f}×{print_mm[1]:.0f}毫米，距前缘{x0 * mm_per_px:.0f}毫米、距顶部{y0 * mm_per_px:.0f}毫米。',
             f'距帽边{gap_mm:.1f}毫米（红色虚线）。灰色虚线为缝线。']
    sheet = (f'<svg {NS} width="{W + 2 * PAD:.0f}" height="{H + PT + PAD + 130:.0f}"><rect width="100%" height="100%" fill="#fff"/>'
             f'<g transform="translate({PAD},{PT})"><path d="{cap_d}" fill="{spec["base"]["hex"]}" stroke="#9aa3ad" stroke-width="2"/>{seams}{img}'
             f'<path d="{geom_d(outline.buffer(-pu.GAP))}" fill="none" stroke="#fff" stroke-width="5"/>'   # readable on any cap colour
             f'<path d="{geom_d(outline.buffer(-pu.GAP))}" fill="none" stroke="#FF4D4F" stroke-width="2.5" stroke-dasharray="10 7"/></g>'
             + ''.join(f'<text x="{PAD}" y="{34 + 28 * i}" font-family="{FONT}" font-size="20" fill="#333">{t}</text>' for i, t in enumerate(lines_top))
             + ''.join(f'<text x="{PAD}" y="{H + PT + 40 + 26 * i:.0f}" font-family="{FONT}" font-size="17" fill="#666">{t}</text>' for i, t in enumerate(notes))
             + '</svg>')
    render(sheet, f'{pngd}/{slug}_side-A_layout.png')
    # 4. mockup in the cap colours + hero
    caps = [spec['base']] + spec.get('variants', [])[:2]
    sheen = ('<defs><radialGradient id="sh" cx="0.35" cy="0.18" r="0.75"><stop offset="0" stop-color="#fff" stop-opacity="0.25"/>'
             '<stop offset="0.6" stop-color="#fff" stop-opacity="0.03"/><stop offset="1" stop-color="#000" stop-opacity="0.16"/></radialGradient></defs>')

    def cell(hex_):
        return f'<path d="{cap_d}" fill="{hex_}"/>{seams}{img}<path d="{cap_d}" fill="url(#sh)"/>'
    gap = 60
    body = ''.join(f'<g transform="translate({gap},{100 + i * (H + 110):.0f})">{cell(c["hex"])}</g>'
                   f'<text x="{gap + W / 2}" y="{100 + i * (H + 110) + H + 45:.0f}" text-anchor="middle" font-family="{FONT}" font-size="30" fill="#222">{c.get("ral", c["hex"])}</text>'
                   for i, c in enumerate(caps))
    title = (spec.get('i18n', {}).get('en', {}).get('name') or slug)
    mock = (f'<svg {NS} width="{W + 2 * gap:.0f}" height="{100 + len(caps) * (H + 110):.0f}">{sheen}<rect width="100%" height="100%" fill="#DADDE1"/>'
            f'<text x="{gap}" y="62" font-family="{FONT}" font-weight="bold" font-size="40" fill="#1d1d1d">{title} - mockup / 效果图</text>{body}</svg>')
    render(mock, f'{od}/{slug}_mockup.png', scale=0.6)
    render(f'<svg {NS} width="{W:.0f}" height="{H:.0f}">{sheen}{cell(spec["base"]["hex"])}</svg>', f'{od}/_hero.png', scale=0.5)
    checks = {'A': dict(print='full_colour', layout=layout, place=place, print_mm=[round(v) for v in print_mm], print_px=list(px),
                        print_pos_mm=[round(x0 * mm_per_px), round(y0 * mm_per_px)], gap_mm=round(gap_mm, 1), dpi=DPI,
                        inside_safe_ok=True, inks_ok=True, gap_ok=True, inks_used=None, min_gap_between_inks_px=None)}
    json.dump(checks, open(f'{od}/_checks.json', 'w', encoding='utf-8'), indent=1)
    return checks


def snap_caps(spec):
    """Cap colours on RAL Classic (the print itself is full colour and is not snapped)."""
    for c in [spec['base']] + spec.get('variants', []):
        r = ral.nearest(c['hex'])
        c.update(hex_src=c['hex'], hex=r['hex'], ral=r['code'])


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--shape', required=True, choices=shapes.PU)
    ap.add_argument('--slug', required=True)
    ap.add_argument('--theme', default='')
    ap.add_argument('--preset', default='')
    ap.add_argument('--refs', nargs='*', default=[], help='reference images: what the client roughly means')
    ap.add_argument('--layout', default='placement', choices=['placement', 'allover'],
                    help='placement: character with BRAND lettering; allover: full-colour print over the whole cap side')
    ap.add_argument('--rebuild', action='store_true', help='rebuild from _gemini/raw.png without calling Gemini')
    a = ap.parse_args()
    gdir = os.path.join(OUT, a.slug, '_gemini')
    os.makedirs(gdir, exist_ok=True)
    cap_txt = 'kids PU swim cap (coated fabric)' if a.shape == 'pu_kids' else 'adult PU swim cap (coated fabric)'
    if a.rebuild:
        spec = json.load(open(f'{gdir}/spec.json', encoding='utf-8'))
        raw = Image.open(f'{gdir}/raw.png')
        raw = raw.convert('RGBA') if spec.get('upload') else raw.convert('RGB')
    else:
        preset = a.preset or ('kids' if a.shape == 'pu_kids' else 'free')
        extra = PRESETS.get(preset, PRESETS['free'])['extra'].replace('Segment MUST be', 'Segment should be')
        if a.layout == 'allover':
            extra += ("\nLAYOUT: an ALL-OVER print over the entire side of the cap, but WITHOUT a background: several elements "
                      "(characters, objects, plants...) spread across the whole side on the plain cap colour, not a single sticker and "
                      "not a filled scene. image_prompt describes the elements and their arrangement only.")
        client_refs = [on_white(Image.open(r)) for r in a.refs]
        if a.refs:   # keep the references with the design
            import shutil
            os.makedirs(f'{gdir}/refs', exist_ok=True)
            for n, r in enumerate(a.refs, 1):
                shutil.copy(r, f'{gdir}/refs/ref_{n}{os.path.splitext(r)[1].lower() or ".png"}')
        r = gg.client().models.generate_content(
            model=gg.TEXT_MODEL, contents=[BRIEF.format(cap=cap_txt, theme=a.theme, extra=extra) + ('\n' + gg.REF_NOTE if client_refs else ''), *client_refs],
            config=types.GenerateContentConfig(response_mime_type='application/json', temperature=1.0))
        spec = json.loads(r.text)
        spec.update(slug=a.slug, shape=a.shape, print='full_colour', logo='styled', pu_layout=a.layout)
        if a.shape == 'pu_kids':
            spec['segment'] = 'Детская'
        snap_caps(spec)
        print('art direction:', spec['name'], '-', spec['image_prompt'][:120], flush=True)
        ref_dir = os.path.join(ROOT, 'app', 'assets', 'pu_refs')   # optional examples of your PU prints (style reference)
        refs = [on_white(Image.open(os.path.join(ref_dir, f))) for f in sorted(os.listdir(ref_dir))
                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))][:3] if os.path.isdir(ref_dir) else []
        refs += client_refs   # the client's references after the BRAND style examples
        raw = None
        for _ in range(2):
            if a.layout == 'allover':   # drawn on the cap silhouette, like the shaped silicone caps
                try:
                    import shape_canvas
                    tpl, aspect = shape_canvas.canvas(spec)
                    rr = gg.client().models.generate_content(
                        model=gg.IMAGE_MODEL, contents=[IMAGE_ALLOVER.format(cap=cap_txt, base=spec['base']['hex'], prompt=spec['image_prompt'])
                                                        + ('\nThe first image is the template to paint on; the others are the client\'s '
                                                           'references for the idea only.' if client_refs else ''), tpl, *client_refs],
                        config=types.GenerateContentConfig(response_modalities=['IMAGE'], image_config=types.ImageConfig(aspect_ratio=aspect, image_size='2K')))
                    part = next(p for p in rr.candidates[0].content.parts if p.inline_data is not None)
                    raw = shape_canvas.crop_back(Image.open(io.BytesIO(part.inline_data.data)).convert('RGB'), spec)
                    break
                except Exception as e:
                    print('image attempt failed:', str(e)[:200], flush=True)
                    continue
            try:
                rr = gg.client().models.generate_content(
                    model=gg.IMAGE_MODEL, contents=[IMAGE.format(cap=cap_txt, prompt=spec['image_prompt']) + (
                        f"\nThe last {len(client_refs)} attached image(s) are the client's references for the idea - follow their idea and style, do not copy."
                        if client_refs else ''), *refs],
                    config=types.GenerateContentConfig(response_modalities=['IMAGE'], image_config=types.ImageConfig(aspect_ratio='1:1', image_size='2K')))
                part = next(p for p in rr.candidates[0].content.parts if p.inline_data is not None)
                raw = Image.open(io.BytesIO(part.inline_data.data)).convert('RGB')
                break
            except Exception as e:
                print('image attempt failed:', str(e)[:200], flush=True)
        if raw is None:
            raise SystemExit('Gemini returned no image')
        raw.save(f'{gdir}/raw.png')
    art = make_art(raw, spec)
    spec['inks'] = [dict(hex=c['hex'], name='', role='print colour', share=c['share']) for c in dominant_colours(art)]
    json.dump(spec, open(f'{gdir}/spec.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    import spec_xlsx
    spec_xlsx.translations(a.slug, spec)
    checks = build(spec, art)
    spec_xlsx.write(a.slug)
    print(json.dumps({'slug': a.slug, 'checks': checks}, ensure_ascii=False))
