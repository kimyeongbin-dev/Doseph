// ── E2E 시드 데이터 (setup) ──────────────────────────────────────────
// 흐름: 저장된 세션으로 API 호출 -> 프로필 확인 -> 해당 데이터가 없으면 생성
//       -> 데이터 의존 흐름 스펙(복약 목록/상세, 챌린지 카드 등)이 skip 없이 돌 수 있게 한다
//
// 왜 필요한가: dev 계정은 프로필 1건 외 처방전·복약·챌린지가 0건이라 데이터 의존 스펙이
// 전부 skip 되어 "안전망에 구멍"이 생긴다. 시드가 있어야 특성화가 실제로 성립한다.
//
// 원칙:
//   - **멱등(idempotent)**: 이미 데이터가 있으면 만들지 않는다(반복 실행 안전).
//   - 앱의 실제 생성 엔드포인트를 그대로 사용한다(DB 직접 삽입 금지 — 스키마 우회 방지).
//   - 처방전 그룹에는 생성 API 가 없다. 복약을 만들면 그룹이 함께 생긴다.
//   - 도메인별로 setup 을 분리한다 — 한 도메인의 멱등 early return 이 다른 도메인의
//     시드를 건너뛰게 만들지 않기 위함.
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

// 시드 챌린지 2종 — main 의 챌린지 카드는 "활성 챌린지 중 하나"를 고르므로,
// 2건 이상이어야 '선택'이라는 동작 자체가 관측 가능해진다.
// LLM 가이드를 거치지 않는 수동 생성 경로(POST /challenges)라 결정적이다.
const SEED_CHALLENGES = [
  { title: 'E2E 물 2L 마시기', description: '하루 2L 물 마시기', target_days: 7, difficulty: '쉬움' },
  { title: 'E2E 가볍게 걷기', description: '하루 20분 걷기', target_days: 7, difficulty: '보통' },
]

// ── 시드 소유자 프로필 조회 ──────────────────────────────────────────
// 흐름: 저장된 세션으로 /profiles 조회 -> 첫 프로필 ID 반환
async function resolveProfileId(ctx) {
  const profilesRes = await ctx.get(`${API}/profiles`)
  expect(profilesRes.ok(), '세션이 유효해야 한다(auth.setup 선행 확인)').toBeTruthy()
  const profiles = await profilesRes.json()
  expect(profiles.length, '프로필이 최소 1개 있어야 한다').toBeGreaterThan(0)
  return profiles[0].id
}

// ── 복약 시드 (멱등) ─────────────────────────────────────────────────
// 흐름: 프로필 확보 -> 기존 복약 확인 -> 없으면 2종 생성(처방전 그룹 동반 생성)
setup('복약 시드 생성(멱등)', async () => {
  const ctx = await playwrightRequest.newContext({ storageState: AUTH_FILE })
  const profileId = await resolveProfileId(ctx)

  const existingRes = await ctx.get(`${API}/medications?profile_id=${profileId}`)
  const existing = existingRes.ok() ? await existingRes.json() : []
  if (existing.length > 0) {
    await ctx.dispose()
    return
  }

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

// ── 활성 챌린지 시드 (멱등) ──────────────────────────────────────────
// 흐름: 프로필 확보 -> 활성 챌린지 수 확인 -> 2건 미만이면 생성 후 PATCH /start 로 활성화
// 활성 조건은 서버가 정한다: 생성 직후 is_active=false 이고, /start 를 거쳐야
// challenge_status=IN_PROGRESS + is_active=true (= FE 의 activeChallenges 필터 통과).
setup('활성 챌린지 시드 생성(멱등)', async () => {
  const ctx = await playwrightRequest.newContext({ storageState: AUTH_FILE })
  const profileId = await resolveProfileId(ctx)

  const listActive = async () => {
    const res = await ctx.get(`${API}/challenges?profile_id=${profileId}`)
    const all = res.ok() ? await res.json() : []
    return { all, active: all.filter((c) => c.is_active && c.challenge_status === 'IN_PROGRESS') }
  }

  const { all: challenges, active } = await listActive()
  for (const challenge of SEED_CHALLENGES) {
    // 같은 제목이 이미 활성이면 건너뛴다(멱등 + 부분 실패 후 재실행 안전)
    if (active.some((c) => c.title === challenge.title)) continue

    // 생성됐지만 활성화 전에 중단된 경우 재생성하지 않고 활성화만 이어서 한다
    let challengeId = challenges.find((c) => c.title === challenge.title)?.id
    if (!challengeId) {
      const createRes = await ctx.post(`${API}/challenges`, {
        data: { ...challenge, profile_id: profileId },
      })
      expect(
        createRes.ok(),
        `시드 챌린지 생성 실패(${challenge.title}): ${createRes.status()} ${await createRes.text()}`,
      ).toBeTruthy()
      challengeId = (await createRes.json()).id
    }

    const startRes = await ctx.patch(`${API}/challenges/${challengeId}/start`, { data: {} })
    expect(
      startRes.ok(),
      `시드 챌린지 활성화 실패(${challenge.title}): ${startRes.status()} ${await startRes.text()}`,
    ).toBeTruthy()
  }

  // 시드가 "보장한다"고 말하는 전제는 시드 스스로 단언한다.
  // (전제가 깨진 채 스펙이 통과하면 안전망이 아니라 착시다 — 대장 D16)
  const { active: verified } = await listActive()
  expect(
    verified.length,
    `활성 챌린지가 ${SEED_CHALLENGES.length}건 이상이어야 '하나를 고른다'가 관측 가능하다`,
  ).toBeGreaterThanOrEqual(SEED_CHALLENGES.length)

  await ctx.dispose()
})
