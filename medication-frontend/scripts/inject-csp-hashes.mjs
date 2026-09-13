// ── CSP script-src 인라인 해시 주입 (로드맵5 H6) ──────────────────────
// 흐름: out/**/*.html 인라인 <script> 추출 -> SHA-256/base64 해시 산출
//       -> out/_headers 의 플레이스홀더 토큰을 해시 목록으로 치환
// 전제: 정적 export 인라인 스크립트는 빌드마다 내용(청크 해시)이 변함
//       -> 하드코딩 불가, 배포하는 그 빌드에서 산출해야 정합.

import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, readdirSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

// _headers 커밋본 script-src 에 심어 둘 치환 대상 토큰
export const HASH_PLACEHOLDER = '__INLINE_SCRIPT_HASHES__';

// src 속성이 없는 <script>...</script> 매칭(외부 스크립트 제외)
const INLINE_SCRIPT_RE = /<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/gi;

// ── 인라인 스크립트 추출 ────────────────────────────────────────────────
// 흐름: src 속성 없는 <script>...</script> 본문만 수집(외부 스크립트 제외)
export function extractInlineScripts(html) {
  const bodies = [];
  for (const match of html.matchAll(INLINE_SCRIPT_RE)) {
    bodies.push(match[1]);
  }
  return bodies;
}

// ── 스크립트 본문 -> CSP 해시 토큰 ──────────────────────────────────────
// 흐름: 본문 UTF-8 SHA-256 -> base64 -> "'sha256-<b64>'"(따옴표 포함)
export function hashScriptBody(body) {
  const digest = createHash('sha256').update(body, 'utf8').digest('base64');
  return `'sha256-${digest}'`;
}

// ── 여러 HTML -> 정렬된 고유 해시 토큰 배열 ─────────────────────────────
// 흐름: 각 HTML 인라인 추출 -> 해시 -> Set 중복 제거 -> 정렬(결정적)
export function collectScriptHashes(htmlContents) {
  const tokens = new Set();
  for (const html of htmlContents) {
    for (const body of extractInlineScripts(html)) {
      tokens.add(hashScriptBody(body));
    }
  }
  return [...tokens].sort();
}

// ── _headers 플레이스홀더 치환 ──────────────────────────────────────────
// 흐름: 토큰 존재 확인(없으면 throw) -> 해시 목록을 공백조인으로 치환
export function injectHashes(headersText, hashTokens) {
  if (!headersText.includes(HASH_PLACEHOLDER)) {
    throw new Error(
      `[inject-csp-hashes] placeholder '${HASH_PLACEHOLDER}' 없음 — public/_headers 템플릿 확인 필요`,
    );
  }
  return headersText.replaceAll(HASH_PLACEHOLDER, hashTokens.join(' '));
}

// ── 디렉터리 재귀 HTML 수집 ─────────────────────────────────────────────
// 흐름: out/ 하위 *.html 경로 전체 나열(경로별 인라인 합집합 대상)
function listHtmlFiles(dir) {
  const found = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      found.push(...listHtmlFiles(full));
    } else if (entry.endsWith('.html')) {
      found.push(full);
    }
  }
  return found;
}

// ── CLI 러너 (next build 이후 post-build 스텝) ─────────────────────────
// 흐름: out/**/*.html 해시 수집 -> out/_headers 치환 -> 덮어쓰기
//       배포하는 빌드에서 실행되어야 CF Pages 산출물과 해시 정합.
function main() {
  const outDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'out');
  const headersPath = join(outDir, '_headers');

  const htmlFiles = listHtmlFiles(outDir);
  const htmlContents = htmlFiles.map((f) => readFileSync(f, 'utf8'));
  const hashes = collectScriptHashes(htmlContents);

  if (hashes.length === 0) {
    console.error('[inject-csp-hashes] FAIL: 인라인 스크립트 해시 0개 (빌드 산출물 이상)');
    process.exit(1);
  }

  const headersText = readFileSync(headersPath, 'utf8');
  const injected = injectHashes(headersText, hashes);
  writeFileSync(headersPath, injected, 'utf8');

  console.log(
    `[inject-csp-hashes] PASS: HTML ${htmlFiles.length}개 -> 고유 해시 ${hashes.length}개 주입 (out/_headers)`,
  );
}

// 직접 실행 시에만 러너 동작(테스트 import 시엔 순수함수만 노출)
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  main();
}
