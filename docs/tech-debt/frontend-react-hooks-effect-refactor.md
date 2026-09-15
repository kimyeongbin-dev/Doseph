# [TECH DEBT] 프론트엔드 react-hooks effect 리팩터

> 🗓️ 등록: 2026-08-14 (Phase 1 정적 export 작업 중 발견) · 갱신: 2026-09-14
> ✅ 상태: **완료 (2026-09-14)** — 32건 **전건 해소**, 3규칙 **error 승격 완료**(`3854331`).
> 이 문서는 이력 보존용이며 더 이상 추적할 잔여가 없다.
> 🎯 목표였던 것: 경고 0 + 강등한 규칙을 **error 로 복구**(해소 → 안정화 → 승격) — **달성**

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
3. ✅ 완료 후 `eslint.config.mjs` 의 강등 override 제거 → **3규칙을 error 로 복구**하고 경고 0 유지.

## 안전망 현황

> 📐 **규칙 정본 = `docs/TESTING_SAFETY_NET_RULES.md`** — 무엇을 단언하고 무엇을 단언하지 않는지,
> 층을 어떻게 나누는지. 아래는 그 규칙에 따라 현재 확보된 자산의 현황이다.

- ✅ **컴포넌트/컨텍스트 층**: `medication-frontend/__tests__/` — Vitest + RTL 특성화 테스트 29개.
  백엔드 불필요(mock)하여 결정적.
- ✅ **페이지/흐름 층**: Playwright 55개 통과·skip 0. `auth.setup.js` 는 **mock IdP + 진짜 콜백**으로
  재작성(제거된 개발자 백도어 의존 해소) → `docs/tech-debt/e2e-auth-strategy.md`,
  `seed.setup.js` 가 앱의 실제 생성 API 로 멱등 시드(복약 2종 · 활성 챌린지 2건, 도메인별
  setup 분리 — 한 도메인의 멱등 early return 이 다른 도메인 시드를 건너뛰지 않게).
  ⚠️ **skip 은 안전망이 아니다**: 데이터 의존 스펙의 `test.skip(count === 0)` 이 레이트 리밋 429 를
  '조용한 통과'로 덮고 있었다(실측 매 실행 1~2건). 전부 단언으로 전환 → 실패로 드러나게 했고,
  원인인 한도 하드코딩은 설정값으로 분리(`d70bda9`).

## 진행 현황 (2026-09-14)

### ✅ 해소 32건 (전건)

