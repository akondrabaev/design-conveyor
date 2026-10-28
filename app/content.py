"""Pipeline 2: marketplace photos of the fixed AI models wearing a chosen cap design (no infographics for now).

personas   -> 8 fixed models (2 per group: woman, man, girl, boy), one reference portrait each = stable identity
pose sheets-> per group a 5x2 sheet of faceless mannequin poses (prompt: pose_sheet_prompt.txt), cut into cells
guide      -> guide.py: the design wrapped on a mannequin head at the pose's head angle (side A = left, B = right)
shots      -> Gemini image: identity + pose cell + placement guide + flat sides, in the chosen scene
pack       -> packs/<id>/: shots/, pack.json, <id>.zip
"""
import os, shutil, threading, time, uuid, zipfile
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from PIL import Image, ImageOps
from common import ROOT, CONFIG, PERSONAS, PACKS, DESIGNS, read_json, write_json, file_url, gen_image, gen_json
import catalog, guide

POSES_DIR = os.path.join(ROOT, 'poses')
os.makedirs(POSES_DIR, exist_ok=True)
BY_ID = {k: {x['id']: x for x in CONFIG[k]} for k in ('poses', 'scenes', 'groups')}
SIZE = CONFIG.get('image_size', '2K')

# ---------- personas ----------

def persona_ref_path(pid):
    for ext in ('jpg', 'png', 'jpeg', 'webp'):
        p = os.path.join(PERSONAS, pid, f'ref.{ext}')
        if os.path.exists(p):
            return p
    return None


# The model list is user-editable: personas/personas.json, seeded from app/config.json on first run.
PERSONAS_FILE = os.path.join(PERSONAS, 'personas.json')
PERSONA_LOCK = threading.Lock()


def load_personas():
    data = read_json(PERSONAS_FILE)
    if data is None:
        data = CONFIG['personas']
        write_json(PERSONAS_FILE, data)
    return data


def persona(pid):
    p = next((x for x in load_personas() if x['id'] == pid), None)
    if not p:
        raise RuntimeError(f'модель {pid} удалена')
    return p


def list_personas():
    return [dict(p, ref=file_url(persona_ref_path(p['id'])) if persona_ref_path(p['id']) else None) for p in load_personas()]


def create_persona(group, name, look, wear):
    g = BY_ID['groups'][group]
    with PERSONA_LOCK:
        data = load_personas()
        ids = {p['id'] for p in data} | set(os.listdir(PERSONAS))
        n = 1
        while f'{group}{n}' in ids:
            n += 1
        same = sum(1 for p in data if p['group'] == group) + 1
        word = {'woman': 'Женщина', 'man': 'Мужчина', 'girl': 'Девочка', 'boy': 'Мальчик'}.get(group, g['label'])
        p = dict(id=f'{group}{n}', group=group, label=f'{word} {same}', name=name.strip() or f'{word} {same}',
                 look=look.strip(), wear=wear.strip() or DEFAULT_WEAR[group])
        data.append(p)
        write_json(PERSONAS_FILE, data)
    return p


DEFAULT_WEAR = {'woman': 'a dark one-piece sports swimsuit', 'man': 'dark swim jammers',
                'girl': "a bright kids' one-piece swimsuit", 'boy': "a kids' rash guard swim shirt and swim shorts"}


def update_persona(pid, fields):
    with PERSONA_LOCK:
        data = load_personas()
        p = next((x for x in data if x['id'] == pid), None)
        if not p:
            raise KeyError(pid)
        for k in ('name', 'look', 'wear'):
            if k in fields:
                p[k] = str(fields[k]).strip()
        write_json(PERSONAS_FILE, data)
    return p


def delete_persona(pid):
    """Soft delete: the reference photo goes to personas/_trash/ so a mistake can be undone by hand."""
    with PERSONA_LOCK:
        data = [p for p in load_personas() if p['id'] != pid]
        write_json(PERSONAS_FILE, data)
    d = os.path.join(PERSONAS, pid)
    if os.path.isdir(d):
        trash = os.path.join(PERSONAS, '_trash')
        os.makedirs(trash, exist_ok=True)
        os.replace(d, os.path.join(trash, f'{pid}_{time.strftime("%Y%m%d_%H%M%S")}'))


PERSONA_PROMPT = ("Photorealistic studio casting reference sheet of one fictional catalogue model: {look}, wearing {wear}. "
                  "Two views of the SAME person side by side on one image: left - head and shoulders facing the camera, "
                  "right - strict side profile. Hair dry and neatly pulled back, no swim cap, no accessories, no makeup look. "
                  "Neutral light-grey seamless background, soft even light, natural skin texture, no text, no watermark.")


def generate_persona(job, pid):
    p = persona(pid)
    job.say(f'Генерация эталона: {p["label"]} ({p["name"]})')
    save_persona(pid, gen_image(PERSONA_PROMPT.format(look=p['look'], wear=p['wear']), aspect='3:2'))
    job.say('Готово')
    return dict(ref=file_url(persona_ref_path(pid)))


def save_persona(pid, im):
    d = os.path.join(PERSONAS, pid)
    os.makedirs(d, exist_ok=True)
    for f in os.listdir(d):
        if f.startswith('ref.'):
            os.remove(os.path.join(d, f))
    im.convert('RGB').save(os.path.join(d, 'ref.jpg'), quality=92)


# ---------- pose sheets ----------

def pose_path(group, pose_id):
    return os.path.join(POSES_DIR, group, f'{pose_id}.png')


