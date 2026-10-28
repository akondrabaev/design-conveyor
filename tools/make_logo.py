"""Turn your logo into the vector file the engine prints with (one ink, traced with potrace).

    python tools/make_logo.py my_logo.png adult        # -> lib/logo_adult.txt  (wordmark: adult caps, PU, constructor)
    python tools/make_logo.py my_logo_kids.png kids    # -> lib/logo_kids.txt   (logo for kids caps)
    python tools/make_logo.py --text ACME adult        # quick placeholder from text

Input: a dark logo on a light / transparent background (PNG, JPG). Output format: first line "width height",
then one SVG path (even-odd fill) in that coordinate space.
"""
import argparse, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'lib'))


def mask_from_image(path):
    im = Image.open(path).convert('RGBA')
    bg = Image.new('RGBA', im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    g = np.asarray(bg.convert('L'))
    m = g < 128
    ys, xs = np.where(m)
    return m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def mask_from_text(text):
    font = None
    for f in ('arialbd.ttf', 'DejaVuSans-Bold.ttf', 'Arial Bold.ttf'):
        for d in (r'C:\Windows\Fonts', '/usr/share/fonts/truetype/dejavu', '/Library/Fonts'):
            if os.path.exists(os.path.join(d, f)):
                font = ImageFont.truetype(os.path.join(d, f), 240)
                break
        if font:
            break
    font = font or ImageFont.load_default(240)
    im = Image.new('L', (300 * len(text) + 100, 400), 255)
    ImageDraw.Draw(im).text((40, 40), text, font=font, fill=0)
    m = np.asarray(im) < 128
    ys, xs = np.where(m)
    return m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def trace(mask):
    import potrace
    bm = potrace.Bitmap(~np.pad(mask, 4))   # potracer traces False pixels
    pl = bm.trace(turdsize=10, alphamax=1.0, opticurve=True, opttolerance=0.2)
    P = lambda p: f'{p.x - 4:.1f},{p.y - 4:.1f}' if hasattr(p, 'x') else f'{p[0] - 4:.1f},{p[1] - 4:.1f}'
    d = ''
    for c in pl:
        d += f'M{P(c.start_point)} '
        for seg in c.segments:
            d += f'L{P(seg.c)} L{P(seg.end_point)} ' if seg.is_corner else f'C{P(seg.c1)} {P(seg.c2)} {P(seg.end_point)} '
        d += 'Z '
    return d


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('src', nargs='?', help='logo image (dark on light / transparent)')
    ap.add_argument('kind', choices=['adult', 'kids'])
    ap.add_argument('--text', help='make a placeholder wordmark from text instead of an image')
    a = ap.parse_args()
    m = mask_from_text(a.text) if a.text else mask_from_image(a.src)
    h, w = m.shape
    out = os.path.join(ROOT, 'lib', f'logo_{a.kind}.txt')
    open(out, 'w').write(f'{w} {h}\n{trace(m)}')
    print(f'{out}: {w}x{h}')