| 대상 | 규칙 | 처리 방식 | 커밋 |
|---|---|---|---|
| `components/ui/ThemeToggle.jsx` | set-state | **`useSyncExternalStore`** 전환. mount 가드 제거(하이드레이션은 서버 스냅샷 `null` 이 담당) | `41b63f1` |
| `components/medication/TodaySchedule.jsx` | set-state | **TanStack Query 이관**(`qk.intakeLogs.byDate` 신설, mutation 후 invalidate) | `6707ab2` |
| `components/medication/MedicineNameAutocomplete.jsx` | set-state | **이벤트 기반 전환**(onChange 에서 debounce 시작). `userTypedRef`·`skipFetchRef` 제거 | `5e3ca01` |
| `components/medication/TimeSlotPicker.jsx` | set-state + deps | **렌더 중 state 조정**(prevId 비교). 부모 `key` 리셋 대신 택해 안전망 범위 유지 | `9819516` |
| `components/lifestyle/SymptomLogForm.jsx` | deps ×3 | **effect 유지 + 의존성 정정**(RHF 내부 스토어 = 정당한 외부 동기화) | `5c620d5` |
| `components/AuthGuard.jsx` | set-state | **public 분기를 렌더 중 파생**으로 이동. 부수 개선: public 방문이 인증 결과를 `ok` 로 오염시켜 보호 경로를 미검증 렌더하던 문제 제거 | `955f450` |
| `app/medication/page.jsx` | set-state | **초깃값 + 이벤트 핸들러로 해소**. 확정 검색어를 버퍼 `useState` 초깃값으로 잡고, `applySearch` 가 두 값을 함께 갱신 | `ae90cec` |
| `app/medication/group/page.jsx` | set-state ×2 | **쿼리 계층 이관 + 렌더 중 파생**. 로딩/에러 복제 state 제거(`usePrescriptionGroupDetail` 신설), 선택 약품 보정은 `validSelectedId` 파생으로 | `12fa883` |
| `components/chat/ChatModal.jsx` | set-state ×3 | **effect 3개 -> 1개**. 초기화는 비동기 콜백에서만 setState(재시도는 이벤트 핸들러), 활성 세션 보정·안내 메시지는 렌더 중 파생, 메시지 로드는 같은 비동기 흐름에 병합. 부수=전송 중 낙관적 메시지를 덮어쓰던 경쟁 제거 | `1849f55` |
| `app/main/page.jsx` | set-state ×2 | **B1=초깃값**(진입 URL 이 최초 표시를 정함, effect 는 쿼리 정리 전용으로 축소) · **B2=렌더 중 파생**(마운트당 고정 시드로 인덱스 계산). 뿌리인 `ChallengeContext` 파생 배열 참조 안정화(`b974825`)를 선행 | `460cbac` |
| `app/mypage/page.jsx` | set-state + deps + immutability | **E3=초깃값**(진입 URL 이 최초 탭 결정) · **E1·E2=쿼리 계층 이관**. `fetchData`+useState 3개+`isInitialLoad` ref 제거, 진행 챌린지는 `ChallengeContext` 재사용해 `/challenges` **중복 GET 제거**, 오늘 복약·연속 복약은 공유 훅(`e5af3ab`) | `9fd85dd` |
| `app/lifestyle-guide/page.jsx` | set-state ×4 + deps ×2 | **effect 4개 -> 0개**. 오늘 증상은 쿼리 계층 이관(`src/queries/dailyLogs.js` 신설)하고 탭 진입 재조회는 **이벤트 핸들러**로, `selectedGuide` 자동 보정과 챌린지 페이지 리셋은 **렌더 중 파생/조정**으로 | `1c46731` |

| `contexts/PrescriptionGroupContext.jsx` | deps | **`data || []` 를 useMemo 로 고정**. 실측: 데이터가 있을 때는 TanStack 이 쥔 같은 배열이라 이미 안정적이고, 매 렌더 새 배열이 생기는 구간은 data 가 undefined 일 때(로딩·에러)뿐 — 테스트도 그 상태로 세워야 Red 가 된다 | `4bf6957` |
| `contexts/ChatSessionContext.jsx` + `components/chat/ChatModal.jsx` | set-state ×2 | **"X 가 바뀌면 리셋" 을 렌더 중 조정으로**(prev 비교). 프로필 전환 시 활성 세션 해제(M1) · 세션 전환 시 GPS 토글 리셋(G4). 새 화면이 이전 상태로 한 번 그려지는 창을 없앤다 | `ad5c8c7` |

| `contexts/LifestyleGuideContext.jsx` | deps | **`data || []` 를 useMemo 로 고정**. data 가 undefined 인 구간에서 컨텍스트 value 의 useMemo 가 깨져 모든 소비자가 리렌더되던 문제 | `3c9ed16` |
| `contexts/ProfileContext.jsx` | deps + set-state | **보정은 렌더 중 파생 / localStorage 반영만 effect**. 한 effect 가 겸하던 두 역할을 분리했고, 고른 프로필이 삭제돼도 state 를 되돌리지 않고 파생에서 무시한다. 공개 setter 는 상태만 바꾸도록 축소 | `d57946a` |

**판단 기준(억지 제거 금지)**: "React 바깥과 동기화하는가"
→ 파생·이벤트 반응이면 제거 / 서버 상태면 쿼리 계층 / 외부 스토어면 effect 유지하고 deps 만 정정.

