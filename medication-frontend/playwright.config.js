// Playwright E2E 설정 — Doseph 프론트엔드
//
// 검증 대상(target)은 환경변수 E2E_TARGET 으로 전환한다.
//   - static (기본): 정적 export 산출물 out/ 을 serve 로 :3000 서빙 → "P1 전환 후"의 진짜 검증 대상
//   - dev         : next dev(:3000) — 전환 전/후 라우팅 Red 캡처·빠른 반복용
//
// 백엔드는 docker-compose(fastapi:8000)를 먼저 띄워야 인증·데이터 테스트가 통과한다.
// 로컬 백엔드는 localhost:3000 을 CORS(allow_credentials) 허용하므로 :3000 서빙이면 상호작용까지 동작한다.

import { defineConfig, devices } from '@playwright/test'

const TARGET = process.env.E2E_TARGET === 'dev' ? 'dev' : 'static'
const PORT = 3000
const BASE_URL = `http://localhost:${PORT}`

// target 별 웹서버 기동 커맨드
const WEB_SERVER = {
  static: {
    // out/ 은 사전에 `npm run build`(output:export) 로 생성돼 있어야 한다.
    command: 'npm run serve:static',
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
  dev: {
    command: 'npm run dev',
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
}

export default defineConfig({
  testDir: './e2e',
  // 상호작용 테스트는 데이터 상태에 민감하므로 파일 간 병렬은 유지하되 테스트 내 순서는 보존
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  // json 리포터는 CI 게이트(scripts/gates/code/check_e2e_inventory.py)가
  // **몇 건이 실제로 돌았는지**를 세는 유일한 입력이다. 끄면 그 게이트가 눈이 먼다.
  reporter: [['list'], ['html', { open: 'never' }], ['json', { outputFile: 'playwright-report.json' }]],

  timeout: 30_000,
  expect: { timeout: 7_000 },

  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  projects: [
    // 1) mock IdP 로그인으로 세션 쿠키를 확보해 storageState 로 저장
    { name: 'setup', testMatch: /auth\.setup\.js/ },

    // 2) 데이터 의존 스펙이 skip 되지 않도록 시드 생성(멱등) — 세션이 있어야 하므로 setup 이후
    { name: 'seed', testMatch: /seed\.setup\.js/, dependencies: ['setup'] },

    // 3) 로그인 상태로 도는 인증 페이지·상호작용 테스트
    {
      name: 'authed',
      testMatch: /.*\.spec\.js/,
      dependencies: ['seed'],
      use: {
        ...devices['Desktop Chrome'],
        storageState: 'e2e/.auth/user.json',
      },
    },
  ],

  webServer: WEB_SERVER[TARGET],
})
