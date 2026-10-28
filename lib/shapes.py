"""Kids cap shapes: the standard ('sym') flat cap body plus moulded silicone parts (horns, fin, ears, crest).

Template orientation = side A as everywhere: left edge = forehead, right edge = nape, top arc = head midline.
The print of a shaped cap runs along the whole outline, moulded parts included (KIDS_MARGIN from the edge);
cap_<kind>_body.txt is the head part without the moulded parts (logo position, sizes, 3-D guide).
Shapes that are not left-right symmetric (fish, dragon) use the mirrored template on side B, like the long cap.

python3 lib/shapes.py   -> writes lib/cap_<kind>.txt (outline), lib/cap_<kind>_body.txt, lib/shapes.json (offsets);
round ears and PU caps are built here, the other kids shapes are traced from lib/shape_src/ (trace_shapes.py)
"""
import json, os
import numpy as np
from shapely.geometry import LineString, Polygon, Point
from shapely.ops import unary_union
from shapely import affinity

LIB = os.path.dirname(os.path.abspath(__file__))
PAD = 12

SHAPES = {
    'sym': dict(ru='Стандартная', en='Standard swim cap', zh='标准泳帽', photo='a classic swim cap'),
    'long': dict(ru='Для длинных волос', en='Swim cap for long hair', zh='长发泳帽', photo=None),
    'kid_horns': dict(ru='Детская: рожки', en='Kids swim cap with horns', zh='儿童角造型泳帽', kids=True, panel='front', parts='horns',
                      photo='a kids swim cap with two small soft moulded silicone horns on top of the head, left and right, same colour as the cap',
                      hint='two little horns on top: a cute friendly monster / calf / sheep / little dragon face'),
    'kid_fish': dict(ru='Детская: рыбка', en='Kids swim cap, fish shape', zh='儿童鱼造型泳帽', kids=True, asym=True, parts='fins',
                     photo='a kids swim cap shaped like a fish: a soft moulded silicone dorsal fin along the top of the head pointing backward and a small forked tail fin at the back of the head, same colour as the cap',
                     hint='a dorsal fin on top and a tail at the back of the head: draw a cute fish / shark / dolphin character'),
    'kid_cat': dict(ru='Детская: острые ушки', en='Kids swim cap with pointed ears', zh='儿童尖耳造型泳帽', kids=True, panel='front', parts='ears',
                    photo='a kids swim cap with two small pointed moulded silicone cat ears on top of the head, same colour as the cap',
                    hint='two pointed ears on top: a cute cat / fox / tiger / owl face'),
    'kid_bear': dict(ru='Детская: круглые ушки', en='Kids swim cap with round ears', zh='儿童圆耳造型泳帽', kids=True, panel='front', parts='ears',
                     photo='a kids swim cap with two round moulded silicone ears on top of the head like a teddy bear, same colour as the cap',
                     hint='two round ears on top: a cute bear / panda / mouse / frog face (frog: eyes in the ears)'),
    'kid_dragon': dict(ru='Детская: драконий гребень', en='Kids swim cap with dragon crest', zh='儿童龙脊造型泳帽', kids=True, asym=True, parts='crest',
                       photo='a kids swim cap with a row of soft moulded silicone spikes (a dragon crest) running along the middle of the head from the forehead over the crown to the nape, same colour as the cap',
                       hint='a spiky crest along the top: draw a cute dragon / dinosaur character'),
    # PU caps: coated fabric with stitched seams, full-colour print (heat transfer) on the wearer's left side
    'pu_kids': dict(ru='ПУ детская (полноцвет)', en='Kids PU swim cap', zh='儿童PU泳帽', pu=True,
                    photo='a kids PU swim cap: smooth satin-matte coated fabric with visible stitched seams (a narrow centre panel '
                          'from forehead to nape and two side panels) and a soft binding at the rim; the full-colour print sits on '
                          'the side panel'),
    'pu_adult': dict(ru='ПУ взрослая (полноцвет)', en='Adult PU swim cap', zh='成人PU泳帽', pu=True,
                     photo='an adult PU swim cap: smooth satin-matte coated fabric with visible stitched seams (a narrow centre '
                           'panel from forehead to nape and two side panels) and a soft binding at the rim; the full-colour print '
                           'sits on the side panel'),
}
KIDS = [k for k, v in SHAPES.items() if v.get('kids')]
KIDS_MARGIN = 12   # px of 1000 (~2.5 mm): print of shaped caps goes right up to the outline
PU = [k for k, v in SHAPES.items() if v.get('pu')]
# print area of a PU cap side panel, as fractions of the flat cap: centre x, centre y, max width, max height
PU_PRINT_BOX = (0.5, 0.55, 0.72, 0.78)   # the manufacturer prints PU caps over the full height and length; 'allover' uses all of it
# Two constructions. 'side': left/right halves joined front-to-back (standard, long, fish, dragon): flat image = side view,
# left edge = forehead. 'front': front/back halves joined ear to ear (horns, ears): flat image = front view of the face,
# left edge = wearer's right ear; side A = front (face), side B = back of the head.
FRONT = {k for k, v in SHAPES.items() if v.get('panel') == 'front'}


def panel(kind):
    return 'front' if kind in FRONT else 'side'


