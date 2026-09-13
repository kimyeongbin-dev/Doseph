// Vitest 설정 — Doseph 프론트엔드 컴포넌트/유닛 테스트 레이어 (6C-A)
//
// 층 배분: 여러 페이지 흐름 = Playwright(e2e/), 컴포넌트/컨텍스트 세부 로직 = Vitest+RTL(__tests__/).
// jsdom 가상 DOM 위에서 컴포넌트를 격리 렌더 -> 데이터는 mock 으로 제어(결정적, 백엔드 시드 불필요).
// Next.js 16 공식 Testing(Vitest) 가이드 기준. @ alias 는 jsconfig(@/* -> ./src/*)와 동일하게 맞춘다.

import { fileURLToPath } from 'node:url'

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.js'],
    // 유닛/컴포넌트 테스트만 수집. Playwright e2e(*.spec.js)는 제외.
    include: ['__tests__/**/*.test.{js,jsx}'],
    css: false,
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
})
