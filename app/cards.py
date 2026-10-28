"""Infographic templates: one fixed visual format for every product card (1200x1600) and rich block (1200x800).
Photos come from Gemini; all text is drawn here, so typography is exact and identical across products."""
import colorsys, os
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from common import LIB

INK = '#0E1A2B'      # main text colour
PAPER = '#F4F2EE'    # light background
MUTED = '#5B6676'

_FONT_DIRS = [r'C:\Windows\Fonts', '/usr/share/fonts/truetype/dejavu', '/usr/share/fonts/truetype/roboto',
              '/Library/Fonts', '/System/Library/Fonts/Supplemental']
_FONT_FILES = {
    'head': ['RobotoCondensed-Bold.ttf', 'bahnschrift.ttf', 'arialbd.ttf', 'DejaVuSansCondensed-Bold.ttf', 'Arial Bold.ttf'],
    'bold': ['Roboto-Bold.ttf', 'segoeuib.ttf', 'arialbd.ttf', 'DejaVuSans-Bold.ttf', 'Arial Bold.ttf'],
    'body': ['Roboto-Regular.ttf', 'segoeui.ttf', 'arial.ttf', 'DejaVuSans.ttf', 'Arial.ttf'],
    'black': ['ariblk.ttf', 'Arial Black.ttf', 'DejaVuSans-Bold.ttf', 'arialbd.ttf'],
}
_font_cache = {}


def font(kind, size):
    key = (kind, size)
    if key not in _font_cache:
        for name in _FONT_FILES[kind]:
            for d in _FONT_DIRS:
                p = os.path.join(d, name)
                if os.path.exists(p):
                    _font_cache[key] = ImageFont.truetype(p, size)
                    break
            if key in _font_cache:
                break
        else:
            _font_cache[key] = ImageFont.load_default(size)
    return _font_cache[key]


def rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def lum(h):
    r, g, b = [c / 255 for c in rgb(h)]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def pick_accent(spec):
    """Most saturated, not-too-light colour of the design: the per-product accent inside the fixed format."""
    cands = [spec['base']['hex']] + [i['hex'] for i in spec['inks']]

    def score(h):
        r, g, b = [c / 255 for c in rgb(h)]
        _, l, s = colorsys.rgb_to_hls(r, g, b)
        return s * 0.7 + (1 - lum(h)) * 0.5 - (0.8 if lum(h) > 0.75 else 0)
    return max(cands, key=score)


def on_color(h):
    return '#FFFFFF' if lum(h) < 0.6 else INK


def logo(kind, height, color='#FFFFFF'):
    """BRAND logo from the traced vector in lib/logo_<kind>.txt."""
    import core
    if kind == 'kids':  # kids logo is a tall wave + wordmark: give it more height to read at the same size
        height = round(height * 1.7)
    head, d = open(os.path.join(LIB, f'logo_{kind}.txt'), encoding='utf-8').read().split('\n', 1)
    w, h = map(float, head.split())
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}"><path d="{d.strip()}" fill="{color}" fill-rule="evenodd"/></svg>'
    tmp = os.path.join(os.environ.get('TEMP', '/tmp'), f'brand_logo_{kind}_{color.lstrip("#")}.png')
    if not os.path.exists(tmp):
        core.render(svg, tmp, scale=2)
    im = Image.open(tmp).convert('RGBA')
    return im.resize((round(im.width * height / im.height), height), Image.LANCZOS)


def wrap(draw, text, fnt, width):
    lines = []
    for para in str(text).split('\n'):
        cur = ''
        for word in para.split():
            t = (cur + ' ' + word).strip()
            if draw.textlength(t, font=fnt) <= width or not cur:
                cur = t
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
    return lines


def fit_text(draw, text, kind, size, width, max_lines, min_size=40):
    """Shrink the font until the text fits in max_lines."""
    while True:
        f = font(kind, size)
        lines = wrap(draw, text, f, width)
        if len(lines) <= max_lines or size <= min_size:
            return f, lines[:max_lines]
        size -= 4


