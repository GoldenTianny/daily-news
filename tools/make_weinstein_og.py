#!/usr/bin/env python3
"""와인스타인 RS 제로선 돌파 페이지 전용 OG 썸네일 생성기 (1200×630).

make_og.py의 폰트·그라디언트·뱃지·푸터 헬퍼를 재사용해 미너비니(minervini.png)와
같은 비주얼 언어로 그린다. 결과: assets/og/weinstein.png

사용: python3 tools/make_weinstein_og.py
"""
import sys
from pathlib import Path
from PIL import ImageDraw

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'tools'))
import make_og as og  # 헬퍼 재사용

# 검색기와 같은 인디고 계열 + 보라(RS선 색) 악센트
PAL = {
    'bg_top': (26, 35, 126), 'bg_mid': (40, 53, 147), 'bg_bot': (57, 73, 171),
    'glow': (124, 178, 255),
    'accent': (206, 147, 216),
    'badge_bg': (206, 147, 216),
    'badge_fg': (60, 10, 80),
}

def main():
    img = og.make_gradient(PAL)
    draw = ImageDraw.Draw(img)

    og.draw_brand_badge(draw, PAL, 'WEINSTEIN RS')

    og.draw_text_smart(draw, (60, 190), '와인스타인 RS 제로선 돌파',
                       92, og.WEIGHT_HEAVY, (255, 255, 255))
    og.draw_text_smart(draw, (62, 322), '시장에 뒤지던 종목이 이기기 시작한 순간, 매일 선별',
                       46, og.WEIGHT_MEDIUM, (205, 218, 245))
    og.draw_text_smart(draw, (62, 392), '주가÷코스피 · 1년 평균선 상향 돌파 · 1일째부터 순서대로',
                       38, og.WEIGHT_MEDIUM, (160, 182, 224))

    # 우측 상단: 제로선(점선)을 아래에서 위로 넘는 RS선
    x0, x1, zero = 900, 1140, 118
    for x in range(x0, x1, 14):
        draw.line([x, zero, x + 7, zero], fill=(160, 182, 224), width=3)
    pts = [(900, 175), (940, 160), (975, 168), (1010, 150), (1045, 132),
           (1075, 112), (1105, 84), (1140, 56)]
    draw.line(pts, fill=(206, 147, 216), width=8, joint='curve')
    cx, cy = 1088, 100
    draw.ellipse([cx - 9, cy - 9, cx + 9, cy + 9], fill=(255, 255, 255))
    draw.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=(206, 147, 216))

    og.draw_footer(draw, PAL, '')

    out = REPO / 'assets' / 'og' / 'weinstein.png'
    img.save(out)
    print('saved', out, img.size)

if __name__ == '__main__':
    main()
