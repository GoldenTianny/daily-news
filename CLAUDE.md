# 작업 메모

## 관리자 > 매매 복기 (마스터 본인 전용)
사용자가 매매 체결내역 파일을 주며 "올려줘/반영해줘" 하면:
1. 어떤 양식이든 읽어서 `{"rows":[{"date":"YYYY-MM-DD","time":"HH:MM","side":"B|S","name":"종목명","qty":수량,"price":단가,"amt":금액,"note":""}]}` JSON 으로 바꾼다.
   이 JSON·원본은 **스크래치패드 등 저장소 밖**에 둔다. 체결내역 평문은 절대 커밋하지 않는다 (공개 저장소).
2. 항상 **전체 내역**(기존 + 새 내역, 중복 제거)으로 만든다. 기존 내역은 사용자에게 받은 파일로만 알 수 있고 암호문은 여기서 풀 수 없으므로, 이어 붙일 때는 이전 파일도 같이 달라고 하거나 사용자가 준 파일이 전체인지 확인한다.
3. `node admin/journal-encrypt.mjs <json 또는 정리 txt> "<출처 메모>"` → `admin/data/journal.enc.json` 갱신 후 커밋.
4. 공개키 `admin/data/journal.pub.json` 은 바꾸지 않는다 (바꾸면 Supabase 의 개인키와 안 맞아 못 푼다).
   개인키는 Supabase `journal_secret` 에만 있다 (`supabase/003_journal_secret.sql`).
