# [TECH DEBT] 프론트엔드 react-hooks effect 리팩터

> 🗓️ 등록: 2026-08-14 (Phase 1 정적 export 작업 중 발견) · 갱신: 2026-09-14
> 📌 상태: **진행 중** — 32건 중 **10건 해소(리프 컴포넌트 8 + 페이지/게이트 2)**, **22건 잔여**
> 🎯 최종 목표: 경고 0 + 강등한 규칙을 **error 로 복구**(해소 → 안정화 → 승격)

---

## 배경

`eslint-config-next 16`(React 19)이 새로 끌어온 **React Compiler 지향 preview 규칙**
(`react-hooks/set-state-in-effect`, `react-hooks/immutability`)이 기존 코드베이스 전반의 관용 패턴
(mount 가드, 파생상태 동기화, URL 파라미터 처리 등)을 error 로 잡았다.

Phase 1(정적 export) 범위 밖의 광범위 상태관리 리팩터이며 behavior 회귀 위험이 커서,
당장은 `medication-frontend/eslint.config.mjs` 에서 두 규칙을 **`warn` 으로 강등**(에러 0 확보)하고
실제 수정은 이 문서로 이관했다.

> ⚠️ **2026-09-14 실측 정정**: 최초 등록 시 22건으로 집계했으나 `exhaustive-deps` 를 세지 않았다.
> 실제 총계는 **32건**(`set-state-in-effect` 21 · `exhaustive-deps` 10 · `immutability` 1).
> 강등 override 대상은 앞의 2규칙이고 `exhaustive-deps` 는 next 기본 warn 이지만,
> **최종 승격 목표는 3규칙 모두 error** 로 확정했다.

## 처리 조건 (반드시)

1. **별도 커밋/작업 단위** — 기능 변경과 절대 섞지 않는다(refactor/feature 분리).
2. **안전망 우선** — 대상 파일의 현재 동작을 특성화 테스트로 못 박은 뒤에만 손댄다.
3. 완료 후 `eslint.config.mjs` 의 강등 override 제거 → **3규칙을 error 로 복구**하고 경고 0 유지.

## 안전망 현황

- ✅ **컴포넌트/컨텍스트 층**: `medication-frontend/__tests__/` — Vitest + RTL 특성화 테스트 24개.
  백엔드 불필요(mock)하여 결정적.
- ❌ **페이지/흐름 층**: Playwright 인증 스펙이 **차단**됨 — `auth.setup.js` 가 이미 제거된
  개발자 로그인 백도어에 의존. → `docs/tech-debt/e2e-auth-strategy.md`

## 진행 현황 (2026-09-14)

### ✅ 해소 10건

| 대상 | 규칙 | 처리 방식 | 커밋 |
|---|---|---|---|
| `components/ui/ThemeToggle.jsx` | set-state | **`useSyncExternalStore`** 전환. mount 가드 제거(하이드레이션은 서버 스냅샷 `null` 이 담당) | `41b63f1` |
| `components/medication/TodaySchedule.jsx` | set-state | **TanStack Query 이관**(`qk.intakeLogs.byDate` 신설, mutation 후 invalidate) | `6707ab2` |
| `components/medication/MedicineNameAutocomplete.jsx` | set-state | **이벤트 기반 전환**(onChange 에서 debounce 시작). `userTypedRef`·`skipFetchRef` 제거 | `5e3ca01` |
| `components/medication/TimeSlotPicker.jsx` | set-state + deps | **렌더 중 state 조정**(prevId 비교). 부모 `key` 리셋 대신 택해 안전망 범위 유지 | `9819516` |
| `components/lifestyle/SymptomLogForm.jsx` | deps ×3 | **effect 유지 + 의존성 정정**(RHF 내부 스토어 = 정당한 외부 동기화) | `5c620d5` |
| `components/AuthGuard.jsx` | set-state | **public 분기를 렌더 중 파생**으로 이동. 부수 개선: public 방문이 인증 결과를 `ok` 로 오염시켜 보호 경로를 미검증 렌더하던 문제 제거 | `955f450` |
| `app/medication/page.jsx` | set-state | **초깃값 + 이벤트 핸들러로 해소**. 확정 검색어를 버퍼 `useState` 초깃값으로 잡고, `applySearch` 가 두 값을 함께 갱신 | `ae90cec` |

**판단 기준(억지 제거 금지)**: "React 바깥과 동기화하는가"
→ 파생·이벤트 반응이면 제거 / 서버 상태면 쿼리 계층 / 외부 스토어면 effect 유지하고 deps 만 정정.

> 💡 **함정 기록**: TanStack Query 이관 시 `query.data || []` 가 매 렌더 새 배열을 만들어
> `useCallback` 의존성을 흔들어 **경고가 오히려 2건 늘었다** → `useMemo` 로 해결.
> **같은 패턴이 남은 컨텍스트들에도 있다**(`listQuery.data || []`).

### ⬜ 잔여 22건

**공유 컨텍스트 5건** — 컨텍스트 자체 계약은 테스트로 잠겼으나 **페이지와의 통합 동작은 미잠금**
(blast radius 가 커서 페이지 레벨 E2E 확보 후 착수).

| 파일 | 규칙 |
|---|---|
| `contexts/ProfileContext.jsx` | deps + set-state |
| `contexts/ChatSessionContext.jsx` | set-state |
| `contexts/LifestyleGuideContext.jsx` | deps |
| `contexts/PrescriptionGroupContext.jsx` | deps |

**페이지/흐름 17건** — 페이지/흐름 E2E 안전망 확보 완료(`a68484e`·`6c3c06d`·`698355d`), 저위험순 착수 중.

| 파일 | 건수 | 패턴 힌트 |
|---|---|---|
| `app/lifestyle-guide/page.jsx` | 6 | 증상 조회, 가이드 전환 시 챌린지 페이지 리셋 |
| `app/main/page.jsx` | 2 | `?showSurvey` 모달, 활성 챌린지 랜덤 선택 |
| `app/medication/group/page.jsx` | 2 | groupId 변경 시 로딩/에러 + 상세 fetch |
| `app/mypage/page.jsx` | 3 | `?tab=family` 탭 활성, fetchData 클로저(immutability) |
| `components/chat/ChatModal.jsx` | 4 | 세션 초기화·보정, 메시지 로드, GPS/스크롤 |

> 라인 번호는 편집으로 이동하므로 착수 시 `npm run lint` 로 최신 위치를 재확인할 것.

## 남은 순서

1. **E2E 인증 전략 확립**(프로그래매틱 로그인) → 페이지/흐름 안전망 구축
2. 공유 컨텍스트 5건 → 페이지/흐름 19건 리팩터
3. **안정화 확인 후 3규칙 error 승격** + 이 문서 종료

계획 정본: `docs-private/PLAN_FE_HOOKS_EFFECT.md`
