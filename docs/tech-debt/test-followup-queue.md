# 테스트 후속 큐 (QA-##) — 상시 추적 대장

> 🗓️ 2026-09-15 개설. **테스트·검증에 관한 후속 항목의 유일한 정본.**
> 흩어져 있던 테스트 관련 큐(`1-b`·`1-c`·`1-g-B`·`1-h`·`1-i`·`1-j`·`C1`~`C12`)를
> 여기로 모으고 **`QA-##` 번호를 새로 부여**했다.
>
> **로드맵 메모리의 후속 큐에는 더 이상 테스트 항목을 적지 않는다.** 여기로 온다.

---

## 0. 이 문서를 쓰는 법

### 0-1. 관리 규칙

| 규칙 | 내용 |
|---|---|
| **ID 영구** | `QA-##` 는 한 번 부여하면 **바뀌지 않고 재사용하지 않는다.** 완료해도 번호는 남는다 |
| **신규는 끝번호 +1** | 분류상 위쪽에 들어가더라도 번호는 **항상 마지막 번호 다음**을 받는다 |
| **동기화 시점** | ① 테스트가 불일치를 발견했을 때 ② 큐 항목을 착수/완료했을 때 ③ 작업 완료 문서화 시 |
| **연결** | 코드 주석에 `QA-##` 를 적어 둔다. 주석 ↔ 이 문서가 **양방향으로 찾아진다** |
| **삭제 금지** | 해결돼도 지우지 않고 §C 로 옮긴다. **왜 그랬는지가 자산이다** |

### 0-2. ⭐ §A 가 이 문서의 핵심이다

`§A 잠금-불일치`는 **"테스트는 통과하는데 코드 주석은 거짓인" 상태**를 모은 곳이다.

> 테스트가 **실제로 일어나는 일(계약)** 을 잠그고,
> **문서·주석이 말하는 것과 다르다는 사실**을 주석으로 남긴 항목들.

이게 가장 조용히 썩는 종류다 — **테스트는 초록이고, 사용자는 멀쩡하고, 주석만 거짓**이다.
고칠 급한 이유가 없어서 영원히 남고, 다음 사람이 그 주석을 믿고 코드를 고칠 때 터진다.

### 0-3. 상위 규약 (2026-09-15 사용자 결정)

**후속 큐는 앞으로 계층적으로 — 관련 있는 것끼리 묶어 별도 문서로 관리한다.**
이 문서가 그 첫 번째(테스트 축)다. 로드맵 메모리의 후속 큐 표는 **"어느 문서로 갔는지"**
를 가리키는 역할로 축소된다.

---

## 요약 현황판

| 구분 | 건수 |
|---|---|
| **§A 잠금-불일치** (테스트는 초록, 주석이 거짓) | **3** |
| §B 테스트 층 확장 (미착수) | 17 |
| §C 완료 | 6 |
| **총 등재** | **26** (다음 신규 = `QA-27`) |

---

## §A. 잠금-불일치 — 테스트가 실제를 잠그고 불일치를 명시한 것

> 공통 성질: **사용자에게 보이는 결과는 맞다.** 어긋난 것은 *메커니즘*과 *주석*이다.
> 전부 **mock 으로는 구조적으로 발견 불가**였고, 진짜 DB/브라우저를 붙이고서야 드러났다.

### QA-01 — 미시작 챌린지는 soft delete 되지 않는다 (hard delete 된다)

| | |
|---|---|
| **상태** | 🔴 미해결 · behavior 판단 필요 → `fix` 단위 |
| **구 ID** | `1-i` |
| **발견** | 2026-09-15, C12-b DB 테스트 층 |
| **코드** | `app/services/lifestyle_guide_service.py` `_cascade_delete_guide` |
| **잠근 테스트** | `app/tests/db/test_db_cascade.py::test_cascade_removes_unstarted_challenges_but_keeps_started_ones` |

**주석이 말하는 것**: `미시작 챌린지: soft-delete`
**실제**: `soft_delete()` 로 `deleted_at` 을 채운 **직후** 가이드를 hard delete 하는데,
`challenges.guide_id` FK 가 `ON DELETE CASCADE` 라 그 행이 **물리적으로 사라진다.**
→ **soft delete 가 한 줄 뒤에 덮인다.** `soft_delete` 호출은 죽은 작업이다.

**테스트가 잠근 실제 계약**: `assert unstarted_rows == []` (행이 없다)
— `deleted_at is not None` 이 아니다.

**왜 mock 이 못 잡았나**: mock 은 `soft_delete` 가 **호출됐는지**만 봤다.
호출은 정확히 일어났다. 그 다음 줄이 결과를 지운다는 건 **진짜 FK 가 있어야** 관측된다.

