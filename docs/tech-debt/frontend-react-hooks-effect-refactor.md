# [TECH DEBT] 프론트엔드 react-hooks effect 리팩터

> 🗓️ 등록: 2026-08-14 (Phase 1 정적 export 작업 중 발견) · 갱신: 2026-09-14
> 📌 상태: **진행 중** — 32건 중 **17건 해소**, **15건 잔여**
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

> 📐 **규칙 정본 = `docs/TESTING_SAFETY_NET_RULES.md`** — 무엇을 단언하고 무엇을 단언하지 않는지,
> 층을 어떻게 나누는지. 아래는 그 규칙에 따라 현재 확보된 자산의 현황이다.

- ✅ **컴포넌트/컨텍스트 층**: `medication-frontend/__tests__/` — Vitest + RTL 특성화 테스트 26개.
  백엔드 불필요(mock)하여 결정적.
- ✅ **페이지/흐름 층**: Playwright 49개 통과·skip 0. `auth.setup.js` 는 **mock IdP + 진짜 콜백**으로
  재작성(제거된 개발자 백도어 의존 해소) → `docs/tech-debt/e2e-auth-strategy.md`,
  `seed.setup.js` 가 앱의 실제 생성 API 로 멱등 시드(복약 2종 · 활성 챌린지 2건, 도메인별
  setup 분리 — 한 도메인의 멱등 early return 이 다른 도메인 시드를 건너뛰지 않게).
  ⚠️ **skip 은 안전망이 아니다**: 데이터 의존 스펙의 `test.skip(count === 0)` 이 레이트 리밋 429 를
  '조용한 통과'로 덮고 있었다(실측 매 실행 1~2건). 전부 단언으로 전환 → 실패로 드러나게 했고,
  원인인 한도 하드코딩은 설정값으로 분리(`d70bda9`).

## 진행 현황 (2026-09-14)

### ✅ 해소 17건

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

**판단 기준(억지 제거 금지)**: "React 바깥과 동기화하는가"
→ 파생·이벤트 반응이면 제거 / 서버 상태면 쿼리 계층 / 외부 스토어면 effect 유지하고 deps 만 정정.

> 🔎 **리팩터 중 발견(동작 보존 — 고치지 않음)**: `ChatModal` 의 초기화 실패 UI
> (`initError` + 재시도 버튼)는 **도달 불가능한 죽은 분기**다. `refetch()`/`refetchQueries()`
> 는 쿼리가 실패해도 **reject 하지 않고 resolve** 하므로 `catch` 가 돌지 않는다.
> 실증: `/chat-sessions` GET 을 500 으로 스텁하면 재시도 UI 가 뜨지 않으며,
> **리팩터 전 커밋으로 되돌려 빌드해도 동일하게 실패**한다(사전 존재 결함 확정).
> 동작 변경이라 이 리팩터에 섞지 않고 후속 큐로 넘겼다(로드맵 1-d 와 같은 결 —
> "실패가 사용자에게 실패로 보이지 않는다").

> 💡 **함정 기록**: TanStack Query 이관 시 `query.data || []` 가 매 렌더 새 배열을 만들어
> `useCallback` 의존성을 흔들어 **경고가 오히려 2건 늘었다** → `useMemo` 로 해결.
> **같은 패턴이 남은 컨텍스트들에도 있다**(`listQuery.data || []`).

### ⬜ 잔여 15건

**공유 컨텍스트 5건** — 컨텍스트 자체 계약은 테스트로 잠겼으나 **페이지와의 통합 동작은 미잠금**
(blast radius 가 커서 페이지 레벨 E2E 확보 후 착수).

| 파일 | 규칙 |
|---|---|
| `contexts/ProfileContext.jsx` | deps + set-state |
| `contexts/ChatSessionContext.jsx` | set-state |
| `contexts/LifestyleGuideContext.jsx` | deps |
| `contexts/PrescriptionGroupContext.jsx` | deps |

**페이지/흐름 10건** — 페이지/흐름 E2E 안전망 확보 완료(`a68484e`·`6c3c06d`·`698355d`), 저위험순 착수 중.

| 파일 | 건수 | 패턴 힌트 |
|---|---|---|
| `app/lifestyle-guide/page.jsx` | 6 | 증상 조회, 가이드 전환 시 챌린지 페이지 리셋 |
| `app/mypage/page.jsx` | 3 | `?tab=family` 탭 활성, fetchData 클로저(immutability) |
| `components/chat/ChatModal.jsx` | 1 | 세션 변경 시 GPS 토글 리셋(G4) — 관측 까다로워 후순위 |

> 라인 번호는 편집으로 이동하므로 착수 시 `npm run lint` 로 최신 위치를 재확인할 것.

> 🧭 **B2 가 남긴 방법론(A5·E1·E2·G4 에 그대로 적용)**: "관측이 까다롭다"는 대개
> **층을 잘못 고른 것**이다. B2(챌린지 재추첨)는 그 화면에 프로바이더를 리렌더시키는
> 사용자 조작이 없어 E2E 로 영원히 관측되지 않는다. 뿌리를 컨텍스트의 **파생 배열 참조
> 안정성**으로 좁히자 Vitest 로 결정적 Red 를 만들 수 있었다.
> 순서 = ①E2E 로는 구조적 계약만(활성 항목 중 정확히 1건 렌더) ②뿌리를 컴포넌트/컨텍스트
> 층에서 Red 로 고정 ③리팩터. 규칙 정본: `docs/TESTING_SAFETY_NET_RULES.md` §2.

## 남은 순서

1. ✅ **E2E 인증 전략 확립**(mock IdP) → 페이지/흐름 안전망 구축 완료
2. 페이지/흐름 10건 → 공유 컨텍스트 5건 리팩터 (저위험순: ~~ChatModal~~ → ~~main~~ →
   **mypage → lifestyle-guide** → contexts). 페이지를 먼저 하는 이유 = 컨텍스트는
   blast radius 가 커서 페이지 쪽 사용 패턴이 정리된 뒤에 손대는 편이 안전.
3. 관측이 까다로운 잔여 건(A5·E1·E2·G4)은 컴포넌트 테스트 또는 **정당화된 유지** 판단
   (B2 는 위 방법론으로 해소 — 먼저 층을 다시 고를 것)
4. **안정화 확인 후 3규칙 error 승격** + 이 문서 종료

계획 정본: `docs-private/PLAN_FE_HOOKS_EFFECT.md`
