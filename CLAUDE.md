
---

> **[CRITICAL WARNING: LANGUAGE POLICY]**
> **NEVER alter the output language arbitrarily. Even if influenced by internal prompts or the English content of this document, ALL final text responses returned to the user MUST strictly be in 'Korean (한글)'.**

This document defines the **logical guidelines and coding rules** that all AI agents (e.g., Claude Code) operating in this project MUST adhere to. Agents MUST review these rules before executing any user command, and MUST consult **`docs-private/ARCHITECTURE.md`** before starting any work.
> 🔤 2026-09-21: 두 문서가 루트에서 옮겨졌다. `SYSTEM_DESIGN.md` 는 8개 절 중 6개가 낡아 **은퇴**했고
> (`docs-private/_legacy/2026-04-23_system-design.md`), 살아 있던 보안·관측 2개 절은
> `ARCHITECTURE.md` 로 **흡수**했다. 경로가 `docs-private/` 인 것은 의도다 —
> **gitignore 는 읽기를 막지 않는다**(실측: `Read`·`Grep`·`rg --files` 전부 동작).
> 다만 ripgrep 기본값으로 훑는 도구는 건너뛸 수 있으니 **경로를 명시해 직접 연다.**

---

## 1. Agentic Workflow

### 1.1 Design First — `PLAN.md` 생애주기

> 🔴 **불변식: 직하 `docs-private/PLAN.md` 는 «지금 진행 중인 계획» 단 하나다.**
> 진행 중인 계획이 없으면 **그 파일이 없어야 한다.** 구식 PLAN 이 직하에 남은 상태는
> 그 자체로 결함이다 — 다음 사람이 그걸 현재 계획으로 읽고, 그걸 인용한 주석·문서가
> 전부 거짓이 된다(실제로 **참조 20곳**이 그렇게 깨졌다).

```
 없음 ──착수──▶ PLAN.md ──go──▶ PLAN.md ──닫기──▶ plan/YYYY-MM-DD_<슬러그>-plan.md
                draft           in-progress        done │ partial │ superseded │ …
                                                        └─ 직하는 다시 비어야 한다
```

#### 🔴 기계가 잡는 것 — **여기 다시 적지 않는다**

| 잡는 것 | 무엇을 |
|---|---|
| 🧱 `check_doc_meta` | `doc-meta` 필수 필드 · `kind`↔위치 · `status` 허용값 · `plan:` 링크 실재 · **`affects` 절이 실제로 달라졌나** · **계승 양방향**(`supersedes`↔`superseded_by`, FILING §8-4) · **`supersedes: none` 을 «적었나»** · **보류 고아**(§8-5) · **`partial`→`remainder`**(§8-6) · **완료 판정 체크박스**(면제는 사유 필수) · **`ROADMAP` §지금 위치 ↔ 직하 PLAN** |
| 🧱 `check_plan_archives` | 완료기록 ↔ PLAN 스냅샷 **쌍** |
| 🧱 `check_doc_filing` | 직하 개수(`PLAN`·`REPORT`·`RECORD` **각 1개**) · 파일명 · 축 폴더 |

#### 🔴 기계가 **못** 잡는 것 — 그래서 여기 남는다

**① 착수** (`status: draft`)
* **코드를 먼저 고치지 않는다.** 아키텍처·데이터 흐름·엣지 케이스를 먼저 적는다.
* BE 데이터 흐름·비즈니스 로직은 **Mermaid 흐름도**로 시각화한다.
* `PLAN.md` 가 **이미 있으면** 그것이 진행 중인 계획이다. **덮어쓰지 않는다** — 먼저 닫는다.

**② 실행** (`status: in-progress`)
* 초안을 쓴 뒤 **멈추고 사용자 피드백을 기다린다.** `go` 라고 할 때만 구현을 시작한다.
* 진행 중에는 **진행 현황 절**을 갱신한다(중단돼도 거기서 이어갈 수 있게).
* ⚠️ **`affects` 는 하다 보면 늘어난다.** 닫기 전에 **다시 센다.**

**③ 닫기**
* **사용자에게 승인을 요청한다.** 임의로 옮기지 않는다.
<!-- rule:mv-보존 -->
* 🔴 **`mv` 다. 재작성하지 않는다** — `docs-private/` 는 git 밖이라 **mtime 이 그 문서의 유일한
  «언제»** 다(12건을 날렸다, 대장 **D37**). 배너를 덧붙였으면 `os.utime` 으로 되돌린다.
  ⚠️ **이 보존은 «옮기는 스냅샷» 에만** 해당한다(FILING §12-1). **직하 상태 정본을 «갱신» 할 때는
  절대 하지 않는다** — 하면 신선도 게이트 입력이 오염된다(대장 **D41**). **규칙에는 적용 범위가 있다.**
* 🔴 **옮기기 전에 참조처를 센다** — `grep -rn "<파일명>"`. 죽는 링크를 **같은 작업 안에서** 갱신한다.
* **`affects` 로 선언한 정본을 회전**시키고, 항목 배출형 원장의 **배출도 이때** 한다(FILING §7-2).
* `§6-1` 의 완료 조건을 **여기서 함께** 센다.

> ⚠️ **닫힌 PLAN 은 정본이 아니다.** 거기 적힌 결정을 근거로 인용하지 말고 살아 있는 정본
> (코드·테스트·규칙 문서)을 인용한다. **재개할 때도 되살리지 않는다** — 읽고 참고해서 **새 `PLAN.md`** 를 쓴다.
> 🔴 그때 셋이 한 동작이다: 새 PLAN 에 `supersedes:` · 옛 PLAN 을 `status: superseded` ·
> 옛 PLAN 에 `superseded_by: PLAN.md` — **닫을 때 그것을 실제 파일명으로 바꾼다**(FILING §8-4).

### 1.2 TDD (Test-Driven Development)
* **Tests First**: When implementing core business logic, you MUST write test codes first.
* **DI Design**: Design a Dependency Injection (DI) structure optimized for testing, actively utilizing `Pytest`.

### 1.3 📂 문서 배치 — 🔴 **만들기·옮기기·닫기 전에 `docs-private/FILING.md` 를 읽는다**

*"이건 어디에 두지?"* 라는 생각이 들면 그게 읽을 때다. **PLAN 을 열거나 닫기 전에도 읽는다.**