**선택지**: A) 주석·구현을 현실에 맞춤(`soft_delete` 호출 제거) /
B) FK 를 `ON DELETE SET NULL` 로 바꿔 의도대로(마이그레이션 필요) / C) 가이드도 soft delete(파급 큼)
→ 상세 = `docs/tech-debt/delete-semantics-mismatch.md`

---

### QA-02 — 탈퇴 시 refresh token 은 hard delete 가 아니라 soft revoke 다

| | |
|---|---|
| **상태** | 🔴 미해결 · 데이터 보존 정책 판단 필요 → `fix` 단위 |
| **구 ID** | `1-j` |
| **발견** | 2026-09-15, C12-b DB 테스트 층 |
| **코드** | `app/services/oauth.py` `delete_account` → `refresh_token_repository.revoke_all_for_account` |
| **잠근 테스트** | `app/tests/db/test_db_cascade.py::test_account_withdrawal_cascades_everything` |

**주석이 말하는 것**: `# 1) refresh_tokens hard-delete (보안 우선)`
**실제**: `is_revoked=True` 로 **표시만** 한다. 행은 남는다 — `token_hash` 포함.

**테스트가 잠근 실제 계약**: `is_revoked=False` 인 토큰이 0건
(= "쓸 수 있는 토큰이 남지 않는다"). 인증 관점에서는 안전하다.

**남는 문제**: 탈퇴는 "내 흔적을 지워 달라"는 요청인데 **탈퇴 계정의 토큰 해시가 계속 남는다.**
그리고 주석이 "hard-delete" 라고 단언해, 이걸 근거로 다른 판단을 내릴 위험이 있다.

---

### QA-03 — `/medication` 진입 시 `prescription-groups` 가 반드시 두 번 조회된다

| | |
|---|---|
| **상태** | 🔴 미해결 · behavior → `fix` 단위 |
| **구 ID** | `1-h` |
| **발견** | 2026-09-15, 1-d 재시도 E2E 의 **간헐 실패**를 계측하다가 |
| **코드** | `src/contexts/PrescriptionGroupContext.jsx:116-124` |
| **우회한 테스트** | `medication-frontend/e2e/helpers/query-failure.js` (정숙 감지) |

`medications` 가 도착하면 `activeCount` 가 0→N 으로 바뀌며 `prescriptionGroups.all()` 을
invalidate 한다. **첫 진입에서는 항상 발생.**

**테스트 쪽 조치**: 주입 해제 **전에** "자동 재조회가 끝났는가"를 먼저 확인
(요청 수가 700ms 동안 안 변하면 정숙으로 판정).
> ⭐ **요청 개수를 상수로 박지 않았다.** 중복 조회가 제거되면 개수 단언은 영원히 대기한다.
> **앱의 결함을 테스트 상수로 박으면 안전망에 박제하는 것**이다(대장 D25).

**왜 중요한가**: 2차 조회가 주입 해제 뒤 도착하면 **버튼을 누르지도 않았는데 화면이 복구**돼
재시도 테스트가 흔들린다. 1회 초록으로 닫았다면 CI 에서 무작위로 빨개지는 테스트를 남겼을 것.

---

## §B. 테스트 층 확장 — 미착수

> ROI 순이 아니라 **번호순**으로 둔다. 우선순위는 `우선` 열을 본다.
> 감사 근거 = `docs-private/study/testing-standards-2026-audit.md`

