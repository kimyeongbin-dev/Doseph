"""구조 지도 생성기 — **손으로 쓴 구조 문서를 다시 만들지 않기 위해** (트랙 B-14 · `문서-9`).

왜 필요한가
-----------
손으로 쓴 ``PROJECT_STRUCTURE_REPORT.md`` 는 5개월 만에 **12개 항목이 전부 틀린 채**
은퇴했다(`_legacy/2026-09-15_PROJECT_STRUCTURE_REPORT.retired.md`):

===================================  ==========================================
그 문서                              실제 (2026-09-15 실측)
===================================  ==========================================
저장소 ``AH_02_06/``                 ``Doseph/``
AWS EC2 · PostgreSQL 15              GCP e2-micro · PG 17.11
JWT **RS256**                        **HS256**
소셜 로그인 "Kakao, **Naver**"       Naver **0건**
라우터 **9개**                       실제 **15개**
"**10개** 테이블"                    실제 **18개**
모델 ``drug_interaction_cache``      🔴 파일도 테이블도 **없다**
===================================  ==========================================

🔑 **대안은 «다시 쓰기» 가 아니라 «생성» 이다.** 위 12개는 **전부 기계가 셀 수 있는 것**이었다 —
사람이 세다 틀린 게 아니라, **한 번 세고 그 뒤로 안 셌기 때문에** 틀렸다.

🔴 이 생성기가 지키는 네 가지
-----------------------------
**① 구조를 문자열로 세지 않는다**(대장 ``D47``).
   라우터 엔드포인트도 모델도 **AST** 로 센다. 정규식으로 ``@router.get`` 을 찾으면
   docstring·문자열 안의 것을 줍는다 — 그러면 0도 에러도 아닌 *"그럴듯한 수"* 가 나오고
   **틀렸다는 신호가 없다.**

**② 0건은 «없다» 가 아니라 «못 셌다»** (대장 ``D31``).
   폴더가 사라지거나 경로가 바뀌면 생성기는 조용히 0을 적는다. 축마다 **바닥값**을 두고
   미달이면 **생성 자체를 거부**한다 — 거짓 지도를 내놓느니 아무것도 안 내놓는 게 낫다.

**③ 산출물을 커밋하지 않는다.**
   커밋하면 **그 순간부터 다시 낡기 시작한다** — 지금 은퇴시킨 그 문서가 정확히 그랬다.
   ``docs-private/`` 는 git 밖이라 **읽고 싶을 때 다시 만드는 것**이 유일한 사용법이 된다.

**④ 모르는 것은 «모른다» 고 적는다.**
   실제 DB 테이블 수는 **DB 를 봐야 안다.** 은퇴한 문서가 *"10개 테이블"* 이라 틀린 이유가
   바로 그것이다 — 코드에서 추측했다. 이 지도는 **모델 클래스 수**를 적고, 테이블은
   *"실측하려면 이 명령"* 만 적는다.

사용
----
    uv run python scripts/build_structure_map.py
    uv run python scripts/build_structure_map.py --out -    # 표준출력으로

⚠️ **게이트가 아니다.** ``pre-push`` 에 붙이지 않는다 — 구조가 바뀌는 것은 결함이 아니다.
사람이 *"지금 구조가 어떻게 되지"* 라고 물을 때 부르는 도구다.
"""

import argparse
import ast
from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import sys
import tomllib

from scripts.gates._root import REPO_ROOT

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

#: HTTP 메서드 데코레이터. `@router.get` 처럼 **속성 접근**으로만 인정한다.
HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})

#: 🔑 축별 바닥값 — 실측 2026-09-23. **줄어든 것도 실패로 본다**(`D31`).
#:    구조가 정말 줄었다면 이 상수를 **의식적으로** 내린다 — 조용히 0이 되는 것과 다르다.
FLOORS = {
    "라우터": 12,
    "모델": 14,
    "서비스": 16,
    "리포지토리": 12,
    "워커 도메인": 4,
    "FE 라우트": 10,
    "마이그레이션": 1,
    "테스트": 50,
}


