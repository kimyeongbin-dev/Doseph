// ── ActiveDraftsCard 계약 (QA-42 · 숨김은 프로필마다) ──────────────────
// 흐름: 프로필 A 에서 카드 숨김 -> 프로필 B 로 전환 -> B 의 카드는 보인다
// 잠그는 동작:
//   (1) 숨기기를 누르면 카드가 사라진다
//   (2) 숨김은 그 프로필에만 걸린다 — 다른 프로필로 바꾸면 다시 보인다
//       (예전에는 페이지가 카드를 remount 하지 않아 숨김이 모든 프로필로 번졌다)
// ⚠️ 의도적으로 단언하지 않는 것: 항목 목록의 모양·시간 표기. 숨김의 범위만 계약이다.
// 전제: 없음(순수 컴포넌트, 백엔드 불필요).

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import ActiveDraftsCard from '@/components/medication/ActiveDraftsCard'

const DRAFTS = [{ draft_id: 'd1', status: 'ready', created_at: '2026-10-18T09:00:00+09:00' }]

function card(profileId) {
  return (
    <ActiveDraftsCard drafts={DRAFTS} profileId={profileId} onSelect={() => {}} onDelete={() => {}} />
  )
}

describe('ActiveDraftsCard', () => {
  it('숨기기를 누르면 카드가 사라진다', async () => {
    render(card('profile-a'))
    await userEvent.click(screen.getByRole('button', { name: '카드 숨기기' }))

    expect(screen.queryByText('처방전 (1건)'), '숨긴 카드는 보이지 않아야 한다').not.toBeInTheDocument()
  })

  it('한 프로필에서 숨겨도 다른 프로필로 바꾸면 다시 보인다', async () => {
    const { rerender } = render(card('profile-a'))
    await userEvent.click(screen.getByRole('button', { name: '카드 숨기기' }))

    rerender(card('profile-b'))

    expect(
      screen.getByText('처방전 (1건)'),
      '숨김이 다른 프로필로 번지면 그 프로필의 처방전을 놓친다',
    ).toBeInTheDocument()
  })
})
