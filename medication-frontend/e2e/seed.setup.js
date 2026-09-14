// ── E2E 시드 데이터 (setup) ──────────────────────────────────────────
// 흐름: 저장된 세션으로 API 호출 -> 프로필 확인 -> 복약 데이터가 없으면 생성
//       -> 데이터 의존 흐름 스펙(복약 목록/상세 등)이 skip 없이 돌 수 있게 한다
//
// 왜 필요한가: dev 계정은 프로필 1건 외 처방전·복약이 0건이라 데이터 의존 스펙이
// 전부 skip 되어 "안전망에 구멍"이 생긴다. 시드가 있어야 특성화가 실제로 성립한다.
//
// 원칙:
//   - **멱등(idempotent)**: 이미 데이터가 있으면 만들지 않는다(반복 실행 안전).
//   - 앱의 실제 생성 엔드포인트를 그대로 사용한다(DB 직접 삽입 금지 — 스키마 우회 방지).
//   - 처방전 그룹에는 생성 API 가 없다. 복약을 만들면 그룹이 함께 생긴다.
// 전제: docker fastapi(:8000) 기동 + auth.setup 이 먼저 실행돼 세션 저장됨.

import { test as setup, expect, request as playwrightRequest } from '@playwright/test'

const API = 'http://localhost:8000/api/v1'
const AUTH_FILE = 'e2e/.auth/user.json'

// 시드 약품 2종 — 서로 다른 시간대를 가져 TodaySchedule 블록 분류도 함께 커버한다.
const SEED_MEDICATIONS = [
  {
    medicine_name: '타이레놀정500mg',
    department: '내과',
    dose_per_intake: '1정',
    daily_intake_count: 2,
    total_intake_days: 5,
    intake_instruction: '식후 30분',
    intake_times: ['08:00', '19:00'],
    total_intake_count: 10,
    start_date: new Date().toISOString().split('T')[0],
  },
  {
    medicine_name: '오메프라졸캡슐',
    department: '내과',
    dose_per_intake: '1캡슐',
    daily_intake_count: 1,
    total_intake_days: 5,
    intake_instruction: '식전',
    intake_times: ['13:00'],
    total_intake_count: 5,
    start_date: new Date().toISOString().split('T')[0],
  },
]

setup('데이터 의존 스펙용 시드 생성(멱등)', async () => {
  const ctx = await playwrightRequest.newContext({ storageState: AUTH_FILE })

  // 1) 프로필 확보 — 시드의 소유자
  const profilesRes = await ctx.get(`${API}/profiles`)
  expect(profilesRes.ok(), '세션이 유효해야 한다(auth.setup 선행 확인)').toBeTruthy()
  const profiles = await profilesRes.json()
  expect(profiles.length, '프로필이 최소 1개 있어야 한다').toBeGreaterThan(0)
  const profileId = profiles[0].id

  // 2) 이미 복약이 있으면 시드하지 않는다(멱등)
  const existingRes = await ctx.get(`${API}/medications?profile_id=${profileId}`)
  const existing = existingRes.ok() ? await existingRes.json() : []
  if (existing.length > 0) {
    await ctx.dispose()
    return
  }

  // 3) 복약 생성 — 처방전 그룹은 이때 함께 만들어진다
  for (const medication of SEED_MEDICATIONS) {
    const res = await ctx.post(`${API}/medications`, {
      data: { ...medication, profile_id: profileId },
    })
    expect(
      res.ok(),
      `시드 복약 생성 실패(${medication.medicine_name}): ${res.status()} ${await res.text()}`,
    ).toBeTruthy()
  }

  await ctx.dispose()
})
