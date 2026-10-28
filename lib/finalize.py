"""Verify exported PNGs, write per-design specs, lookbook and README."""
import os, glob, json
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from build import OUT
ASSUMED_MM = {'sym': 220, 'long': 245}   # hand-drawn round 1-2 designs only
from core import GAP, MINW, MARGIN
from designs import DESIGNS

DESC = {
 'w1_jelly_waltz': ('Три медузы разного размера медленно «танцуют» вверх по шапочке. Купола с фестончатым краем и вырезанными арками, щупальца — волнистые ленты.',
                    'Женщины 25–45, фитнес-плавание, бассейн и открытая вода; спокойный «нежный» сегмент.',
                    'Крупные силуэты читаются издалека; 2 краски; вертикальная композиция хорошо работает на высоком куполе шапочки для длинных волос.'),
 'w2_koi_circle': ('Два карпа кои плывут по кругу, образуя знак равновесия (инь-ян). На стороне B — один кои, ныряющий в круги на воде.',
                   'Женщины 25–50, премиальный сегмент, подарок.',
                   'Круговая композиция стабильна на изогнутой поверхности; пятна коралла отделены от белого технологическим зазором — без наложения трафаретов.'),
 'w3_ripple_leaves': ('Два листа монстеры; нижняя часть листьев «под водой» — разрезана волнистыми бликами ряби.',
                      'Женщины 20–40, любители тропической/ботанической эстетики, отпуск, SPA.',
                      'Метафора «граница воды» оригинальна; 2 краски; на светлой шапочке меняется пара красок.'),
 'k1_shark_pup': ('Шапочка превращает ребёнка в акулёнка: глаз, жабры, улыбка с зубами, светлое брюшко. Сторона B — зеркальная мордочка.',
                  'Дети 4–10 лет.', 'Самый «покупательский» детский приём — шапочка-персонаж; двусторонняя печать, обе стороны смотрят вперёд.'),
 'k2_octo_hug': ('Осьминог Окто сидит на голове: на стороне A — мордочка и щупальца, на стороне B — щупальца «обнимают» голову сверху, пузырьки и рыбки.',
                 'Дети 3–9 лет.', 'Яркий персонаж, 3 краски, хорошо смотрится на любой светлой/яркой шапочке.'),
 'k3_yellow_sub': ('Жёлтая подлодка с иллюминаторами и перископом, пузыри и стайка рыбок.',
                   'Дети 4–12 лет, мальчики и девочки.', '2 краски, крупные простые формы — дешёвая и надёжная печать.'),
 'u1_refraction': ('Слово SWIM разрезано «линией воды»: нижняя часть сдвинута, как при преломлении. Буквы нарисованы с нуля (не шрифт).',
                   'Подростки и взрослые 14–40, городские бассейны, клубный мерч.', 'Мгновенно считываемая идея, 2 краски, крупная типографика без мелкого текста.'),
 'u2_bathymetry': ('Карта глубин: изолинии океанского дна вокруг впадины, самая глубокая точка залита. Сторона B — другой участок той же карты.',
                   'Взрослые 18–55, открытая вода, триатлон, «умный» минимализм.', 'Узор на всю сторону в духе вашей геометрической линейки, но с осмысленным сюжетом; 2 краски.'),
 'u3_manta_glide': ('Манта-скат скользит по диагонали, за ней — два маленьких ската. Передний край крыльев выделен бирюзой, «рёбра» — вырезы.',
                    'Взрослые и подростки, унисекс.', 'Динамичная диагональ, крупный силуэт, 2 краски.'),
}

def verify_png(p, palette):
    im = Image.open(p); ok_mode = im.mode == 'RGBA'
    a = np.array(im.convert('RGBA'))
    alpha = a[..., 3]
    transparent_share = float((alpha == 0).mean())
    corners_clear = all(alpha[y, x] == 0 for y in (0, -1) for x in (0, -1))
    op = a[alpha == 255][:, :3]
    cols, cnt = np.unique(op.reshape(-1, 3), axis=0, return_counts=True)
    main = [('#%02X%02X%02X' % tuple(c)) for c, n in zip(cols, cnt) if n > 0.002*len(op)]
    pal = [h.upper() for h in palette]
    return dict(mode=im.mode, size=im.size, rgba_ok=ok_mode, transparent_share=round(transparent_share, 3),
                corners_transparent=corners_clear, opaque_colours=main, colours_match_palette=set(main) <= set(pal), n_colours=len(main))