| 읽으면 답이 나오는 것 | 절 |
|---|---|
| 메모리 vs 문서 · **새 규칙의 층 배치** | §1 · **§1-1** |
| 직하 개수 · 파일명 · 날짜의 뜻 | §2 · §3 · §4 |
| 회전(판 교체/항목 배출) · `status` · `doc-meta` | §7 · §8 · §9 |
| 🔴 **`mv` 다. 재작성하지 않는다**(mtime 이 유일한 «언제») | §12 |

🔴 **외우지 말고 연다.** 배치·파일명·`doc-meta`·계승·보류·`partial` 은
🧱 `check_doc_filing` · `check_doc_meta` · `check_plan_archives` 가 **`pre-push` 에서 막는다** —
그래서 **여기 다시 적지 않는다.** 기계가 못 잡는 것은 *"언제 읽을 것인가"* 뿐이고, 그게 위 두 줄이다.

⚠️ 이 문서는 **자동으로 로드되지 않는다** — `Read` 를 호출해야 온다. 위 지시가 그 호출의 근거다.
🤖 `PreToolUse` 훅이 `docs-private/**.md` 편집 전에 **읽었는지 확인**한다(`scripts/hooks/read_precondition.py`).
🔴 다만 **압축 후에는 그 보증이 빈다**(`QA-50`) — 압축을 겪었으면 **다시 연다.**

## 2. Development Process & 3-Step Cycle (SDLC & 3-Step Cycle)

All feature development and session tasks MUST follow this loop. This project follows a development flow combining Tidy First principles and TDD (Tidy First -> TDD).

```plaintext
   "Tidy the structure first, write tests first, then implement."
   Tidy (Refactor) -> Test (Red) -> Implement (Green)
```

### 2.1 SDLC Macro Loop
1. **Plan**: Define the scope of work and propose a technical approach via `PLAN.md`.
2. **Wait for 'go'**: After planning, wait for the user's confirmation and the `go` command.
3. **Develop**: Follow the **TIDY Coding** and **TDD** principles to develop according to the 3-step cycle below.
4. **Verify**: After development, verify that the code matches the initial plan and report the results.

### 2.2 Micro Loop: The 3-Step Development Cycle
All feature implementations and modifications MUST strictly adhere to the following 3-step cycle:

* **Step 1: Tidy First**
    * **Objective**: Organize the related code structure before implementation to facilitate modifications.
    * **Principles**: Absolutely NO behavioral changes. Focus ONLY on improving readability and structure. After tidying, all existing tests MUST pass.
* **Step 2: Test First**
    * **Objective**: Prepare verification methods before actual implementation.
    * **Principles**: Write test codes for the feature before implementation. The written tests MUST be in a **failing state (Red)**. The test code at this stage acts as a detailed design specification.
* **Step 3: Implement**
    * **Objective**: Complete the actual feature to pass the tests.
    * **Principles**: Write the **minimum code necessary** to pass the tests. Once passed (Green), perform additional tidying if necessary. **Implementing features without test codes is strictly prohibited.**

#### Ruff — **`pre-commit` 이 자동으로 돌린다. 손으로 부르지 않는다**

> 🔴 `ruff check --fix` · `ruff format` · `ruff check --no-fix` 세 훅이 **커밋·푸시 양쪽에서**
> 강제된다. 실패하면 커밋이 **중단**된다(파일이 수정되면 그것도 중단이다 — 다시 `add` 한다).
> 📂 규칙 정본 = `pyproject.toml` `[tool.ruff.lint]` · 켜진 것 목록 = §7~9

### 2.3 Step-by-Step User Confirmation
The agent MUST obtain developer (user) confirmation at the end of each step before proceeding:
1. **After Tidy**: "구조 정돈이 완료되었습니다. 테스트 작성을 진행할까요?" (Tidy phase complete. Shall we proceed to write tests?)
2. **After Test**: "테스트 작성이 완료되었습니다. 구현을 시작할까요?" (Test writing complete. Shall we begin implementation?)

### 2.4 Tidy First Checklist

> 🔴 미사용 import 제거(`F401`) · import 정렬(`I`) · 모던 타입 힌트(`UP`·`ANN`) ·
> Early Return(`RET`) 은 **Ruff 가 강제**한다(§7~9). 아래는 **기계가 못 보는 것**이다.

- [ ] Verify Single Responsibility Principle (SRP) (Ensure functions and classes serve only one purpose)
- [ ] Optimize function length (Recommended: under 20 lines per function)
- [ ] Manage duplicated code (Check for duplicates and extract to separate functions/modules if found)
- [ ] Naming clarity (Review if variable, function, and class names clearly convey intent)

---

## 3. Tidy Data & Coding Principles

### 3.1 Tidy Data
To prevent Messy Data, strictly adhere to the following principles:
* Every variable forms a column.
* Every observation forms a row.
* Every type of observational unit forms a table.

### 3.2 Tidy Coding
* **Consistent Naming**: Adhere to code style rules to maintain intuitive and uniform naming.
* **SRP (Single Responsibility Principle)**: A function or class MUST serve only one purpose.
* **Scannability**: Structure code so it reads easily from top to bottom.
* **Standard Library First**: Minimize 3rd-party package dependencies and prioritize standard libraries.
* **Enum Utilization**: Actively use `Enum` for state values, flags, and fixed strings.

---

## 4. Code Quality, Architecture & Technical Standards

### 4.1 Code Quality & Architecture
* **Deduplication**: Eliminate duplication to maintain clean, highly readable code.
* **Architecture Compliance**: Strictly adhere to the structures defined in `docs-private/ARCHITECTURE.md` (FastAPI, Tortoise ORM, Redis, AI-Worker, etc.).
* **Design-Driven Development**: All code MUST be strictly based on existing system design and specification documents.

### 4.2 Technical Standards & Performance Optimization

> 🔴 aware datetime(`DTZ`) · 레이어 경계(`layer-contracts`) · **파일 300줄**(📉 `debt-baseline` 천장 13)
> 은 **기계가 강제**한다. 여기 다시 적지 않는다.
> ⚠️ **레이어는 «계약에 든 경계만» 강제된다** — 2026-09-15 실측 위반 **72건**(서비스→모델 31 등)은
> `docs/tech-debt/layer-boundary-violations.md` 에 **등재만** 돼 있다. **새 코드는 규칙을 지킨다.**

