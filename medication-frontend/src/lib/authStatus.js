/**
 * 인증 상태 힌트 — localStorage 기반, 보안 목적 아닌 UX 차별화용.
 *
 * 목적:
 *  - 최초 접속자(NONE) 에게 /profiles 인증 체크 호출을 생략해 401 노이즈 제거.
 *  - RTR 완전 실패(자동 로그아웃) 시에만 사용자에게 이유를 안내.
 *    명시적 로그아웃은 사용자가 직접 수행한 행위라 별도 안내 불필요.
 *
 * 주의:
 *  - localStorage 는 XSS 로 탈취 가능하므로 "로그인 했는지 힌트" 용도로만 쓴다.
 *    실제 인증은 항상 BE API (/profiles, /auth/refresh 등) 로 검증한다.
 *  - 토큰은 저장하지 않는다. access 는 HttpOnly 쿠키, refresh 도 동일.
 */

export const AUTH_STATUS = {
  NONE: 'none', // 현재 로그인 이력 없음 (최초 접속자 + 명시적 로그아웃한 재방문자)
  LOGIN: 'login', // 세션이 유효하다고 믿는 상태
}

export const LOGOUT_REASON = {
  SESSION_EXPIRED: 'session_expired', // Access + Refresh 모두 만료 — 자동 로그아웃
}

const STATUS_KEY = 'authStatus'
const REASON_KEY = 'logoutReason'

export function getAuthStatus() {
  if (typeof window === 'undefined') return AUTH_STATUS.NONE
  return localStorage.getItem(STATUS_KEY) || AUTH_STATUS.NONE
}

export function markLoggedIn() {
  if (typeof window === 'undefined') return
  localStorage.setItem(STATUS_KEY, AUTH_STATUS.LOGIN)
  localStorage.removeItem(REASON_KEY)
}

/**
 * 로그인 힌트와 (선택적으로) 사유를 초기화한다.
 *  - 명시적 로그아웃 / 계정 탈퇴: reason 없이 호출 → 조용히 NONE 복귀.
 *  - RTR 완전 실패: reason=SESSION_EXPIRED → 로그인 페이지가 1회성 토스트 표시.
 */
export function markLoggedOut({ reason } = {}) {
  if (typeof window === 'undefined') return
  localStorage.removeItem(STATUS_KEY)
  if (reason) {
    localStorage.setItem(REASON_KEY, reason)
  } else {
    localStorage.removeItem(REASON_KEY)
  }
}

/**
 * 로그아웃 사유를 읽고 즉시 삭제한다 (1회성). 새로고침 시 반복 표시 방지.
 */
export function consumeLogoutReason() {
  if (typeof window === 'undefined') return null
  const reason = localStorage.getItem(REASON_KEY)
  if (reason) localStorage.removeItem(REASON_KEY)
  return reason
}