# Flat cap sizes from the supplier's drawings, cm: body width (without horns / ears / fins), height, width of the rim.
# Template: the body is 1000 px wide, so 1 px = width / 1000. Weight = silicone weight of the cap.
SIZES = {
    'sym': {'kids_50g': dict(g=50, w=22.0, h=19.0, rim=18.0, ru='детская 50 г', en='kids 50 g'),
            'adult_60g': dict(g=60, w=24.0, h=20.0, rim=20.8, ru='взрослая 60 г', en='adult 60 g')},
    'long': {'60g': dict(g=60, w=25.1, h=19.3, rim=19.6, ru='60 г', en='60 g')},
    'kid_horns': {'40g': dict(g=40, w=21.0, h=18.0, rim=18.0, ru='40 г', en='40 g')},
    'kid_fish': {'40g': dict(g=40, w=21.0, h=18.0, rim=17.5, ru='40 г', en='40 g'),
                 '60g': dict(g=60, w=22.2, h=19.2, rim=None, ru='60 г', en='60 g')},
    'kid_cat': {'40g': dict(g=40, w=21.0, h=18.0, rim=17.5, ru='40 г', en='40 g'),
                '60g': dict(g=60, w=22.2, h=19.2, rim=None, ru='60 г', en='60 g')},
    'kid_bear': {'60g': dict(g=60, w=22.2, h=19.2, rim=18.7, ru='60 г', en='60 g')},
    'kid_dragon': {'60g': dict(g=60, w=22.2, h=19.2, rim=18.7, ru='60 г', en='60 g')},
    'pu_kids': {'kids': dict(g=None, w=23.5, h=17.5, rim=None, ru='детская', en='kids')},
    'pu_adult': {'adult': dict(g=None, w=24.5, h=19.0, rim=None, ru='взрослая', en='adult')},
}


def sizes_for(kind, segment=None):
    """Sizes the design is produced in: every size of a shaped kids cap; standard cap by segment."""
    if kind == 'sym':
        key = 'kids_50g' if segment == 'Детская' else 'adult_60g'
        return {key: SIZES['sym'][key]}
    return SIZES.get(kind, SIZES['sym'])


def main_size(kind, segment=None):
    """The size the artwork is drawn for (the first one); other sizes scale the same artwork."""
    return next(iter(sizes_for(kind, segment).values()))
MIRROR_B = {'long'} | {k for k, v in SHAPES.items() if v.get('asym')}   # side B printed on the mirrored template


def _body():
    import core
    d = open(f'{LIB}/cap_sym.txt').read()
    return core.parse_path(d).buffer(0)


def _top(body, x):
    """y of the top edge of the body at x (y grows downward)."""
    minx, miny, maxx, maxy = body.bounds
    i = body.intersection(LineString([(x, miny - 10), (x, maxy + 10)]))
    return i.bounds[1]


def _soft(g, r=10):
    """Round the corners a little (moulded silicone has no sharp edges)."""
    return g.buffer(-r).buffer(r)


def _bear(b):
    return [Point(130, 70).buffer(112, quad_segs=32), Point(870, 70).buffer(112, quad_segs=32)]


# drawn parts; horns, pointed ears, fish and dragon crest are traced from the supplier's pictures (trace_shapes.py)
PARTS = dict(kid_bear=_bear)


def _pu_outline(kind):
    """Flat PU cap seen from the side: dome on top, straight sides, rim with binding; 1000 px wide, real proportions."""
    z = next(iter(SIZES[kind].values()))
    W, H = 1000, round(1000 * z['h'] / z['w'])
    ry = H * 0.62
    dome = Point(W / 2, ry).buffer(1, quad_segs=64)
    dome = affinity.scale(dome, W / 2, ry, origin=(W / 2, ry))
    from shapely.geometry import box
    g = unary_union([dome.intersection(box(0, 0, W, ry)), box(0, ry - 1, W, H)]).buffer(-25).buffer(25)
    return affinity.translate(g, 0, -g.bounds[1])


def generate():
    import core
    body = _body()
    meta = {}
    for kind, fn in PARTS.items():
        outline = unary_union([body] + fn(body)).buffer(0)
        minx, miny = outline.bounds[:2]
        dx, dy = PAD - minx, PAD - miny
        outline = affinity.translate(outline, dx, dy)
        b = affinity.translate(body, dx, dy)
        open(f'{LIB}/cap_{kind}.txt', 'w').write(core.geom_d(outline))
        open(f'{LIB}/cap_{kind}_body.txt', 'w').write(core.geom_d(b))
        meta[kind] = dict(offset=[round(dx, 2), round(dy, 2)])
    for kind in PU:   # no moulded parts: outline = body = print frame
        open(f'{LIB}/cap_{kind}.txt', 'w').write(core.geom_d(_pu_outline(kind)))
    old = json.load(open(f'{LIB}/shapes.json')) if os.path.exists(f'{LIB}/shapes.json') else {}
    json.dump(dict(old, **meta), open(f'{LIB}/shapes.json', 'w'), indent=1)
    import trace_shapes
    trace_shapes.main()
    return meta


def offset(kind):
    """Shift of the body inside the shape frame (logo and other body-referenced positions)."""
    p = f'{LIB}/shapes.json'
    return tuple(json.load(open(p)).get(kind, {}).get('offset', (0, 0))) if os.path.exists(p) else (0, 0)


if __name__ == '__main__':
    import sys
    sys.path.insert(0, LIB)
    print(generate())
