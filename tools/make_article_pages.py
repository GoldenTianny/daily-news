# -*- coding: utf-8 -*-
"""좋은글 개별 정적 페이지 + sitemap.xml 생성기.

article/articles.json의 1,258편 각각을 article/p/<id>.html 정적 페이지로 생성한다.
목적: 검색엔진 색인(SEO). 기존 뷰어(/article/#id)와 공유 stub(/article/s/)은 그대로 둔다.

- OG 썸네일: assets/og/article/01~12.jpg 중 글 id 해시로 1장 고정 배정
- 이전/다음 글 링크(시간순)로 크롤러 내부 링크 확보
- sitemap.xml(루트)에 전체 페이지 + 주요 섹션 URL 등록

새 좋은글 추가 후 실행: python3 tools/make_article_pages.py
"""
import hashlib
import html
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "article", "p")
BASE = "https://gjbuffet.kr"
PHOTO_COUNT = 12

# ── 뷰어(article/index.html)와 동일한 위/아래 picsum 이미지 선택 로직 (JS 1:1 재현) ──
NATURE_IMAGES = [
    10, 11, 13, 14, 15, 16, 17, 18, 19,
    25, 27, 28, 29, 30, 31, 36, 37, 38,
    42, 47, 49, 50, 53, 54, 56, 57, 58, 60,
    65, 67, 76, 100, 101, 110, 122, 130, 134, 142, 165,
]
M32 = 0xFFFFFFFF


def _hash_code(s):
    h = 0
    for ch in s:
        h = (h * 31 + ord(ch)) & M32
    return h


def _imul(a, b):
    return (a * b) & M32


def _seeded_random(seed):
    state = {"a": seed & M32}

    def rand():
        state["a"] = (state["a"] + 0x6D2B79F5) & M32
        t = state["a"]
        t = _imul(t ^ (t >> 15), t | 1)
        t = (t ^ (t + _imul(t ^ (t >> 7), t | 61))) & M32
        return ((t ^ (t >> 14)) & M32) / 4294967296

    return rand


def pick_images(article_id):
    rand = _seeded_random(_hash_code(article_id))
    arr = NATURE_IMAGES[:]
    for i in range(len(arr) - 1, 0, -1):
        j = int(rand() * (i + 1))
        arr[i], arr[j] = arr[j], arr[i]
    return [f"https://picsum.photos/id/{pid}/800/500" for pid in arr[:2]]

PAGE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
<meta name="theme-color" content="#1a3a6c">
<title>{title_esc} · 좋은글 · 가좌버핏 뉴스</title>
<meta name="description" content="{desc_esc}">
<link rel="canonical" href="{base}/article/p/{id}.html">
<link rel="icon" type="image/png" href="../../assets/title.png">
<link rel="apple-touch-icon" href="../../assets/title.png">

<!-- 링크 공유 미리보기 -->
<meta property="og:type" content="article">
<meta property="og:title" content="{title_esc}">
<meta property="og:description" content="{desc_esc}">
<meta property="og:image" content="{base}/assets/og/article/{photo}.jpg">
<meta property="og:url" content="{base}/article/p/{id}.html">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title_esc}">
<meta name="twitter:description" content="{desc_esc}">
<meta name="twitter:image" content="{base}/assets/og/article/{photo}.jpg">

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-4BP2MLV035"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', 'G-4BP2MLV035');
</script>

<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Noto Sans KR", "Malgun Gothic", sans-serif;
    background: #f7f3ec; color: #2a2a2a; line-height: 1.9;
    -webkit-text-size-adjust: 100%;
}}
.top-bar {{
    position: sticky; top: 0; z-index: 10;
    background: #1a3a6c; color: white; padding: 13px 16px;
    display: flex; justify-content: space-between; align-items: center;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}}