@dataclass
class Axis:
    """구조의 한 축.

    Attributes:
        name: 축 이름(`라우터` 등).
        items: 센 것들의 이름. **`count` 는 이 목록의 길이다** — 세는 수와 인쇄하는 수를 하나로 둔다.
        detail: 축 안의 하위 집계(`{"엔드포인트": 87}`).
        floor: 바닥값. 미달이면 `problem` 이 선다.
        problem: 셀 수 없었던 이유. `None` 이면 셀 수 있었다.
    """

    name: str
    items: list[str] = field(default_factory=list)
    detail: dict[str, int] = field(default_factory=dict)
    floor: int = 0
    problem: str | None = None

    @property
    def count(self) -> int:
        """센 항목 수."""
        return len(self.items)

    def check_floor(self) -> None:
        """바닥값 미달이면 `problem` 을 세운다."""
        if self.problem is None and self.count < self.floor:
            self.problem = (
                f"**{self.count}건**으로 바닥값 {self.floor} 아래다 — "
                "경로가 바뀌어 못 셌을 수 있다(0건은 «없다» 가 아니라 «못 셌다»)"
            )


# ── 폴더를 열 수 있나 ────────────────────────────────────────────────
# 흐름: 존재 확인 -> 없으면 fail-closed 축을 돌려준다
def _guard(folder: Path, name: str, floor: int) -> Axis | None:
    """폴더가 없으면 «못 셌다» 축을 만든다.

    Args:
        folder: 검사할 폴더.
        name: 축 이름.
        floor: 바닥값.

    Returns:
        폴더가 없으면 `problem` 이 선 `Axis`, 있으면 `None`.
    """
    if folder.is_dir():
        return None
    return Axis(name=name, floor=floor, problem=f"`{folder}` 가 없다 — **경로가 바뀌었거나 삭제됐다**")


def _parse(path: Path) -> ast.Module | None:
    """파이썬 파일을 AST 로 연다. 못 읽으면 `None`."""
    try:
        return ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return None


# ── 라우터 — 파일 수와 **엔드포인트 수**를 함께 센다 ─────────────────
# 흐름: *_routers.py 수집 -> AST 로 @router.<method> 데코레이터 세기
def collect_routers(root: Path, floor: int = 0) -> Axis:
    """API 라우터와 엔드포인트를 센다.

    Args:
        root: 저장소 루트.
        floor: 바닥값.

    Returns:
        축 결과. `detail["엔드포인트"]` 에 데코레이터 수.
    """
    folder = root / "app" / "apis" / "v1"
    guarded = _guard(folder, "라우터", floor)
    if guarded:
        return guarded

    axis = Axis(name="라우터", floor=floor)
    endpoints = 0
    for path in sorted(folder.glob("*_routers.py")):
        tree = _parse(path)
        if tree is None:
            continue
        # 🔴 **AST 로 센다.** 정규식이면 docstring 안의 `@router.get` 을 줍는다(`D47`).
        found = sum(
            1 for node in ast.walk(tree) for dec in getattr(node, "decorator_list", []) if _is_route_decorator(dec)
        )
        endpoints += found
        axis.items.append(f"{path.stem} ({found})")
    axis.detail["엔드포인트"] = endpoints
    axis.check_floor()
    return axis


def _is_route_decorator(dec: ast.expr) -> bool:
    """`@router.get(...)` 꼴인가."""
    call = dec.func if isinstance(dec, ast.Call) else dec
    return isinstance(call, ast.Attribute) and call.attr in HTTP_METHODS


