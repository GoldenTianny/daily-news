#!/usr/bin/env python3
"""가좌버핏 뉴스 — OG 썸네일 자동 생성기.

카테고리별로 다른 색감의 1200×630 PNG를 만들고, 해당 HTML의
og:image / twitter:image 메타를 새 PNG로 자동 갱신합니다.

사용:
  python3 tools/make_og.py archive/2026-05-27.html       # 단일 파일
  python3 tools/make_og.py --all                          # 전체 글 일괄
  python3 tools/make_og.py --samples                      # 카테고리별 샘플 4장

카테고리 자동 감지: 경로(/archive/, /analysis/, /companies/) + 책리뷰는
HTML 안의 "BOOK REVIEW" 라벨로 분기.
"""
import re
import html as html_lib
import argparse
import os
import sys
from datetime import date
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

REPO = Path(__file__).resolve().parent.parent
OG_DIR = REPO / 'assets' / 'og'
FONT_BOLD = str(REPO / 'assets' / 'fonts' / 'Pretendard-Bold.otf')
FONT_MEDIUM = str(REPO / 'assets' / 'fonts' / 'Pretendard-Medium.otf')
# Pretendard에 없는 한자(美·中·英 등)는 Apple SD Gothic Neo로 폴백.
HANJA_FALLBACK = '/System/Library/Fonts/AppleSDGothicNeo.ttc'
W, H = 1200, 630

# Pretendard 단일 파일(weight별로 다른 파일). 의미별 weight 지정용 상수.
WEIGHT_HEAVY, WEIGHT_BOLD, WEIGHT_MEDIUM, WEIGHT_REGULAR = 8, 6, 4, 3

PALETTES = {
    'daily': {
        'bg_top': (20, 33, 61), 'bg_mid': (26, 58, 108), 'bg_bot': (42, 92, 168),
        'glow': (192, 57, 43),
        'accent': (244, 211, 94),
        'badge_label': 'DAILY BRIEF',
        'badge_bg': (192, 57, 43),
        'badge_fg': (255, 255, 255),
    },
    'analysis': {
        'bg_top': (42, 13, 77), 'bg_mid': (58, 26, 108), 'bg_bot': (74, 42, 140),
        'glow': (76, 201, 240),
        'accent': (118, 220, 255),
        'badge_bg': (76, 201, 240),
        'badge_fg': (28, 16, 60),
    },
    'company': {
        'bg_top': (13, 59, 46), 'bg_mid': (20, 116, 95), 'bg_bot': (26, 140, 112),
        'glow': (244, 211, 94),
        'accent': (244, 211, 94),
        'badge_bg': (244, 211, 94),
        'badge_fg': (13, 59, 46),
    },
    'book': {
        'bg_top': (20, 33, 61), 'bg_mid': (26, 58, 108), 'bg_bot': (42, 92, 168),
        'glow': (244, 211, 94),
        'accent': (244, 211, 94),
        'badge_bg': (244, 211, 94),
        'badge_fg': (20, 33, 61),
    },
}


def fnt(size, weight=WEIGHT_HEAVY):
    # Heavy/Bold → Pretendard-Bold, Medium/Regular → Pretendard-Medium
    path = FONT_BOLD if weight >= WEIGHT_BOLD else FONT_MEDIUM
    return ImageFont.truetype(path, size)


def _hanja_fnt(size, weight):
    """한자 폴백 폰트 (Apple SD Gothic Neo)."""
    idx = 8 if weight >= WEIGHT_BOLD else 4
    return ImageFont.truetype(HANJA_FALLBACK, size, index=idx)


def _is_hanja(c):
    return 0x4E00 <= ord(c) <= 0x9FFF or 0x3400 <= ord(c) <= 0x4DBF


def _split_runs(text):
    """텍스트를 한자/비한자 run으로 분할."""
    if not text:
        return []
    runs = []
    cur = [text[0]]
    cur_is_hanja = _is_hanja(text[0])
    for c in text[1:]:
        h = _is_hanja(c)
        if h == cur_is_hanja:
            cur.append(c)
        else:
            runs.append((''.join(cur), cur_is_hanja))
            cur = [c]
            cur_is_hanja = h
    runs.append((''.join(cur), cur_is_hanja))
    return runs


def draw_text_smart(draw, pos, text, size, weight, fill):
    """한자 폴백 적용 텍스트 렌더링."""
    x, y = pos
    primary = fnt(size, weight)
    fallback = _hanja_fnt(size, weight)
    for run, is_hanja in _split_runs(text):
        f = fallback if is_hanja else primary
        draw.text((x, y), run, font=f, fill=fill)
        x += draw.textlength(run, font=f)


def textlength_smart(draw, text, size, weight):
    """한자 폴백 고려한 전체 텍스트 폭."""
    primary = fnt(size, weight)
    fallback = _hanja_fnt(size, weight)
    total = 0.0
    for run, is_hanja in _split_runs(text):
        f = fallback if is_hanja else primary
        total += draw.textlength(run, font=f)
    return total


