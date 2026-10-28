"""Brand of the generated products. The code and the prompts use the neutral token BRAND; the real name comes from
BRAND_NAME (environment, .env or .env.example) and is put into every prompt right before it is sent to the model.

    BRAND_NAME=ACME   ->  "the BRAND logo" -> "the ACME logo",  "B-R-A-N-D" -> "A-C-M-E"
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _from_env_files():
    for name in ('.env', '.env.example'):
        p = os.path.join(ROOT, name)
        if os.path.exists(p):
            for line in open(p, encoding='utf-8'):
                k, _, v = line.strip().partition('=')
                if k.strip() == 'BRAND_NAME' and v.strip():
                    return v.strip().strip('"').strip("'")
    return None


NAME = (os.environ.get('BRAND_NAME') or _from_env_files() or 'BRAND').strip()
LETTERS = '-'.join(NAME)


def text(s):
    """Put the brand into a prompt / label."""
    if NAME == 'BRAND' or not isinstance(s, str):
        return s
    # ASCII-only word boundaries: Chinese characters right next to the token (BRAND标志) must not block it
    return re.sub(r'(?<![A-Za-z0-9_])BRAND(?![A-Za-z0-9_])', NAME, s.replace('B-R-A-N-D', LETTERS))


def contents(c):
    """Recursively brand the string parts of a Gemini `contents` argument (images and other objects pass through)."""
    if isinstance(c, str):
        return text(c)
    if isinstance(c, (list, tuple)):
        return type(c)(contents(x) for x in c)
    return c
