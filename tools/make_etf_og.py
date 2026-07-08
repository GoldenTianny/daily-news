#!/usr/bin/env python3
"""ETF 종목 검색기 전용 OG 썸네일 생성기 (1200×630).

make_og.py의 폰트·그라디언트·뱃지·푸터 헬퍼를 재사용해 사이트와
같은 비주얼 언어로 그린다. 결과: assets/og/etf.png

사용: python3 tools/make_etf_og.py
"""
import os, sys
from pathlib import Path
from PIL import ImageDraw

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'tools'))
import make_og as og  # 헬퍼 재사용 (import 시 부작용 없음)

# 검색기 헤더 색감(인디고 #1a237e→#283593)에 골드 악센트
PAL = {
    'bg_top': (26, 35, 126), 'bg_mid': (40, 53, 147), 'bg_bot': (57, 73, 171),
    'glow': (124, 178, 255),
    'accent': (255, 213, 79),
    'badge_bg': (255, 213, 79),
    'badge_fg': (26, 35, 126),
}

def main():
    img = og.make_gradient(PAL)
    draw = ImageDraw.Draw(img)

    og.draw_brand_badge(draw, PAL, 'ETF SCREENER')

    # 큰 제목
    og.draw_text_smart(draw, (60, 205), 'ETF 종목 검색기',
                       104, og.WEIGHT_HEAVY, (255, 255, 255))
    # 서브 카피 2줄
    og.draw_text_smart(draw, (62, 345), '내가 산 종목, 어떤 ETF에 담겼을까?',
                       48, og.WEIGHT_MEDIUM, (205, 218, 245))
    og.draw_text_smart(draw, (62, 415), '보유 ETF를 비중순으로 한눈에',
                       44, og.WEIGHT_MEDIUM, (160, 182, 224))

    og.draw_footer(draw, PAL, '가좌버핏')

    out = REPO / 'assets' / 'og' / 'etf.png'
    img.save(out)
    print('saved', out, img.size)

if __name__ == '__main__':
    main()
