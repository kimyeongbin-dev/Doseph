"""주석이 거짓이 된 것을 **기계가 잡을 수 있는 범위까지** 잡는다.

`pre-commit` 의 ``pre-push`` 스테이지에서 실행된다.

왜 이게 있나 — 실측 근거
------------------------
커밋 ``c395776`` 은 QA-01(soft delete 폐지) 이후에도 **거짓으로 남아 있던 문장 57줄**을
정정했다. 그중 2줄은 OpenAPI ``summary`` 와 DTO ``description`` 으로 **사용자에게까지
노출**돼 있었다. 그 57줄을 표본으로 각 수단의 검출률을 셌다:

* **폐기 어휘 사전** — 47 / 57 (82%)
* **주석 속 식별자 실재 검사** — +2 → 49 / 57 (86%)
* 의미 일치 일반 — **불가**

남는 8줄은 전부 *"주석이 계약을 서술"* 한 것이라 기계로는 못 잡는다.
그건 게이트가 아니라 규칙으로 막는다 — **계약은 테스트가 말한다**(CLAUDE.md).

두 가지 검사 — 하나만 게이트다
------------------------------
1. **폐기 어휘 (🔴 게이트)**: 개념을 폐기할 때 그 *어휘*를 ``comment_vocabulary.toml`` 에
   등록하면 저장소 전역에서 전수 검출된다. 주석뿐 아니라 **문자열·식별자도 본다** —
   가장 비쌌던 거짓(OpenAPI ``summary``)이 주석이 아니라 코드였기 때문이다.

2. **식별자 실재 (🟡 보고 전용 — 게이트 아님)**: 주석이 백틱으로 인용한 이름이
   코드에 없으면 보고한다. 표본에서 진짜 2건을 잡았지만, **저장소 전체에 돌려보니
   186건이 나왔고 필터 후에도 78건이 남았다. 확인한 상위 항목은 전부 오탐이었다** —
   외부 API 필드명(``prdtName``) · 라이브러리 파라미터(``limits``) · 과거형 서술이
   인용한 옛 이름 · 스캔 범위 밖(``ai_worker``)에 실재하는 이름.

   > **정밀도가 낮은 검사를 게이트로 만들면 사람이 게이트를 끈다.**
   > 그러면 같이 걸려 있던 정확한 검사까지 죽는다. 그래서 분리했다.

허용목록에는 **사유가 필수**다. 사유 없는 허용은 곧 통과 기계가 된다.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
import re
import sys
import tomllib

# Windows 콘솔 기본 코드페이지(cp949)에서 한글 출력이 깨지거나 죽지 않도록 고정한다.
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

RULES_PATH = Path("scripts/comment_vocabulary.toml")
SCAN_ROOTS = (Path("app"), Path("ai_worker"), Path("scripts"))

SOURCE_SUFFIXES = frozenset({".py"})
SKIP_DIRS = frozenset({".git", "node_modules", "__pycache__", ".venv", "venv"})

#: 주석·docstring 이 백틱으로 인용한 이름. ``name`` 또는 `name` 둘 다 본다.
#: 파이썬 식별자 모양만 대상으로 한다 — 산문까지 검사하면 오탐 공장이 된다.
QUOTED_NAME = re.compile(r"``([A-Za-z_][A-Za-z0-9_]*)``|`([A-Za-z_][A-Za-z0-9_]*)`")

#: 저장소에 실제로 정의된 이름으로 인정하는 형태.
DEFINITION = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
ASSIGNMENT = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*[:=]", re.MULTILINE)


@dataclass(frozen=True)
class Hit:
    """한 건의 검출 위치."""

    path: str
    line: int
    text: str


@dataclass(frozen=True)
class MissingName:
    """주석이 말했지만 저장소에 없는 이름."""

    path: str
    line: int
    name: str


# ── 규칙 로드 (허용에는 사유가 필수) ──────────────────────────────────
# 흐름: TOML 읽기 -> banned/allow 추출 -> 사유 없는 allow 는 즉시 실패
def load_vocabulary_rules(path: Path) -> tuple[list[str], list[str]]:
    """Load banned words and allowed paths.

    Args:
        path: TOML rules file.

    Returns:
        (banned words, allowed path fragments).

    Raises:
        ValueError: When an allow entry has no ``reason``.
    """
    if not path.is_file():
        return [], []

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    banned = [entry["word"] for entry in data.get("banned", [])]

    allow: list[str] = []
    for entry in data.get("allow", []):
        if not entry.get("reason"):
            message = f"허용 항목에 reason 이 없다: {entry.get('path')!r} — 사유 없는 허용은 통과 기계가 된다"
            raise ValueError(message)
        allow.append(entry["path"])
    return banned, allow


# ── 소스 파일 순회 ────────────────────────────────────────────────────
def _iter_sources(root: Path) -> Iterator[Path]:
    """Yield scannable source files under ``root``."""
    for path in sorted(root.rglob("*")):
        if path.suffix not in SOURCE_SUFFIXES or not path.is_file():
            continue
        if SKIP_DIRS & set(path.parts):
            continue
        yield path


# ── 검사 ① 폐기 어휘 ─────────────────────────────────────────────────
# 흐름: 폐기어 목록 -> 소스 전수 스캔(주석·문자열·식별자 전부) -> 허용 경로 제외
# 주석만 보지 않는 이유: 가장 비쌌던 거짓은 OpenAPI summary — 코드였다.
def find_banned_vocabulary(root: Path, banned: list[str], allow: list[str]) -> list[Hit]:
    """Find lines still using vocabulary of an abolished concept.

    Args:
        root: Directory to scan.
        banned: Words that must no longer appear.
        allow: Path fragments exempted (each carries a reason in the rules file).

    Returns:
        Matching locations.
    """
    if not banned:
        return []

    hits: list[Hit] = []
    for path in _iter_sources(root):
        location = path.as_posix()
        if any(fragment in location for fragment in allow):
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            lowered = line.lower()
            if any(word.lower() in lowered for word in banned):
                hits.append(Hit(path=location, line=lineno, text=line.strip()))
    return hits


# ── 검사 ② 주석 속 식별자 실재 ───────────────────────────────────────
# 흐름: 저장소 전체의 정의된 이름 수집 -> 주석의 백틱 인용 이름 추출
#       -> 정의 집합에 없으면 보고
# 오탐을 줄이려고 **파이썬 식별자 모양 + 백틱 인용**만 본다.
def find_missing_identifiers(root: Path) -> list[MissingName]:
    """Find names quoted in comments that exist nowhere in the tree.

    Args:
        root: Directory to scan.

    Returns:
        Quoted names with no definition anywhere under ``root``.
    """
    sources = list(_iter_sources(root))
    texts = {path: path.read_text(encoding="utf-8", errors="replace") for path in sources}

    defined: set[str] = set()
    for text in texts.values():
        defined.update(DEFINITION.findall(text))
        defined.update(ASSIGNMENT.findall(text))

    missing: list[MissingName] = []
    for path, text in texts.items():
        for lineno, line in enumerate(text.splitlines(), start=1):
            for double, single in QUOTED_NAME.findall(line):
                name = double or single
                if name and name not in defined:
                    missing.append(MissingName(path=path.as_posix(), line=lineno, name=name))
    return missing


def main() -> int:
    """pre-push 훅 진입점.

    Returns:
        검출이 없으면 0, 있으면 1 (push 거부).
    """
    # fail-closed: 금지 어휘가 0건이면 "깨끗하다"가 아니라 "사전을 못 읽었다"이다.
    banned, allow = load_vocabulary_rules(RULES_PATH)
    if not banned:
        print(f"\n[거부] 폐기 어휘 사전에서 금지어를 한 건도 못 읽었다 — {RULES_PATH}", file=sys.stderr)
        print("  사전이 비었거나 파서가 깨졌다. 검사가 무력화된 상태다(fail-closed).\n", file=sys.stderr)
        return 1

    hits: list[Hit] = []
    for root in SCAN_ROOTS:
        if root.is_dir():
            hits.extend(find_banned_vocabulary(root, banned, allow))

    if not hits:
        return 0

    print("\n[거부] 폐기된 개념의 어휘가 아직 남아 있다\n", file=sys.stderr)
    for hit in hits:
        print(f"  {hit.path}:{hit.line}\n    {hit.text}", file=sys.stderr)
    print(
        f"\n  문장을 고치거나, 정당한 사용이면 {RULES_PATH} 의 [[allow]] 에\n  **사유와 함께** 등록한다.\n",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
