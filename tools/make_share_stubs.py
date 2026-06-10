# -*- coding: utf-8 -*-
"""좋은글 공유 stub 페이지 생성기.

assets/og/article/NN.jpg 사진 1장당 article/s/NN.html stub을 만든다.
각 stub은 og:image만 다르고, 사람이 열면 ?a=<글ID>를 읽어 ../#<글ID>로 즉시 이동한다.
공유 버튼(article/index.html)이 현재 '분'에 따라 stub을 골라 공유하므로
카톡 썸네일이 분마다 다른 사진으로 보인다 (URL별 캐시 분리).

사진을 추가/교체한 뒤 실행: python3 tools/make_share_stubs.py
"""
import glob
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHOTO_DIR = os.path.join(ROOT, "assets", "og", "article")
STUB_DIR = os.path.join(ROOT, "article", "s")

TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex">
<title>좋은글 · 가좌버핏 뉴스</title>
<link rel="canonical" href="https://gjbuffet.kr/article/">

<!-- 링크 공유 미리보기 -->
<meta property="og:type" content="website">
<meta property="og:title" content="가좌버핏 뉴스 · 좋은글">
<meta property="og:description" content="마음을 따뜻하게 데우는 글 1,200여 편">
<meta property="og:image" content="https://gjbuffet.kr/assets/og/article/{nn}.jpg">
<meta property="og:url" content="https://gjbuffet.kr/article/s/{nn}.html">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="가좌버핏 뉴스 · 좋은글">
<meta name="twitter:description" content="마음을 따뜻하게 데우는 글 1,200여 편">
<meta name="twitter:image" content="https://gjbuffet.kr/assets/og/article/{nn}.jpg">

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-4BP2MLV035"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', 'G-4BP2MLV035');
</script>

<script>
  // ?a=<글ID> → 본문으로 즉시 이동
  var a = new URLSearchParams(location.search).get('a');
  location.replace('../' + (a ? '#' + a : ''));
</script>
<noscript><meta http-equiv="refresh" content="0;url=../"></noscript>
</head>
<body></body>
</html>
"""


def main():
    photos = sorted(glob.glob(os.path.join(PHOTO_DIR, "[0-9][0-9].jpg")))
    if not photos:
        raise SystemExit("사진이 없습니다: " + PHOTO_DIR)
    os.makedirs(STUB_DIR, exist_ok=True)
    for p in photos:
        nn = os.path.splitext(os.path.basename(p))[0]
        out = os.path.join(STUB_DIR, nn + ".html")
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(TEMPLATE.format(nn=nn))
        print("stub:", os.path.relpath(out, ROOT))
    print(f"총 {len(photos)}개 — 공유 버튼의 STUB_COUNT를 {len(photos)}(으)로 맞춰주세요.")


if __name__ == "__main__":
    main()
