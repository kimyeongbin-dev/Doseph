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
    // React 19 / React Compiler 지향 규칙 3종을 **error 로 승격**한다 (2026-09-14).
    // 2026-08-14 에 기존 코드 32건이 걸려 warn 으로 강등했던 부채를 전건 해소하고 복구한 것.
    // exhaustive-deps 는 next 기본이 warn 이라 여기서 함께 올린다.
    // 이력·처리 방식: docs/tech-debt/frontend-react-hooks-effect-refactor.md
    rules: {
      "react-hooks/set-state-in-effect": "error",
      "react-hooks/immutability": "error",
      "react-hooks/exhaustive-deps": "error",
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