def draw_lines(draw, xy, lines, fnt, fill, spacing=1.15):
    x, y = xy
    for ln in lines:
        draw.text((x, y), ln, font=fnt, fill=fill)
        y += round(fnt.size * spacing)
    return y


def cover(im, w, h, focus_y=0.4):
    """Crop-fill; focus_y keeps heads (upper part) in frame."""
    s = max(w / im.width, h / im.height)
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    x = (im.width - w) // 2
    y = round((im.height - h) * focus_y)
    return im.crop((x, y, x + w, y + h))


def rounded(im, r):
    m = Image.new('L', im.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, im.width - 1, im.height - 1], r, fill=255)
    out = im.convert('RGBA')
    out.putalpha(m)
    return out


def gradient(w, h, top_alpha, bottom_alpha, color=(8, 14, 24)):
    g = Image.new('L', (1, h))
    for y in range(h):
        g.putpixel((0, y), round(top_alpha + (bottom_alpha - top_alpha) * (y / max(h - 1, 1)) ** 1.6))
    layer = Image.new('RGBA', (w, h), color + (0,))
    layer.putalpha(g.resize((w, h)))
    return layer


def shadow(canvas, box, r, blur=24, alpha=60):
    sh = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle(box, r, fill=(0, 0, 0, alpha))
    canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur)))


