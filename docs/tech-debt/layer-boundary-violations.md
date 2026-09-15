# 부채 원장 — 레이어 경계를 건너뛰는 import 72건

> 2026-09-15 개설. **레이어 계약 게이트(import-linter)를 붙이면서 실측한 것.**
> 고치지 않았다. **발견 ≠ 처리** — 이 구간의 목표는 "경계를 세는 기계를 만드는 것"이지
> "경계를 바로잡는 것"이 아니다. 바로잡기를 같이 시작하면 이 단계가 닫히지 않는다.

| 상태 | ⬜ **미착수 (등재만)** — 게이트에 넣지 않았다. 아래 §4 의 판단 근거를 보라 |
|---|---|
| 측정 방법 | `grimp` 로 `app`·`ai_worker` 의 import 그래프를 만들어 **직접 import 간선만** 셌다 (259파일 · 482의존) |
| 측정 시점 | 2026-09-15, 커밋 `3feafe4` 기준 |
| 다시 세는 법 | `uv run python scripts/check_layers.py --verbose` (계약에 들어간 것만) / 전수는 아래 §5 |

---

## 1. 무엇이 규칙인가

`CLAUDE.md` §4.2:

> **Layered Architecture Enforcement**: Router → Service → Repository → Model.
> Skipping layers is strictly prohibited.

이 규칙은 **처음부터 있었고, 한 번도 세어진 적이 없다.** 이 저장소의 전제 한 줄
(`docs/QUALITY_GATES.md` §0)이 그대로 적용된다 — *문서로 "지키자"고 적는 방식은 반증됐다.*

세어 보니 **직접 import 72건**이 이 규칙 또는 그 연장선을 벗어나 있었다.

---

## 2. 실측 (2026-09-15)

### A. 층 건너뛰기 — 36건

| 간선 | 건수 | 무슨 뜻인가 |
|---|---:|---|
| `app.services` → `app.models` | 31 | 서비스가 저장소를 거치지 않고 ORM 모델을 직접 다룬다 |
| `app.workers` → `app.models` | 3 | 배치 워커가 모델을 직접 질의한다 |
| `app.dependencies` → `app.models` | 1 | `security.py` 가 `User` 를 직접 안다 |
| `app.apis.v1.ocr_routers` → `app.models.profiles` | 1 | 라우터가 프로필 소유권을 직접 조회한다 |

> ⚠️ 라우터 → `app.models.accounts` **12건은 위반으로 세지 않았다.**
> `Annotated[User, Depends(get_current_user)]` 는 FastAPI DI 시그니처에 모델 타입이
> 들어갈 수밖에 없다. 이 12건은 계약에 **사유와 함께 예외로 등재**돼 있다
> (`pyproject.toml` 의 `ignore_imports`).

### B. 계층표에 없는 방향 — 6건

| 간선 | 건수 | 무슨 뜻인가 |
|---|---:|---|
| `app.dtos` → `app.models` | 4 | 경계 계약(DTO)이 ORM 모델을 안다 |
| `app.repositories` → `app.dtos` | 2 | 안쪽 계층이 바깥 계약에 의존한다 (방향이 거꾸로다) |

`app.repositories` → `app.dtos` 의 실물:

```
app.repositories.challenge_repository   -> app.dtos.lifestyle_guide
app.repositories.medication_repository  -> app.dtos.medication
```

`CLAUDE.md` §5.4 는 *"Pydantic 검증은 시스템의 가장 바깥에"* 라고 적는다. 이 2건은
그 문장과 정면으로 어긋난다 — **가장 바깥의 계약이 가장 안쪽에서 참조되고 있다.**

### C. `ai_worker` 가 `app` 내부 계층을 직접 쓴다 — 30건

| 간선 | 건수 |
|---|---:|
| `ai_worker` → `app.dtos` | 9 |
| `ai_worker` → `app.repositories` | 7 |
| `ai_worker` → `app.services` | 5 |
| `ai_worker` → `app.models` | 5 |
| `ai_worker` → `app.db` | 4 |

`ai_worker` → `app.core.logger` 1건은 **위반으로 세지 않았다** — 로깅 설정 공유는 의도다.