def list_pose_sheets():
    out = []
    for g in CONFIG['groups']:
        sheet = os.path.join(POSES_DIR, g['id'], 'sheet.png')
        cells = {p['id']: file_url(pose_path(g['id'], p['id'])) for p in CONFIG['poses'] if os.path.exists(pose_path(g['id'], p['id']))}
        out.append(dict(g, sheet=file_url(sheet) if os.path.exists(sheet) else None, cells=cells))
    return out


def generate_pose_sheet(job, group, attempts=3):
    g = BY_ID['groups'][group]
    prompt = open(os.path.join(ROOT, 'app', 'pose_sheet_prompt.txt'), encoding='utf-8').read()
    prompt = prompt.replace('{body}', g['body']).replace('{suit}', g['suit'])
    d = os.path.join(POSES_DIR, group)
    os.makedirs(d, exist_ok=True)
    for k in range(1, attempts + 1):
        job.say(f'Лист ракурсов: {g["label"]}, попытка {k}…')
        im = gen_image(prompt, aspect='16:9', size=SIZE)
        cells = segment_sheet(im)
        if cells:
            im.save(os.path.join(d, 'sheet.png'))
            job.say('Нарезано 10 поз, проверяю направление профилей…')
            save_cells(group, orient(cells))
            job.say('Готово')
            return {}
        job.say('На листе не 5+5 фигур, генерирую заново')
    raise RuntimeError('Gemini не нарисовал ровную сетку 5×2, попробуйте ещё раз')


def segment_sheet(im):
    """Cut 10 figures by their silhouettes (cells are not always equal). Returns {1..10: PIL} or None."""
    import cv2
    a = np.asarray(im.convert('RGB')).astype(np.int16)
    ink = ((255 - a.min(-1)) > 22).astype(np.uint8)
    ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))   # drops the thin grid lines
    H, W = ink.shape
    rows = ink.sum(1)
    mid = H * 35 // 100 + int(np.argmin(rows[H * 35 // 100: H * 65 // 100]))
    out = {}
    for r, (y0, y1) in enumerate(((0, mid), (mid, H))):
        cols = ink[y0:y1].sum(0) > 2
        runs, x = [], 0
        while x < W:
            if cols[x]:
                s0 = x
                while x < W and cols[x]:
                    x += 1
                runs.append([s0, x])
            x += 1
        merged = []                                   # join pieces of one figure split by a narrow gap
        for rr in runs:
            if merged and rr[0] - merged[-1][1] < W * 0.012:
                merged[-1][1] = rr[1]
            else:
                merged.append(rr)
        merged = [m for m in merged if m[1] - m[0] > W * 0.02]
        if len(merged) != 5:
            return None
        for c, (x0, x1) in enumerate(merged):
            ys = np.where(ink[y0:y1, x0:x1].any(1))[0]
            by0, by1 = y0 + ys[0], y0 + ys[-1]
            out[r * 5 + c + 1] = _frame(im.crop((x0, by0, x1, by1)))
    return out