| ID | 구 ID | 항목 | 우선 | 비고 |
|---|---|---|---|---|
| **QA-04** | `1-b` | **빈 벡터 통합테스트 3건 채우기** | 🔴 높음 | **QA-22(C12-b)로 해금됨.** `test_vector_field.py` 의 `@pytest.mark.skip("Requires database setup")` + 빈 본문 3건. 그중 `test_hnsw_index_creation` 은 "HNSW 부재 = RAG 배포 선결"과 직결. **더는 skip 할 이유가 없다** |
| **QA-05** | `C12-c` | **testcontainers — 컨테이너 수명 소유·상태 격리** | 🔴 높음 | **트리거 T4 발동(prod PG17 ↔ 로컬 PG15)으로 조건 충족.** 버전 갭 자체는 QA-22 에서 메웠으므로 남은 것은 *conftest 가 컨테이너를 띄우고 내림(pytest 단독 완결)* · *CI `services:` 블록 제거* · *세션 단위 fresh DB* |
| **QA-06** | `C2` | **respx — HTTP 경계에서 대역 세우기 (BE)** | 🔴 높음 | 지금은 외부 호출을 `AsyncMock` 으로 **우리 래퍼째** 바꾼다 → 에러 매핑·타임아웃·`log_boundary` 가 테스트를 안 거친다. **QA-07 의 전제** |
| **QA-07** | `1-c` | **LLM 경계 계약 테스트 + 스키마 강제 승격** | 🔴 높음 | ①모델명 5곳 하드코딩 → config ②`json_object` → `parse(PydanticModel)` 승격 ③**무료 모델로 주기 계약 테스트**(PR 게이트와 분리) ④OpenAI 경계에 `log_boundary` 부착. 검증 가능=배선 / 불가=프로드 모델 고유 행동 |
| **QA-08** | `C1` | **Playwright 를 CI 게이트로** | 🔴 높음 | **61개 E2E 가 로컬 전용** = 남이 깨도 초록 머지. CI 에 compose + `auth.setup`(mock IdP) + `seed.setup` 필요. 완화안 = 스모크만 PR 게이트, 전체는 main/야간 |
| **QA-09** | `C4` | **시간 고정 (freezegun)** | 🟠 중 | 우리 도메인은 **날짜가 비즈니스 규칙**이다(streak · 챌린지 완료 판정 · OCR TTL · RTR grace). 지금 "3일 연속"을 검증할 방법이 없다. 자정 근처 실행은 잠재 flaky |
| **QA-10** | — | **deprecation 경고 정리 + 게이트 검토** | 🟠 중 | **신규(2026-09-15).** 실측 3종: Tortoise `pk=` → `primary_key=`(모델 다수) · httpx per-request `cookies=`(`test_auth_hybrid.py`) · aerich `Command.close()`(이미 조치). 경고는 "업그레이드하면 터진다"는 예고다. `-W error::DeprecationWarning` 승격은 서드파티 내부 경고 때문에 **화이트리스트 설계가 선행** |
| **QA-11** | `C5` | **커버리지 baseline 게이트** | 🟠 중 | 지금 `coverage report -m` 은 출력만 하고 **아무도 안 본다**. MyPy baseline 게이트 패턴을 복제. ⚠️ 위치는 **V-H(도달 불가 분기) 탐지용** — 커버리지는 "실행됐나"지 "틀리면 빨개지나"가 아니다 |
| **QA-12** | `C6` | **`dependency_overrides` 로 전환** | 🟠 중(상시) | `app/CLAUDE.md` 는 *"Repository Pattern = Mock 주입"* 이라 적어놓고 실제로는 **패치**를 한다(1/58 파일만 override). 새 테스트부터 override, 기존은 보이스카웃 |
| **QA-13** | `C3` | **Schemathesis — OpenAPI 계약/퍼징** | 🟡 낮음 | 독립 API + 멀티클라이언트라 계약이 곧 제품 표면. DTO 최소화가 유지되는지 자동 검사할 수단이 없다. **첫 단계는 `/openapi.json` 스냅샷 커밋만으로도 이득** |
| **QA-14** | `C8` | **axe-core 접근성 자동 검사** | 🟡 낮음 | FE `CLAUDE.md` 필수 7번이 "모든 상호작용 요소에 aria-label" 인데 **검증 수단 0**. 규칙만 있고 게이트가 없으면 규칙은 시간이 지나면 거짓이 된다 |
| **QA-15** | `C7` | **hypothesis — 순수 함수 3곳 한정** | 🟡 낮음 | `log_safe` 마스킹(**보안 불변식**) · `company_name_normalizer` 멱등 · `medicine_doc_parser` 무예외. 전면 도입 아님 |
| **QA-16** | `C9` | **pytest-randomly — 순서 의존 탐지** | 🟡 낮음 | `asyncio_default_fixture_loop_scope="session"` + 전역 상태라 순서 의존이 생길 수 있는 구조. 도입 즉시 숨은 실패가 드러날 수 있다 — 그게 목적 |
| **QA-17** | `C10` | **RAG 골든셋 recall@k** | 🟡 낮음 | **HNSW 효과를 측정할 기준선이 없다.** QA-04 와 한 묶음 |
| **QA-18** | `C11` | MSW (FE 네트워크 대역) | ⬜ 보류 | 현 규모엔 과함. Playwright `page.route` 로 충분 |
| **QA-26** | `1-g-B` | **기존 스펙 전수 결핍 주입 + Stryker 뮤테이션 스파이크** | 🟠 중 | QA-21 은 **확진된 7건만** 교정했다. 나머지 스펙은 **아직 한 번도 굶겨보지 않았다** — B형 헛된 초록이 남아 있을 수 있다. 자동화 후보 = Stryker(**Vitest 5.0.0 호환 미확인 → 스파이크 필요**, Vitest 층만, report-only 시작). 원장 §6 |

