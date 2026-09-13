// ── 빌드 산출물 보안헤더 검증 (로드맵5 H3) ──────────────────────────────
// 흐름: out/_headers 읽기 -> 라우트 매칭(/*) 확인 -> 필수 헤더·CSP 지시어 검사
//       -> 누락 시 목록 출력 후 exit 1 (CI/로컬 게이트)
// 전제: `next build`(output:'export')가 public/_headers 를 out/_headers 로 복사.

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const HEADERS_PATH = join(__dirname, '..', 'out', '_headers');

// 산출물에 반드시 존재해야 하는 헤더 이름(대소문자 무시)
// H4 enforce 승격(2026-09-13): Report-Only -> 강제(Content-Security-Policy).
const REQUIRED_HEADERS = [
  'Content-Security-Policy',
  'Reporting-Endpoints',
  'X-Content-Type-Options',
  'X-Frame-Options',
  'Referrer-Policy',
  'Permissions-Policy',
];

// CSP 값에 반드시 포함돼야 하는 토큰(정책 골격 + 리포팅 경로)
// H6 enforce(2026-09-13): script-src 는 'unsafe-inline' 대신 인라인 해시(sha256) 사용.
const REQUIRED_CSP_TOKENS = [
  "default-src 'self'",
  // 인라인 해시 승격: inject-csp-hashes 가 주입한 sha256 이 존재해야 함
  "script-src 'self' 'sha256-",
  // Cloudflare Web Analytics 비콘(H4 실측 위반) 허용
  'https://static.cloudflareinsights.com',
  // OCR 업로드 미리보기 blob: URL(ocr/page.jsx createObjectURL) 허용
  "img-src 'self' data: blob:",
  "connect-src 'self' https://api.doseph.com",
  "frame-ancestors 'none'",
  "base-uri 'none'",
  'report-uri https://api.doseph.com/api/v1/security/csp-report',
  'report-to csp-endpoint',
];

// ── 산출물 로드 ────────────────────────────────────────────────────────
// 흐름: 파일 부재 시 즉시 실패(빌드 누락/복사 실패 신호)
function loadHeaders() {
  try {
    return readFileSync(HEADERS_PATH, 'utf8');
  } catch {
    console.error(`[verify-headers] FAIL: ${HEADERS_PATH} 없음 (next build 미실행 또는 public/_headers 미복사)`);
    process.exit(1);
  }
}

// ── 검증 본문 ──────────────────────────────────────────────────────────
// 흐름: 라우트 블록(/*) 확인 -> 필수 헤더 존재 -> CSP 토큰 존재 -> 결과 집계
function verify(content) {
  const failures = [];
  const lower = content.toLowerCase();

  if (!content.includes('/*')) {
    failures.push('라우트 매칭 블록 `/*` 없음');
  }

  for (const header of REQUIRED_HEADERS) {
    if (!lower.includes(`${header.toLowerCase()}:`)) {
      failures.push(`헤더 누락: ${header}`);
    }
  }

  for (const token of REQUIRED_CSP_TOKENS) {
    if (!content.includes(token)) {
      failures.push(`CSP 지시어/토큰 누락: ${token}`);
    }
  }

  // H6: 해시 미주입(플레이스홀더 잔존) 채 배포되는 사고 방지
  if (content.includes('__INLINE_SCRIPT_HASHES__')) {
    failures.push('해시 미주입: __INLINE_SCRIPT_HASHES__ 잔존 (inject-csp-hashes 미실행)');
  }

  // H6: enforce CSP 헤더 라인의 script-src 만 검사(주석/다른 지시어 오탐 방지)
  const cspLine = content
    .split('\n')
    .find((l) => l.trim().toLowerCase().startsWith('content-security-policy:'));
  const scriptSrc = cspLine && cspLine.match(/script-src[^;]*/);
  if (scriptSrc && scriptSrc[0].includes("'unsafe-inline'")) {
    failures.push("script-src 에 'unsafe-inline' 잔존 (해시 승격 무력화)");
  }

  return failures;
}

const failures = verify(loadHeaders());

if (failures.length > 0) {
  console.error('[verify-headers] FAIL:');
  for (const f of failures) console.error(`  - ${f}`);
  process.exit(1);
}

console.log('[verify-headers] PASS: out/_headers 필수 보안헤더·CSP 지시어 모두 존재');