.top-bar a {{ color: inherit; text-decoration: none; font-weight: 700; font-size: 15px; }}
.top-bar .sub {{ font-size: 12px; opacity: 0.85; }}
.wrap {{ max-width: 560px; margin: 0 auto; padding: 24px 16px 60px; }}
.card {{
    background: #fffdf8; border-radius: 14px; padding: 34px 26px 30px;
    box-shadow: 0 3px 14px rgba(107,79,58,0.10); border: 1px solid #efe7d8;
}}
.date {{ font-size: 12.5px; color: #b89878; letter-spacing: 1px; margin-bottom: 10px; }}
h1 {{ font-size: 21px; font-weight: 800; color: #5a4632; line-height: 1.45; margin-bottom: 18px; word-break: keep-all; }}
.poem {{ white-space: pre-line; font-size: 16px; color: #3a3530; word-break: keep-all; }}
.aimg {{ width: 100%; aspect-ratio: 8/5; object-fit: cover; border-radius: 10px;
    background: #ece4d4; box-shadow: 0 2px 8px rgba(107,79,58,0.12); display: block; }}
.aimg.top {{ margin-bottom: 20px; }}
.aimg.bottom {{ margin-top: 20px; }}
.nav {{ display: flex; gap: 8px; margin-top: 22px; }}
.nav a {{
    flex: 1; text-align: center; padding: 12px 8px; border-radius: 10px;
    background: #fffdf8; border: 1px solid #e8dcc8; color: #6b4f3a;
    text-decoration: none; font-size: 13.5px; font-weight: 600;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}}
.nav a:active {{ background: #f3ead9; }}
.more {{ display: block; text-align: center; margin-top: 12px; padding: 14px; border-radius: 10px;
    background: #6b4f3a; color: #fff; text-decoration: none; font-size: 14.5px; font-weight: 700; }}
.share {{ display: block; width: 100%; margin-top: 10px; padding: 13px; border-radius: 10px;
    background: #fffdf8; border: 1px solid #e8dcc8; color: #6b4f3a;
    font-size: 14px; font-weight: 700; font-family: inherit; cursor: pointer; }}
.footer {{ text-align: center; margin-top: 28px; font-size: 12px; color: #a99a85; }}
.footer a {{ color: #8b6f4e; }}
@media (prefers-color-scheme: dark) {{
    body {{ background: #1c1f26; color: #c8ccd4; }}
    .card {{ background: #242831; border-color: #323845; box-shadow: 0 3px 14px rgba(0,0,0,0.35); }}
    h1 {{ color: #e8d9bd; }}
    .poem {{ color: #c8ccd4; }}
    .date {{ color: #9a8a72; }}
    .nav a, .share {{ background: #242831; border-color: #3a4150; color: #d4c4a8; }}
    .more {{ background: #8b6f4e; }}
    .footer {{ color: #6a7180; }}
    .aimg {{ background: #2a2f3a; box-shadow: 0 2px 8px rgba(0,0,0,0.4); }}
}}
</style>
</head>
<body>
<div class="top-bar">
    <a href="../../index.html">📰 가좌버핏 뉴스</a>
    <span class="sub">✨ 좋은글</span>
</div>
<div class="wrap">
    <div class="card">
        <div class="date">{date_kr}</div>
        <h1>{title_esc}</h1>
        <img class="aimg top" src="{img_top}" alt="" onerror="this.style.display='none'">
        <div class="poem">{body_esc}</div>
        <img class="aimg bottom" src="{img_bottom}" alt="" loading="lazy" onerror="this.style.display='none'">
    </div>
    <div class="nav">{prev_link}{next_link}</div>
    <a class="more" href="../#{id}">✨ 좋은글 {total:,}편 모두 보기 →</a>
    <button class="share" id="shareBtn" type="button">📤 이 글 공유하기</button>
    <div class="footer">가좌버핏 뉴스 · <a href="../../index.html">gjbuffet.kr</a> · <a href="../../privacy/">개인정보 안내</a></div>
</div>
<script>
document.getElementById('shareBtn').addEventListener('click', async () => {{
    const url = location.href.split('#')[0];
    const text = `✨ {title_js}\\n\\n{body_js}\\n\\n${{url}}`;
    if (navigator.share) {{
        try {{ await navigator.share({{ title: {title_json}, text }}); }} catch (e) {{}}
    }} else {{
        try {{ await navigator.clipboard.writeText(text); alert('링크가 복사되었습니다.'); }}
        catch (e) {{ prompt('복사해 주세요:', text); }}
    }}
}});
</script>
</body>
</html>
"""

KR_WEEK = "월화수목금토일"


def photo_for(aid):
    n = int(hashlib.md5(aid.encode()).hexdigest(), 16) % PHOTO_COUNT + 1
    return f"{n:02d}"


def date_kr(iso):
    y, m, d = iso.split("-")
    return f"{int(y)}년 {int(m)}월 {int(d)}일"


def desc_of(body):
    flat = re.sub(r"\s+", " ", body).strip()
    return (flat[:88] + "…") if len(flat) > 90 else flat


def body_js_excerpt(body, n=280):
    """공유 문구용 본문 발췌 — JS 템플릿 리터럴에 안전하게 삽입 (줄바꿈 보존)."""
    s = body.strip()
    out = s[:n] + ("..." if len(s) > n else "")
    out = out.replace("\\", "").replace("`", "").replace("$", "")
    out = out.replace("\r", "").replace("\n", "\\n")
    return out


def main():
    with open(os.path.join(ROOT, "article", "articles.json"), encoding="utf-8") as fh:
        arts = json.load(fh)
    arts.sort(key=lambda a: a["id"])  # YYYYMMDD_NN → 시간순
    os.makedirs(OUT_DIR, exist_ok=True)
    total = len(arts)

    for i, a in enumerate(arts):
        prev_a = arts[i - 1] if i > 0 else None
        next_a = arts[i + 1] if i < total - 1 else None
        prev_link = (f'<a href="{prev_a["id"]}.html">← {html.escape(prev_a["title"][:14])}</a>'
                     if prev_a else '')
        next_link = (f'<a href="{next_a["id"]}.html">{html.escape(next_a["title"][:14])} →</a>'
                     if next_a else '')
        img_top, img_bottom = pick_images(a["id"])
        page = PAGE.format(
            id=a["id"],
            base=BASE,
            img_top=img_top,
            img_bottom=img_bottom,
            title_esc=html.escape(a["title"]),
            title_js=a["title"].replace("\\", "").replace("`", "").replace("$", ""),
            body_js=body_js_excerpt(a["body"]),
            title_json=json.dumps(a["title"], ensure_ascii=False),
            desc_esc=html.escape(desc_of(a["body"])),
            body_esc=html.escape(a["body"]),
            date_kr=date_kr(a["date"]),
            photo=photo_for(a["id"]),
            prev_link=prev_link,
            next_link=next_link,
            total=total,
        )
        with open(os.path.join(OUT_DIR, a["id"] + ".html"), "w", encoding="utf-8") as fh:
            fh.write(page)

    # ── sitemap.xml ──
    core = [
        ("", "1.0"), ("archive/", "0.8"), ("article/", "0.9"),
        ("analysis/", "0.7"), ("companies/", "0.7"), ("book/", "0.7"),
    ]
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, pr in core:
        lines.append(f"  <url><loc>{BASE}/{path}</loc><priority>{pr}</priority></url>")
    for a in arts:
        lines.append(f"  <url><loc>{BASE}/article/p/{a['id']}.html</loc>"
                     f"<lastmod>{a['date']}</lastmod><priority>0.6</priority></url>")
    lines.append("</urlset>")
    with open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    # ── robots.txt ──
    robots = os.path.join(ROOT, "robots.txt")
    if not os.path.exists(robots):
        with open(robots, "w", encoding="utf-8") as fh:
            fh.write("User-agent: *\nAllow: /\n\nSitemap: " + BASE + "/sitemap.xml\n")

    print(f"pages: {total}  →  article/p/")
    print(f"sitemap.xml: {total + len(core)} URLs")


if __name__ == "__main__":
    main()
