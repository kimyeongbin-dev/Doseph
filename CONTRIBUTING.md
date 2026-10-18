# 개발 규칙

## 1. 시작하기

클론한 직후에 한 번 실행합니다. 의존성을 설치하고, Git 훅(pre-commit · commit-msg · pre-push)을 연결합니다.

```bash
uv sync                                  # Python 의존성 + 개발 도구(Ruff·MyPy·pre-commit)
uv run pre-commit install                # 훅 3종 설치 (.pre-commit-config.yaml 의 default_install_hook_types)
npm --prefix medication-frontend ci      # FE 의존성 — ESLint·Prettier 훅이 여기서 돈다
git config blame.ignoreRevsFile .git-blame-ignore-revs   # 형식만 바꾼 대량 커밋을 git blame 이 건너뛴다
cp .env.example .env                     # 값은 직접 채웁니다. .env 는 커밋되지 않습니다
```

> `git blame` 은 각 줄을 마지막으로 바꾼 커밋을 보여 줍니다. 재포맷 커밋이 그 줄들을 덮으면
> «왜 이렇게 됐나» 를 찾을 수 없어서, 그런 커밋을 `.git-blame-ignore-revs` 에 적어 둡니다.
> GitHub 화면은 이 파일을 자동으로 읽고, 로컬은 위 설정을 한 번 해야 합니다.
> 이 파일에는 **동작을 바꾸지 않은 형식 전용 커밋만** 넣고, 해시는 `git rev-parse` 출력에서 복사합니다.

로컬 서버와 테스트는 Docker 안에서 돌립니다. 테스트는 경로를 붙이지 않고 **전체**를 돌립니다.

```bash
docker compose up -d --wait postgres redis fastapi
docker compose exec -T fastapi sh -c 'cd /app && uv run --no-sync pytest -q'
```

---

## 2. 커밋 컨벤션

