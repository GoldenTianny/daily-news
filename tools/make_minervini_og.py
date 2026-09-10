#!/usr/bin/env python3
"""미너비니 트렌드 템플릿 전용 OG 썸네일 생성기 (1200×630).

make_og.py의 폰트·그라디언트·뱃지·푸터 헬퍼를 재사용해 ETF 검색기(etf.png)와
같은 비주얼 언어로 그린다. 결과: assets/og/minervini.png

사용: python3 tools/make_minervini_og.py
"""
import sys
from pathlib import Path
from PIL import ImageDraw

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'tools'))
import make_og as og  # 헬퍼 재사용

# 검색기와 같은 인디고 계열 + 초록(추세 상승) 악센트
PAL = {
    'bg_top': (26, 35, 126), 'bg_mid': (40, 53, 147), 'bg_bot': (57, 73, 171),
    'glow': (124, 178, 255),
    'accent': (129, 199, 132),
    'badge_bg': (129, 199, 132),
    'badge_fg': (13, 50, 20),
}

def main():
    img = og.make_gradient(PAL)
    draw = ImageDraw.Draw(img)

    og.draw_brand_badge(draw, PAL, 'TREND TEMPLATE')

    og.draw_text_smart(draw, (60, 190), '미너비니 트렌드 템플릿',
                       92, og.WEIGHT_HEAVY, (255, 255, 255))
    og.draw_text_smart(draw, (62, 322), '8개 추세 조건을 모두 충족한 종목, 매일 선별',
                       46, og.WEIGHT_MEDIUM, (205, 218, 245))
    og.draw_text_smart(draw, (62, 392), '이동평균 정렬 · 52주 고저 · RS 등급 · CANSLIM 추가 선별',
                       38, og.WEIGHT_MEDIUM, (160, 182, 224))

    # 우측 상단(글자와 겹치지 않는 영역): 상승 추세를 암시하는 계단형 바
    x0, base = 930, 150
    heights = [34, 52, 70, 92, 118]
    for i, h in enumerate(heights):
        x = x0 + i * 44
        col = (129, 199, 132) if i == len(heights) - 1 else (98, 122, 200)
        draw.rounded_rectangle([x, base - h, x + 32, base], radius=5, fill=col)

    og.draw_footer(draw, PAL, '')

    out = REPO / 'assets' / 'og' / 'minervini.png'
    img.save(out)
    print('saved', out, img.size)

if __name__ == '__main__':
    main()
