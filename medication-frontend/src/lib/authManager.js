/**
 * Auth Manager (인증 관리자)
 * 인증 상태 관리, 토큰 갱신, 로그아웃 처리
 */

import api from './api';
import { LOGOUT_REASON, markLoggedOut } from './authStatus';

let isRefreshing = false;
let refreshSubscribers = [];
let refreshAttempts = 0;
const MAX_REFRESH_ATTEMPTS = 3;

function subscribeTokenRefresh(callback) {
  refreshSubscribers.push(callback);
}

function onRefreshed(newToken) {
  refreshSubscribers.forEach((callback) => callback(newToken));
  refreshSubscribers = [];
}

function onRefreshFailed(error) {
  refreshSubscribers.forEach((callback) => callback(null, error));
  refreshSubscribers = [];
}

export async function refreshToken() {
  if (isRefreshing) {
    return new Promise((resolve, reject) => {
      subscribeTokenRefresh((token, error) => {
        if (error) reject(error);
        else resolve(token);
      });
    });
  }

  if (refreshAttempts >= MAX_REFRESH_ATTEMPTS) {
    console.error('Token refresh max attempts exceeded');
    handleLogout();
    return null;
  }

  isRefreshing = true;
  refreshAttempts++;

  try {
    await api.post('/api/v1/auth/refresh');
    onRefreshed(true);
    refreshAttempts = 0;
    return true;
  } catch (error) {
    const status = error.response?.status;
    // 401 (refresh 만료) / 403 token_compromised 모두 자동 로그아웃 → 세션 만료 안내로 수렴.
    // 구분 메시지가 필요해지면 LOGOUT_REASON 에 케이스 추가해 이 분기만 바꿀 것.
    if (status === 401 || status === 403) {
      handleLogout();
    } else {
      console.error('Token refresh failed:', error);
    }

    onRefreshFailed(error);
    return null;
  } finally {
    isRefreshing = false;
  }
}

/**
 * 자동 로그아웃 — RTR 완전 실패 / 재시도 한도 초과 시 호출.
 * 사유는 SESSION_EXPIRED 고정. 로그인 페이지에서 localStorage 힌트를 소비해
 * 안내 문구를 표시한다 (redirect 중 토스트가 사라지는 문제 회피).
 */
export async function handleLogout() {
  refreshAttempts = 0;
  try {
    await api.post('/api/v1/auth/logout');
  } catch {
    // 서버 세션이 이미 무효일 가능성. 로컬 정리만 진행한다.
  }

  markLoggedOut({ reason: LOGOUT_REASON.SESSION_EXPIRED });

  if (typeof window !== 'undefined' && !window.location.pathname.includes('/login')) {
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- 비컴포넌트(lib): router 훅 불가 + 로그아웃 상태 초기화 위해 전체 이동
    window.location.href = '/login';
  }
}

export function isTokenRefreshing() {
  return isRefreshing;
}

export function resetRefreshAttempts() {
  refreshAttempts = 0;
}