> 🔎 **리팩터 중 발견(동작 보존 — 고치지 않음)**: `ChatModal` 의 초기화 실패 UI
> (`initError` + 재시도 버튼)는 **도달 불가능한 죽은 분기**다. `refetch()`/`refetchQueries()`
> 는 쿼리가 실패해도 **reject 하지 않고 resolve** 하므로 `catch` 가 돌지 않는다.
> 실증: `/chat-sessions` GET 을 500 으로 스텁하면 재시도 UI 가 뜨지 않으며,
> **리팩터 전 커밋으로 되돌려 빌드해도 동일하게 실패**한다(사전 존재 결함 확정).
> 동작 변경이라 이 리팩터에 섞지 않고 후속 큐로 넘겼다(로드맵 1-d 와 같은 결 —
> "실패가 사용자에게 실패로 보이지 않는다").

> 🔎 **리팩터로 생긴 동작 차이(후속 큐)**: `mypage` 통계 조회가 실패하면 이전에는
> `handleApiError` 토스트가 떴으나, 쿼리 계층 이관 후에는 **값이 0 으로 조용히 렌더**된다.
> 위 `ChatModal` 초기화 실패 UI·로드맵 1-d 와 **같은 부류**("실패가 사용자에게 실패로
> 보이지 않는다") → 조회 실패 표면화를 한 건으로 묶어 별도 작업으로 처리할 것.
> 동작 변경이므로 refactor 커밋에 섞지 않았다.

> 💡 **함정 기록**: TanStack Query 이관 시 `query.data || []` 가 매 렌더 새 배열을 만들어
> `useCallback` 의존성을 흔들어 **경고가 오히려 2건 늘었다** → `useMemo` 로 해결.
> **같은 패턴이 남은 컨텍스트들에도 있다**(`listQuery.data || []`).

### ⬜ 잔여 0건

전건 해소. `eslint.config.mjs` 의 강등 override 를 제거하고 3규칙을 error 로 승격했다(`3854331`).
최종 실측: `npm run lint` **0 error · 0 warning** / Playwright **55 passed · 0 skipped** / Vitest **29 passed**.

> 🧭 **"관측이 까다롭다"는 대개 층이나 대역 지점을 잘못 고른 것이다**
> - **B2**(챌린지 재추첨): 그 화면에 프로바이더를 리렌더시키는 사용자 조작이 없어
>   E2E 로는 영원히 관측되지 않는다 → 뿌리를 컨텍스트의 **파생 배열 참조 안정성**으로
>   좁히자 Vitest 로 결정적 Red 를 만들 수 있었다(**층**을 다시 고른 경우).
> - **G4**(GPS 토글): 층은 맞았고 **대역 지점**이 문제였다. `/messages/ask` 를
>   `202 + action=request_geolocation` 으로 고정하니 토글 등장이 그대로 관측됐다
>   (실제 위치 권한은 불필요). "까다롭다"는 판단이 실제로는 미탐색이었다.
> 순서 = ①E2E 는 구조적 계약만 ②관측이 안 되면 층 또는 대역 지점을 다시 고른다
> ③Red 로 고정 ④리팩터. 규칙 정본: `docs/TESTING_SAFETY_NET_RULES.md` §2·§5.

## 종료 기록

1. ✅ E2E 인증 전략 확립(mock IdP) → 페이지/흐름 안전망 구축
2. ✅ 리프 컴포넌트 → 페이지/흐름 → 공유 컨텍스트 순 전건 리팩터
3. ✅ 3규칙(`set-state-in-effect` · `immutability` · `exhaustive-deps`) **error 승격**
4. ⬜ 후속 큐(별도 작업): **조회 실패 표면화** — mypage 통계 0 무음 렌더 ·
   ChatModal 초기화 실패 UI 죽은 분기 · 로드맵 1-d 를 한 건으로 묶어 처리

중간 기록: `docs-private/record/2026-09-14_fe-hooks-effect-6C-B-record.md`
계획 정본: `docs-private/PLAN_FE_HOOKS_EFFECT.md`