# ── 모델 — **`Model` 을 상속한 클래스**만 테이블이다 ─────────────────
# 흐름: app/models/*.py -> AST ClassDef -> 기반 클래스에 Model 이 있나
def collect_models(root: Path, floor: int = 0) -> Axis:
    """Tortoise 모델 클래스를 센다.

    Args:
        root: 저장소 루트.
        floor: 바닥값.

    Returns:
        축 결과. `items` 는 `파일: 클래스` 꼴.
    """
    folder = root / "app" / "models"
    guarded = _guard(folder, "모델", floor)
    if guarded:
        return guarded

    axis = Axis(name="모델", floor=floor)
    classes = 0
    for path in sorted(folder.glob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = _parse(path)
        if tree is None:
            continue
        names = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and any(_is_model_base(b) for b in node.bases)
        ]
        classes += len(names)
        axis.items.append(f"{path.stem}: {', '.join(names) if names else '—'}")
    axis.detail["모델 클래스"] = classes
    axis.check_floor()
    return axis


def _is_model_base(base: ast.expr) -> bool:
    """기반 클래스가 `Model` 또는 `models.Model` 인가."""
    if isinstance(base, ast.Name):
        return base.id == "Model"
    return isinstance(base, ast.Attribute) and base.attr == "Model"


# ── 단순 파일 축(서비스·리포지토리·테스트) ───────────────────────────
# 흐름: 폴더 확인 -> glob -> __init__ 제외
def collect_files(root: Path, rel: str, name: str, pattern: str = "*.py", floor: int = 0) -> Axis:
    """한 폴더의 파일을 센다.

    Args:
        root: 저장소 루트.
        rel: 루트 기준 폴더 경로.
        name: 축 이름.
        pattern: glob 패턴.
        floor: 바닥값.

    Returns:
        축 결과.
    """
    folder = root / rel
    guarded = _guard(folder, name, floor)
    if guarded:
        return guarded

    axis = Axis(name=name, floor=floor)
    axis.items = sorted(p.stem for p in folder.glob(pattern) if p.name != "__init__.py")
    packages = sorted(p.name for p in folder.iterdir() if p.is_dir() and (p / "__init__.py").is_file())
    if packages:
        axis.detail["하위 패키지"] = len(packages)
    axis.check_floor()
    return axis


# ── 워커 도메인 ──────────────────────────────────────────────────────
# 흐름: ai_worker/domains/ 의 **패키지**만 (캐시 폴더 제외)
def collect_worker_domains(root: Path, floor: int = 0) -> Axis:
    """ai-worker 의 도메인 패키지를 센다.

    Args:
        root: 저장소 루트.
        floor: 바닥값.

    Returns:
        축 결과.
    """
    folder = root / "ai_worker" / "domains"
    guarded = _guard(folder, "워커 도메인", floor)
    if guarded:
        return guarded

    axis = Axis(name="워커 도메인", floor=floor)
    # 🔑 `__pycache__` 는 폴더지만 패키지가 아니다 — `__init__.py` 로 가른다.
    axis.items = sorted(p.name for p in folder.iterdir() if p.is_dir() and (p / "__init__.py").is_file())
    axis.check_floor()
    return axis


# ── FE 라우트 — `page.jsx` 의 **경로**가 곧 라우트다 ─────────────────
# 흐름: src/app 아래 page.jsx 수집 -> 상대경로를 URL 로
def collect_frontend_routes(root: Path, floor: int = 0) -> Axis:
    """Next.js App Router 의 라우트를 센다.

    Args:
        root: 저장소 루트.
        floor: 바닥값.

    Returns:
        축 결과. `items` 는 `/medication/detail` 꼴.
    """
    folder = root / "medication-frontend" / "src" / "app"
    guarded = _guard(folder, "FE 라우트", floor)
    if guarded:
        return guarded

    axis = Axis(name="FE 라우트", floor=floor)
    routes = []
    for path in folder.rglob("page.jsx"):
        rel = path.parent.relative_to(folder).as_posix()
        routes.append("/" if rel == "." else "/" + rel)
    axis.items = sorted(routes)
    axis.check_floor()
    return axis


