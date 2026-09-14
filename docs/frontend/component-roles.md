# 프론트엔드 컴포넌트·컨텍스트 역할 레퍼런스 (Doseph)

> 🗓️ 작성 2026-09-14 · 6C(react-hooks effect 리팩터) 안전망 작업 중 정리 · **갱신 2026-09-14(6C 완료 반영)**
> 각 컴포넌트가 "이 앱에서 실제로 무슨 일을 하는가"를 정리한 문서. 리팩터 시 동작 보존 기준으로 참조.
> 아래 "6C 처리 결과" 줄은 **실제로 어떻게 처리했는지**의 기록이다(32건 전건 해소).
> 대상 파일 경로는 `medication-frontend/src/` 기준.

이 문서는 6C 리팩터 대상(또는 인접) 컴포넌트/컨텍스트의 **역할**만 다룬다. 코딩 규칙은
`medication-frontend/DESIGN_SYSTEM.md`·`CLAUDE.md`, 리팩터 계획은
`docs-private/PLAN_FE_HOOKS_EFFECT.md` 참조.

---

## 1. UI 컴포넌트

### ThemeToggle — `components/ui/ThemeToggle.jsx`
**역할**: 라이트/다크 테마 전환 버튼(헤더/네비에 배치).
- 마운트 시 `localStorage('theme')` 우선, 없으면 OS 선호(`prefers-color-scheme`)로 초기 테마 결정.
- 클릭 시 테마 전환 → `<html data-theme>` 속성 갱신(= `globals.css` 의 `:root[data-theme]`
  오버라이드와 연동) + `localStorage` 저장.
- 마운트 전엔 아이콘 없는 자리표시자만 렌더(SSR/CSR 하이드레이션 불일치 방지). FOUC 방지
  인라인 스크립트는 `layout` head 에 별도로 있음.
- 6C 처리 결과(L1) ✅: 외부 스토어(localStorage/OS) 구독이라 **`useSyncExternalStore`** 로 전환(`41b63f1`).

### TimeSlotPicker — `components/medication/TimeSlotPicker.jsx`
**역할**: 약 **한 개**의 복약 시간대 토글 피커. 슬롯 = 아침(08:00)/점심(13:00)/저녁(19:00)/취침(21:00).
- `medication.intake_times` 를 슬롯 활성 상태로 반영(HH:MM 정규화).
- 슬롯 탭 → **낙관적 업데이트**(서버 응답 전 UI 즉시 반영) → `PATCH /medications/{id}` →
  `MedicationContext.refetchMedications()` 로 홈(TodaySchedule) 즉시 반영. 실패 시 롤백.
- `medication.id` 가 바뀌면(다른 약 선택) 시간대 state 를 새 약 기준으로 재초기화(6C J1 대상).

### TodaySchedule — `components/medication/TodaySchedule.jsx`
**역할**: 메인(홈)의 "오늘의 복약" 섹션.
- `medications` 를 시간대 블록(아침/점심/저녁/취침)으로 분류, 현재 시간대 블록 강조.
  `intake_times` 없는 약은 "복약 시간 미설정" 섹션에 모음.
- 마운트 시 오늘 `intake-logs` 조회 → `TAKEN` 상태를 완료 표시(진행률 바 + n/m 완료).
- 체크(복용 기록 `POST` + `/take`)·언체크(`DELETE`)·"전체 완료"(블록 일괄) 지원.
- 6C 처리 결과(K1) ✅: 서버 상태라 **TanStack Query 이관**(`6707ab2`). 이후 공유 훅 `@/queries/intakeLogs` 로 추출(`e5af3ab`) — 마이페이지 통계와 같은 키를 보게 되어 queryFn 을 한 곳으로 모았다.

### MedicineNameAutocomplete — `components/medication/MedicineNameAutocomplete.jsx`
**역할**: 약품명 실시간 자동완성 입력(약 등록/편집 폼).
- 250ms **debounce** + 최소 2자 + `AbortController`(in-flight 취소) → `GET /medicines/suggest`
  (백엔드 pg_trgm fuzzy 매칭, 최대 8건) → dropdown.
- 키보드 ↑/↓/Enter/Esc 지원. `react-hook-form` 의 `Controller` 와 **제어형(controlled)** 으로 사용.
- 마운트 시 prefilled value(OCR 결과 자동 채움 등)는 조회 스킵(사용자 typing 시에만 조회).
- 6C 처리 결과(I1) ✅: **이벤트 기반 전환**(onChange 에서 debounce 시작). effect 흉내내던 ref 2개 제거(`5e3ca01`).

---

### ChatModal — `components/chat/ChatModal.jsx`
**역할**: AI 상담 모달. 좌측 세션 사이드바(생성/이름변경/삭제/전환) + 우측 대화 영역.
`next/dynamic`(`ssr:false`)으로 지연 로드된다.

#### ⚠️ 발신자 구분 계약 (이 컴포넌트에서 가장 자주 틀리는 지점)

**BE 가 주는 필드명과 FE 내부에서 쓰는 필드명이 다르다.**

| 경계 | 필드 | 값 |
|---|---|---|
| BE 응답 (`GET /messages/session/{id}`) | `sender_type` | `USER` \| `ASSISTANT` (`app/models/messages.py` 의 `SenderType`) |
| FE 내부 상태 (`messages[]`) | `role` | `'user'` \| `'assistant'` |

