"""Gemini step of the print pipeline.

1. art_direction(): text model proposes concept + cap base colour + <=3 ink colours (JSON).
2. render_print(): image model draws a flat screen-print pattern in exactly those colours.
3. quantize(): snaps the raster to the palette, removes specks, reports ink checks.
The result (indexed ink masks + palette) is what finalize.py vectorizes into stencils.

The API key is read from GEMINI_API_KEY and never printed.
"""
import io, json, os, re
import numpy as np
from PIL import Image
import cv2
from google import genai
from google.genai import types

TEXT_MODEL = os.environ.get("GEMINI_TEXT_MODEL", "gemini-3.5-flash")
IMAGE_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3-pro-image")
MIN_STROKE_PX = 8  # at 3000 px canvas width, same threshold as finalize.py checks

_client = None


class _BrandedModels:
    """client.models with the brand put into every prompt (lib/brand.py)."""
    def __init__(self, models):
        self._m = models

    def generate_content(self, model, contents, **kw):
        import brand
        return self._m.generate_content(model=model, contents=brand.contents(contents), **kw)

    def __getattr__(self, k):
        return getattr(self._m, k)


class _BrandedClient:
    def __init__(self, c):
        self._c = c
        self.models = _BrandedModels(c.models)

    def __getattr__(self, k):
        return getattr(self._c, k)


def make_client():
    return _BrandedClient(_make_client())


def _make_client():
    """Gemini client. GEMINI_BASE_URL (+ RELAY_SECRET) sends the requests through a relay, e.g. the
    Cloudflare worker in deploy/gemini-relay/, for servers in regions Google does not serve.
    Without them the client talks to Google directly (HTTPS_PROXY is honoured as usual)."""
    base = os.environ.get("GEMINI_BASE_URL", "").strip()
    if not base:
        return genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    headers = {"X-Relay-Secret": os.environ["RELAY_SECRET"]} if os.environ.get("RELAY_SECRET") else None
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"],
                        http_options=types.HttpOptions(base_url=base, headers=headers))


def client():
    global _client
    if _client is None:
        _client = make_client()
    return _client


ART_BRIEF = """You are the art director for BRAND, a swim cap brand. Swim caps are silicone,
printed by screen printing with at most 3 inks on a coloured cap base.
Theme for this design: {theme}
Liked directions so far: "refraction" (light bending through water) and "leaves in ripples".
Previous rejected attempts used candy pastels (#A8E6CF mint, #F4B6C2 pink) and clip-art motifs: avoid both.
{extra}
Return JSON only:
{{"slug": short latin snake_case id,
  "name": short design name in Russian,
  "concept": one sentence in Russian,
  "segment": "Женская" | "Детская" | "Унисекс",
  "base": {{"hex": main cap silicone colour, "name": Russian colour name, "ral": nearest RAL, marked (≈)}},
  "inks": [{{"hex":..., "name": Russian name, "ral": nearest RAL marked (≈), "file": short latin name, "role": "main|accent|detail"}}] (2 or 3 inks, each clearly distinct from base and from each other, deltaE > 20),
  "variants": [{{"hex":..., "name": Russian name, "ral": nearest RAL, "inks": [hex per ink, same order as "inks"]}}] (1-2 more cap colours; the same stencils are printed on them, but the ink colours may change per cap colour: every ink must stay clearly readable on that cap (deltaE > 30) - e.g. a white ink becomes navy on a white cap),
  "image_prompt": an English prompt for an image model describing the pattern only (composition, motif scale, line weight)}}"""

IMAGE_TEMPLATE = """Flat vector-style screen-print pattern for a silicone swim cap, seen flat (not a mockup).
{prompt}
Strict print rules: background is a solid flat fill of {base}. Use ONLY these solid ink colours: {inks}.
No gradients, no shading, no texture, no halftone, no anti-aliased soft edges, no text, no logos.
Bold shapes, every line at least 1% of image width thick, gaps between colours clearly visible.
Pattern fills the whole canvas edge to edge, landscape 4:3."""


