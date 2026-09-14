# 부채 원장 — 헛된 초록(vacuous green) 전수 정리

> 🗓️ 개설: 2026-09-14 · 상태: **미착수(후속 큐 1-g)**
> 📌 대상: `medication-frontend/__tests__/**` · `medication-frontend/e2e/**`
> 🔗 관련: `docs/TESTING_SAFETY_NET_RULES.md` R3 · 대장 D16 · D19 · **D20**

## 왜 이 원장이 필요한가

D19(2026-09-14)에서 **한 건**을 고치고 끝냈다. 같은 결함이 **같은 파일 안에**,
그리고 다른 스펙에도 남아 있었다. 한 건씩 대응하면 계속 새로 발견된다 →
**한 번에 전수로 훑고 규칙으로 고정**한다.

결함의 형태는 하나다:

> **"무엇을 검증하려는가"(특정 영역의 값) 와 "무엇을 찾고 있는가"(페이지/화면 전체의 텍스트)가 어긋난다.**

`findByText` / `getByText` 는 **렌더 트리 전체**를 본다. 그래서
프리셋 칩·로딩 문구·이웃 라벨처럼 **항상 존재하는 텍스트**에 걸리면,
검증 대상이 망가져도 초록이 된다.

---

## 1. 확진 (실측으로 증명됨)

### V1. 증상 조회 테스트가 조회를 검증하지 않는다 🔴

- **위치**: `e2e/hooks-lifestyle-flow.spec.js:110` — "증상 탭 진입 시 오늘 증상이 조회되어 표시된다 (A1·A3)"
- **무엇**: `page.getByText('두통').first()` / `page.getByText('어지러움').first()`
- **왜 헛된가**: 두 단어 모두 `SymptomLogForm.jsx:58` 의 **`PRESET_SYMPTOMS` 칩 라벨**이다.
  칩은 조회 결과와 무관하게 **항상 렌더**된다. `.first()` 가 다중 매칭 경고까지 덮는다.
- **실측(2026-09-14)**: 스텁을 `symptoms: []` 로 **비워도 테스트가 통과**했다.
  → 이 테스트는 A1·A3(오늘 증상 조회) 계약을 **전혀** 잠그고 있지 않다.
- **처방**: 같은 파일 `:185` 가 이미 쓰는 방식 — 요약 카드 영역(`summary`)에
  스코프를 걸고 **그 안에서만** 찾는다. + 저장 전 부재를 함께 단언.

---

## 2. 약한 대기 (loading 상태를 settled 상태로 오인)

`findByText` 가 **로딩 중에도 참인 값**에 걸려 즉시 resolve → 그 뒤 단언이
**쿼리가 끝나기 전** 상태를 검사한다. 통과해도 의도한 계약을 보지 않는다.

| # | 위치 | 기다리는 값 | 문제 |
|---|---|---|---|
| **V2** | `__tests__/contexts/ProfileContext.test.jsx:90` | `findByText('0')` | 프로필 0건은 **로딩 중에도 0**. 이어지는 `selected === 'none'` 단언도 로딩 중 참 → **effect 가 아예 안 돌아도 통과** |
| **V3** | `__tests__/contexts/LifestyleGuideContext.test.jsx:85` | `findByText('0')` | 실패 전에도 count 0 → 참조 안정성 비교가 settle 이전에 시작될 수 있음 |
| **V4** | `__tests__/contexts/PrescriptionGroupContext.test.jsx:91` | `findByText('empty')` | 위와 동일 |

- **처방**: 대기 지점을 **상태가 실제로 바뀌는 값**에 건다
  (`waitFor(() => expect(getByTestId('error')).toHaveTextContent('true'))` 처럼
  settled 에서만 참인 값). 2026-09-14 의 1-d 작업에서 신규 4건은 이미 이 방식으로 작성했다.

---

## 3. 검토 필요 (확진 아님 — 스코프가 넓어 회귀를 놓칠 수 있음)

| # | 위치 | 내용 |
|---|---|---|
| V5 | `e2e/hooks-medication-flow.spec.js:123` | `getByText('타이레놀정500mg').first()` — 테스트 이름은 "**시간대 블록에 분류**되어 보인다"인데, 블록 소속을 단언하지 않는다. 블록 분류가 깨져도 통과 |
| V6 | `e2e/hooks-mypage-stats.spec.js:25-27` | 라벨 3종 존재만 단언. 값 자리는 (2)(3) 이 일부 커버하지만 '오늘 복약'은 값 단언 없음 |
| V7 | `__tests__/medication/TodaySchedule.test.jsx:49` | `expect(api.get).toHaveBeenCalledWith(...)` 가 **await 이전**에 실행 — 호출 타이밍에 의존(플레이크 위험) |

---

## 처방 — 이 단계에서 할 일

1. V1 을 영역 스코프 + 부재 단언으로 교정하고, **교정 후 스텁을 비워 Red 가 되는지 실측**한다.
2. V2~V4 의 대기 지점을 settled 값으로 옮긴다.
3. V5~V7 을 판정한다(교정 or "의도적으로 단언하지 않음"을 파일 주석에 명시).
4. `docs/TESTING_SAFETY_NET_RULES.md` §3 에 규칙을 추가한다:
   **페이지/화면 전체 텍스트 검색 금지 — 검증 대상 영역에 스코프를 건다.**
   `.first()` 는 다중 매칭을 덮으므로 **이유를 주석에 적은 경우에만** 허용.

## 판정 질문 (커밋 전 자문)

> **"이 스텁/시드를 비우면 이 테스트가 빨개지는가?"**

"아니오"거나 "모르겠다"면 그 단언은 아직 안전망이 아니다.
`.first()` 를 붙이고 싶어지는 순간이 대개 그 신호다.