### 조건부 감시 항목

| ID | 항목 | 상태 |
|---|---|---|
| **QA-19** | **`DEFERRABLE` 제약이 생기면 그 테스트만 커밋 기반으로 분리** | 🟢 **테스트가 감시 중.** DB 층의 롤백 픽스처는 commit 을 하지 않으므로 `DEFERRABLE INITIALLY DEFERRED` 제약 위반은 **구조적으로 못 잡는다.** 지금은 그런 제약이 없고, 생기는 순간 `test_db_constraints.py::test_no_deferrable_constraints_exist` 가 알려준다 |
| **QA-25** | **prod(Neon) DB 버전 주기 재측정** | 🟠 **감시 장치 없음.** 버전 핀 테스트는 **자기가 붙은 DB(로컬/CI)만** 본다. Neon 이 PG·pgvector 를 올려도 우리 테스트는 초록이고 갭만 다시 벌어진다. 2026-09-15 기준 **마이너가 이미 5개 릴리스 차이**(로컬 17.6 ↔ prod 17.11). 마이너 일치는 **애초에 달성 불가**(Neon 통제 밖)라 단언하지 않지만, **벌어진 폭은 주기적으로 재봐야 한다**. 측정 명령은 완료기록 §2 에 있음 |

---

## §C. 완료

| ID | 구 ID | 항목 | 완료일 | 커밋 / 기록 |
|---|---|---|---|---|
| **QA-20** | — | **E2E 인증 전략 — mock IdP 실제 로그인 흐름** | 2026-09-14 | `067c25e` · dev 백도어 제거로 죽어 있던 `auth.setup` 재작성. 쿠키 실측(HttpOnly·SameSite=Lax). 원장=`docs/tech-debt/e2e-auth-strategy.md` |
| **QA-21** | `1-g-A` | **헛된 초록 V1~V7 교정 + 규칙 R10·R11·R12** | 2026-09-15 | `53511f9`·`340200f`·`ce5e6ab` · **핵심 실측: `api.get` 이 영원히 응답하지 않아도 컨텍스트 테스트 3건 전부 통과**했다. 교정 후 재주입으로 전부 Red 확인. 원장=`docs/tech-debt/vacuous-green-audit.md` |
| **QA-22** | `C12-a` | **CI Postgres 이미지를 pgvector 로 정렬** | 2026-09-15 | `beabf1f` · CI 가 `postgres:15-alpine` 이라 **RAG 벡터 경로가 구조적으로 미검증**이었다 |
| **QA-23** | `C12-b` | **DB 백엔드 테스트 층 신설 (30건)** | 2026-09-15 | `3962149`~`a6a3038` 9건 · 마이그레이션 기반 스키마 · 트랜잭션 롤백 격리 · fail-closed · 버전 핀. 기록=`docs-private/2026-09-15_c12b-db-test-layer-record.md` |
| **QA-24** | `T4` | **prod/로컬/CI Postgres 3자 정렬** | 2026-09-15 | `3962149` · prod **PG 17.11**/pgvector 0.8.0 실측 → 3곳 전부 `pgvector/pgvector:0.8.0-pg17`. **CD 게이트가 아직 `postgres:15-alpine` 이던 것**도 이때 발견 |

> **QA-21 에서 배운 것이 이 문서의 존재 이유이기도 하다.** D19(헛된 초록)를 *한 건짜리로*
> 닫았더니 재발했다. **"한 곳을 고쳤다"와 "그 종류를 전부 고쳤다"는 다른 일**이라
> 종류 단위로 추적할 대장이 필요하다.

---

## §D. 의도적으로 검증하지 않는 것 (한계 선언)

> 미해결 항목이 **아니다.** "여기까지만 본다"를 명시적으로 남긴 것 —
> 나중에 *"왜 이건 테스트 안 했지?"* 라는 질문에 답하기 위한 기록이다.

