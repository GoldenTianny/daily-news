# ETF 원본 엑셀 업로드 폴더

여기에 HTS/MTS에서 받은 ETF 엑셀 파일을 올리면 **자동으로 검색기 데이터가 갱신**됩니다.

## 사용법 (매일 2단계)

1. HTS/MTS에서 ETF 엑셀 다운로드
2. GitHub 웹에서 이 폴더(`tools/etf/raw/`)를 열고 → **Add file → Upload files** → 드래그&드롭 → Commit

이후는 GitHub Actions가 자동 처리:
- `build_data.py`로 JSON 변환 (`tools/etf/data/YYYY-MM-DD.json`)
- `dates.json` 갱신
- 자동 커밋 후 원본 엑셀은 삭제 (저장소 용량 관리)

## 파일명 규칙

- 파일명에 8자리 날짜가 있으면 그 날짜를 기준일로 사용
  - 예: `ETF_Raw_20260709.xlsx` → `2026-07-09`
- 날짜가 없으면 업로드한 날(한국시간)을 기준일로 사용

## 확인

업로드 후 1~2분 뒤 [Actions 탭](../../../actions)에서 "ETF 데이터 자동 변환" 실행 결과를 확인할 수 있습니다.
성공하면 검색기 화면의 기준일 목록에 새 날짜가 나타납니다.
