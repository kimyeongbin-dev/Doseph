# 프론트엔드 컴포넌트·컨텍스트 역할 레퍼런스 (Doseph)

> 🗓️ 작성 2026-09-14 · 6C(react-hooks effect 리팩터) 안전망 작업 중, 대상 컴포넌트가
> "이 앱에서 실제로 무슨 일을 하는가"를 정리. 리팩터 시 동작 보존 기준으로 참조.
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
- 6C 리팩터 방향(L1): 외부 스토어(localStorage/OS) 구독이므로 `useSyncExternalStore` 정석.

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
- 6C 리팩터 방향(K1): 로그 조회 effect. 외부 데이터 동기화라 정당화 유지 후보.

### MedicineNameAutocomplete — `components/medication/MedicineNameAutocomplete.jsx`
**역할**: 약품명 실시간 자동완성 입력(약 등록/편집 폼).
- 250ms **debounce** + 최소 2자 + `AbortController`(in-flight 취소) → `GET /medicines/suggest`
  (백엔드 pg_trgm fuzzy 매칭, 최대 8건) → dropdown.
- 키보드 ↑/↓/Enter/Esc 지원. `react-hook-form` 의 `Controller` 와 **제어형(controlled)** 으로 사용.
- 마운트 시 prefilled value(OCR 결과 자동 채움 등)는 조회 스킵(사용자 typing 시에만 조회).
- 6C 리팩터 방향(I1): 입력 파생 상태 → 렌더 계산/이벤트 정리 검토.

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
- 6C 리팩터 방향(P1/P2): 선택 정합 effect. 폴백 체인이 까다로워 안전망 선점 필수.

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
