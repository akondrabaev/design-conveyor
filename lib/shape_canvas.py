"""Shaped kids caps: the image model draws ON the cap template, so the character is composed along the cap outline.

canvas(spec)    -> (template image for Gemini, aspect ratio string, crop box of the cap frame inside the template)
crop_back(img, spec) -> the generated image cut back to the cap frame (same frame as lib/cap_<kind>.txt), so the
                        pipeline's cover-fit maps it 1:1 onto the template
styled_logo(spec, slug) -> BRAND lettering in the style of the character, traced to a one-ink vector logo that the
                        engine places on side A only (never mirrored to side B)
"""
import io, os
import numpy as np
from PIL import Image, ImageDraw

import shapes
from core import load_cap, load_body, geom_d

ASPECTS = {'1:1': 1.0, '5:4': 1.25, '4:3': 4 / 3, '3:2': 1.5, '16:9': 16 / 9, '4:5': 0.8, '3:4': 0.75}
SIDE = 1536   # long side of the template in px


def _hex(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _tint(rgb, k):
    return tuple(round(c + (255 - c) * k) for c in rgb)


def _layout(kind):
    _, outline, W, H = load_cap(kind)
    ar = W / H
    name = min(ASPECTS, key=lambda a: abs(np.log(ASPECTS[a] / ar)))
    a = ASPECTS[name]
    CW, CH = (W, W / a) if a <= ar else (H * a, H)       # padded canvas in template units
    s = SIDE / max(CW, CH)
    ox, oy = (CW - W) / 2, (CH - H) / 2
    return name, (round(CW * s), round(CH * s)), s, (ox, oy), (W, H)


def _poly(draw, geom, s, ox, oy, fill):
    gs = getattr(geom, 'geoms', [geom])
    for g in gs:
        draw.polygon([((x + ox) * s, (y + oy) * s) for x, y in g.exterior.coords], fill=fill)
        for r in g.interiors:
            draw.polygon([((x + ox) * s, (y + oy) * s) for x, y in r.coords], fill=(255, 255, 255))


def canvas(spec):
    kind = spec['shape']
    name, size, s, (ox, oy), _ = _layout(kind)
    base = _hex(spec['base']['hex'])
    im = Image.new('RGB', size, (255, 255, 255))
    d = ImageDraw.Draw(im)
    _poly(d, load_cap(kind)[1], s, ox, oy, base)                # the whole silhouette, moulded parts included, is printable
    return im, name


def crop_back(img, spec):
    name, size, s, (ox, oy), (W, H) = _layout(spec['shape'])
    k = img.width / size[0]
    box = (round(ox * s * k), round(oy * s * k), round((ox + W) * s * k), round((oy + H) * s * k))
    return img.crop(box)


def layout_text(spec):
    kind = spec['shape']
    sh = shapes.SHAPES[kind]
    logo = spec.get('logo', 'small')
    calm = ('' if logo == 'none' else
            ' Keep a small area plain cap colour for the logo: ' +
            ('at the bottom centre under the face.' if kind in shapes.FRONT else 'the lower RIGHT (back) corner of the body.'))
    if kind in shapes.FRONT:
        where = ("This is the FRONT of the cap, worn over the forehead; the two moulded " + sh['parts'] + " stand on top of the head. "
                 "Draw the character's FACE front-on and symmetric, filling the whole silhouette: two big eyes in the upper middle, "
                 "nose/snout in the centre, the mouth/muzzle in the lower middle reaching the bottom edge, cheeks / stripes / patches "
                 "running into the left and right edges, the " + sh['parts'] + " coloured.")
    else:
        where = ("This is ONE side of the cap seen from the side of the head: the LEFT edge is the forehead, the RIGHT edge is the back "
                 "of the head, the top edge is the midline over the crown (the other side of the cap is the mirror image, so the "
                 "character must read as one head from both sides). The LEFT edge of the silhouette is the CENTRE LINE of the "
                 "face. Paired features (eye, cheek, gills, fin) are drawn ONCE on this side. Features that sit on the centre of the "
                 "face (glasses, mask, nose, mouth, eyebrows, a forehead stripe) are drawn only as their HALF, cut by the left edge, "
                 "so the mirrored other side completes them: e.g. ONE lens of the glasses touching the left edge, never two lenses. "
                 "Place the features relative to the outline: one big eye in the "
                 "upper front area, a wide mouth with teeth running along the BOTTOM edge from the front (left) edge, its colour band "
                 "touching the bottom outline; gills / fins / spots / scales / belly further back, also running into the edges; the "
                 "moulded " + sh['parts'] + " coloured as part of the same creature.")
    return where + calm


SHAPED_IMAGE = """The attached image is the flat template of a silicone swim cap for kids ({cap_en}). Edit it into the screen-print design.
- The whole silhouette (solid {base}), including the moulded {parts}, is the canvas. Everything outside it stays pure white.
  Do not change the outline, do not add a frame, background or border line.
- The silhouette itself IS the character: its shape is the character's head. The cap colour {base} is the character's skin.
  Design the print exactly along the contour: colour areas (mouth, belly, mask, cheeks, stripes, patches) run right up to the
  outline and are cut by it; the moulded {parts} are coloured as part of the character (inner ears, horn tips, coloured crest
  spikes or fin...). Like the classic moulded animal caps (panda with black ears, dino with an orange crest, shark with a
  toothy mouth along the bottom edge). No rectangular picture, no scene, no pattern wallpaper, no outline drawn along the edge.
- {layout}
Character: {prompt}
Strict print rules: use ONLY these solid ink colours: {inks} (plus the cap colour). No gradients, no shading, no texture, no halftone,
no text, no letters, no logos. Bold simple shapes like a kids' sticker, every line at least 1% of the image width thick."""


CHECK = """The image is ONE side of a kids' swim cap seen in profile; the other side is its mirror image and both sides meet
at the LEFT edge of this image, which is the centre line of the character's face. Check the drawing (ignore white areas):
Return JSON {{"ok": true|false, "problems": "short English list"}}. ok = false if ANY of:
- a whole centre object is drawn on this one side: glasses with two lenses / two eye holes, a full front-on nose or mouth, a front-on face;
- more than one eye on this side;
- the main features do not follow the cap outline (a rectangular picture, a scene or background);
- any letters or text."""


def check_side(img, client, types, text_model):
    import json
    r = client.models.generate_content(
        model=text_model, contents=[CHECK, img.resize((img.width // 2, img.height // 2))],
        config=types.GenerateContentConfig(response_mime_type='application/json', temperature=0))
    return json.loads(r.text)


def render(spec, client, image_model, types, text_model=None, attempts=3, refs=()):
    """Side-panel caps are checked for half-object symmetry and regenerated with the found problems (up to 3 times)."""
    best, note = None, ''
    for k in range(attempts):
        img = _render_once(spec, client, image_model, types, note, refs)
        if spec['shape'] in shapes.FRONT or not text_model:
            return img
        try:
            res = check_side(img, client, types, text_model)
        except Exception:
            return img
        print(f'shape check {k + 1}: ' + ('ok' if res.get('ok') else res.get('problems', '')), flush=True)
        best = best or img
        if res.get('ok'):
            return img
        note = '\nA PREVIOUS ATTEMPT WAS WRONG, FIX: ' + res.get('problems', '')
    return best


def _render_once(spec, client, image_model, types, note='', refs=()):
    tpl, aspect = canvas(spec)
    sh = shapes.SHAPES[spec['shape']]
    prompt = SHAPED_IMAGE.format(cap_en=sh['en'].lower(), base=spec['base']['hex'], parts=sh['parts'], layout=layout_text(spec),
                                 prompt=spec['image_prompt'], inks=', '.join(i['hex'] for i in spec['inks'])) + note
    r = client.models.generate_content(
        model=image_model, contents=[prompt + ("\nThe FIRST attached image is the cap template to edit; the other images are "
                                               "the client's references for the idea and style only - do not copy them."
                                               if refs else ''), tpl, *refs],
        config=types.GenerateContentConfig(response_modalities=['IMAGE'], image_config=types.ImageConfig(aspect_ratio=aspect)))
    for part in r.candidates[0].content.parts:
        if part.inline_data is not None:
            return crop_back(Image.open(io.BytesIO(part.inline_data.data)).convert('RGB'), spec)
    raise RuntimeError('Gemini returned no image')


# ---------- styled BRAND lettering (side A only) ----------

LOGO_PROMPT = """The word BRAND (exactly the letters B-R-A-N-D) as bold playful cartoon lettering for a kids' swim cap,
in the style of this character: {concept}. Solid pure black letters on a pure white background, flat, no outline effect, no shadow,
no 3-D, no other elements or decorations, letters clearly separated, wide landscape composition."""


def styled_logo(spec, slug, client, image_model, types, out_dir):
    """BRAND lettering in the character's style -> one-ink vector logo file (header 'w h' + SVG path), path returned."""
    import cv2
    from gemini_design import _trace, SUPERSAMPLE
    from shapely import affinity
    r = client.models.generate_content(
        model=image_model, contents=[LOGO_PROMPT.format(concept=spec.get('image_prompt', '')[:400])],
        config=types.GenerateContentConfig(response_modalities=['IMAGE'], image_config=types.ImageConfig(aspect_ratio='16:9')))
    part = next(p for p in r.candidates[0].content.parts if p.inline_data is not None)
    im = Image.open(io.BytesIO(part.inline_data.data)).convert('L')
    im.save(os.path.join(out_dir, 'logo_styled_raw.png'))
    m = np.asarray(im) < 128
    m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)).astype(bool)
    g = _trace(m)
    if g is None or g.is_empty:
        raise RuntimeError('styled logo: nothing traced')
    g = affinity.scale(g, SUPERSAMPLE, SUPERSAMPLE, origin=(0, 0))   # _trace scales down for the cap frame; undo
    x0, y0, x1, y1 = g.bounds
    g = affinity.translate(g, -x0, -y0)
    p = os.path.join(out_dir, 'logo_styled.txt')
    open(p, 'w').write(f'{x1 - x0:.1f} {y1 - y0:.1f}\n{geom_d(g)}')
    return p