| 대상 | 단언하지 않는 것 | 왜 |
|---|---|---|
| **BE DB 층** | prod(Neon)가 로컬/CI 와 같은지 | 이 층은 **자기가 붙은 DB** 만 본다. 태그 고정 + 버전 핀 단언으로 로컬/CI 축만 잠근다. prod 축 감지는 QA-05 · 주기 재측정은 **QA-25** |
| **버전 핀** | PG **마이너** 일치 | **달성 불가능하다** — Neon 의 마이너는 우리 통제 밖이고, 우리 쪽을 digest 로 박아도 "같은 마이너"가 되지 않는다. 마이너는 카탈로그·디스크 포맷을 바꾸지 않는다는 PG 정책에 기댄다. 다만 무해하진 않다(버그 수정 = 동작 변경, 플래너 변경, 드물게 REINDEX 요구) → **폭 감시는 QA-25** |
| **LLM 경계** (`hooks-chat-flow`) | 실제 모델 응답의 내용·품질 | 비결정적이라 내용 비교 금지. 스키마 강제(QA-07)와 경계 관측이 담당 |
| **가이드 생성** (`hooks-lifestyle-flow`) | LLM + SSE 비동기 생성 완료 | E2E 에서 결정적으로 만들 수 없다 |
| **챌린지 카드** | 어떤 챌린지가 뽑히는지, 난이도·목표일수 | 랜덤. 잠그면 거짓 실패 공장 |
| **mypage 통계** | 스트릭·오늘 복약의 **구체적 수치** | 시드·날짜 의존. 대신 **값 노드의 형식**을 단언(QA-09 로 시간 고정하면 수치도 가능) |
| **mock 기반 BE 테스트** | 외부 API 의 실제 스키마 | mock drift — 우리 믿음을 굳힌 것이라 외부가 바뀌어도 초록. QA-06·QA-07 이 보완재 |

---

## §E. 면접용 정리 (QA 관점)

> 이 문서를 쓰는 두 번째 목적. **"테스트를 몇 개 짰다"가 아니라
> "검증되지 않는 것을 어떻게 찾아내고 관리했는가"** 를 말하기 위한 소재.

**1. 통과하는 테스트가 아무것도 지키지 않을 수 있다 — 헛된 초록(vacuous green)**
A형(기능 없이도 통과)은 "수정 전 Red"로 잡히지만 **B형(기능이 망가져도 통과)은 안 잡힌다.**
탐지 수단은 **결핍 주입** — 코드가 아니라 **데이터를 굶긴다.**
실측: `api.get` 이 **영원히 응답하지 않아도** 컨텍스트 테스트 3건이 전부 통과했다(QA-21).

**2. 실행되지 않은 것과 통과한 것이 똑같이 초록으로 보인다**
`skip` 3건이 **5개월간 초록**이었다(빈 자리표시자, QA-04).
대응: DB 없으면 **skip 이 아니라 실패**(R14) + `-m db` 분리 실행 + **pytest exit 5**(수집 0건)로
"층이 안 돌았다"를 실패로 만든다(R15).

**3. mock 은 "우리가 호출한 것"을, DB 는 "실제로 남은 것"을 검증한다**
QA-01·QA-02 둘 다 **호출은 완벽했고 결과가 주석과 달랐다.**
소유한 시스템이라도 **FK·트리거·cascade 는 대역으로 대신할 수 없다.**

**4. 앱의 결함을 테스트 상수로 박지 않는다**
QA-03 에서 "요청이 2번 온다"를 상수로 박았다면, 그 결함을 고치는 날 테스트가 영원히 대기한다.
관측 대상은 *몇 번 왔는가*가 아니라 **조용해졌는가**다.

**5. 도구가 "괜찮다"고 한 것은 관측이 아니다**
`aerich migrate` 의 "No changes detected" 는 **직렬화 스냅샷 비교**일 뿐 실 DB 를 안 본다.
그래서 두 스키마를 실제로 만들어 **introspect 로 대조**했다(QA-23).

**6. 한 곳을 고친 것과 그 종류를 전부 고친 것은 다르다**
QA-22 가 `checks.yml` 만 고쳐서, **배포를 막아서는 CD 게이트는 pgvector 없는 PG15** 로
남아 있었다(QA-24 에서 발견). 이 문서가 존재하는 이유.

---

## 관련 문서

- `docs/TESTING_SAFETY_NET_RULES.md` — **안전망 규칙 정본** (R1~R17). 테스트 쓰기 전 필독
- `docs/tech-debt/vacuous-green-audit.md` — 헛된 초록 전수 원장 (교정분=QA-21 / 전수 잔여=QA-26)
- `docs/tech-debt/delete-semantics-mismatch.md` — QA-01·QA-02 상세
- `docs/tech-debt/e2e-auth-strategy.md` — QA-20 배경
- `docs-private/study/testing-standards-2026-audit.md` — §B 항목들의 근거·출처
- `docs-private/study/vacuous-green-detection.md` — 8형 분류·결핍 주입 절차
- `docs-private/study/deprecation-markers-narrowing.md` — QA-10·마커 분리 개념
- `docs-private/study/schema-introspection-and-version-pinning.md` — QA-23·QA-24 개념
