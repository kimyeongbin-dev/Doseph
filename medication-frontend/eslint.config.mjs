import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";

const eslintConfig = defineConfig([
  ...nextVitals,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
  {
    // [TECH DEBT / TODO] React 19 시대에 새로 도입된 React Compiler 지향 preview 규칙
    // (effect 내 setState 금지 등). 기존 코드베이스 전반의 관용 패턴(mount 가드, 파생상태 동기화)이
    // 걸리므로 error -> warn 으로 강등해 가시성만 유지한다.
    // 실제 effect 리팩터(22건) 후 이 override 를 제거하고 error 로 복구할 것.
    // 상세 목록·처리 조건: docs/tech-debt/frontend-react-hooks-effect-refactor.md
    rules: {
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/immutability": "warn",
    },
  },
  {
    // Vitest 테스트/셋업 파일: globals:true 로 주입되는 테스트 전역을 ESLint 에 인지시켜
    // no-undef 오탐을 막는다. (플러그인 추가 없이 전역 선언만 — 최소 의존성)
    files: ['__tests__/**/*.{js,jsx}', 'vitest.setup.js'],
    languageOptions: {
      globals: {
        describe: 'readonly',
        it: 'readonly',
        test: 'readonly',
        expect: 'readonly',
        vi: 'readonly',
        beforeAll: 'readonly',
        afterAll: 'readonly',
        beforeEach: 'readonly',
        afterEach: 'readonly',
      },
    },
  },
  {
    // [보안 게이트] dangerouslySetInnerHTML 사용 차단 — DOM 기반 XSS 의 대표적 sink.
    // 현재 코드베이스 사용처 0건이므로 error 로 넣어 신규 유입을 CI 에서 차단한다.
    // 정말 필요하면 해당 라인에 sanitize(예: DOMPurify) 후 명시적 eslint-disable 로 예외 처리.
    rules: {
      "react/no-danger": "error",
    },
  },
]);

export default eslintConfig;