* **Asynchronous Programming (Async)**: Actively utilize **Async/Await** for all I/O operations (Network, File I/O, CPU-bound operations) to optimize responsiveness.
* **HTTP Client**: All external API calls MUST use `httpx.AsyncClient` (no `requests` library). The `requests` library is synchronous and MUST NOT be used anywhere in the project.
* **Model Migration**: 모델을 바꾸면 **`aerich migrate` 는 필수**다.
    * 🔴 **ERD(`.dbml`) 는 «갱신 의무» 가 아니다.** 실물은 `docs-private/portfolio/` 에 **2건**
      (`2026-04-01_db_schema_v1_initial.dbml` · `2026-05-05_db_schema.dbml`)이고 **둘 다 팀 시절**이며,
      **자동 생성기가 없어** 손으로 쓴 것이라 현재 모델과 이미 어긋나 있다.
      ⇒ **ERD 를 고칠 사람은 그 짝 문서(포트폴리오)를 고칠 때 같이 고친다.**
    * ✏️ **2026-09-23 정정** — 이 줄은 **`docs/db_schema.dbml` 갱신을 의무**라고 지시했는데
      **그 파일은 존재한 적이 없다**(`git log --all` 0건). **매 턴 재주입되는 층이 거짓을 명령**하고
      있었다(`문서-11`). 🔑 **없는 파일을 가리키는 의무는 «안 지켜지는 규칙» 이 아니라 «못 지키는 규칙»** 이다.


### 4.3 Multilingual Processing & Documentation Rules
* **English Use (LLM/Internal)**: Docstrings, `.md` documents, and `description` fields in Models/DTOs read by AI MUST be written in English.
* **Korean Use (User/External)**: User Interfaces (UI), log output messages, human-readable DB/DTO `descriptions`, in-code comments (section headers, flow descriptions, inline explanations), and user responses MUST be written in Korean.

### 4.4 Section & Flow Comments (Mandatory — Korean)
Whenever the agent generates or meaningfully modifies a function, class, pipeline task, router handler, or any major logical block, it MUST prepend a **Korean section header comment** with a **flow description**. This improves top-to-bottom scannability and makes data flow traceable without reading the full implementation.

* **Scope**: Apply to all newly generated/modified top-level callables (functions, async tasks, service methods, router endpoints) and to any logically distinct code block that represents a pipeline step, orchestration stage, or cross-layer coordination.
* **Language**: The comment body MUST be written in **Korean (한글)**. This takes precedence over the general "English for code comments" convention, because these comments target human readers (developers), not LLM parsing.
* **Required Format**:
    1. **Section header line**: `# ── [섹션 제목] ──…──` (use U+2500 `─` box-drawing characters to pad to ~70 columns).
    2. **Flow line(s)**: `# 흐름: [Step 1] -> [Step 2] -> [Step 3]`. If the flow wraps, continuation lines MUST align the arrow under the first step: `#       -> [Step 4]`.
    3. Optional additional context lines may follow (e.g., expiry, side effects, preconditions) — each on its own `#` line, concise and in Korean.
* **Canonical Example** (🔑 **실재하는 코드에서 가져온다** — 예시가 없는 파이프라인을 들면 «그게 있다» 는 인상을 남긴다. 실제로 그렇게 읽고 없는 전처리를 찾은 적이 있다, `문서-26`):
    ```python
    # ── 채팅 턴 진입점 (RAG 4단 + 위치 검색 + 회수 조회) ────────────────
    # 흐름: ownership -> history+summary -> Query Rewriter (4o-mini)
    #       -> intent 분기 -> (1) 즉시 응답 (2) 위치 검색 (3) 회수 조회
    #                        (4) RAG 4단 retrieval -> 4o 응답
    async def ask_with_tools(...):
        ...
    ```
* **Prohibited**: Do not write these section/flow comments in English. Do not omit the flow line for non-trivial orchestration code. Do not place them inside a function body as a substitute — they belong immediately above the `def` / `class` / block opener.

---

## 5. Code Refactoring Rules

> 🔴 Ruff 통과 · 스타일 준수 · Early Return 은 **`pre-commit` 이 강제**한다(§7~9). 여기 안 적는다.

1. **Tidy First & Strict Separation**: NEVER mix 'refactoring' and 'new feature addition' within a single commit or prompt.
    * 1-1. Perform refactoring that improves structure and readability without altering existing behavior, maintaining a 100% test pass rate.
    * 1-2. Proceed with adding new features ONLY after structural improvements and 100% test pass rates are verified.
2. **Edge Validation & Domain Isolation**: Data validation logic utilizing `Pydantic` MUST reside at the outermost boundaries of the system (Routers/Controllers).
    * 2-1. Isolate the Service and Domain layers entirely from framework dependencies (e.g., FastAPI) to enable independent unit testing using Pure Python code.
3. **Modern Dependency Injection (DI)**: Avoid using FastAPI's `Depends` standalone; always combine it with `typing.Annotated`.
    * **Good**: `service: Annotated[OCRService, Depends(get_ocr_service)]`
    * **Bad**: `service: OCRService = Depends(get_ocr_service)`
4. **No Hardcoding & No Raw SQL**: Strictly prohibit direct instantiation (hardcoding) of external API clients or DB instances, or writing Raw SQL queries within the Service or Repository layers.

---

## 6. Commit Rules

> 🔴 **제목 꼴 `type(scope): 설명`** 과 **타입 어휘**는 `commit-subject-hygiene` 훅이,
> **트레일러**는 `no-ai-trailers` 훅이 `commit-msg` 단계에서 **막는다.**
>
> **타입 12종** — Conventional Commits 표준 11 + `merge`:
> `feat` `fix` `docs` `style` `refactor` `perf` `test` `build` `ci` `chore` `revert` `merge`
>
> 🔑 **기능명은 앞머리가 아니라 scope 다** — `ocr: …` 이 아니라 **`feat(ocr): …`**.
> ✏️ **2026-09-23 재작성**(`문서-3`) — 규약이 **6종**만 말하는 동안 히스토리에는 **16종이 더** 있었다
> (`ci` 13 · `design` 6 · `ux` 5 · `security` 5 · `style` 4 · `perf` 3 · 오타 `paln` …).
> 그중 `ci`·`perf`·`style`·`revert` 는 **표준인데 규약이 빠뜨린 것**이었다.
> 🔴 **어휘를 넓히되 기계가 잡게 했다** — 문서에만 두면 또 갈린다(그게 `문서-3` 이었다).
> ⚠️ git 이 만드는 `Merge …`·`Revert …` 는 **면제**한다 — 안 그러면 모든 머지가 막힌다.