[Conventional Commits](https://www.conventionalcommits.org/ko/v1.0.0/)를 따르고, 요약은 한국어로 씁니다.

```
<type>(<scope>): <요약>

<본문 (선택)>
```

### 2-1. type

| type | 용도 | 예시 |
|---|---|---|
| `feat` | 사용자에게 보이는 기능 추가·변경 | `feat(ocr): 처방전 날짜 인식 추가` |
| `fix` | 버그 수정 | `fix(auth): 로그아웃 후 쿠키가 남던 문제 수정` |
| `refactor` | 동작 변화 없는 구조 개선 | `refactor(rag): 검색 단계를 서비스 계층으로 이동` |
| `perf` | 성능 개선 | `perf(chat): 대화 요약 조회 캐싱` |
| `style` | 포맷 등 동작과 무관한 코드 스타일 | `style: Ruff 포맷 적용` |
| `test` | 테스트 추가·수정 | `test(contract): 모델 응답 스키마 계약 테스트 추가` |
| `docs` | 문서·주석만 변경 | `docs: 로컬 실행 가이드 보강` |
| `build` | 빌드·의존성·Docker 설정 | `build: pgvector 이미지 태그 고정` |
| `ci` | CI 설정 | `ci: PR 대상 브랜치에 dev 추가` |
| `chore` | 그 밖의 잡무 (설정 파일, 스크립트 등) | `chore(security): DB 비밀번호 기본값 제거` |
| `revert` | 이전 커밋 되돌리기 | `revert: feat(ocr): 처방전 날짜 인식 추가` |
| `merge` | 손으로 쓰는 머지 커밋 | `merge: dev 를 main 에 통합` |

### 2-2. scope (선택)
- 변경된 영역을 영문 소문자로 씁니다. 예: `auth`, `ocr`, `rag`, `chat`, `logging`, `gates`, `compose`, `security`
- **기능명은 앞머리가 아니라 scope입니다.** `ocr: …`이 아니라 `feat(ocr): …`
- 여러 영역에 걸치면 생략합니다.
- 하위 호환이 깨지는 변경은 type 뒤에 `!`를 붙입니다. 예: `feat(api)!: 복약 응답 형식 변경`

### 2-3. 요약 (첫 줄)
- **50자 이내** (type·scope 포함)를 목표로 하고, 끝에 마침표를 찍지 않습니다.
- 관련 추적 ID가 있으면 끝에 붙입니다. 예: `… — QA-64`
- 한 커밋에는 하나의 논리적 변경만 담습니다. 구조 정돈(`refactor`)과 기능(`feat`)을 한 커밋에 섞지 않습니다.

### 2-4. 본문 (선택)
- 요약과 본문 사이는 한 줄 비웁니다.
- **왜** 바꿨는지, 이전에 어떤 문제가 있었는지를 씁니다. 무엇을 바꿨는지는 diff로 알 수 있습니다.
- 목록은 `- `로 시작합니다.

### 2-5. 트레일러
- AI 도구의 `Co-authored-by`, `Generated with ...` 같은 트레일러는 **커밋과 PR 본문에 넣지 않습니다.**
  AI 도구를 어떻게 활용했는지는 README의 기술 스택·회고 섹션과 PR 본문에서 밝힙니다.
- 사람 공동 작업자의 `Co-authored-by`, 이슈 참조(`Refs: #12`) 같은 트레일러는 써도 됩니다.

### 2-6. 임시 커밋
- 작업 중에는 `wip: ...`, `fixup! ...`, `squash! ...` 커밋을 만들어도 됩니다.
- PR을 머지하기 전에 `git rebase -i --autosquash`로 정리합니다. `main`·`dev`에 남기지 않습니다.

---

## 3. 브랜치

| 브랜치 | 용도 |
|---|---|
| `main` | 릴리스 기준. push되면 백엔드가 자동 배포됩니다(`deploy.yml`). 버전 태그를 이 브랜치에 답니다 |
| `dev` | 다음 릴리스를 통합하는 브랜치 |
| `feature/<이름>` | 기능·수정 단위 작업. `dev`에서 갈라져 PR로 `dev`에 머지 |
| `production` | 프론트엔드 공개 배포용(Cloudflare Pages가 이 브랜치를 배포) |

### 작업 흐름
1. `git switch -c feature/<이름> dev`
2. 컨벤션에 맞춰 커밋한 뒤 push
3. `dev`를 대상으로 PR을 엽니다. PR 본문에 구현 내용, 트러블슈팅 과정, 고민한 점을 적어 개발 기록으로 남깁니다.
4. CI(`checks.yml`)가 초록인 것을 확인하고 **Merge commit**으로 머지합니다(기능 단위 커밋과 PR 연결을 보존). 머지한 feature 브랜치는 삭제합니다.
5. 버전 목표를 달성하면 `dev` → `main` PR로 릴리스하고, `main`에 버전 태그를 답니다. **`main` 머지는 곧 배포**입니다.

---

## 4. Git 훅이 자동으로 막는 것

[pre-commit](https://pre-commit.com/) 프레임워크로 관리하며, 정의는 `.pre-commit-config.yaml`, 게이트 설명은 [`docs/QUALITY_GATES.md`](docs/QUALITY_GATES.md)에 있습니다. 실패하면 커밋·푸시가 중단됩니다(훅이 파일을 고쳤을 때도 중단되니 다시 `git add` 합니다).

| 훅 | 막는 것 |
|---|---|
| `pre-commit` | **Ruff** 린트(자동 수정 후 재검사)·포맷, **ESLint**·**Prettier** 형식 검사(FE), 한글 출력 UTF-8 방어, 줄끝 공백·파일 끝 개행·YAML/TOML/JSON 문법·머지 충돌 표식·섞인 줄바꿈·큰 파일 |
| `commit-msg` | 위 형식(`type(scope): 요약`, type 12종)에 맞지 않는 제목, 앞머리 오염(이모지·대괄호·`@`·공백), AI 트레일러 |
| `pre-push` | **MyPy**·부채·커버리지 baseline(새로 늘어난 것만), 레이어 계약, Bandit 보안 린트, CR 줄바꿈, 문서 배치·메타·참조 정합성 |

Git이 자동으로 만드는 `Merge ...`, `Revert "..."` 메시지는 통과시킵니다. **훅은 우회(`--no-verify`)하지 않습니다.**

### 줄바꿈
모든 텍스트 파일은 **LF**입니다(`.gitattributes`의 `* text=auto eol=lf`, `.editorconfig`). 스크립트로 파일을 쓸 때는 `open(..., newline="\n")`처럼 줄바꿈을 명시합니다 — Windows의 기본값은 CRLF입니다.

### 비밀값
API 키, DB 접속 정보, 비밀번호는 코드나 `.env.example`에 넣지 않습니다. 실제 값은 `.env`에 두고, `.env.example`에는 키 이름과 자리표시자(`your-...`, `change-me`)만 둡니다.

### 린트·포맷 명령
| 목적 | 명령 |
|---|---|
| 전체 훅 실행 | `uv run pre-commit run --all-files` |
| Python 린트·포맷 | `uv run ruff check --fix .` · `uv run ruff format .` |
| FE 린트 | `npm --prefix medication-frontend run lint` |
| FE 포맷 | `npm --prefix medication-frontend run format` (검사만: `run format:check`) |

### AI 도구 하네스
Claude Code 같은 AI 도구에는 [CLAUDE.md](CLAUDE.md)의 규칙이 적용됩니다. 커밋 규칙은 사람과 똑같이 위 훅이 강제합니다.
