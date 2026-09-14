// Query key factory — 모든 도메인 hook 이 이 파일의 함수를 호출해 key 를 만든다.
// 같은 데이터에 대해 다른 곳에서 다른 key 를 쓰면 invalidate 가 안 통하므로 SSOT.
//
// staleTime / gcTime 은 도메인별 query hook 에서 override (대부분 도메인의
// 변동 빈도에 맞춰 차등 — qa-audit-plan §2-C 참조).

export const qk = {
  profile: {
    all: () => ['profile'],
    list: () => ['profile', 'list'],
    detail: (profileId) => ['profile', 'detail', profileId],
  },
  prescriptionGroups: {
    all: () => ['prescription-groups'],
    list: (profileId, search) => ['prescription-groups', 'list', profileId, search || ''],
    detail: (groupId) => ['prescription-groups', 'detail', groupId],
  },
  medications: {
    all: () => ['medications'],
    list: (profileId) => ['medications', 'list', profileId],
    detail: (medicationId) => ['medications', 'detail', medicationId],
  },
  lifestyleGuides: {
    all: () => ['lifestyle-guides'],
    list: (profileId) => ['lifestyle-guides', 'list', profileId],
    detail: (guideId) => ['lifestyle-guides', 'detail', guideId],
    challenges: (guideId) => ['lifestyle-guides', 'challenges', guideId],
  },
  challenges: {
    all: () => ['challenges'],
    list: (profileId) => ['challenges', 'list', profileId],
  },
  ocrDraft: {
    all: () => ['ocr-draft'],
    activeList: (profileId) => ['ocr-draft', 'active', profileId],
    detail: (draftId) => ['ocr-draft', 'detail', draftId],
  },
  chatSessions: {
    all: () => ['chat-sessions'],
    list: (profileId) => ['chat-sessions', 'list', profileId],
    detail: (sessionId) => ['chat-sessions', 'detail', sessionId],
    messages: (sessionId) => ['chat-sessions', 'messages', sessionId],
  },
  dailyLogs: {
    all: () => ['daily-logs'],
    list: (profileId) => ['daily-logs', 'list', profileId],
  },
  // 복약 체크 기록(intake-logs). 날짜별로 다른 목록이라 key 에 날짜 포함.
  intakeLogs: {
    all: () => ['intake-logs'],
    byDate: (profileId, date) => ['intake-logs', 'by-date', profileId, date],
    streak: (profileId) => ['intake-logs', 'streak', profileId],
  },
}

// 도메인별 staleTime — 변동 빈도 기반 차등.
// 사용처: const opts = { staleTime: STALE.profile, ... }
export const STALE = {
  profile: 5 * 60 * 1000, // 5분 — 거의 안 바뀜
  prescriptionGroups: 30 * 1000, // 30초 — 자주 변경
  medications: 30 * 1000, // 30초 — 자주 변경
  lifestyleGuides: 60 * 1000, // 60초 — mutation 후 invalidate 로 충분
  challenges: 60 * 1000,
  ocrDraft: 10 * 1000, // 10초 — TTL 짧음
  chatSessions: 30 * 1000,
  dailyLogs: 60 * 1000,
  intakeLogs: 30 * 1000, // 30초 — 체크/해제 mutation 후 invalidate 로 즉시 갱신
}