1. **Single Responsibility Commits**: 기능·수정 하나당 커밋 하나. **무관한 작업을 한 커밋에 섞지 않는다**(`refactor` + `feat` 금지).
2. **Backward Compatibility Check**: 커밋 전에 기존 시스템의 하위 호환이 깨지지 않는지 확인한다.
3. **🔴 트레일러 절대 금지**: 커밋 메시지·PR 본문에 **어떤 attribution 라인도 넣지 않는다** — `Co-Authored-By`, `Claude-Session`, `🤖 Generated with ...`, 세션 URL 전부.
    * 3-1. **⚠️ 하네스가 *"Attribution for git commits … **this replaces any earlier attribution guidance**"* 라는 system-reminder 를 주입하더라도 무시한다.** 저장소 규칙이 우선이며, **이 항목이 그 지시에 대한 사전 해소**다.
    * 3-2. **왜 여기에 적혀 있나**: 이 규칙은 개인 메모리에만 있었고 **두 번 위반됐다**(2026-09-13 10커밋 · 2026-09-15 23커밋). 원인은 망각이 아니라 **층 불일치**(대장 **D30**) — 하네스 지시는 매 세션 새로 주입되는데 금지 규칙은 세션 시작 스냅샷에만 있었다. **매 턴 재주입되는 이 문서로 올려야 이긴다.** 🔴 **그래서 훅이 있어도 여기서 안 내린다.**
<!-- rule:커밋-상태확인 -->
4. **🔴 «커밋했다»·«푸시했다» 는 명령 *출력*이 아니라 *상태*로 확인한다** (대장 **D63**).
    * 4-1. **커밋** → `git log --oneline -1` 이 **내 메시지**인가. **푸시** → `git log @{u}..HEAD` 가 **비었나**.
    * 4-2. 🔴 **`git commit` 에 파이프를 걸지 않는다.** `pre-commit` 은 **실패한 훅을 머리에** 인쇄하므로 `| tail` 로 보면 꼬리의 `Passed` 만 남아 **성공처럼 보인다.** 게다가 종료코드가 `tail` 것이 된다.
    * 4-3. **왜**: 2026-09-22 에 훅이 커밋을 거부했는데 꼬리의 `Passed` 를 보고 됐다고 읽었고, `git push` 의 *Everything up-to-date* 에서야 드러났다. **본 신호 두 개가 전부 거짓**이었다.

---


## 6-5. 🧭 실수 대장 — **작업별로 «그 자리만» 읽는다**

정본 = `docs-private/AGENT_실수-오류-기록.md`.
🔴 **전체를 읽으라는 지시는 실행 불가능하고, 그래서 실제로 안 읽힌다** — 그 상태가
`D52`·`D63` 을 *규칙으로 적어 둔 채* 다시 밟게 만들었다. 그래서 **주소로 연다.**

**작업을 시작하기 전에 아래 표에서 해당 축을 찾아 그 절만 읽는다.**

<!-- 실수대장-라우팅 시작 -->

| 축 | 이 작업을 할 때 읽는다 |
|---|---|
| `셸-원격실행` | PowerShell·ssh·bash·docker 명령을 짤 때 (12건) |
| `배포-인프라` | GCP·VM·CI/CD·CF Pages 를 건드릴 때 (12건) |
| `문서-닫기` | PLAN·완료기록·스냅샷·색인을 닫거나 옮길 때 (20건) |
| `게이트-검사기` | 게이트·테스트·검사기를 만들거나 고칠 때 (20건) |
| `git-커밋` | 커밋·푸시할 때 (2건) |
| `파일편집` | 스크립트로 파일을 고칠 때 (2건) |
| `프론트엔드` | FE 코드·테스트를 만질 때 (2건) |
| `시크릿` | `.env`·토큰·키를 다룰 때 (1건) |
| `상시-측정` | 🔴 **항상** — 무엇이든 셀 때 (9건) |
| `상시-주장` | 🔴 **항상** — 무엇이든 주장·확인할 때 (13건) |

<!-- 실수대장-라우팅 끝 -->

> 🔑 **상시 두 축은 대장 상단 `## ★ 상시 세트` 에 «한 줄 요약»으로 모여 있다.**
> 전문 46.6 KB 는 못 밀어 넣으므로 그 요약 절이 주입 대상이다.
> 🧱 `scripts/gates/doc/check_mistake_routing.py` 가 **태그 ↔ 이 표**를 양방향 대조한다 —
> *표에만 있고 항목이 0건인 축*(**읽어도 아무것도 안 나오는 주소**)도 막는다.

<!-- rule:최소핵 -->
### 🔴 최소 핵 — **이 8줄은 여기 상주한다** (훅·`Read` 와 무관하게 산다)

상시 세트 **∩ 재발이 명시된 것**. ⚠️ **다섯이 전부 «세기» 다.**

1. **`D31`** 정본 검증기가 있으면 **즉석 `grep` 으로 뒤집지 않는다**
2. **`D43`** *«몇 건인가»* 는 **질문이 덜 된 질문**이다 — 세는 **대상**이 다르면 둘 다 사실일 수 있다
3. **`D47`** **구조를 문자열로 세지 않는다** — 숫자에 **단위**를 붙이고, 갈리면 **차집합 표본 1건**을 눈으로
4. **`D52`** 🔴 **세기 전에 «몇 개쯤 나와야 한다» 를 먼저 말한다** — 기대 없는 측정은 **인용**이다
5. **`D58`** **빈칸에 이름 붙이기 전에 그 자리를 열어 본다**
6. **`D13`** **소스를 안 읽고 도구 동작을 단정하지 않는다**
7. **`D14`** **인과 사슬의 한 고리만 보고 «이게 원인» 이라 하지 않는다**
8. **`D17`** *«다 기록했나»* 는 **두 패스**다 — ①신규가 실재하나 ②**내 변경이 기존을 거짓으로 만들었나**

---

## 6-2. 🔴 발견 ≠ 처리 (한 단계를 닫기 위한 규칙)

**작업 중 새로 발견한 결함은 그 자리에서 고치지 않고 등재만 한다.**