def esc(s): return s.replace('|', '/')

def write_spec(D):
    """Gemini designs: Excel spec in English and Chinese with RAL colours (spec_xlsx). Hand-drawn round 1-2
    designs (no _gemini/spec.json) keep the old Russian markdown spec below."""
    if os.path.exists(f"{OUT}/{D['slug']}/_gemini/spec.json"):
        import spec_xlsx
        md = f"{OUT}/{D['slug']}/{D['slug']}_spec.md"
        if os.path.exists(md):
            os.remove(md)
        return spec_xlsx.write(D['slug'])
    od = f"{OUT}/{D['slug']}"; slug = D['slug']
    checks = json.load(open(f'{od}/_checks.json'))
    inks = [i[1] for i in D['inks']]
    sides = list(D['sides'].keys())
    pngv = {s: verify_png(f'{od}/{slug}_side-{s}_print_transparent.png', inks) for s in sides}
    idea, aud, why = DESC[slug]
    mm = ASSUMED_MM[D['cap']] / 1000
    capname = 'шапочка для длинных волос' if D['cap'] == 'long' else 'симметричная шапочка'
    L = [f"# {D['title']} — спецификация", '',
         f"**Линейка:** {D['segment']}  ", f"**Изделие:** {capname} (силуэт из lib/cap_*.txt)  ",
         f"**Логотип:** {'детский (волна + BRAND)' if D['logo']=='kids' else 'взрослый (BRAND)'} — краской «{D['inks'][D['logo_ink']][0]}»  ",
         f"**Печать:** {'двусторонняя (A + B)' if len(sides) > 1 else 'односторонняя (сторона A)'}, трафарет, {len([i for i in D['inks']])} краски(-а) = {len(D['inks'])} трафарета(-ов) на сторону", '',
         '## Идея', idea, '', f'**Аудитория:** {aud}', '', f'**Почему работает на шапочке:** {why}', '',
         '## Краски принта', '| # | Краска | HEX | Ближайший RAL (приблизительно) | Файл трафарета |', '|---|---|---|---|---|']
    for i, (n, h, ral, fs) in enumerate(D['inks']):
        L.append(f'| {i+1} | {n} | `{h}` | {esc(ral)} | `*_stencil{i+1}_{fs}` |')
    L += ['', '## Цвета шапочки (до 3 вариантов)', '| Вариант | HEX (мокап) | RAL материала | Краски принта |', '|---|---|---|---|']
    for V in D['variants']:
        vi = V.get('inks', inks)
        L.append(f"| {V['cap_name']} | `{V['cap_hex']}` | {esc(V['cap_ral'])} | {', '.join(f'`{x}`' for x in vi)}{' — ' + V['note'] if V.get('note') else ''} |")
    L += ['', '> RAL указан как ближайший визуальный аналог, не как точное совпадение. Цвет на экране ≠ цвет силикона и краски: финальный оттенок утверждать по физическому образцу / выкрасу.', '',
          '## Расположение и размеры (ПРЕДВАРИТЕЛЬНО)',
          f"- Все файлы принта в координатах плоской шапочки: холст = габарит шапочки (1000 px по ширине; PNG — 3000 px).",
          f"- Условная ширина плоской шапочки **{ASSUMED_MM[D['cap']]} мм** — это допущение, замените фактическим замером. Тогда 1 px ≈ {mm:.2f} мм.",
          f"- Отступ от края (зона без печати): {MARGIN} px ≈ {MARGIN*mm:.0f} мм; мин. толщина линии/детали: {MINW} px ≈ {MINW*mm:.1f} мм; технологический зазор между красками: {GAP} px ≈ {GAP*mm:.1f} мм.",
          '- Логотип — сторона A, внизу слева (как в текущей линейке).']
    if D['cap'] == 'long' and 'B' in sides:
        L.append('- Сторона B у шапочки для длинных волос печатается по **зеркальному** шаблону (объём под волосы оказывается слева) — это учтено в файлах side-B.')
    if len(sides) > 1:
        L.append('- Сторона B на голове — противоположный бок; рисунок B ориентирован так, чтобы «смотреть вперёд» вместе со стороной A.')
    L += ['', '## Автоматическая проверка']
    for s in sides:
        c = checks[s]; v = pngv[s]
        L.append(f"**Сторона {s}:** красок {c['inks_used']} (≤3: {'да' if c['inks_ok'] else 'НЕТ'}); за зоной печати: {c['outside_safe_px2']} px² ({'ок' if c['inside_safe_ok'] else 'ОШИБКА'}); "
                 f"мин. зазор между красками: {c['min_gap_between_inks_px'] if c['min_gap_between_inks_px'] is not None else '—'} px; "
                 f"доля участков тоньше {MINW} px по краскам: {c['thin_area_pct_by_ink']} %; "
                 f"PNG: {v['mode']}, {v['size'][0]}×{v['size'][1]}, прозрачных пикселей {v['transparent_share']*100:.0f}%, углы прозрачные: {'да' if v['corners_transparent'] else 'нет'}, "
                 f"цвета в PNG {v['opaque_colours']} — совпадают с палитрой: {'да' if v['colours_match_palette'] else 'НЕТ'}  ")
    L += ['', '## Технические замечания',
          '- Краски не перекрываются: верхний элемент вырезает нижний с зазором — каждый трафарет печатается независимо, без треппинга.',
          '- Логотип в файлах — из lib/logo_*.txt (заменитель). Перед изготовлением сеток подставьте оригинальный вектор логотипа.' +
          (' У детского логотипа тонкие внутренние штрихи волн: при ширине логотипа ~33 мм они ≈0,4–0,5 мм, контур волн ≈1 мм — для трафарета это на грани. Рекомендую: логотип ≥45–50 мм или упрощённая «трафаретная» версия (без внутренних завитков).' if D['logo'] == 'kids' else ''),
          '- Участки «тоньше мин. толщины» в отчёте — это в основном острые кончики (хвосты, щупальца, зубцы), а не тонкие линии; если печатник требует, кончики можно затупить.',
          '- Векторы: SVG с чистыми контурами (полилинии высокой плотности), по одному слою-группе на краску; открываются в Illustrator/Corel/Inkscape.', '',
          '## Файлы']
    for f in sorted(os.listdir(od)):
        if not f.startswith('_'): L.append(f'- `{f}`')
    open(f'{od}/{slug}_spec.md', 'w').write('\n'.join(L) + '\n')
    return pngv