변환은 `loadMessagesForSession` 한 곳에서만 일어난다:
```js
role: m.sender_type === 'USER' ? 'user' : 'assistant'
```

이 구분이 화면에서 만들어 내는 **관측 가능한 차이**는 두 가지다:

1. **정렬/색**: `user` 는 오른쪽 정렬 + accent 배경, `assistant` 는 왼쪽 + surface 배경.
2. **렌더 방식**: `user` 는 **원문 그대로**(`whitespace-pre-wrap` 텍스트),
   `assistant` 는 **`react-markdown` 을 통과**한다(LLM 이 Markdown 으로 답하므로).
   → assistant 메시지의 `**굵게**` 는 `<strong>` 이 되고, user 메시지의 `**굵게**` 는
   별표가 그대로 보인다.

> 🔴 **실제 사고(2026-09-14)**: E2E mock 이 `role` 을 보내고 있었다. 컴포넌트는 `sender_type`
> 을 보므로 **모든 mock 메시지가 assistant 로 렌더**됐는데, 테스트는 "텍스트가 보이는가"만
> 단언해서 **초록이었다**. 매핑이 깨져도 잡히지 않는 구멍.
> → mock 을 `sender_type` 으로 정정하고, 위 2번(Markdown 렌더 차이)을 단언해 잠갔다.
> **교훈: mock 의 필드명이 실제 계약과 같은지 확인하고, 매핑 결과가 눈에 보이는 차이로
> 드러나게 단언하라.** 텍스트 존재만 보는 단언은 매핑을 검증하지 못한다.

`role` 은 화면 렌더 외에 **한 곳 더** 쓰인다 — `isPendingResponse`:
```js
displayMessages[displayMessages.length - 1].role === 'user'   // 마지막이 user = BE 응답 대기 중
```
모달을 닫았다 열어도 "답변 대기 중" 상태가 자동 인식되고 중복 전송이 막히는 근거가 이것이다.
즉 **발신자 매핑이 틀어지면 렌더뿐 아니라 중복 전송 차단까지 깨진다.**

#### 상태 구조 (2026-09-14 리팩터 후)
- `messages` = 실제 대화 state. 서버 로드분 + 전송 중 낙관적 추가분이 한 배열에 있다.
- `displayMessages` = 렌더용 **파생값**. 프로필 없음 / 세션 없음 안내는 state 로 들고 있지 않는다.
- `effectiveSessionId` = 렌더 중 파생. Context 의 `activeSessionId` 가 현재 목록에 없으면
  (삭제·프로필 전환) 첫 세션으로 물러난다. 낡은 id 를 effect 로 지우지 않고 **무시**한다.
- 세션 동기화 effect는 **모달 열림 시 1회**(+재시도)만 돈다. 전환·생성·삭제는 각 이벤트
  핸들러가 직접 메시지를 로드한다 — effect 가 `activeSessionId` 를 구독하면 전송 중
  낙관적 메시지를 서버 목록으로 덮어쓴다.
- GPS 토글(JIT opt-in): 세션이 바뀌면 hidden + OFF 로 리셋. 6C 처리 결과(G4) ✅: effect → **렌더 중 조정**(`ad5c8c7`). E2E 는 `/messages/ask` 를 `202 + action=request_geolocation` 으로 고정해 토글 등장을 관측한다.

---

## 2. 전역 상태(Context)

### ProfileContext — `contexts/ProfileContext.jsx`
**역할**: 가족 프로필 도메인의 전역 상태(멀티 프로필 = 본인 + 가족).
- `TanStack Query` 로 `GET /profiles` 목록 관리(staleTime 5분, public path 에선 비활성 →
  비인증 라우트 401 노이즈 방지).
- **선택 프로필(`selectedProfileId`) 자동 정합**: 목록 변화 시 저장값 복원 → 없으면
  `SELF`(본인) 프로필로 폴백 → 첫 프로필 순. `localStorage('selectedProfileId')` 동기화.
- CRUD 는 `useMutation`, 성공 시 list 캐시 직접 patch. 삭제 시 연관 도메인 캐시(처방전/복약/
  가이드/챌린지/챗/OCR) invalidate(BE cascade 동기화). `RELATION_LABELS` 등 상수 제공.
- 6C 처리 결과(P1/P2) ✅: 한 effect 가 겸하던 "선택 보정"과 "localStorage 반영"을 분리 — 보정은 **렌더 중 파생**, 저장만 effect(state 미변경)(`d57946a`).

---

## 3. 기법 용어

### debounce (디바운스)
컴포넌트가 아니라 **기법**. 연속으로 쏟아지는 이벤트(타이핑 등)에서 "마지막 입력 후 N ms
동안 잠잠하면 그때 한 번만" 실행. 매 글자마다 API 를 때리지 않고 입력이 멈춘 뒤 1회 호출 →
네트워크·렌더 절약. Autocomplete 는 `setTimeout` + `clearTimeout`(ref 보관)으로 250ms 구현.
(비슷한 사촌: throttle = "N ms 마다 최대 1회". debounce = "멈추면 1회".)

---

## 관련 문서
- 개념/테스트 기법(controlled·harness·TanStack Query 등) = `docs-private/study/react-hooks-effect-testing.md`
- 리팩터 계획·경고 목록 = `docs-private/PLAN_FE_HOOKS_EFFECT.md`, `docs/tech-debt/frontend-react-hooks-effect-refactor.md`