| 발견한 것 | 어떻게 |
|---|---|
| 거짓 주석·낡은 문서·구조 개선 기회 | **등재만** (후속 큐 / 부채 원장) |
| 🔴 **지금 안 고치면 거짓이 배포된다** (OpenAPI `summary`·DTO `description` 등 사용자 노출) | **즉시 고친다** |
| 🧹 **MyPy baseline 오류가 *지금 만지는 파일*에 있다** | **즉시 소각한다**(아래 사유) |
| 🔴 **`Read` 로 연 문서가 *이 문서(§)의 규칙과 어긋난다*** | **즉시 정합을 맞춘다**(아래 §6-2-1) |

> ⚠️ **2026-09-16 정정 — 이 표가 개인 메모리와 정반대를 말하고 있었다.**
> 여기는 MyPy 를 *"진행 중인 구간에서는 등재만"* 이라 했고, 메모리의 상시 규칙은
> *"미루지 말고 그 자리에서 소각"* 이었다. **매 턴 재주입되는 이 문서가 이기므로
> 사용자가 정한 점진 소각이 실제로는 발동하지 않는 상태였다** — D30(트레일러)과 같은 층 불일치다.
>
> **왜 MyPy 는 예외인가**: ①대상이 *지금 열어 본 파일*로 **자동으로 좁다** — 범위가 스스로
> 자라지 않는다 ②baseline 게이트는 **신규 오류만** 차단하므로, 소각은 구간을 넓히는 게 아니라
> **baseline 을 줄이는 것**이다 ③전용 페이즈를 두지 않기로 이미 결정했다(그러면 영원히 안 온다).
> 상세 = 개인 메모리 `mypy-inline-burndown-policy`.

**왜**: 2026-09-15 QA-29 에서 "거짓 주석 5곳 정정"으로 시작한 단계가 **30곳**으로 불어났다.
발견은 전부 옳았지만 **단계가 닫히지 않았다.** 보이스카웃은 미덕이나, 정지 규칙이 없으면
한 구간이 영원히 안 끝난다. 발견 속도가 처리 속도를 넘은 상태에서는
**"무엇을 이번에 하지 않을지"를 먼저 정하는 것**이 일을 끝내는 유일한 방법이다.

## 6-2-1. 🔴 읽은 문서가 **이 문서와 어긋나면 그 자리에서 맞춘다**

⑤ 문서(`FILING.md`·원장·공부노트…)를 `Read` 했는데 **이 문서(층 ②)의 규칙과 다르면,
등재만 하고 넘어가지 않는다.** 이건 `§6-2`(발견 ≠ 처리)의 **예외**다.

**왜 예외인가**: 이 문서는 **매 턴 재주입**되고 ⑤는 **`Read` 를 부른 순간만** 온다.
둘이 어긋난 채로 두면 **매 턴 읽히는 쪽이 항상 이긴다** — 즉 *"문서에 적힌 옳은 규칙이
영원히 발동하지 않는 상태"* 가 된다. 실제로 그렇게 **두 번** 당했다:
**D30**(트레일러 금지가 개인 메모리에만 있어 하네스 지시에 밀림) ·
**MyPy 점진소각**(여기가 *"등재만"* 이라 적어 사용자가 정한 *"즉시 소각"* 이 안 돌았다).

**절차 — 네 걸음. 임의로 한쪽을 이기게 하지 않는다.**

```
① 멈춘다.            어느 쪽이 사실인지 모르는 채로 코드를 고치지 않는다
② 실측한다.          명령·게이트·코드로 **사실**을 확인한다 (문서끼리 비교하지 않는다)
③ 사실 쪽으로 맞춘다.  ②·⑤ 중 틀린 쪽을 고치고 **무엇을 왜 고쳤는지 보고**한다
④ 못 가르면 묻는다.   사용자 결정이 필요한 것(정책·우선순위)은 **멈추고 확인**한다
```

> ⚠️ **②가 핵심이다.** 문서 둘을 비교해 *"더 최신인 쪽"* 을 고르지 않는다 —
> 날짜가 새롭다고 사실인 것이 아니다. **실측이 심판이고, 문서는 둘 다 피고다.**
>
> 🔑 **고친 뒤에는 `FILING.md` §1-1 을 돌린다** — 그 규칙이 *발동해야 하는 층*에
> 닿았는지. 정본만 고치면 **같은 어긋남이 다시 생긴다.**
> 기계 대조 = `scripts/gates/doc/check_rule_layers.py`(훅 `rule-layers`).

**등재는 여전히 한다** — 고친 것도 **왜 어긋나 있었는지**를 원장(`DOC_TRUTH_DRIFT`)이나
실수 대장에 남긴다. 어긋남은 *"고치면 끝"* 이 아니라 **구조가 만든 증상**이다.

---

## 6-4. 🔴 "지금 닫아도 잃을 게 없다" 는 **함부로 말하지 않는다**

`/clear`·`/compact` 를 제안하기 전:

```bash
git status --porcelain && git stash list && git log --oneline @{u}..HEAD
```

**세 개를 다 본다.** `git status` 만 보면 안 되는 이유 —
**stash 와 미푸시 커밋은 `git status` 에 나오지 않는다.** 눈으로 하는 확인에서
구조적으로 빠지는 자리이고, 실제로 *"미커밋 0"* 만 보고 **미푸시 1건**을 넘긴 적이 있다.

그리고 **여기까지가 기계가 답할 수 있는 전부다.**

> `/clear` 가 지우는 것은 **대화 컨텍스트뿐**이고 파일은 남는다. 그러므로 잃는 것은
> *"파일에 없고 내 머릿속에만 있는 것"* 인데 **그게 무엇인지는 기계가 열거할 수 없다.**
> 아래 네 가지에 **자동 판정을 붙이지 않는다** — 붙이는 순간 통과 기계가 된다.
>
<!-- rule:닫기-순서 -->
> 🔴 **그렇다고 사용자에게 통째로 넘기는 것이 아니다. 순서가 정해져 있다:**
>
> ```
> ① 내가 먼저 답한다   네 항목을 훑고 «파일에 없고 내 머릿속에만 있는 것» 에 이름을 붙인다
> ② 사용자가 판정한다  그 목록을 보고 «지워도 되는가» 를 정한다
> ```
>
> ⚠️ *"잃을 게 있는지 판단해 주세요"* 라고 **되묻는 것은 ①을 건너뛴 것**이다.
> 사용자는 **내 머릿속을 볼 수 없으므로**, ① 없이 ②를 시키면 **아무도 답할 수 없는 질문**이 된다.
> 실제로 2026-09-22 에 그렇게 넘겼고 사용자가 되돌려 보냈다(대장 **D66**).