REF_NOTE = "The attached images are the client's REFERENCES - what they roughly mean (character, mood, style, composition, colours). Use them as inspiration for the idea and style; do not copy them, and never copy brand or licensed characters or logos."


def art_direction(theme, extra="", images=()):
    last = None
    for model in (TEXT_MODEL, "gemini-3-flash-preview", "gemini-3.6-flash"):
        try:
            r = client().models.generate_content(
                model=model,
                contents=[ART_BRIEF.format(theme=theme, extra=extra) + ("\n" + REF_NOTE if images else ""), *images],
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=1.0),
            )
            break
        except Exception as e:  # overloaded or no quota on this model: try the next one
            last = e
    else:
        raise last
    d = json.loads(r.text)
    d["inks"] = d["inks"][:3]
    return d


def render_print(spec, refs=()):
    """refs: optional PIL images of liked examples, passed as style references."""
    import shapes
    if spec.get("shape") in shapes.KIDS:   # shaped kids caps: drawn on the cap template, along its outline
        import shape_canvas
        return shape_canvas.render(spec, client(), IMAGE_MODEL, types, TEXT_MODEL, refs=refs)
    prompt = IMAGE_TEMPLATE.format(
        prompt=spec["image_prompt"],
        base=spec["base"]["hex"],
        inks=", ".join(i["hex"] for i in spec["inks"]),
    )
    contents = [prompt] + [*refs]
    if refs:
        contents[0] += "\n" + REF_NOTE
    r = client().models.generate_content(
        model=IMAGE_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(aspect_ratio="4:3"),
        ),
    )
    for part in r.candidates[0].content.parts:
        if part.inline_data is not None:
            return Image.open(io.BytesIO(part.inline_data.data)).convert("RGB")
    raise RuntimeError("Gemini returned no image")


def _hex(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


def quantize(img, spec, width=3000):
    """Snap to base+inks in Lab space, drop specks/hairlines, return (index map, report).
    index 0 = base (no ink), 1..n = inks."""
    h = round(img.height * width / img.width)
    img = img.resize((width, h), Image.LANCZOS)
    pal = [_hex(spec["base"]["hex"])] + [_hex(i["hex"]) for i in spec["inks"]]
    lab = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2LAB).astype(np.float32)
    pal_lab = cv2.cvtColor(np.array([pal], dtype=np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)[0]
    # nearest palette colour, one colour at a time (a 4-D distance array needs ~300 MB at 3000 px)
    idx = np.zeros(lab.shape[:2], np.uint8)
    best = np.full(lab.shape[:2], np.inf, np.float32)
    for n, c in enumerate(pal_lab):
        d = ((lab - c) ** 2).sum(-1)
        idx[d < best] = n
        np.minimum(best, d, out=best)
    idx = cv2.medianBlur(idx, 5)

    # remove parts thinner than MIN_STROKE_PX: morphological open per ink, freed pixels go to base
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (MIN_STROKE_PX, MIN_STROKE_PX))
    report = {"inks": {}}
    for n in range(1, len(pal)):
        m = (idx == n).astype(np.uint8)
        opened = cv2.morphologyEx(m, cv2.MORPH_OPEN, k)
        thin = m.sum() - opened.sum()
        idx[(m == 1) & (opened == 0)] = 0
        report["inks"][n] = {
            "hex": spec["inks"][n - 1]["hex"],
            "coverage_pct": round(100 * opened.mean(), 1),
            "thin_removed_pct": round(100 * thin / max(m.sum(), 1), 2),
        }
    report["ink_count"] = sum(1 for v in report["inks"].values() if v["coverage_pct"] > 0.5)
    report["size"] = list(idx.shape[::-1])
    return idx, report


def render_index(idx, spec):
    pal = np.array([_hex(spec["base"]["hex"])] + [_hex(i["hex"]) for i in spec["inks"]], dtype=np.uint8)
    return Image.fromarray(pal[idx])


def ink_masks(idx, n_inks):
    """Binary PIL masks per ink, the input finalize.py vectorizes."""
    return [Image.fromarray(((idx == n) * 255).astype(np.uint8)) for n in range(1, n_inks + 1)]
