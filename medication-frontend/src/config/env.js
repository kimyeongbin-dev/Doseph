/**
 * 환경별 설정 (JavaScript 복구 버전)
 */

const ENV = process.env.NEXT_PUBLIC_ENV || 'local';

// 환경별 기본값
// 정적 export 전환 이후 동일출처 rewrites 프록시가 없으므로 API_BASE_URL 은 "풀 백엔드 URL"이어야 한다.
// 우선순위: NEXT_PUBLIC_API_BASE_URL(빌드 시 주입) > 아래 기본값.
const ENV_CONFIG = {
  local: {
    API_BASE_URL: 'http://localhost:8000',
    KAKAO_REDIRECT_URI: 'http://localhost:3000/auth/kakao/callback',
  },
  dev: {
    API_BASE_URL: 'http://localhost:8000',
    KAKAO_REDIRECT_URI: 'http://localhost:3000/auth/kakao/callback',
  },
  prod: {
    // 배포 환경변수 NEXT_PUBLIC_API_BASE_URL 로 반드시 주입 (예: https://api.doseph.com)
    API_BASE_URL: '',
    // 실제 카카오 redirect_uri 는 백엔드 /auth/kakao/config 가 내려주므로
    // 이 흐름에서 FE 기본값은 사용되지 않음(플랫폼 중립을 위해 하드코딩 제거).
    KAKAO_REDIRECT_URI: '',
  },
};

const currentConfig = ENV_CONFIG[ENV] || ENV_CONFIG.local;

// API URL에서 후행 슬래시 자동 제거
const cleanApiUrl = (url) => {
  if (!url) return '';
  return url.replace(/\/$/, '');
};

// 보안 유틸리티
export const securityUtils = {
  detectEnvironmentTampering: () => {
    const clientEnv = process.env.NEXT_PUBLIC_ENV;
    const runtimeEnv = ENV;

    if (clientEnv !== runtimeEnv) {
      console.warn('Environment tampering detected');
      return true;
    }
    return false;
  }
};

export const config = {
  ENV,
  API_BASE_URL: cleanApiUrl(process.env.NEXT_PUBLIC_API_BASE_URL ?? currentConfig.API_BASE_URL),
  KAKAO_CLIENT_ID: process.env.NEXT_PUBLIC_KAKAO_CLIENT_ID || '',
  KAKAO_REDIRECT_URI: process.env.NEXT_PUBLIC_KAKAO_REDIRECT_URI || currentConfig.KAKAO_REDIRECT_URI || '',
};

export default config;