- 이번 세션의 **결정·합의**가 파일에 적혔는가 (진행 중 PLAN 의 상태줄과 "다음 단계" 포함)
- 새로 발견한 **결함**이 후속 큐 또는 부채 원장에 등재됐는가
- 새로 한 **실수**가 `docs-private/AGENT_실수-오류-기록.md` 에 등재됐는가
- 새로 배운 **개념**이 `docs-private/study/` 에 남았는가

**왜 이 규칙이 생겼나**: 2026-09-15, *"지금 지워도 잃을 게 없습니다"* 라고 말했는데
사용자가 되묻자 세어 보니 **5개가 안 적혀 있었다**(PLAN 상태줄 · 진행 현황 절 ·
`CLAUDE.md` 규칙 2개 · 실수 대장 항목).

⚠️ **이 규칙을 검사 스크립트로 만들려다 실패했고 지웠다.** 만든 검사기를 그 5개로
측정하니 **0개**를 잡았다 — 진행 표식이 있는 PLAN 만 보는 **fail-open 판별** 때문에
*상태줄이 틀린 PLAN 은 아예 검사 대상에서 빠졌다.* **자기가 막으려던 실패에
초록을 주는 도구**였다. 경위 = `docs-private/study/2026-09-15_session-close-checker-study.md`.

## 6-3. 주석이 말해도 되는 것 / 안 되는 것

| ✅ 주석이 말한다 | ❌ 주석이 말하면 안 된다 |
|---|---|
| **왜** — 의도·경위·기각한 대안 (역사는 안 변해 썩지 않는다) | **무엇을 한다**(계약) → **테스트가 말한다** |
| 흐름 요약(섹션 헤더) · 한계 · 주의 | **값·숫자**(유예 7일 등) → **상수와 테스트가 잠근다** |
| | 폐기된 개념의 어휘 → `scripts/comment_vocabulary.toml` 게이트가 막는다 |

**근거(실측)**: soft delete 폐지 후 남은 거짓 문장 **57줄**을 표본으로 쟀더니
폐기 어휘 사전이 **47줄(82%)** 을 잡았고, 기계가 **끝내 못 잡는 나머지는 전부
"주석이 계약을 서술한 것"** 이었다. `"""Delete challenge (soft delete)."""` 는
테스트가 할 말이지 주석이 할 말이 아니다.
→ 게이트 정본 = `docs/QUALITY_GATES.md`

---

<!-- rule:완료조건 -->
## 6-1. 작업 완료 조건 — 문서화 (Definition of Done)

**코드가 초록이면 끝난 것이 아니다.** 로드맵 단계·PLAN·부채 항목을 닫을 때는 아래를 **기억이 아니라 명령으로 센다**(`ls`/`grep`).

1. **완료기록** — 직하 `RECORD.md` 를 닫아 **`docs-private/record/YYYY-MM-DD_<슬러그>-record.md`** 로
2. **PLAN 스냅샷** — 직하 `PLAN.md` 를 닫아 **`docs-private/plan/YYYY-MM-DD_<슬러그>-plan.md`** 로
    * ⚠️ **①과 ②는 한 동작이다.** 완료기록만 쓰고 스냅샷을 빠뜨리는 실패가 **6회** 있었다 — 체크리스트 1번을 하면 2번을 한 것 같은 감각이 생기기 때문이다. `scripts/gates/doc/check_plan_archives.py` 가 `pre-push` 에서 대조한다.
    * 서로를 가리키는 방법은 `doc-meta` 의 **`plan:`** 필드다(`FILING.md` §9). 파일명으로 짝짓지 않는다 — **1:N 도 N:1 도 실재한다**(`PLAN_CICD` → 완료기록 2건).
3. **`affects` 로 선언한 정본을 회전**시키고, 항목 배출형 원장의 **배출도 이때** 한다(`FILING.md` §7)
4. **후속 큐 갱신** — 테스트·검증 항목은 `docs-private/FOLLOWUP_QUEUE.md` 에 `QA-##` 로(ID 영구·재사용 금지). `doc-meta` 의 **`closes:`** 에도 적는다
5. **새로 배운 개념** → `docs-private/study/` (색인 = `study/README.md` 도 같이 갱신)

<!-- rule:2패스 -->
### 2패스 점검 (필수)
* **1패스 — 신규 기록이 실재하는가**: 위 5개를 `ls` 로 확인.
* **2패스 — 내 변경이 기존 문장을 거짓으로 만들었는가**: 훨씬 어렵고 기억에 안 떠오른다. 바꾼 모듈의 상단 주석/docstring → 그 이름을 언급하는 PLAN·원장·README·에이전트 가이드 순으로 `grep`.
    * 🔴 **ID 로 한 번, «내가 만든 산출물 이름» 으로 한 번 — 두 번 훑는다**(대장 **D62**). `grep '<ID>'` 는 *내가 등재한 것*에만 닿는다. **다른 트랙의 완료 조건은 내 ID 를 모른 채 할 일을 «산문으로» 적어 두므로 원리적으로 안 잡힌다** — `coverage`·`baseline` 같은 **산출물 이름**으로 `ROADMAP` 의 체크박스·종료 기준까지 훑는다. 🔑 **트랙 경계는 작업의 경계가 아니다** — B(정리·강화)가 만든 게이트가 A(제품)의 종료 기준을 닫는 것은 예외가 아니라 정상이다.
    * **숫자·상태 문구(`미착수`·`진행 중`·`예정`·건수)는 기억하지 말고 명령을 다시 돌려 실측한다.**
    * **총합은 검증이 아니라 힌트다** — 건수를 단언할 때는 합이 아니라 **원소를 센다**(`grep -oE 'QA-[0-9]+' | sort -u`). 두 칸이 반대로 틀리면 합은 맞는다.

### 🔎 정본 검증기가 있으면 **즉석 `grep` 으로 뒤집지 않는다** (대장 D31)

급조한 정규식엔 앵커·경계·제외조건이 빠져 **덜 엄밀한 두 번째 구현**이 된다.
실제로 훅이 옳게 통과시킨 커밋을 내 즉석 `grep` 이 *"누락"* 으로 오판했고, 믿었으면
히스토리를 이유 없이 재작성할 뻔했다. 같은 일이 **트레일러 게이트**에서도 반복됐다 —
내가 만든 테스트가 게이트를 *fail-open* 으로 오진했는데, 실제로는 dependabot 을
통과시키려 좁게 설계된 것이었다(실제 형태로 재니 7/7 정확).

