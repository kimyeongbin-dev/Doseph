// ── 공유 테스트 픽스처 / mock 팩토리 ─────────────────────────────────
// 흐름: 각 테스트가 필요한 가짜 데이터를 여기 팩토리로 생성 -> props/응답으로 주입.
// 목적: props·mock 을 한 곳에서 제어(DRY) -> 재사용·수정 용이 + 수동 테스트에도 재활용.
//
// 6C-A 에서는 골격(시그니처)만 둔다. 실제 필드는 6C-B Phase 0 에서 각 컴포넌트
// 특성화 테스트를 작성하며 대상 모델(app/models·응답 DTO) 기준으로 채운다.
//
// 사용 예:
//   import { makeMedication } from '@/../__tests__/fixtures'
//   render(<TimeSlotPicker medication={makeMedication({ intake_times: ['08:00'] })} />)

// 약품 1건. overrides 로 특정 필드만 교체.
export function makeMedication(overrides = null) {
  return {
    id: 'med-1',
    name: '타이레놀',
    intake_times: ['08:00', '13:00', '19:00'],
    ...(overrides || {}),
  }
}

// 프로필 1건. relation_type 기본 'SELF'(선택 폴백 검증용).
export function makeProfile(overrides = null) {
  return {
    id: 'profile-1',
    name: '홍길동',
    relation_type: 'SELF',
    ...(overrides || {}),
  }
}

// 약품명 제안 API(/api/v1/medicines/suggest) 응답 형태 mock.
export function mockSuggestResponse(items = null) {
  return { data: items || [] }
}