두 프로세스는 **DB 를 공유하는 별도 배포 단위**다. 지금 구조에서는 워커가
백엔드의 내부 구현(저장소 메서드 시그니처·ORM 모델 필드)에 직접 묶여 있어,
**백엔드 리팩터링이 워커를 조용히 깨뜨릴 수 있다.** 지금은 같은 저장소에 있어
테스트가 잡아 주지만, 배포 단위를 분리하는 순간 그 안전망이 사라진다.

---

## 3. 왜 지금 고치지 않나

세 가지가 전부 참이다:

1. **사용자에게 보이는 결함이 아니다.** 지금 동작은 맞다.
2. **고치면 diff 가 크다.** A 의 31건은 서비스마다 저장소 메서드를 새로 만들어야 하고,
   그건 *새 기능 추가*에 가깝다. `CLAUDE.md` §5.2 — 정돈과 기능 추가를 한 커밋에 섞지 않는다.
3. **이 구간의 목표가 아니다.** 2026-09-15 QA-29 에서 *"거짓 주석 5곳 정정"* 으로 시작한
   단계가 **30곳**으로 불어나 닫히지 않았다(`CLAUDE.md` §6-2). 같은 실패를 반복하지 않는다.

---

## 4. 왜 이걸 게이트에 안 넣었나 (중요)

게이트에 넣으려면 위반 72건을 전부 `ignore_imports` 예외로 등재해야 한다.
그러면 **계약은 초록인데 아무것도 막지 않는다.** 그건 게이트가 아니라 장식이다.

S1.5 에서 같은 판단을 이미 한 번 했다 — 주석 속 식별자 실재 검사는 표본 검출률이
86% 였는데도 저장소 전체에서 오탐 78건이 나와 **게이트에서 뺐다.**
*정밀도 낮은 게이트는 사람이 끄고, 그러면 옆의 정확한 게이트까지 죽는다.*

그래서 계약에는 **지금 위반 0건인 경계만** 넣었다. 실제로 들어간 것:

| 계약 | 예외 |
|---|---|
| 계층 방향 (역방향 금지) | 0 |
| 라우터 → 저장소 직접 호출 금지 | 0 |
| 라우터 → 모델 직접 접근 금지 | 13 (accounts 12 + ocr→profiles 1, 사유 명시) |
| `core`·`utils` 는 상위 계층을 모른다 | 0 |
| 모델은 어떤 상위 계층도 모른다 | 0 |
| `ai_worker` 는 HTTP 계층을 모른다 | 0 |

**이 문서가 나머지 72건의 보관처다.** 게이트가 침묵한다고 해서 깨끗하다는 뜻이 아니라는
사실을, 게이트 자신이 아니라 이 문서가 말한다.

---

## 5. 다시 세는 법

게이트는 계약에 든 것만 본다. 전수는 그래프를 직접 물어야 한다:

```python
# uv run python - (저장소 루트에서, PYTHONPATH=.)
import grimp

graph = grimp.build_graph("app", "ai_worker", cache_dir=None)
for mod in sorted(graph.modules):
    if not mod.startswith("app.services."):
        continue
    for imported in sorted(graph.find_modules_directly_imported_by(mod)):
        if imported.startswith("app.models."):
            print(mod, "->", imported)
```

**이 숫자를 기억하지 말고 다시 세라.** 코드가 변하면 이 문서의 72 는 곧 거짓이 된다.

---

## 6. 해소한다면 순서

우선순위는 *"깨졌을 때 누가 조용히 다치는가"* 로 매긴다.

| 순서 | 대상 | 이유 |
|---|---|---|
| 1 | **B** — `app.repositories` → `app.dtos` (2건) | 가장 적고, 방향이 명백히 거꾸로다. 저장소가 dict/모델을 반환하고 서비스가 DTO 로 감싸면 끝난다 |
| 2 | **C** — `ai_worker` → `app.repositories`·`app.models` (12건) | 배포 단위를 나누는 순간 조용히 깨진다. 지금은 테스트가 가려 준다 |
| 3 | **A** — `app.services` → `app.models` (31건) | 가장 크고 가장 덜 급하다. 저장소 메서드 신설이 필요해 사실상 기능 작업이다 |

각 단계는 해소 직후 `pyproject.toml` 의 계약에 **예외 0으로** 추가하는 것으로 마무리한다.
그래야 되돌아가지 않는다.