def make_gradient(pal):
    img = Image.new('RGB', (W, H), pal['bg_top'])
    px = img.load()
    for y in range(H):
        ny = y / H
        for x in range(W):
            t = x / W * 0.45 + ny * 0.55
            if t < 0.5:
                k = t / 0.5
                c = tuple(pal['bg_top'][i] + (pal['bg_mid'][i]-pal['bg_top'][i])*k for i in range(3))
            else:
                k = (t-0.5)/0.5
                c = tuple(pal['bg_mid'][i] + (pal['bg_bot'][i]-pal['bg_mid'][i])*k for i in range(3))
            px[x, y] = (int(c[0]), int(c[1]), int(c[2]))
    glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for r, a in [(380, 22), (260, 30), (160, 35)]:
        gd.ellipse([(W-r-80, -r+120), (W+r-80, r+120)], fill=pal['glow'] + (a,))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=40))
    return Image.alpha_composite(img.convert('RGBA'), glow).convert('RGB')


def draw_brand_badge(draw, pal, badge_text):
    # 브랜드 라벨은 빼고 카테고리 배지만 표시 (2026-05-27 결정)
    if len(badge_text) > 24:
        badge_text = badge_text[:23] + '…'
    bw = textlength_smart(draw, badge_text, 34, WEIGHT_BOLD)
    px_pad, py_pad = 26, 14
    bx0, by0 = 60, 60
    draw.rounded_rectangle(
        [(bx0, by0), (bx0+bw+px_pad*2, by0+34+py_pad*2)],
        radius=26, fill=pal['badge_bg'])
    draw_text_smart(draw, (bx0+px_pad, by0+py_pad-2), badge_text,
                    34, WEIGHT_BOLD, pal['badge_fg'])


def draw_footer(draw, pal, left_text, right_text="gjbuffet.kr"):
    fy = H - 80
    if left_text:
        draw_text_smart(draw, (60, fy), left_text, 36, WEIGHT_BOLD, pal['accent'])
    if right_text:
        rw = textlength_smart(draw, right_text, 36, WEIGHT_BOLD)
        draw_text_smart(draw, (W-60-rw, fy), right_text, 36, WEIGHT_BOLD, (255, 255, 255))
    draw.rectangle([(0, H-8), (W, H)], fill=pal['accent'])


def wrap_korean(text, max_chars):
    if len(text) <= max_chars:
        return [text]
    for delim in [' — ', '—', ' · ', ' ', '·']:
        if delim in text:
            head, _, rest = text.partition(delim)
            if len(head) >= 4:
                return [head + (delim.rstrip() if delim != ' ' else '')] + wrap_korean(rest, max_chars)
    return [text[:max_chars]] + wrap_korean(text[max_chars:], max_chars)


def date_from_filename(fn):
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', fn)
    return f"{m.group(1)}.{m.group(2)}.{m.group(3)}" if m else ''


def day_of_week_kr(fn):
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', fn)
    if not m:
        return ''
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일'][date(y, mo, d).weekday()]


# ----- per-category generators -----

def gen_daily(filepath, html):
    pal = PALETTES['daily']
    img = make_gradient(pal)
    draw = ImageDraw.Draw(img)
    draw_brand_badge(draw, pal, pal['badge_label'])

    fn = os.path.basename(filepath)
    date_str = date_from_filename(fn)
    dow = day_of_week_kr(fn)

    # big date
    draw_text_smart(draw, (60, 160), date_str, 124, WEIGHT_HEAVY, (255, 255, 255))
    draw_text_smart(draw, (60, 300), f"{dow} · 오늘의 핵심뉴스", 44, WEIGHT_BOLD, pal['accent'])

    # headlines: override meta 우선, 없으면 top 3 h3
    override = re.search(r'<meta name="og-headlines-short" content="([^"]+)"', html)
    if override:
        headlines = [h.strip() for h in override.group(1).split('|') if h.strip()][:3]
    else:
        h3s = re.findall(r'<article[^>]*>.*?<h3[^>]*>(.*?)</h3>', html, re.S)
        headlines = [html_lib.unescape(re.sub(r'<[^>]+>', '', h)).strip() for h in h3s[:3]]

    # safety truncate
    headlines = [(h[:19] + '…') if len(h) > 20 else h for h in headlines]

    y = 380
    for head in headlines:
        draw_text_smart(draw, (60, y), f"·  {head}", 42, WEIGHT_MEDIUM, (220, 230, 245))
        y += 60

    draw_footer(draw, pal, "")
    return img