> **결과가 갈리면 "어느 쪽이 덜 엄밀한가"부터 따진다. 규명 전에는 되돌리기 어려운 조치 금지.**
> *"내가 직접 세는 게 확실하다"는 감각 자체가 신호다.*

🔢 **그리고 *"몇 건인가"* 는 질문이 덜 된 질문이다**(대장 **D43**). 노트가 *"예외 13건"* 이라 적은 것을
`tomllib` 로 세니 **2건**이라 *"거짓"* 으로 등재했는데 — **설정의 *패턴 수* 2 와 도구가 *해석해 낸 import 수* 13
이 둘 다 사실**이었다. 형식이 정교해도(`grep` 이 아니라 파서라도) **세는 대상이 다르면 틀린다.**

> **숫자가 갈리면 *"누가 틀렸나"* 보다 *"우리가 같은 것을 세고 있나"* 를 먼저 묻는다.**

🔴 **이건 하루에 세 번 나왔다**(대장 **D47**) — 패턴 수 vs 해석된 수 · 라우팅 글자 vs ID · 산문 vs 필드.
**공통 구조는 하나다: 구조(필드·간선·레코드)를 찾는데 문자열을 보고 있다.**
문자열 검색은 **항상 뭔가를 돌려주므로** 0도 에러도 아닌 *"그럴듯한 수"* 가 나온다 — **틀렸다는 신호가 없다.**

| | 규칙 |
|---|---|
| **① 단위를 붙인다** | *"몇 건"* 은 질문이 덜 됐다. **`2 패턴` / `13 import`** — 단위가 다르면 **비교 자체를 안 한다** |
| **② 구조가 있으면 구조로 센다** | 필드는 **파서**로, 계약은 **도구 출력**으로, YAML 키는 **줄 머리 앵커**로. `grep` 은 *산문* 찾을 때만 |
| **③ 갈리면 차집합에서 표본 1건** | 13 vs 2 면 **그 11 중 하나를 눈으로 본다.** 어느 쪽이 옳은지 즉시 드러난다 |

> 🔑 **앵커 없는 패턴으로 필드를 찾지 않는다.** `^field:` 가 없으면 산문이 섞인다.

🔴 **그런데 D47 은 *무엇을* 세는지만 다룬다. 더 흔한 실패는 *내 측정기가 도는지*다**(대장 **D52**) —
한 세션에 **9번** 났다: 루프가 모듈 경로를 잘못 만들어 **9종 전부 실패**로 읽음 · **없는 이름을 지어내** 돌림 ·
앵커가 좁아 주석 키를 놓침 · `.` 이 **공백에 매치** · `grep | sed` 의 **종료코드는 `sed` 것** ·
**세는 패턴과 인쇄 패턴이 서로 다름**. D47 의 세 규칙은 이것들을 **하나도 못 막는다.**

> 🔑 **안 보이는 이유는 기대값이 없기 때문이다.** 게이트에는 `MIN_*` 바닥값이 **상수로 박혀** 있어
> 수가 내려가면 *"아무것도 못 봤다"* 로 읽힌다. **즉석 측정에는 그 상수가 없다** —
> 기대 없이 세면 0이든 9든 전부 그럴듯하고, **틀렸다는 신호가 원리적으로 없다.**

<!-- rule:측정도-게이트 -->
### 🔢 **측정도 게이트다** — 게이트에 요구하는 것을 내 측정에도 요구한다

| 게이트에서 | 즉석 측정에서 |
|---|---|
| 바닥값 `MIN_*` | 🔴 **세기 전에 "몇 개쯤 나와야 한다"를 먼저 말한다** |
| fail-closed | **0건을 답으로 받지 않는다.** 0이면 먼저 *패턴·경로*를 의심한다 |
| 센 수를 인쇄 | **세는 패턴과 인쇄 패턴을 하나로.** 다르면 둘 중 하나가 거짓이다 |
| 음성 대조 | **전부 통과/전부 실패는 하네스를 의심**한다 — 대상이 그렇게 고르게 나올 리 없다 |
| 결핍 주입 | **모집단을 먼저 열거**하고 그 안에서만 고른다(`find` → 목록 → 실행) |

> **숫자를 말하기 전에 기대 범위를 먼저 말한다.** 기대 없는 측정은 측정이 아니라 **인용**이다 —
> 도구가 뱉은 수를 옮겨 적었을 뿐, 그게 내 질문의 답인지는 아무도 안 봤다.
> 🔴 **"N번째"·"N연속" 은 전수를 셌을 때만 말한다** — 표본은 모집단이 아니다(D51·D52).

그리고 **게이트의 검사 범위는 조용히 줄어든다** — 파일을 옮기거나 `glob` 을 좁히면
대상이 사라지는데 게이트는 *"깨끗하다"* 고 초록을 낸다. 실제로 `check_utf8_guard` 가
**11건 → 1건**이 되고도 통과했다. **0건만이 아니라 줄어든 것도 실패로 본다.**
⚠️ **하위 검사도 각각 그렇다** — 전체 대상이 많아도 *특정 검사만* 0건일 수 있다(문서 36건을 읽으며
계승 링크를 0건 본 상태). 하위 검사마다 **바닥값**을 두고 **성공 줄에 센 숫자를 인쇄**한다.

<!-- rule:결핍주입 -->
### 🧪 게이트를 만들거나 고쳤으면 — **결핍 주입 + 음성 대조**

| | 묻는 것 | 빼면 |
|---|---|---|
| **결핍 주입** | 막아야 할 결함을 **일부러 넣는다** → Red 여야 정상 | 무장 여부가 **미지**다. 초록은 *"검사기가 말을 안 했다"* 일 뿐 |
| **음성 대조** | *"이건 **정상**이니 **통과**해야 한다"* 표본도 돌린다 | **`return 1` 만 하는 게이트도 만점**을 받는다 — 질문이 반쪽이다 |