# ── 스택 — 선언된 버전을 **선언한 파일에서** 읽는다 ──────────────────
# 흐름: pyproject -> package.json -> docker-compose 이미지 태그
def collect_stack(root: Path) -> dict[str, str]:
    """스택 버전을 선언 파일에서 읽는다.

    Args:
        root: 저장소 루트.

    Returns:
        `{항목: 값}`. 못 읽은 것은 `?` 로 남긴다 — **추측하지 않는다**.
    """
    out: dict[str, str] = {}
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        project = data.get("project", {})
        out["Python"] = str(project.get("requires-python", "?"))
        for dep in project.get("dependencies", []):
            for key in ("fastapi", "tortoise-orm", "pydantic", "openai"):
                if dep.lower().startswith(key):
                    out[key] = dep
    pkg = root / "medication-frontend" / "package.json"
    if pkg.is_file():
        deps = json.loads(pkg.read_text(encoding="utf-8")).get("dependencies", {})
        for key in ("next", "react", "tailwindcss", "@tanstack/react-query"):
            if key in deps:
                out[key] = deps[key]
    compose = root / "docker-compose.yml"
    if compose.is_file():
        # 🔑 이미지 태그는 **줄머리 `image:` 앵커**로 — 산문 속 이름을 줍지 않는다(`D47`).
        for m in re.finditer(r"(?m)^\s*image:\s*(\S+)\s*$", compose.read_text(encoding="utf-8")):
            out.setdefault(f"image:{m.group(1).split(':')[0].split('/')[-1]}", m.group(1))
    return out


# ── 지도 렌더 ────────────────────────────────────────────────────────
# 흐름: 머리(언제·무엇에서·경고) -> 축별 표 -> 모르는 것 선언
def render(axes: list[Axis], root: Path, stack: dict[str, str] | None = None) -> str:
    """구조 지도를 마크다운으로 만든다.

    Args:
        axes: 축 결과들.
        root: 저장소 루트(머리에 적는다).
        stack: 스택 버전.

    Returns:
        마크다운 전문.
    """
    now = datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    lines = [
        # 🔑 생성물도 `doc-meta` 를 단다 — 직하 규약의 예외가 아니다(`FOLLOWUP_INDEX` 선례).
        "<!-- doc-meta",
        "kind:     architecture",
        "status:   current",
        "note:     🤖 생성물이다 — 손으로 고치지 않는다. 코드를 고치고 다시 생성한다. 커밋하지 않는다.",
        "-->",
        "",
        "# 구조 지도 (생성물)",
        "",
        f"> 🤖 **생성 {now}** · 저장소 `{root.name}` · 만든 것 = `scripts/build_structure_map.py`",
        ">",
        "> 🔴 **손으로 고치지 않는다. 그리고 커밋하지 않는다.**",
        "> 손으로 쓴 앞 판(`PROJECT_STRUCTURE_REPORT.md`)은 5개월 만에 **12개 항목이 전부 틀린 채**",
        "> 은퇴했다. 틀린 것 자체보다 **틀린 줄 몰랐다**는 것이 위험했다.",
        "> 커밋하면 이 파일도 그 순간부터 낡기 시작하므로, **읽고 싶을 때 다시 만드는 것**이 사용법이다:",
        ">",
        "> ```bash",
        "> uv run python scripts/build_structure_map.py",
        "> ```",
        "",
    ]
    for axis in axes:
        detail = " · ".join(f"{k} **{v}**" for k, v in axis.detail.items())
        head = f"## {axis.name} — **{axis.count}**" + (f" ({detail})" if detail else "")
        lines += [head, ""]
        if axis.problem:
            lines += [f"🔴 **셀 수 없었다** — {axis.problem}", ""]
            continue
        lines += ["```", *axis.items, "```", ""]

    if stack:
        lines += ["## 스택 — **선언된 값**", "", "| 항목 | 선언 |", "|---|---|"]
        lines += [f"| `{k}` | `{v}` |" for k, v in sorted(stack.items())]
        lines += [""]

    lines += [
        "## 🔴 이 지도가 **모르는 것**",
        "",
        "| 모르는 것 | 왜 | 실측하려면 |",
        "|---|---|---|",
        "| **실제 DB 테이블 수** | 코드가 아니라 **DB 가 정본**이다. 은퇴한 앞 판이 "
        '*"10개 테이블"* 이라 틀린 이유가 이것이다 — 코드에서 추측했다 | '
        "`\\dt` (psql) 또는 `information_schema.tables` 조회 |",
        "| **실제 인덱스** | 〃. 마이그레이션에 있는 것과 DB 에 있는 것이 다르다"
        "(`QA-17`: HNSW 가 계획에만 있다) | `\\di` |",
        "| **엔드포인트가 살아 있나** | 데코레이터 수는 *선언*이지 *동작*이 아니다 | `GET /docs` (OpenAPI) |",
        "| **무엇이 무엇을 부르나** | 이 지도는 **목록**이지 **그래프**가 아니다 | "
        "레이어 경계는 🧱 `check_layers` 가 강제한다 |",
        "",
        "> 🔑 **모르는 것을 «모른다» 고 적는 칸이 이 지도의 핵심이다.**",
        "> 앞 판은 이 칸이 없어서 추측을 사실처럼 적었다.",
    ]
    return "\n".join(lines) + "\n"


