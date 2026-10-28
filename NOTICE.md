# Third-party data

- `lib/ral_classic.json` — RAL Classic colour names and sRGB approximations from the npm package
  [ral-colors](https://www.npmjs.com/package/ral-colors) 1.0.1 (MIT). Chinese names added. RAL is a trademark of
  RAL gGmbH; screen colours are approximations — approve colours on physical RAL samples.
- Cap outlines `lib/cap_*.txt` are simplified templates; replace them with the exact flat patterns of your manufacturer
  (`lib/trace_shapes.py` traces outlines from images placed in `lib/shape_src/`).
- `lib/logo_*.txt` are placeholders; create your own with `tools/make_logo.py`.