def gen_titled(filepath, html, category):
    pal = PALETTES[category]
    # extract cover label / h1 / subtitle
    cov_lbl = re.search(r'<div class="cover">.*?<div class="label">([^<]+)</div>', html, re.S)
    cov_h1 = re.search(r'<div class="cover">.*?<h1>(.*?)</h1>', html, re.S)
    cov_sub = re.search(r'<div class="cover">.*?<div class="subtitle">([^<]+)</div>', html, re.S)

    label = html_lib.unescape(cov_lbl.group(1).strip()) if cov_lbl else category.upper()

    # OG-specific override metas (preferred) — fall back to cover h1/subtitle
    override_title = re.search(r'<meta name="og-title-short" content="([^"]+)"', html)
    override_sub = re.search(r'<meta name="og-subtitle-short" content="([^"]+)"', html)

    if override_title:
        h1_parts = [p.strip() for p in override_title.group(1).split('|') if p.strip()]
    else:
        h1_raw = cov_h1.group(1) if cov_h1 else ''
        h1_parts = [re.sub(r'<[^>]+>', '', p).strip() for p in re.split(r'<br\s*/?>', h1_raw)]
        h1_parts = [html_lib.unescape(p) for p in h1_parts if p.strip()]

    if override_sub:
        sub_text = html_lib.unescape(override_sub.group(1).strip())
    else:
        sub_text = html_lib.unescape(cov_sub.group(1).strip()) if cov_sub else ''

    img = make_gradient(pal)
    draw = ImageDraw.Draw(img)
    draw_brand_badge(draw, pal, label)

    # title — up to 2 lines; if h1_parts has 2+, use first 2; else wrap single
    if len(h1_parts) >= 2:
        title_lines = h1_parts[:2]
    elif len(h1_parts) == 1:
        title_lines = wrap_korean(h1_parts[0], 13)[:2]
    else:
        title_lines = ['']

    # cap each line at ~14 chars (fits at 92pt)
    title_lines = [(l[:14] + '…') if len(l) > 15 else l for l in title_lines]

    y = 190
    for line in title_lines:
        draw_text_smart(draw, (60, y), line, 92, WEIGHT_HEAVY, (255, 255, 255))
        y += 118

    if sub_text:
        if len(sub_text) > 28:
            sub_text = sub_text[:27] + '…'
        draw_text_smart(draw, (60, y + 18), sub_text, 40, WEIGHT_MEDIUM, (210, 225, 245))

    draw_footer(draw, pal, date_from_filename(os.path.basename(filepath)))
    return img


# ----- dispatch -----

def detect_category(filepath, html=None):
    p = str(filepath).replace('\\', '/')
    if '/archive/' in p:
        return 'daily'
    if '/analysis/' in p:
        return 'analysis'
    if '/book/' in p:
        return 'book'
    if '/companies/' in p:
        if html is None:
            html = open(filepath, encoding='utf-8').read()
        return 'book' if 'BOOK REVIEW' in html else 'company'
    return None


def update_og_meta(filepath, og_url):
    html = open(filepath, encoding='utf-8').read()
    new_html = re.sub(
        r'(<meta property="og:image" content=")[^"]+(")',
        lambda m: m.group(1) + og_url + m.group(2),
        html, count=1)
    new_html = re.sub(
        r'(<meta name="twitter:image" content=")[^"]+(")',
        lambda m: m.group(1) + og_url + m.group(2),
        new_html, count=1)
    if new_html != html:
        open(filepath, 'w', encoding='utf-8').write(new_html)
        return True
    return False


def process_file(filepath, update_html=True):
    filepath = Path(filepath)
    html = open(filepath, encoding='utf-8').read()
    cat = detect_category(filepath, html)
    if not cat:
        print(f"  [SKIP] {filepath}: unknown category")
        return
    slug = filepath.stem
    OG_DIR.mkdir(parents=True, exist_ok=True)
    out = OG_DIR / f"{slug}.png"

    img = gen_daily(filepath, html) if cat == 'daily' else gen_titled(filepath, html, cat)
    img.save(out, 'PNG', optimize=True)

    if update_html:
        relpath = out.relative_to(REPO).as_posix()
        og_url = f"https://gjbuffet.kr/{relpath}"
        updated = update_og_meta(filepath, og_url)
        meta_state = 'updated' if updated else 'unchanged'
    else:
        meta_state = 'skipped'

    print(f"  [{cat:8}] {filepath.name} → {out.name}  meta:{meta_state}")


def find_all():
    files = []
    for d in ['archive', 'analysis', 'companies', 'book']:
        for f in sorted((REPO / d).glob('*.html')):
            if f.name == 'index.html':
                continue
            files.append(f)
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path', nargs='?')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--samples', action='store_true')
    ap.add_argument('--no-update-html', action='store_true')
    args = ap.parse_args()

    if args.samples:
        targets = [
            REPO / 'archive' / '2026-05-27.html',
            REPO / 'analysis' / '2026-05-27_kospi-8000.html',
            REPO / 'companies' / '2026-05-14_samsung-skhynix-citi.html',
            REPO / 'book' / '2026-05-22_oneil-successful-investor.html',
        ]
        for t in targets:
            process_file(t, update_html=False)
    elif args.all:
        for f in find_all():
            process_file(f, update_html=not args.no_update_html)
    elif args.path:
        p = Path(args.path)
        if not p.is_absolute():
            p = REPO / p
        process_file(p, update_html=not args.no_update_html)
    else:
        ap.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
