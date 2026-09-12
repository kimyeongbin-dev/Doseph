/**
 * API 에러 처리 모듈 (JavaScript 복구 버전)
 */

import toast from 'react-hot-toast';

export const HTTP_STATUS_MESSAGES = {
  400: '잘못된 요청입니다.',
  401: '인증이 필요합니다.',
  403: '접근 권한이 없습니다.',
  404: '요청한 리소스를 찾을 수 없습니다.',
  422: '입력값이 올바르지 않습니다.',
  429: '요청이 너무 많습니다. 잠시 후 다시 시도해주세요.',
};

const SERVER_ERROR_MESSAGE = '일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주세요.';

export const ERROR_CODE_MESSAGES = {
  invalid_request: '잘못된 요청입니다.',
  account_disabled: '비활성화된 계정입니다. 고객센터에 문의해주세요.',
  rate_limit_exceeded: '요청 횟수를 초과했습니다. 잠시 후 다시 시도해주세요.',
  network_error: '서버와 통신할 수 없습니다. 네트워크 연결을 확인해주세요.',
  token_exchange_failed: '로그인 처리 중 오류가 발생했습니다.',
  userinfo_failed: '사용자 정보를 가져올 수 없습니다.',
  token_expired: '로그인이 만료되었습니다. 다시 로그인해주세요.',
  invalid_token: '유효하지 않은 인증입니다. 다시 로그인해주세요.',
  missing_token: 'Refresh token이 없습니다. 다시 로그인해주세요.',
  token_compromised: '보안을 위해 로그아웃되었습니다. 다시 로그인해주세요.',
  invalid_input: '허용되지 않는 입력입니다.',
  KOE010: '인증 정보가 올바르지 않습니다.',
  KOE320: '인가 코드가 만료되었거나 유효하지 않습니다.',
};

export const ERROR_ACTIONS = {
  REDIRECT_TO_LOGIN: ['token_expired', 'invalid_token', 'missing_token', 'token_compromised'],
  RETRYABLE: ['network_error', 'rate_limit_exceeded'],
};

export function parseApiError(error) {
  const response = error.response;
  const status = response?.status;
  const data = response?.data;

  const result = {
    status: status || 0,
    code: null,
    message: '알 수 없는 오류가 발생했습니다.',
    shouldRedirectToLogin: false,
    isRetryable: false,
    raw: data,
  };

  if (!response) {
    result.code = 'network_error';
    result.message = ERROR_CODE_MESSAGES.network_error;
    result.isRetryable = true;
    return result;
  }

  if (status >= 500) {
    result.code = 'server_error';
    result.message = SERVER_ERROR_MESSAGE;
    result.isRetryable = true;
    return result;
  }

  const detail = data?.detail;
  if (detail) {
    if (typeof detail === 'object') {
      result.code = detail.error || detail.error_code;
      result.message = detail.error_description
        || ERROR_CODE_MESSAGES[result.code]
        || detail.msg
        || HTTP_STATUS_MESSAGES[status]
        || result.message;
    } else if (typeof detail === 'string') {
      result.message = detail;
    }
  } else {
    result.message = HTTP_STATUS_MESSAGES[status] || result.message;
  }

  if (result.code) {
    result.shouldRedirectToLogin = ERROR_ACTIONS.REDIRECT_TO_LOGIN.includes(result.code);
    result.isRetryable = ERROR_ACTIONS.RETRYABLE.includes(result.code);
  }

  if (status === 401) {
    result.shouldRedirectToLogin = true;
  }

  return result;
}

export function showError(message) {
  toast.error(message);
}

export function handleApiError(error, options = {}) {
  const {
    showMessage = true,
    redirectOnAuth = true,
  } = options;

  const parsed = parseApiError(error);

  if (showMessage) {
    showError(parsed.message);
  }

  if (redirectOnAuth && parsed.shouldRedirectToLogin) {
    if (typeof window !== 'undefined') {
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- 비컴포넌트(lib): router 훅 불가 + 401 시 전체 리로드로 상태 초기화
      window.location.href = '/login';
    }
  }

  return parsed;
}
