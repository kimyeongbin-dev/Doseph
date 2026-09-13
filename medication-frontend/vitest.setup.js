// Vitest 전역 셋업 — 모든 테스트 실행 전 1회 로드 (vitest.config.mjs 의 setupFiles)
//
// jest-dom 매처(toBeInTheDocument, toHaveAttribute 등)를 Vitest 의 expect 에 확장한다.
// v7 의 /vitest 진입점이 Vitest 의 expect 를 자동 감지해 확장한다.

import '@testing-library/jest-dom/vitest'
