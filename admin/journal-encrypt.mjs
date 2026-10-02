#!/usr/bin/env node
/* 매매 복기 체결내역 암호화 → admin/data/journal.enc.json
 *
 *   node admin/journal-encrypt.mjs <입력파일> [출처 메모]
 *
 * 입력파일 (저장소 밖에 둘 것, 절대 커밋하지 않음):
 *   - .json : { "rows": [ { "date":"2026-01-05", "time":"12:53", "side":"B"|"S", "name":"한미반도체",
 *                          "qty":18, "price":158800, "amt":2858400, "note":"" }, ... ] }
 *   - .txt  : "■ 매수 내역" / "■ 매도 내역" 아래 "날짜 시각 종목 수량 단가 금액 [비고]" 정리본
 * 증권사·카톡 원본처럼 양식이 다르면 먼저 위 JSON 형태로 바꿔서 넣는다.
 *
 * 공개키(admin/data/journal.pub.json)로만 잠그므로 누구나 만들 수 있지만,
 * 푸는 개인키는 Supabase journal_secret 테이블(마스터 본인만 읽기)에만 있다.
 * 같은 파일을 덮어쓰므로 항상 "전체 내역"을 넣는다 (기존 내역 + 새 내역 합쳐서). */
import { readFileSync, writeFileSync } from 'node:fs';
import { webcrypto as crypto } from 'node:crypto';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const Journal = require('./journal.js');

const [input, source = ''] = process.argv.slice(2);
if (!input) { console.error('사용법: node admin/journal-encrypt.mjs <입력파일.json|.txt> [출처 메모]'); process.exit(1); }

const text = readFileSync(input, 'utf8');
let rows = input.endsWith('.json') ? JSON.parse(text).rows : Journal.parse(text);
rows = (rows || []).map((r, i) => {
  const o = { date: r.date, time: r.time || '00:00', side: r.side, name: String(r.name || '').trim(), qty: +r.qty, price: +r.price, amt: +(r.amt || Math.round(r.qty * r.price)), note: r.note || '' };
  const bad = !/^\d{4}-\d\d-\d\d$/.test(o.date) || !/^\d\d:\d\d$/.test(o.time) || !['B', 'S'].includes(o.side) || !o.name || !(o.qty > 0) || !(o.price > 0);
  if (bad) throw new Error(`${i + 1}번째 줄 형식 오류: ${JSON.stringify(r)}`);
  return o;
});
if (!rows.length) throw new Error('체결 줄이 없습니다');

const payload = new TextEncoder().encode(JSON.stringify({ source, rows }));
const pub = await crypto.subtle.importKey('jwk', JSON.parse(readFileSync(path.join(here, 'data/journal.pub.json'), 'utf8')),
  { name: 'RSA-OAEP', hash: 'SHA-256' }, false, ['wrapKey']);
const aes = await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, true, ['encrypt']);
const iv = crypto.getRandomValues(new Uint8Array(12));
const ct = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, aes, payload);
const wk = await crypto.subtle.wrapKey('raw', aes, pub, { name: 'RSA-OAEP' });
const b64 = (b) => Buffer.from(b).toString('base64');

const out = { v: 1, updated: new Date().toISOString(), wk: b64(wk), iv: b64(iv), ct: b64(ct) };
writeFileSync(path.join(here, 'data/journal.enc.json'), JSON.stringify(out) + '\n');

const A = Journal.analyze(rows);
console.log(`암호화 완료: 체결 ${rows.length}건 (${A.period[0]} ~ ${A.period[1]}) · 끝난 거래 ${A.cycles.length}회 · 실현손익 ${Math.round(A.realized).toLocaleString()}원`);