def build(root: Path) -> tuple[str, list[str], list[Axis]]:
    """모든 축을 모아 지도를 만든다.

    Args:
        root: 저장소 루트.

    Returns:
        `(마크다운, 문제 목록, 축들)`. 문제가 있으면 호출자가 **생성을 거부**한다.
        🔴 **축을 그대로 돌려주는 것이 요점이다** — 요약을 만들려고 마크다운을 다시
        정규식으로 파싱하면 *세는 패턴과 인쇄 패턴이 갈린다*(대장 `D52`).
        실제로 그렇게 짰다가 축 이름을 좁게 잡는 패턴이 **공백 있는 이름**(`워커 도메인`·`FE 라우트`)을
        놓쳐, 제대로 센 두 축이 요약에서 조용히 사라졌다.
    """
    axes = [
        collect_routers(root, FLOORS["라우터"]),
        collect_models(root, FLOORS["모델"]),
        collect_files(root, "app/services", "서비스", floor=FLOORS["서비스"]),
        collect_files(root, "app/repositories", "리포지토리", floor=FLOORS["리포지토리"]),
        collect_worker_domains(root, FLOORS["워커 도메인"]),
        collect_frontend_routes(root, FLOORS["FE 라우트"]),
        collect_files(root, "app/db/migrations/models", "마이그레이션", floor=FLOORS["마이그레이션"]),
        collect_files(root, "app/tests", "테스트", pattern="test_*.py", floor=FLOORS["테스트"]),
    ]
    problems = [f"`{a.name}` — {a.problem}" for a in axes if a.problem]
    return render(axes, root, collect_stack(root)), problems, axes


def main() -> int:
    """구조 지도를 만들어 `docs-private/STRUCTURE_MAP.md` 에 쓴다.

    Returns:
        종료코드 — 0 이면 생성됨.
    """
    parser = argparse.ArgumentParser(description="구조 지도 생성기")
    parser.add_argument("--out", default=str(REPO_ROOT / "docs-private" / "STRUCTURE_MAP.md"))
    args = parser.parse_args()

    text, problems, axes = build(REPO_ROOT)
    if problems:
        # 🔴 거짓 지도를 내놓느니 아무것도 안 내놓는다.
        print("❌ 구조 지도를 만들지 않았다 — 셀 수 없는 축이 있다:")
        for line in problems:
            print(f"   - {line}")
        print("   🔑 경로가 바뀌었다면 `FLOORS` 와 수집 함수를 **의식적으로** 고친다.")
        return 1

    if args.out == "-":
        print(text)
        return 0
    out = Path(args.out)
    out.write_text(text, encoding="utf-8")
    # 🔑 **센 것을 그대로 인쇄한다.** 마크다운을 다시 파싱하지 않는다(`D52`).
    summary = " · ".join(f"{a.name} {a.count}" for a in axes)
    print(f"✅ 구조 지도 — {summary}")
    print(f"   📄 {out}  (🔴 커밋하지 않는다 — 읽고 싶을 때 다시 만든다)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
