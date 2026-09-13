// ── inject-csp-hashes 단위 테스트 (로드맵5 H6, node:test 내장) ──────────
// 흐름: 인라인 추출 -> 해시 산출 -> 고유·정렬 수집 -> 플레이스홀더 치환
//       각 순수함수 스펙을 Red 로 못 박음(구현 전 실패 상태).

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';

import {
  extractInlineScripts,
  hashScriptBody,
  collectScriptHashes,
  injectHashes,
  HASH_PLACEHOLDER,
} from './inject-csp-hashes.mjs';

// 실측 산출물과 같은 형태의 fixture: 인라인 2 + 외부 1
const FIXTURE_HTML = [
  '<!doctype html><html><head>',
  '<script src="/_next/static/chunks/main.js"></script>',
  '<script>(self.__next_f=self.__next_f||[]).push([0])</script>',
  '</head><body>',
  '<script>self.__next_f.push([1,"page-a"])</script>',
  '</body></html>',
].join('\n');

// ── extractInlineScripts: src 없는 본문만 ───────────────────────────────
test('extractInlineScripts: src 없는 인라인 본문만 추출', () => {
  const bodies = extractInlineScripts(FIXTURE_HTML);
  assert.deepEqual(bodies, [
    '(self.__next_f=self.__next_f||[]).push([0])',
    'self.__next_f.push([1,"page-a"])',
  ]);
});

// ── hashScriptBody: "'sha256-<b64>'" 형식 + sha256 정합 ──────────────────
test('hashScriptBody: 따옴표 포함 sha256 토큰 형식', () => {
  const body = 'self.__next_f.push([1,"page-a"])';
  const expected = `'sha256-${createHash('sha256').update(body, 'utf8').digest('base64')}'`;
  const token = hashScriptBody(body);
  assert.equal(token, expected);
  assert.match(token, /^'sha256-[A-Za-z0-9+/]+=*'$/);
});

// ── collectScriptHashes: 중복 제거 + 정렬(결정적) ──────────────────────
test('collectScriptHashes: 여러 HTML 고유·정렬 해시', () => {
  const htmlB = FIXTURE_HTML.replace('page-a', 'page-b'); // 다른 페이지
  const tokens = collectScriptHashes([FIXTURE_HTML, htmlB]);
  // 공통 인라인 1개 + 페이지별 2개 = 고유 3개
  assert.equal(tokens.length, 3);
  assert.deepEqual(tokens, [...tokens].sort()); // 정렬 보장
  assert.equal(new Set(tokens).size, tokens.length); // 중복 없음
});

// ── injectHashes: 플레이스홀더 치환 ────────────────────────────────────
test('injectHashes: 플레이스홀더를 공백조인 해시로 치환', () => {
  const text = `  Content-Security-Policy: script-src 'self' ${HASH_PLACEHOLDER} https://x;`;
  const out = injectHashes(text, ["'sha256-AAA'", "'sha256-BBB'"]);
  assert.equal(
    out,
    "  Content-Security-Policy: script-src 'self' 'sha256-AAA' 'sha256-BBB' https://x;",
  );
  assert.ok(!out.includes(HASH_PLACEHOLDER));
});

// ── injectHashes: 토큰 부재 시 실패(빌드 안전장치) ─────────────────────
test('injectHashes: 플레이스홀더 없으면 throw', () => {
  assert.throws(() => injectHashes('script-src self', ["'sha256-AAA'"]), /placeholder/i);
});