def check_icon(draw, cx, cy, r, color):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    c = on_color(color)
    w = max(3, r // 4)
    draw.line([(cx - r * .45, cy + r * .02), (cx - r * .1, cy + r * .38), (cx + r * .5, cy - r * .35)], fill=c, width=w, joint='curve')


# ---------- card templates (W x H = 1200 x 1600) ----------

def card_hero(ctx, photo, headline, bullets):
    W, H = ctx['size']
    c = cover(photo, W, H, 0.35).convert('RGBA')
    c.alpha_composite(gradient(W, H // 2, 0, 215), (0, H - H // 2))
    c.alpha_composite(gradient(W, 260, 120, 0), (0, 0))
    c.alpha_composite(logo(ctx['logo_kind'], 64), (70, 64))
    d = ImageDraw.Draw(c)
    pills = [b for b in bullets if b][:3]
    pf = font('bold', 38)
    # pills from the bottom up, then headline above them
    y = H - 90
    rows = []
    for b in reversed(pills):
        lines = wrap(d, b, pf, W - 220)[:2]
        h = 34 + len(lines) * 46
        y -= h
        rows.append((y, lines, h))
        y -= 18
    hf, hl = fit_text(d, headline, 'head', 112, W - 140, 3)
    y -= 26 + len(hl) * round(hf.size * 1.05)
    draw_lines(d, (70, y), hl, hf, '#FFFFFF', 1.05)
    for py, lines, h in rows:
        tw = max(d.textlength(t, font=pf) for t in lines)
        d.rounded_rectangle([70, py, 70 + tw + 110, py + h], 26, fill=ctx['accent'])
        check_icon(d, 70 + 42, py + h // 2, 17, on_color(ctx['accent']))
        draw_lines(d, (70 + 80, py + 15), lines, pf, on_color(ctx['accent']), 1.2)
    return c


def card_benefits(ctx, photo, headline, bullets):
    W, H = ctx['size']
    c = Image.new('RGBA', (W, H), PAPER)
    d = ImageDraw.Draw(c)
    lg = logo(ctx['logo_kind'], 44, INK)
    c.alpha_composite(lg, (70, 60))
    hf, hl = fit_text(d, headline, 'head', 86, W - 140, 2)
    y = draw_lines(d, (70, 60 + lg.height + 24), hl, hf, INK, 1.05) + 30
    ph = 1600 - y - 560
    pbox = (70, y, W - 70, y + ph)
    shadow(c, pbox, 36)
    c.alpha_composite(rounded(cover(photo, pbox[2] - pbox[0], ph, 0.3), 36), (70, y))
    items = [b for b in bullets if b][:4]
    gy = y + ph + 40
    cw, ch = (W - 140 - 30) // 2, 225
    bf = font('bold', 36)
    for i, b in enumerate(items):
        x = 70 + (i % 2) * (cw + 30)
        yy = gy + (i // 2) * (ch + 30)
        d.rounded_rectangle([x, yy, x + cw, yy + ch], 28, fill='#FFFFFF')
        d.ellipse([x + 32, yy + 32, x + 92, yy + 92], fill=ctx['accent'])
        num = str(i + 1)
        nf = font('head', 38)
        d.text((x + 62 - d.textlength(num, font=nf) / 2, yy + 40), num, font=nf, fill=on_color(ctx['accent']))
        f, lines = fit_text(d, b, 'bold', 42, cw - 64, 2, 28)
        draw_lines(d, (x + 32, yy + 112), lines, f, INK, 1.18)
    return c


def card_list(ctx, photo, headline, bullets):
    W, H = ctx['size']
    c = Image.new('RGBA', (W, H), PAPER)
    c.alpha_composite(cover(photo, W, 1000, 0.3).convert('RGBA'), (0, 0))
    c.alpha_composite(gradient(W, 220, 110, 0), (0, 0))
    c.alpha_composite(logo(ctx['logo_kind'], 52), (70, 60))
    top = 900
    panel = Image.new('RGBA', (W, H - top), (0, 0, 0, 0))
    ImageDraw.Draw(panel).rounded_rectangle([0, 0, W, H - top + 60], 56, fill=PAPER)
    c.alpha_composite(panel, (0, top))
    d = ImageDraw.Draw(c)
    d.rounded_rectangle([70, top + 60, 190, top + 72], 6, fill=ctx['accent'])
    hf, hl = fit_text(d, headline, 'head', 92, W - 140, 2)
    y = draw_lines(d, (70, top + 100), hl, hf, INK, 1.05) + 34
    items = [b for b in bullets if b][:4]
    bf = font('body', 46)
    for b in items:
        lines = wrap(d, b, bf, W - 140 - 90)[:2]
        if y + len(lines) * 57 > H - 40:
            break
        check_icon(d, 70 + 27, y + 29, 25, ctx['accent'])
        y = draw_lines(d, (70 + 82, y), lines, bf, INK, 1.22) + 28
    return c


def card_print(ctx, photo, headline, bullets):
    W, H = ctx['size']
    spec = ctx['spec']
    base = spec['base']['hex']
    c = Image.new('RGBA', (W, H), PAPER)
    d = ImageDraw.Draw(c)
    # soft colour field behind the cap
    d.rounded_rectangle([40, 300, W - 40, 1140], 48, fill=_tint(base, 0.86))
    lg = logo(ctx['logo_kind'], 40, INK)
    c.alpha_composite(lg, (70, 50))
    hf, hl = fit_text(d, headline, 'head', 86 if lg.height < 60 else 72, W - 140, 2 if lg.height < 60 else 1)
    draw_lines(d, (70, 50 + lg.height + 16), hl, hf, INK, 1.05)
    cap = ctx['caps'][0].convert('RGBA')
    s = min((W - 200) / cap.width, 760 / cap.height)
    cap = cap.resize((round(cap.width * s), round(cap.height * s)), Image.LANCZOS)
    sh = Image.new('RGBA', c.size, (0, 0, 0, 0))
    sh.paste((0, 0, 0, 90), ((W - cap.width) // 2 + 10, 340 + 30), cap.split()[3])
    c.alpha_composite(sh.filter(ImageFilter.GaussianBlur(26)))
    c.alpha_composite(cap, ((W - cap.width) // 2, 340 + (760 - cap.height) // 2))
    # palette row
    y = 1180
    sw = [(spec['base']['name'], base, 'шапочка')] + [(i['name'], i['hex'], 'принт') for i in spec['inks']]
    colw = (W - 140) // len(sw)
    nf, sf = font('bold', 28), font('body', 24)
    for i, (n, h, role) in enumerate(sw):
        cx = 70 + i * colw + colw // 2
        d.ellipse([cx - 32, y - 20, cx + 32, y + 44], fill=h, outline='#C9CDD3', width=2)
        for j, ln in enumerate(wrap(d, n, nf, colw - 16)[:2]):
            d.text((cx - d.textlength(ln, font=nf) / 2, y + 56 + j * 32), ln, font=nf, fill=INK)
        d.text((cx - d.textlength(role, font=sf) / 2, y + 124), role, font=sf, fill=MUTED)
    y = 1350
    bf = font('body', 36)
    for b in [b for b in bullets if b][:3]:
        lines = wrap(d, b, bf, W - 140 - 70)[:2]
        if y + len(lines) * 44 > H - 40:
            break
        check_icon(d, 70 + 20, y + 22, 18, ctx['accent'])
        y = draw_lines(d, (70 + 60, y), lines, bf, INK, 1.2) + 14
    return c


def card_clean(ctx, photo, headline, bullets):
    W, H = ctx['size']
    c = cover(photo, W, H, 0.35).convert('RGBA')
    c.alpha_composite(gradient(W, 300, 0, 120), (0, H - 300))
    lg = logo(ctx['logo_kind'], 56)
    c.alpha_composite(lg, (W - lg.width - 70, H - lg.height - 70))
    if headline:
        d = ImageDraw.Draw(c)
        f = font('bold', 40)
        tw = d.textlength(headline, font=f)
        d.rounded_rectangle([70, 70, 70 + tw + 60, 70 + 76], 38, fill=ctx['accent'])
        d.text((100, 84), headline, font=f, fill=on_color(ctx['accent']))
    return c


def _tint(h, k):
    r, g, b = rgb(h)
    return '#%02X%02X%02X' % tuple(round(v + (255 - v) * k) for v in (r, g, b))


CARD_TEMPLATES = dict(hero=card_hero, benefits=card_benefits, list=card_list, print=card_print, clean=card_clean)


def render_card(ctx, template, photo, headline, bullets):
    if photo is None:  # template needs a photo but none chosen: use the clean cap on a tinted field
        photo = cap_on_field(ctx, ctx['size'])
    return CARD_TEMPLATES[template](ctx, photo, headline or '', bullets or []).convert('RGB')


def cap_on_field(ctx, size):
    W, H = size
    c = Image.new('RGBA', (W, H), _tint(ctx['spec']['base']['hex'], 0.82))
    cap = ctx['caps'][0].convert('RGBA')
    s = min(W * 0.8 / cap.width, H * 0.6 / cap.height)
    cap = cap.resize((round(cap.width * s), round(cap.height * s)), Image.LANCZOS)
    c.alpha_composite(cap, ((W - cap.width) // 2, (H - cap.height) // 2))
    return c.convert('RGB')


# ---------- rich content block (1200 x 800): photo half + text half, alternating sides ----------

def render_rich(ctx, i, photo, headline, text):
    W, H = ctx['rich_size']
    c = Image.new('RGBA', (W, H), PAPER if i % 2 == 0 else '#FFFFFF')
    pw = W // 2
    img = cover(photo if photo is not None else cap_on_field(ctx, (pw, H)), pw, H, 0.3)
    left = i % 2 == 0
    c.paste(img, (0 if left else W - pw, 0))
    d = ImageDraw.Draw(c)
    x = (pw + 60) if left else 60
    tw = W - pw - 120
    d.rounded_rectangle([x, 90, x + 100, 102], 6, fill=ctx['accent'])
    hf, hl = fit_text(d, headline or '', 'head', 64, tw, 3, 36)
    y = draw_lines(d, (x, 130), hl, hf, INK, 1.05) + 24
    bf, bl = fit_text(d, text or '', 'body', 32, tw, 10, 30)
    draw_lines(d, (x, y), bl, bf, MUTED, 1.3)
    return c.convert('RGB')
