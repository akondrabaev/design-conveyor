"""Segment presets: extra art-direction text appended to gemini_gen.ART_BRIEF.
These are the exact texts used for the October 2026 designs."""
PRESETS = {
 'kids': dict(segment='Детская', extra=(
  "Segment MUST be \"Детская\" (kids 4-10). Fun, bright, playful, original characters only: "
  "no existing cartoon, film, game or brand characters, no recognizable copyrighted designs. "
  "Big friendly shapes with clear outlines, readable on a small cap, cheerful contrasting colours "
  "(not candy pastels). Characters with simple happy faces are welcome.")),
 'unisex_sport': dict(segment='Унисекс', extra=(
  "Segment MUST be \"Унисекс\" (adult swimmers, men and women). Premium performance sportswear aesthetic "
  "comparable to top swimwear brands: bold, dynamic, confident, speed and energy. Do NOT copy or imitate any "
  "brand logo, swoosh, wordmark or signature pattern of Arena, Nike, Speedo or others; style level only. "
  "Slavic folk geometry (rushnyk embroidery rhombuses, solar signs, stepped crosses, zigzags) reworked into a "
  "modern sporty graphic: sharp diagonals, speed lines, motion. Strong contrast, not folksy-cute, no clichés like matryoshka.")),
 'female': dict(segment='Женская', extra=(
  "Segment MUST be \"Женская\" (long swim cap for long hair, adult women). Tender, feminine, graceful, elegant: "
  "flowing curves, fine but printable linework, airy composition with breathing space. Soft refined palette "
  "(e.g. dusty rose, pearl, champagne, lilac, sage on a deeper or muted cap colour) with enough contrast to print; "
  "not candy pastels, not clip-art, no text.")),
 'free': dict(segment=None, extra=''),
}