def _frame(fig, pad=0.08):
    """Figure centred on a white 3:4 canvas."""
    w, h = fig.size
    H = round(max(h, w * 4 / 3) * (1 + 2 * pad))
    W = round(H * 3 / 4)
    c = Image.new('RGB', (W, H), 'white')
    c.paste(fig, ((W - w) // 2, (H - h) // 2))
    return c


FACING = {3: 'left', 4: 'right', 5: 'left', 10: 'left'}   # cell -> where the head must point (q_left, q_right, profiles)


def orient(cells):
    """Gemini vision says where each mannequin's head points; mirror the cells that face the wrong way."""
    from common import gen_json
    ids = list(FACING)
    try:
        r = gen_json('For each of the attached images of a faceless mannequin (in order), answer where the FRONT of its head '
                     '(the face side) points: "left" (toward the left edge of the image), "right", "camera" or "away". '
                     'Return JSON: {"facing": ["left"|"right"|"camera"|"away", ...]}',
                     temperature=0, images=[cells[i] for i in ids])
        for i, f in zip(ids, r.get('facing', [])):
            if f in ('left', 'right') and f != FACING[i]:
                cells[i] = ImageOps.mirror(cells[i])
    except Exception:
        pass   # orientation check is best effort; the UI has a manual flip
    return cells


def save_cells(group, cells):
    for f in os.listdir(os.path.join(POSES_DIR, group)):
        if f.startswith('cell_'):
            os.remove(os.path.join(POSES_DIR, group, f))
    for n, im in cells.items():
        im.save(os.path.join(POSES_DIR, group, f'cell_{n:02d}.png'))
    derive_poses(group)


def derive_poses(group):
    for p in CONFIG['poses']:
        if 'cell' not in p:   # hands poses have no mannequin cell
            continue
        cell = Image.open(os.path.join(POSES_DIR, group, f'cell_{p["cell"]:02d}.png'))
        (ImageOps.mirror(cell) if p.get('mirror') else cell).save(pose_path(group, p['id']))


def flip_pose(group, pose_id):
    """Manual fix: mirror the source cell of this pose (its mirrored twin follows)."""
    n = BY_ID['poses'][pose_id]['cell']
    p = os.path.join(POSES_DIR, group, f'cell_{n:02d}.png')
    ImageOps.mirror(Image.open(p)).save(p)
    derive_poses(group)


# ---------- placement guide ----------

PRODUCT = {x['id']: x for x in CONFIG['product_poses']}
ASSETS = os.path.join(ROOT, 'app', 'assets')


def flat_side(slug, side):
    return catalog.cap_image(slug, side, scale=1.0, sheen=False)


def is_head_pose(pose_id):
    return pose_id in BY_ID['poses'] and 'yaw' in BY_ID['poses'][pose_id]


def guide_image(slug, pose_id, size=900):
    """Head poses: cached render of the design on the mannequin head at the pose's head angle.
    Hands / product / kit shots: the clean cap render itself (there is no head angle)."""
    with catalog.RENDER_LOCK:
        if not is_head_pose(pose_id):
            catalog.cap_image(slug, 'A')
            return os.path.join(DESIGNS, slug, '_cap_A.png')
        return _guide_image(slug, pose_id, size)


def _guide_image(slug, pose_id, size):
    pose = BY_ID['poses'][pose_id]
    d = os.path.join(DESIGNS, slug, '_guide')
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, f'{pose_id}.png')
    src = catalog.design_file(slug, 'side-A_print_transparent.png')
    if os.path.exists(out) and os.path.getmtime(out) >= max(os.path.getmtime(src), os.path.getmtime(guide.__file__)):
        return out
    info = catalog.design_info(slug)
    fb = flat_side(slug, 'B') if 'B' in info['sides'] else None
    import shapes
    im = guide.render(flat_side(slug, 'A'), fb, info['base']['hex'], pose['yaw'], pose.get('elev', 10),
                      catalog.is_long(slug), size, panel=shapes.panel(catalog.shape_of(slug)))
    im.save(out + '.tmp.png')
    os.replace(out + '.tmp.png', out)
    return out


# ---------- shots ----------
# kinds: 'model' (cap on the head, or in the hands for poses with "hands"), 'product' (still life), 'kit' (what's in the box)

LONG_SHAPE = ("a LONG swim cap for long hair: the front fits like a classic cap, but at the back it has a smooth, rounded extra "
              "volume - a soft gentle bulge over the back of the head and nape where the gathered long hair sits, clearly visible "
              "in side, 3/4 and back views (see the shape reference). One smooth glossy silicone shape with a few soft natural "
              "wrinkles on the volume; not a pointed bun, not a hair net")
LONG_REF = "- Image {n} - SHAPE REFERENCE of the long cap (another colour and print): copy only its silhouette and the soft volume at the back."

SHOT_PROMPT = """Photorealistic e-commerce photo for a marketplace product card: a person wearing a printed silicone swim cap. Vertical 3:4.

REFERENCE IMAGES
- Image 1 - IDENTITY: show exactly this person (same face, age, skin tone, eye colour, features). Ignore their clothing and background.
- Image 2 - POSE AND FRAMING: copy the body pose, head angle, camera angle and crop of this faceless mannequin ({pose}). It is only a pose guide: ignore its body type and swimsuit.
- Image 3 - CAP PLACEMENT GUIDE: a grey mannequin head wearing this exact cap at this head angle. It shows which part of the print is visible from this angle, where it sits on the head and where the BRAND logo is. Reproduce the print placement on the cap exactly as in this guide.
- Image 4 - flat print of the cap's LEFT half (side A, carries the BRAND logo), laid out as seen from the person's left: left edge of the image = forehead, right edge = nape, bottom edge = rim over the ear, top arc = the head's midline.
{side_b}
{long_ref}

WHAT THE CAMERA SEES IN THIS SHOT: {visible}

CAP CONSTRUCTION (must be respected)
- It is ONE seamless moulded silicone cap, smooth and glossy. Along the midline of the head (forehead -> crown -> nape) there is only a faint, barely visible hairline moulding line: NOT a stitched seam, no ridge, no raised edge, no band or stripe, no fabric look.
- The print is applied to the two sides of the flat cap: the LEFT side covers the person's left half of the head, the RIGHT side the right half. Each side's print stops just short of the midline, leaving only a narrow plain strip (about 1-1.5 cm in total) along the top.
- The print is NOT one picture centred on the forehead. Seen from the front, you see only the front edges of both sides' prints, close to each other at the midline; seen from a side, you see that whole side.
- The BRAND logo appears ONLY ONCE, on the person's LEFT side near the left temple. {right_rule}
- Cap: {cap_kind}, solid {base_name} silicone ({base_hex}); print colours {inks}. ALL hair fully tucked inside the cap: no hair visible below the cap edge at the nape, ears or forehead. Realistic stretch over the skull, slight silicone sheen{wet}. The cap is in sharp focus and not cropped.

PERSON: {look}, wearing {wear}.
SETTING: {scene}.{extra}
Natural skin, natural light. The print on the cap must be EXACTLY the attached design (Images 4-5), not a new or redrawn illustration; keep its colours.
No text, no extra logos, no watermarks, no frames."""

HANDS_PROMPT = """Photorealistic e-commerce photo for a marketplace product card of a printed silicone swim cap. Vertical 3:4.

REFERENCE IMAGES
- Image 1 - IDENTITY: this exact person (face, skin tone, hands). Ignore their clothing and background.
- Image 2 - the cap's LEFT side as a flat cap: exactly this print, its colours and the BRAND logo position (near the front, bottom).
{extra_refs}
- POSE REFERENCES ({pose_refs}): real photos of this action. Copy exactly how the cap is held, how the hands pull it and how the silicone deforms, and the framing. Ignore the people in them, their cap colours and prints.

SHOT: {pose}.
{side_rule}
The cap is {cap_kind}, solid {base_name} silicone ({base_hex}), soft and elastic but always INTACT: never torn, no holes, no ragged or cut edges, a smooth clean rim. The print stretches with the silicone but stays recognisable. Only one BRAND logo, on the printed left side.
PERSON: {look}, wearing {wear}; {hair}.
SETTING: {scene}.{extra}
The print must be EXACTLY the attached design, not redrawn. No text, no arrows, no labels, no extra logos, no watermarks, no frames."""

PRODUCT_PROMPT = """Photorealistic still-life product photo (no people) for a marketplace product card: a printed silicone swim cap. Vertical 3:4.

REFERENCE IMAGES
- Image 1 - the cap's LEFT side as a flat cap: exactly this print, its colours and the BRAND logo (near the front, bottom).
{side_b}{long_ref}

COMPOSITION: {pose}.
{facing}
SURFACE: {surface}. Natural light, realistic soft shadows, shallow depth of field, premium catalogue look.{extra}
The cap is {cap_kind}, soft glossy silicone, solid {base_name} ({base_hex}). Lying flat it shows the silhouette of Image 1 (front on the left, rounded crown, small tabs at the bottom edge).
The print must be EXACTLY the attached design, not redrawn. No people, no hands, no text, no extra logos, no watermarks."""

KIT_PROMPT = """Photorealistic still-life product photo for a marketplace "what is in the box" card. Vertical 3:4.
Three objects lying on the surface, clearly separated with some free space around each:
1. The swim cap lying flat with its LEFT side up: exactly the print, colours and BRAND logo of Image 1 ({cap_kind}, {base_name} silicone).
2. A transparent frosted zip-lock storage bag with the black BRAND wave logo printed on it, like Image 2.
3. Black silicone ear plugs and a nose clip in a small clear plastic box, like Image 3.
SURFACE: {surface}. Natural light, realistic shadows, premium catalogue look.{extra}
No people, no hands, no captions, no labels, no text except the printed logos, no watermarks."""

SIDE_B = ("- Image 5 - flat print of the cap's RIGHT half (side B, NO logo), laid out as seen from the person's right: "
          "right edge of the image = forehead, left edge = nape.")
SIDE_B_PLAIN = ("- Image 5 - the cap's RIGHT half: PLAIN solid {base} silicone with NO print and NO logo at all. "
                "This is a one-sided cap: the print exists only on the left half.")
SYMMETRIC = (" The cap is SYMMETRIC: the right half is the mirror image of the left half (same motifs, mirrored, "
             "so they face forward on both sides of the head), only without the logo.")


def visible_text(yaw, two):
    """Which half faces the camera, in words, so the model cannot put the print on the wrong side."""
    right = 'the right half with its own print (no logo)' if two else 'the PLAIN right half (no print, no logo)'
    if -20 <= yaw <= 20:
        return (f"the face is toward the camera. The person's LEFT half (print + BRAND logo) is on the RIGHT side of the photo; "
                f"the person's RIGHT half is on the LEFT side of the photo and shows {right}. The two prints almost touch along the midline above the middle of the forehead: the plain gap between them is very narrow (a finger-width at most), perfectly smooth and flush with the rest of the glossy silicone - no ridge, no fold, no raised band, no seam.")
    if 20 < yaw < 160:
        return (f"the person's RIGHT side is toward the camera, so the visible cap surface is {right}. No BRAND logo is visible." +
                ('' if two else ' Only a thin sliver of the printed left half may show at the very top/back edge, if at all.'))
    if -160 < yaw < -20:
        return "the person's LEFT side is toward the camera, so the visible cap surface is the printed LEFT half with the BRAND logo near the left temple, exactly as in Image 4."
    return (f"the back of the head is toward the camera. The person's LEFT half (printed) is on the LEFT side of the photo; "
            f"the RIGHT half on the right side of the photo shows {right}. The two prints nearly meet along the midline of the back of the head (only a faint moulding line, no seam). "
            "The BRAND logo is NOT visible from behind: it sits near the left temple at the front.")


FRONT_IMG4 = ("- Image 4 - flat print of the cap's FRONT half (side A, the character's face), laid out as seen from the front: "
              "left edge = the person's right ear, right edge = the person's left ear, bottom edge = rim over the forehead, top arc = the "
              "line over the crown from ear to ear. The moulded {parts} at the top corners stand on top of the head, left and right.")
FRONT_CONSTRUCTION = ("- It is ONE seamless moulded silicone cap, smooth and glossy. The FRONT half carries the face print, the BACK half is {back}; "
                      "they meet over the crown from ear to ear with only a faint moulding line (no seam, no ridge, no stripe).\n"
                      "- The face is centred on the forehead and the top of the head, exactly like Image 4 wrapped over it: eyes above the "
                      "forehead, mouth just above the rim; NOT on the sides of the head.\n"
                      "- The two moulded {parts} stand on top of the head, left and right, part of the same print (e.g. coloured inner ears / horns).\n"
                      "- The BRAND logo appears at most once, small, on the front half at its lower corner.")


def _face_side(text):
    return (text.replace("cap's LEFT side", "cap's FRONT (face) side").replace('LEFT side up', 'FRONT (face) side up')
            .replace('printed LEFT side', 'printed FRONT (face) side').replace('the cap LEFT side', 'the cap FRONT (face) side')
            .replace("cap's RIGHT side", "cap's BACK side").replace('the cap RIGHT side', 'the cap BACK side'))


def visible_front(yaw, parts, back):
    if abs(yaw) <= 20:
        return f"the face print on the front half faces the camera, centred on the forehead; both {parts} are visible on top, left and right."
    if abs(yaw) < 70:
        return f"the face print is seen at an angle (three-quarter view), still centred on the forehead; both {parts} visible on top."
    if abs(yaw) <= 110:
        return (f"side view: the front half with the side edge of the face print is toward the face, the back half ({back}) toward the "
                f"back of the head; the {parts} are seen from the side on top of the head.")
    return f"the back of the head faces the camera: the back half ({back}) is visible, the face is not; the {parts} are seen from behind."


def _front_prompt(prompt, c, pose):
    """Rewrite the side-panel construction of SHOT_PROMPT for caps made of a front (face) and a back half."""
    import shapes
    parts = shapes.SHAPES[c['shape']]['parts']
    lines = prompt.split('\n')
    out = []
    for ln in lines:
        if ln.startswith("- Image 4 - flat print of the cap's LEFT half"):
            out.append(FRONT_IMG4.format(parts=parts))
        elif ln.startswith('- Image 5 -'):
            out.append(f"- Image 5 - the BACK half of the cap: {c['right_txt']}")
        elif ln.startswith('- It is ONE seamless'):
            out.append(FRONT_CONSTRUCTION.format(parts=parts, back=c['right_txt']))
        elif ln.startswith(('- The print is applied', '- The print is NOT one picture', '- The BRAND logo appears ONLY ONCE')):
            continue
        elif ln.startswith('WHAT THE CAMERA SEES'):
            out.append('WHAT THE CAMERA SEES IN THIS SHOT: ' + visible_front(pose['yaw'], parts, c['right_txt']))
        else:
            out.append(ln)
    return '\n'.join(out)


PU_CONSTRUCTION = ("- It is a PU swim cap: smooth satin-matte coated fabric (not glossy silicone) with real neat stitched seams - a "
                   "narrow centre panel from the forehead over the crown to the nape and two side panels - and a soft binding at the rim.\n"
                   "- The full-colour print sits only on the person's LEFT side panel, exactly as in Image 4; the BRAND lettering is part "
                   "of that print. The right side panel is plain.")


def _pu_prompt(prompt):
    out = []
    for ln in prompt.split('\n'):
        if ln.startswith('- It is ONE seamless'):
            out.append(PU_CONSTRUCTION)
        elif ln.startswith(('- The print is applied', '- The print is NOT one picture', '- The BRAND logo appears ONLY ONCE')):
            continue
        else:
            out.append(ln.replace('slight silicone sheen', 'soft satin sheen of coated fabric'))
    return '\n'.join(out)


def _design_ctx(slug):
    info = catalog.design_info(slug)
    two = 'B' in info['sides']
    long = catalog.is_long(slug)
    right_img = _on_white(flat_side(slug, 'B')) if two else plain_side(slug)
    right_txt = ('its own print, without any logo' if two else f'PLAIN solid {info["base"]["name"]} silicone, no print, no logo') + \
        (SYMMETRIC if info.get('side_b') == 'mirror' else '')
    import shapes
    shape = catalog.shape_of(slug)
    if shape in shapes.FRONT:   # B = back half of the head
        right_txt = 'its own print, without any logo' if two else f'PLAIN solid {info["base"]["name"]} silicone, no print, no logo'
    return dict(info=info, two=two, long=long, right_img=right_img, right_txt=right_txt, shape=shape, front=shape in shapes.FRONT,
                pu=shape in shapes.PU,
                cap_kind=LONG_SHAPE if long else _shape_photo(slug),
                flat_a=_on_white(flat_side(slug, 'A')), cap_a=_on_white(catalog.cap_image(slug, 'A')))


def _shape_photo(slug):
    import shapes
    return shapes.SHAPES.get(catalog.shape_of(slug), {}).get('photo') or 'a classic swim cap'


def _shape_ref():
    return Image.open(os.path.join(ASSETS, 'long_cap_shape.jpg')).convert('RGB')


def _has_shape_ref():
    """Optional photo of the long cap shape (app/assets/long_cap_shape.jpg); without it the text description is used."""
    return os.path.exists(os.path.join(ASSETS, 'long_cap_shape.jpg'))


def _assets(*names):
    """Optional reference photos from app/assets/ that exist (a fresh install has none)."""
    return [Image.open(p).convert('RGB') for p in (os.path.join(ASSETS, n) for n in names) if os.path.exists(p)]


def build_shot(pack, shot, c):
    """-> refs, prompt, qa_images, qa_extra_fields"""
    info = c['info']
    kind = shot.get('kind', 'model')
    extra = f"\nNOTES: {shot['note']}" if shot.get('note') else ''
    scene = BY_ID['scenes'][shot['scene']]
    base = dict(base_name=info['base']['name'], base_hex=info['base']['hex'], cap_kind=c['cap_kind'], extra=extra)
    qa_extra = {}
    if kind == 'kit':
        refs = [c['cap_a']] + _assets('kit_bag.jpg', 'kit_accessories.jpg')
        qa_extra['kit_ok'] = 'true if the photo shows the cap, a transparent zip bag and ear plugs with a nose clip'
        kp = KIT_PROMPT.format(surface=scene['surface'], **base)
        if len(refs) < 3:   # no reference photos of the bag / accessories: keep only the descriptions
            kp = kp.replace(', like Image 2.', '.').replace(', like Image 3.', '.')
        return refs, kp, [('the cap LEFT side (with logo)', c['cap_a']), ('the cap RIGHT side', c['right_img'])], qa_extra
    if kind == 'product':
        both = shot['pose'] == 'both_sides'
        refs = [c['cap_a']] + ([c['right_img']] if both else []) + ([_shape_ref()] if c['long'] and _has_shape_ref() else [])
        facing = ('' if both else
                  f"The cap lies with its LEFT side up: the whole visible upper surface is printed exactly like Image 1. "
                  f"The other side ({c['right_txt']}) faces down and is not visible.")
        prompt = PRODUCT_PROMPT.format(side_b=f"- Image 2 - the cap's RIGHT side: {c['right_txt']}\n" if both else '',
                                       facing=facing, pose=PRODUCT[shot['pose']]['prompt'], surface=scene['surface'],
                                       long_ref=LONG_REF.format(n=len(refs)) if c['long'] and _has_shape_ref() else '', **base)
        return refs, prompt, [('the cap LEFT side (with logo)', c['cap_a']), ('the cap RIGHT side', c['right_img'])], qa_extra
    p, pose = persona(shot['persona']), BY_ID['poses'][shot['pose']]
    ref = persona_ref_path(shot['persona'])
    if not ref:
        raise RuntimeError(f'нет эталона модели «{p["label"]}»: создайте его во вкладке «Модели и ракурсы»')
    who = dict(look=p['look'], wear=p['wear'], scene=scene['prompt'])
    if pose.get('hands'):
        refs = [Image.open(ref).convert('RGB'), c['cap_a']]
        extra_refs = []
        if pose.get('on_head'):   # the cap sits on the head: give the placement guide for this head angle too
            refs.append(Image.open(guide_image(pack['design'], pose['guide'])).convert('RGB'))
            extra_refs.append(f"- Image {len(refs)} - CAP PLACEMENT GUIDE: the cap on a mannequin head at this head angle; reproduce where the print and the BRAND logo sit.")
        if c['long'] and _has_shape_ref():
            refs.append(_shape_ref())
            extra_refs.append(LONG_REF.format(n=len(refs)))
        first = len(refs) + 1
        refs += _assets(*[os.path.join('pose_refs', f) for f in pose['refs']])   # optional real photos of the action
        side_rule = ("All hair neatly tucked under the cap. " + visible_text(BY_ID['poses'][pose['guide']]['yaw'], c['two'])
                     if pose.get('on_head') else
                     f"The printed LEFT side faces the camera and its whole visible surface is printed exactly like Image 2; "
                     f"the other side ({c['right_txt']}) is behind it, facing away from the camera.")
        prompt = HANDS_PROMPT.format(
            pose=pose['prompt'], side_rule=side_rule, extra_refs='\n'.join(extra_refs),
            pose_refs=f"Images {first}-{len(refs)}" if len(refs) > first else f"Image {first}" if len(refs) == first else "none attached - follow the SHOT description",
            hair=('hair fully tucked under the cap' if pose.get('on_head') else
                  'their own hair as usual (the cap is in the hands, not on the head)'), **who, **base)
        qa_extra['action_ok'] = ('true if the action matches the pose references: ' + pose['qa'] +
                                 '; false if the cap looks torn, has holes or ragged edges')
        if not pose.get('on_head'):
            qa_extra['print_facing_ok'] = 'true if most of the visible cap surface is the printed side with the BRAND logo (not mostly plain silicone)'
        qa_extra['same_person_ok'] = ('true if the person in the photo is clearly the same person as the IDENTITY reference (face, age, hair colour); true if the face is not in the frame')
        return refs, prompt, [('the cap LEFT side (with logo)', c['cap_a']), ('the cap RIGHT side', c['right_img']), ('IDENTITY reference of the person', Image.open(ref).convert('RGB'))], qa_extra
    pp = pose_path(p['group'], pose['id'])
    if not os.path.exists(pp):
        raise RuntimeError(f'нет листа ракурсов для группы «{BY_ID["groups"][p["group"]]["label"]}»')
    gimg = Image.open(guide_image(pack['design'], pose['id'])).convert('RGB')
    refs = [Image.open(ref).convert('RGB'), Image.open(pp).convert('RGB'), gimg, c['flat_a'], c['right_img']]
    if c['long'] and _has_shape_ref():
        refs.append(_shape_ref())
    side_b = (SIDE_B if c['two'] else SIDE_B_PLAIN.format(base=info['base']['name'])) + \
        (SYMMETRIC if info.get('side_b') == 'mirror' else '')
    prompt = SHOT_PROMPT.format(
        pose=pose['prompt'], side_b=side_b, visible=visible_text(pose['yaw'], c['two']),
        long_ref=LONG_REF.format(n=6) if c['long'] and _has_shape_ref() else '',
        right_rule=('The RIGHT half carries its own print (Image 5) without any logo.' if c['two'] else
                    f'The RIGHT half has NO print at all: plain solid {info["base"]["name"]} silicone, no logo.'),
        inks=', '.join(i['hex'] for i in info['inks']),
        wet='' if shot['scene'] in ('studio', 'locker') else ' and water droplets', **who, **base)
    if c['front']:
        prompt = _front_prompt(prompt, c, pose)
    if c['pu']:
        prompt = _pu_prompt(prompt)
        qa_extra.pop('ridge_or_seam', None)   # PU caps do have stitched seams
    qa_extra['ridge_or_seam'] = 'true if there is a visible raised seam, ridge, stitched line or plain stripe running along the middle of the cap'
    if c['long']:
        qa_extra['long_shape_ok'] = ('true if the cap clearly has a smooth extra volume at the back of the head for long hair '
                                     '(true for a straight front view where the back is not visible)')
    qa_extra['same_person_ok'] = ('true if the person in the photo is clearly the same person as the IDENTITY reference (face, age, hair colour); true if the face is not in the frame')
    return refs, prompt, [('placement guide for this head angle', gimg), ('the cap LEFT side (with logo)', c['flat_a']), ('the cap RIGHT side', c['right_img']), ('IDENTITY reference of the person', Image.open(ref).convert('RGB'))], qa_extra


def plain_side(slug):
    """Right half of a one-sided cap: the mirrored silhouette in base colour, no print."""
    a = flat_side(slug, 'A')
    base = catalog.design_info(slug)['base']['hex']
    m = ImageOps.mirror(a.split()[3])
    bg = Image.new('RGB', a.size, 'white')
    bg.paste(Image.new('RGB', a.size, base), mask=m)
    return bg


def _on_white(im):
    bg = Image.new('RGB', im.size, 'white')
    bg.paste(im, mask=im.split()[3] if im.mode == 'RGBA' else None)
    return bg


QA_PROMPT = """You are the quality checker for marketplace photos of a printed silicone swim cap.
Image 1 is the generated photo. The next images are the references: {refs}.
Judge only the cap (and the listed objects). Return JSON:
{{"same_print": true if the motifs and colours on the cap clearly are this design (not a different illustration),
  "cap_colour_ok": true if the cap base colour matches {base},
  "logo_ok": true if the BRAND logo appears at most once, only on the cap's printed LEFT side (near the left temple when worn), never on the right side or the back,
  "plain_side_ok": true if the cap's right side matches its reference ({right}), or if the right side is not visible,
{extra}  "score": 1-10 overall fidelity,
  "problems": "short list of problems in Russian, empty if none"}}"""
QA_ATTEMPTS = 3


def qa_shot(im, qa_images, qa_extra, c):
    extra = ''.join(f'  "{k}": {v},\n' for k, v in qa_extra.items())
    tpl = QA_PROMPT if not c.get('front') else QA_PROMPT.replace(
        "only on the cap's printed LEFT side (near the left temple when worn), never on the right side or the back",
        "only on the front (face) half, at its lower corner, never on the back").replace("the cap's right side", "the cap's back half")
    r = gen_json(tpl.format(refs='; '.join(f'Image {i + 2}: {n}' for i, (n, _) in enumerate(qa_images)),
                                  base=f"{c['info']['base']['name']} {c['info']['base']['hex']}",
                                  right=c['right_txt'], extra=extra),
                 temperature=0, images=[im.resize((im.width // 2, im.height // 2)), *(img for _, img in qa_images)])
    r['ok'] = bool(all(r.get(k) for k in ('same_print', 'cap_colour_ok', 'logo_ok', 'plain_side_ok'))
                   and all(r.get(k) for k in qa_extra if k.endswith('_ok')) and not r.get('ridge_or_seam'))
    return r


def render_shot(pack, n):
    """Generate, check with Gemini vision, retry with the found problems; keep the best attempt."""
    shot = pack['shots'][n]
    c = _design_ctx(pack['design'])
    refs, prompt, qa_images, qa_extra = build_shot(pack, shot, c)
    if c['front']:   # caps with ears / horns: side A is the front (face) half, not the left half
        prompt = _face_side(prompt)
        qa_images = [(_face_side(n), img) for n, img in qa_images]
    best = None
    for k in range(QA_ATTEMPTS):
        p = prompt
        if k and best[1].get('problems'):
            p += f"\nA PREVIOUS ATTEMPT HAD THESE PROBLEMS, AVOID THEM: {best[1]['problems']}"
        im = gen_image(p, refs, aspect='3:4', size=SIZE)
        try:
            qa = qa_shot(im, qa_images, qa_extra, c)
        except Exception as e:
            qa = dict(ok=True, score=None, problems=f'проверка не выполнена: {str(e)[:80]}')
        if best is None or (qa.get('score') or 0) > (best[1].get('score') or 0):
            best = (im, qa)
        if qa['ok']:
            break
    d = os.path.join(PACKS, pack['id'], 'shots')
    out = os.path.join(d, f'shot_{uuid.uuid4().hex[:10]}.jpg')
    im = best[0]
    im.save(out, quality=93)
    qa = best[1]
    return out, dict(ok=qa['ok'], score=qa.get('score'), problems=qa.get('problems', ''), attempts=k + 1)


# ---------- pack ----------

def pack_dir(pid):
    return os.path.join(PACKS, pid)


def load_pack(pid):
    return read_json(os.path.join(pack_dir(pid), 'pack.json'))


def save_pack(pack):
    write_json(os.path.join(pack_dir(pack['id']), 'pack.json'), pack)


PACK_LOCK = threading.Lock()


def update_shot(pid, n, **kw):
    """Re-read, change one shot, write: several jobs may touch the same pack at once."""
    with PACK_LOCK:
        pack = load_pack(pid)
        old = pack['shots'][n].get('file')
        pack['shots'][n].update(kw)
        save_pack(pack)
        if kw.get('file') and old and old != kw['file']:   # regenerated: the previous image is no longer needed
            _remove(os.path.join(pack_dir(pid), old))
        return pack


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _busy(pack):
    return pack['status'] in ('queued', 'running') or any(s['status'] == 'running' for s in pack['shots'])


def delete_pack(pid):
    with PACK_LOCK:
        pack = load_pack(pid)
        if pack and _busy(pack):
            raise RuntimeError('фотосессия ещё генерируется, дождитесь окончания')
        shutil.rmtree(pack_dir(pid), ignore_errors=True)


def delete_shot(pid, n):
    with PACK_LOCK:
        pack = load_pack(pid)
        if _busy(pack):
            raise RuntimeError('в фотосессии идёт генерация, дождитесь окончания')
        shot = pack['shots'].pop(n)
        if shot.get('file'):
            _remove(os.path.join(pack_dir(pid), shot['file']))
        save_pack(pack)
        make_zip(pack)
        return pack


def dir_size(path):
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def storage():
    """Disk use of everything the pipelines generate, against the configured quota."""
    dirs = {'Фотосессии': PACKS, 'Дизайны': DESIGNS, 'Модели': PERSONAS, 'Ракурсы': POSES_DIR,
            'Старые фото на моделях': os.path.join(ROOT, 'on_model')}
    parts = {k: dir_size(v) for k, v in dirs.items()}
    return dict(used=sum(parts.values()), limit=int(CONFIG.get('storage_limit_gb', 5) * 1024 ** 3), parts=parts)


def set_status(pid, status):
    with PACK_LOCK:
        pack = load_pack(pid)
        pack['status'] = status
        save_pack(pack)
        return pack


def _guide_url(slug, pose):
    """Placement guide of a shot; None when the design was deleted (the shots of the pack stay)."""
    if not os.path.exists(os.path.join(DESIGNS, slug, '_gemini', 'spec.json')):
        return None
    try:
        return file_url(guide_image(slug, pose))
    except Exception:
        return None


def packs_using(slug):
    return [p for p in os.listdir(PACKS) if (load_pack(p) or {}).get('design') == slug]


def pack_view(pack):
    d = pack_dir(pack['id'])
    v = dict(pack)
    v['shots'] = [dict(s, url=file_url(os.path.join(d, s['file'])) if s.get('file') else None,
                       guide=_guide_url(pack['design'], s['pose'])) for s in pack['shots']]
    z = os.path.join(d, f"{pack['id']}.zip")
    v['zip'] = file_url(z) if os.path.exists(z) else None
    info = catalog.design_info(pack['design'])
    v['design_name'] = info['name'] if info else pack['design']
    return v


def list_packs():
    out = []
    for pid in os.listdir(PACKS):
        p = load_pack(pid)
        if not p or 'cards' in p:   # skip packs from the old infographic version
            continue
        info = catalog.design_info(p['design'])
        cover = next((file_url(os.path.join(pack_dir(pid), s['file'])) for s in p['shots'] if s.get('file')), None)
        out.append(dict(id=pid, created=p['created'], design=p['design'], design_name=info['name'] if info else p['design'],
                        status=p['status'], cover=cover, n_shots=len(p['shots']), size=dir_size(pack_dir(pid)),
                        n_ok=sum(1 for s in p['shots'] if s.get('file'))))
    return sorted(out, key=lambda x: x['created'], reverse=True)


def create_pack(req):
    pid = time.strftime('%Y%m%d_%H%M%S_') + req['design'][:24]
    os.makedirs(os.path.join(pack_dir(pid), 'shots'), exist_ok=True)
    pack = dict(id=pid, created=time.time(), status='queued', design=req['design'],
                shots=[dict(kind=s.get('kind', 'model'), persona=s.get('persona'), pose=s['pose'], scene=s['scene'],
                            note=s.get('note', ''), status='queued') for s in req['shots']])
    save_pack(pack)
    return pack


def run_pack(job, pid):
    pack = set_status(pid, 'running')
    todo = [i for i, s in enumerate(pack['shots']) if s['status'] != 'done']
    for n in todo:
        update_shot(pid, n, status='running')
    job.say(f'Кадры: {len(todo)} шт., по 4 параллельно, ~{max(1, len(todo) // 4) * 40} с…')

    def one(n):
        try:
            out, qa = render_shot(load_pack(pid), n)
            return n, os.path.relpath(out, pack_dir(pid)).replace(os.sep, '/'), None, qa
        except Exception as e:
            return n, None, str(e)[:300], None
    for s in {pack['shots'][n]['pose'] for n in todo}:   # warm the shared caches before the threads start
        guide_image(pack['design'], s)
    _design_ctx(pack['design'])
    with ThreadPoolExecutor(4) as ex:
        for n, f, err, qa in ex.map(one, todo):
            update_shot(pid, n, status='done' if f else 'error', file=f, error=err, qa=qa)
            job.say(f'Кадр {n + 1}: ' + (('ok' if qa['ok'] else 'есть замечания') + f" (оценка {qa.get('score')}, попыток {qa['attempts']})"
                                         if f else 'ошибка: ' + err))
    make_zip(set_status(pid, 'done'))
    job.say('Пак готов')
    return dict(id=pid)


def regen_shot(job, pid, n, note=None):
    kw = {'note': note} if note is not None else {}
    pack = update_shot(pid, n, status='running', **kw)
    job.say(f'Перегенерация кадра {n + 1}…')
    try:
        out, qa = render_shot(pack, n)
    except Exception as e:
        update_shot(pid, n, status='error', error=str(e)[:300])
        raise
    pack = update_shot(pid, n, status='done', file=os.path.relpath(out, pack_dir(pid)).replace(os.sep, '/'), error=None, qa=qa)
    job.say(f"Проверка: {'ok' if qa['ok'] else qa['problems']} (оценка {qa.get('score')})")
    with PACK_LOCK:
        make_zip(pack)
    job.say('Готово')
    return dict(id=pid)


def make_zip(pack):
    d = pack_dir(pack['id'])
    z = os.path.join(d, f"{pack['id']}.zip")
    shots = [s for s in pack['shots'] if s.get('file') and os.path.exists(os.path.join(d, s['file']))]
    if not shots:
        _remove(z)
        return
    with zipfile.ZipFile(z, 'w', zipfile.ZIP_STORED) as zf:   # jpgs are already compressed
        for i, s in enumerate(shots):
            zf.write(os.path.join(d, s['file']), f'shots/shot_{i + 1:02d}.jpg')
        zf.write(os.path.join(d, 'pack.json'), 'pack.json')
