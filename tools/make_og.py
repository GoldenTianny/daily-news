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
FONT = '/System/Library/Fonts/AppleSDGothicNeo.ttc'
W, H = 1200, 630

# AppleSDGothicNeo.ttc 인덱스 (TTC weights): 0=Thin..8=Heavy
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
    return ImageFont.truetype(FONT, size, index=weight)


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
    draw.text((60, 52), "가좌버핏 뉴스", font=fnt(36, WEIGHT_HEAVY), fill=(255, 255, 255))
    # truncate badge to fit
    if len(badge_text) > 30:
        badge_text = badge_text[:29] + '…'
    bw = draw.textlength(badge_text, font=fnt(28, WEIGHT_BOLD))
    px_pad, py_pad = 22, 10
    bx0, by0 = 60, 116
    draw.rounded_rectangle(
        [(bx0, by0), (bx0+bw+px_pad*2, by0+28+py_pad*2)],
        radius=22, fill=pal['badge_bg'])
    draw.text((bx0+px_pad, by0+py_pad-2), badge_text,
              font=fnt(28, WEIGHT_BOLD), fill=pal['badge_fg'])


def draw_footer(draw, pal, left_text, right_text="gjbuffet.kr"):
    fy = H - 78
    if left_text:
        draw.text((60, fy), left_text, font=fnt(30, WEIGHT_BOLD), fill=pal['accent'])
    if right_text:
        rw = draw.textlength(right_text, font=fnt(30, WEIGHT_BOLD))
        draw.text((W-60-rw, fy), right_text, font=fnt(30, WEIGHT_BOLD), fill=(255, 255, 255))
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
    draw.text((60, 205), date_str, font=fnt(100, WEIGHT_HEAVY), fill=(255, 255, 255))
    draw.text((60, 322), f"{dow} · 오늘의 핵심뉴스", font=fnt(34, WEIGHT_BOLD), fill=pal['accent'])

    # top 3 h3 headlines
    h3s = re.findall(r'<article[^>]*>.*?<h3[^>]*>(.*?)</h3>', html, re.S)
    headlines = []
    for h in h3s[:3]:
        clean = html_lib.unescape(re.sub(r'<[^>]+>', '', h)).strip()
        if len(clean) > 28:
            clean = clean[:27] + '…'
        headlines.append(clean)

    y = 395
    for head in headlines:
        draw.text((60, y), f"·  {head}", font=fnt(32, WEIGHT_MEDIUM), fill=(220, 230, 245))
        y += 50

    draw_footer(draw, pal, "")
    return img


def gen_titled(filepath, html, category):
    pal = PALETTES[category]
    # extract cover label / h1 / subtitle
    cov_lbl = re.search(r'<div class="cover">.*?<div class="label">([^<]+)</div>', html, re.S)
    cov_h1 = re.search(r'<div class="cover">.*?<h1>(.*?)</h1>', html, re.S)
    cov_sub = re.search(r'<div class="cover">.*?<div class="subtitle">([^<]+)</div>', html, re.S)

    label = html_lib.unescape(cov_lbl.group(1).strip()) if cov_lbl else category.upper()
    # h1: split by <br> to preserve line structure
    h1_raw = cov_h1.group(1) if cov_h1 else ''
    h1_parts = [re.sub(r'<[^>]+>', '', p).strip() for p in re.split(r'<br\s*/?>', h1_raw)]
    h1_parts = [html_lib.unescape(p) for p in h1_parts if p.strip()]
    sub_text = html_lib.unescape(cov_sub.group(1).strip()) if cov_sub else ''

    img = make_gradient(pal)
    draw = ImageDraw.Draw(img)
    draw_brand_badge(draw, pal, label)

    # title — up to 2 lines; if h1_parts has 2+, use first 2; else wrap single
    if len(h1_parts) >= 2:
        title_lines = h1_parts[:2]
    elif len(h1_parts) == 1:
        title_lines = wrap_korean(h1_parts[0], 16)[:2]
    else:
        title_lines = ['']

    # cap each line at ~18 chars (fits at 72pt)
    title_lines = [(l[:18] + '…') if len(l) > 19 else l for l in title_lines]

    y = 225
    for line in title_lines:
        draw.text((60, y), line, font=fnt(72, WEIGHT_HEAVY), fill=(255, 255, 255))
        y += 92

    if sub_text:
        if len(sub_text) > 36:
            sub_text = sub_text[:35] + '…'
        draw.text((60, y + 14), sub_text, font=fnt(30, WEIGHT_MEDIUM), fill=(210, 225, 245))

    draw_footer(draw, pal, date_from_filename(os.path.basename(filepath)))
    return img


# ----- dispatch -----

def detect_category(filepath, html=None):
    p = str(filepath).replace('\\', '/')
    if '/archive/' in p:
        return 'daily'
    if '/analysis/' in p:
        return 'analysis'
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
    for d in ['archive', 'analysis', 'companies']:
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
            REPO / 'companies' / '2026-05-22_oneil-successful-investor.html',
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