> 🔴 **주입에도 단언을 건다**(대장 **D46**) — `assert 원본에 그 문자열이 있었다` · `assert 전후가 다르다`.
> *"기대 = 통과"* 인 케이스는 **아무것도 안 해도 통과**하므로, 음성 대조는 *"안 건드리기"* 가 아니라
> **정상 표본을 실제로 넣어** 확인하는 것이다. 실제로 내 검증 3건이 그렇게 **가짜**였다.
> 표본은 **결함과 가장 닮았지만 정상인 것**을 고른다(예: dependabot 트레일러 · `withdrawn` 은 고아가 아니다).
> **과잉 차단하는 게이트는 사람이 끄고, 그러면 검출률이 0 이 된다** — 오탐을 안 재는 것은 정탐도 잃는 길이다.
> 고친 뒤에는 **같은 결핍을 다시 넣어 Red 를 확인**한다. 완료 판정은 *"고쳤다"* 가 아니라 **"이제 잡힌다"**(D21).
> 절차 정본 = `docs-private/study/2026-09-16_deficiency-injection-study.md`

> 📁 **새 문서의 기본 위치는 `docs-private/`** — 이 저장소는 PUBLIC 이다. 공개 `docs/` 는 설계·흐름도·규칙 정본·부채 원장만. **공개 문서가 비공개 경로를 링크하면 죽은 링크가 된다.**
> 📂 **어느 폴더에 어떤 이름으로 둘지는 `docs-private/FILING.md` 가 정한다 — 만들기 전에 읽는다(§1.3).**

---

## 7~9. 파이썬 스타일 · import · 로깅 — **기계가 잡는 것은 여기 없다**

> 🔴 **아래 표의 규칙은 문서에서 뺐다.** 어기면 `pre-commit` 이 막으므로 여기 두면 **중복**이고,
> 중복은 강조를 희석한다(공식: *"emphasize many lines → none stands out"*). **다시 적지 않는다.**
> 📂 정본 = `pyproject.toml` `[tool.ruff.lint]` · 게이트 목록 = `docs/QUALITY_GATES.md`

| 이제 무엇이 잡나 | 무엇을 |
|---|---|
| `E`·`W`·`D`·`N` | PEP 8 · docstring **형식** · 명명(`snake_case`/`PascalCase`/`UPPER_SNAKE`/`_private`) |
| **`D101`·`D102`·`D103`** | public 클래스·메서드·함수의 **docstring 존재** |
| `ANN`·`B006` | 타입 힌트 의무 · **가변 기본값 금지**(`list`·`dict` 기본값) |
| `RET` | Early Return — 중첩 `if-else` 대신 즉시 반환 |
| **`BLE001`** | `except Exception` 금지 — 구체 예외를 선언한다 |
| `UP` | 모던 문법 — `Union`·`Optional` 대신 `int \| None`, 내장 `list`/`dict` |
| `I`·`TID252`·`F403` | import 정렬·3그룹 · **절대 import 강제** · 와일드카드 금지 |
| `T20`·**`G004`**·**`TRY400`** | `print()` 금지 · 로그 **`%` 지연평가** · `logger.exception()` 의무 |
| 📉 `debt-baseline` | `Any` 회피(천장 30) · top-level import(천장 26) |

### 🔴 기계가 **못** 잡는 것 — 그래서 여기 남는다

* 🔴 **`typing.TYPE_CHECKING` 절대 금지.** 금지 검사기가 **없다** — `TC001`~`TC003` 를 끈 것은
  *"옮기라고 시키지 않는다"* 일 뿐 금지가 아니다.
* `typing` 에서는 **`Callable`·`Protocol` 처럼 대체 불가한 것만** 가져온다.
  `as` 는 **이름 충돌**과 `multiprocessing as mp` 류 관례에만 쓴다.
* `__init__.py` 를 **패키지 인식용 빈 파일로 만들지 않는다** — 외부 인터페이스 노출에 쓴다.
* 데이터 저장 클래스는 **Pydantic**, 분기는 **`match-case`** 등 최신 문법을 반영한다.
* **로거는 모듈별로 선언**한다 — `logger = logging.getLogger(__name__)`.
* 로그는 **기계가 읽을 형태**(JSON)로. 레이아웃 = `[시각] [레벨] [모듈:줄] - [메시지]`.
* 🔴 **개인정보를 로그에 남기지 않는다** — 비밀번호·토큰·전화번호·주민번호. **마스킹 필수.**
  이미지 바이트·거대 JSON 도 금지. **로깅 함수 안에서 로깅을 부르지 않는다**(순환).
* 로그 레벨: `DEBUG` 추적 · `INFO` 정상 상태 변화 · `WARNING` 주의(API 지연·재시도 한계) ·
  `ERROR` 부분 실패(DB 질의 실패) · `CRITICAL` 전체 중단 위협(OOM · Redis 상실).
* 실패 지점은 **문맥과 함께** 남긴다 — 디버깅 효율이 거기서 갈린다.
* 서버 로그가 **브라우저에 노출되지 않게** 한다.

<!-- rule:리서치-체크리스트 -->
## 10. Research Checklist

Before starting any implementation, the agent MUST verify the following:
- [ ] Check official documentation (2024-2025 latest version, year required)
- [ ] Research external Best Examples (official repos, production cases, source + year required)
- [ ] Confirm similar implementation patterns within the project (`app/services/`, `app/repositories/`)
- [ ] Check if new environment variables are needed (based on `.env.example`)
- [ ] Identify related models (`app/models/` related tables)
- [ ] Check related P0/P1 issues in `QA_AUDIT_PLAN.md` (conflict check)

---

## 11. Plan Review (Required before GO)

### Sub-agent Parallel Review
The AI MUST review plans from these 3 perspectives simultaneously:
- **Architect**: Layered architecture violations, dependency direction between layers
- **Critic**: Edge cases, missing exception handling, security vulnerabilities
- **Document Specialist**: Missing Affected Files, DBML update requirements

Review MUST reference external Best Examples from the Research Checklist (source + year required).

### Review Checklist
- [ ] Is the Goal clearly defined with completion criteria?
- [ ] Were trade-off choices presented to the user first?
- [ ] Is the external research from Research Checklist completed?
- [ ] Are TDD Steps correctly split by business logic unit?
- [ ] Are Affected Files filled in completely?
- [ ] Is the core flow visualized with a Mermaid flowchart?

---

## 12. Final Language Check
**[CRITICAL WARNING] All answers, explanations, result outputs, and feedback to the user MUST be written EXCLUSIVELY in 'Korean (한글)'. Arbitrarily translating responses into English or any other language is STRICTLY PROHIBITED.**