TITLE = __import__('brand').NAME + ' · капсула из 9 принтов (трафаретная печать, ≤3 краски)'
def lookbook():
    font_b = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 30)
    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 21)
    font_h = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 44)
    cw, ch = 560, 560
    W = 3*cw + 80; H = 130 + 3*(ch + 40)
    sheet = Image.new('RGB', (W, H), '#DADDE1'); d = ImageDraw.Draw(sheet)
    d.text((40, 40), TITLE, font=font_h, fill='#1d1d1d')
    for i, D in enumerate(DESIGNS):
        r, c = divmod(i, 3)
        x = 40 + c*cw; y = 130 + r*(ch + 40)
        hero = Image.open(f"{OUT}/{D['slug']}/_hero.png").convert('RGBA')
        hero.thumbnail((cw - 30, 440))
        sheet.paste(hero, (x + (cw - 30 - hero.size[0])//2, y), hero)
        d.text((x, y + 455), f"{D['segment']} · {D['title']}", font=font_b, fill='#1d1d1d')
        sw = x
        for n, h, *_ in D['inks']:
            d.rectangle([sw, y + 500, sw + 26, y + 526], fill=h, outline='#555'); sw += 32
        d.text((sw + 6, y + 501), f"{len(D['inks'])} кр. · {'2 стороны' if len(D['sides'])>1 else '1 сторона'} · {len(D['variants'])} цвета шапочки", font=font, fill='#333')
    sheet.save(f'{OUT}/BRAND_capsule_lookbook.png')

if __name__ == '__main__':
    allv = {}
    for D in DESIGNS: allv[D['slug']] = write_spec(D)
    lookbook()
    bad = {k: v for k, v in allv.items() for s, x in v.items() if not (x['rgba_ok'] and x['corners_transparent'] and x['colours_match_palette'] and x['n_colours'] <= 3)}
    print('PNG problems:', bad if bad else 'none')
    for k, v in allv.items(): print(k, {s: (x['n_colours'], x['opaque_colours']) for s, x in v.items()})
