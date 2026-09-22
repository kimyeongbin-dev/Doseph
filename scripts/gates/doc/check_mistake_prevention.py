"""예방 열 게이트 — **«무엇이 이 실수를 막나» 를 기계가 읽게 한다** (트랙 B-13).

왜 필요한가
-----------
`FILING.md` §7-2 는 실수 대장의 **배출 기준**을 *"기계가 막게 됐다"* 로 이미 정해 뒀다.
그런데 **기계가 읽을 자리가 없어서** 아무도 판정을 못 했고, 대장은 한 세션에 못 읽는
크기로 자랐다. 이 게이트는 항목마다 `**예방**:` 값을 **강제**한다.

🔴 **동반값을 강제하는 것이 핵심이다**
--------------------------------------
`기계` 라고만 적을 수 있으면 **«막힌다고 적혀 있는데 안 막히는»** 상태가 만들어지고,
그건 아무것도 없는 것보다 **나쁘다** — 거짓 안심은 확인을 멈춘다.
*만든 것과 도는 것은 다른 사실*이다(대장 **D12**).

종류마다 **실재 검증 방법이 다르므로** 접두사로 디스패치한다:

============  ==========================================  ===============================
접두사         예                                           어디서 확인
============  ==========================================  ===============================
``훅:``        ``no-ai-trailers``                          ``.pre-commit-config.yaml``
``규칙:``      ``BLE001``                                  ``pyproject.toml`` ruff select
``스크립트:``   ``scripts/injection_harness.py``            파일 실재
``CI:``        ``.github/workflows/checks.yml``            파일 실재
``문서:``      ``CLAUDE.md#최소핵``                         **앵커 주석** 실재
============  ==========================================  ===============================

🔴 **훅 id 를 ``substring`` 으로 찾으면 안 된다** — 은퇴한 ``canon-sync`` 가 설정의
**주석에 글자로** 살아 있다(실측 2곳). ``- id:`` 를 **줄머리 앵커로** 판다.

🔴 **`절차` 는 절 번호가 아니라 앵커를 가리킨다** — `CLAUDE.md` 의 절 제목은 **네 형식**이라
(``### 1.1`` / ``## 6-5.`` / ``## 7~9.`` / 번호 없는 헤딩) 번호 대조는 **오탐**과
**저정밀 통과**(96줄짜리 절을 가리켜도 초록)를 동시에 낸다.

🔴 이 게이트가 **못 하는 것** (한계 선언 — 안 적으면 초록이 과잉 해석된다)
--------------------------------------------------------------------------
- **«그 훅이 정말 그 실수를 막는지» 모른다.** 보는 것은 *존재*뿐이다.
  NIST SP 800-53A 의 어휘로는 ``Examine`` 이고 ``Test`` 가 아니다.
- **``per-file-ignores`` 를 안 본다.** `규칙:BLE001` 이 그 실수가 나는 경로에서
  면제돼 있어도 통과한다 — 대장 **D65** 가 겪은 사고다.
- **`기계` 가 «배출해도 된다» 는 뜻이 아니다.** `CLAUDE.md` 본문이 이름으로 부르는
  항목(`D26`·`D30`)은 훅이 있어도 **거기서 안 내린다**(층 불일치, `D30`).
  이 열은 **배출 판정의 입력**이고 배출은 **사용자 승인**이다.

사용
----
    ... check_mistake_prevention [대장경로]

경로를 받는 이유: 하드코딩하면 결핍 주입이 **정본을 훼손하는 길밖에** 없다.
대장은 git 밖이라 되돌릴 안전망이 없다(`FILING.md` §12-1).
"""

from dataclasses import dataclass
from pathlib import Path
import re
import sys
import tomllib

from scripts.gates._root import REPO_ROOT
from scripts.gates.doc.mistake_ledger import DEFAULT_LEDGER, Entry, MarkerError, parse_ledger

# 한글·이모지를 인쇄하므로 Windows cp949 콘솔에서 죽지 않게 먼저 방어한다(대장 D36).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

#: 닫힌 값 집합. 넓히려면 **의식적으로** 넓힌다 — 어휘가 조용히 자라면 열이 뜻을 잃는다.
VALUES = frozenset({"기계", "절차", "없음"})

#: 📉 **천장** — `없음` 은 줄어들 수만 있다. 2026-09-22 실측 43.
#: 🔑 **스냅샷 시점 집합에만** 건다는 뜻이 아니라, 올릴 때 **의식적으로** 올린다는 뜻이다.
#:    새 실수는 대개 `없음` 으로 태어나므로(D67 이 그랬다) 천장을 올리는 일 자체는 정상이다.
#:    올리면서 **왜 못 막는지**를 같이 적는 것이 이 상수의 존재 이유다.
NONE_CEILING = 43

#: 🔴 **배출을 막지 않는 바닥값.** 항목 수에 바닥을 두면 `FILING` §7-2 배출이 차단된다.
#:    그래서 **모집단 + 배출 스냅샷** 의 합을 센다 — 배출해도 합은 안 줄고,
#:    파서가 눈멀면 합이 무너진다.
MIN_TOTAL = 90

#: 배출 목적지. 아직 없어도 정상이다(배출한 적이 없다).
ARCHIVE_DIR = REPO_ROOT / "docs-private" / "mistake"

_HOOK_ID_RE = re.compile(r"(?m)^\s*-\s+id:\s*(\S+)\s*$")
_ARCHIVE_ITEM_RE = re.compile(r"(?m)^### [A-Z]+\d+\.")


@dataclass(frozen=True)
class Known:
    """참조를 대조할 근거들.

    Attributes:
        hooks: `.pre-commit-config.yaml` 이 실제로 배선한 훅 id.
        ruff: `pyproject.toml` 의 `select` 값(규칙군 접두사).
        root: `스크립트:`·`CI:`·`문서:` 경로의 기준 디렉터리.
    """

    hooks: frozenset[str]
    ruff: frozenset[str]
    root: Path


# ── 훅 id 수집 ────────────────────────────────────────────────────────
# 흐름: 줄머리 `- id:` 만 -> 주석 속 은퇴 이름은 자연히 빠진다
def parse_hook_ids(text: str) -> set[str]:
    """`.pre-commit-config.yaml` 에서 실제 배선된 훅 id 를 모은다.

    Args:
        text: 설정 파일 전문.

    Returns:
        훅 id 집합.
    """
    return set(_HOOK_ID_RE.findall(text))


# ── Ruff select ───────────────────────────────────────────────────────
def parse_ruff_select(path: Path) -> set[str]:
    """`pyproject.toml` 의 `[tool.ruff.lint] select` 를 읽는다.

    Args:
        path: `pyproject.toml` 경로.

    Returns:
        규칙군 접두사 집합.
    """
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    return set(data.get("tool", {}).get("ruff", {}).get("lint", {}).get("select", []))


# ── 참조 디스패치 ─────────────────────────────────────────────────────
# 흐름: 종류 접두사 분리 -> 종류마다 다른 검증기 -> 문제 문장 또는 None
# 🔑 if 사슬이 아니라 **표**로 둔다 — 종류는 늘어난다(`CI:` 가 S2 에서 늘었다).
def _verify_hook(value: str, known: Known) -> str | None:
    """훅 id 가 실제로 배선됐나.

    Args:
        value: 훅 id.
        known: 대조 근거.

    Returns:
        문제 설명 또는 `None`.
    """
    if value in known.hooks:
        return None
    return f"`.pre-commit-config.yaml` 에 그 훅 id 가 없다: `{value}` (은퇴했거나 오타)"


def _verify_rule(value: str, known: Known) -> str | None:
    """Ruff 규칙이 `select` 로 켜져 있나.

    Args:
        value: 규칙 코드.
        known: 대조 근거.

    Returns:
        문제 설명 또는 `None`.
    """
    if any(value.startswith(group) for group in known.ruff):
        return None
    return f"ruff `select` 가 켜지 않은 규칙이다: `{value}` — 안 켠 규칙은 아무것도 안 막는다"


def _verify_path(value: str, known: Known) -> str | None:
    """파일이 실재하나 (`스크립트:`·`CI:`).

    Args:
        value: 저장소 기준 상대 경로.
        known: 대조 근거.

    Returns:
        문제 설명 또는 `None`.
    """
    if (known.root / value).is_file():
        return None
    return f"파일이 없다: `{value}`"


def _verify_doc(value: str, known: Known) -> str | None:
    """**앵커 주석**이 그 문서에 실재하나.

    Args:
        value: `파일#앵커`.
        known: 대조 근거.

    Returns:
        문제 설명 또는 `None`.
    """
    document, _, anchor = value.partition("#")
    target = known.root / document
    if not target.is_file():
        return f"파일이 없다: `{document}`"
    if not anchor:
        return f"앵커가 비었다: `{value}` — 절 전체를 가리키면 열어도 그 규칙이 안 보인다"
    if f"<!-- rule:{anchor} -->" in target.read_text(encoding="utf-8", errors="replace"):
        return None
    return f"앵커 주석이 없다: `{value}` — *읽어도 아무것도 안 나오는 주소*다"


#: 종류 → 검증기. 어휘를 넓힐 땐 **여기에 한 줄**을 더한다.
_VERIFIERS = {
    "훅": _verify_hook,
    "규칙": _verify_rule,
    "스크립트": _verify_path,
    "CI": _verify_path,
    "문서": _verify_doc,
}


def verify_reference(reference: str, known: Known) -> str | None:
    """동반값이 **실재하는 것**을 가리키는지 확인한다.

    Args:
        reference: `훅:…`·`규칙:…`·`스크립트:…`·`CI:…`·`문서:파일#앵커`.
        known: 대조 근거.

    Returns:
        문제 설명, 문제가 없으면 `None`.
    """
    kind, separator, value = reference.partition(":")
    if not separator or not value:
        return f"종류 태그가 없다: `{reference}` — `훅:`·`규칙:`·`스크립트:`·`CI:`·`문서:` 중 하나"
    verifier = _VERIFIERS.get(kind)
    if verifier is None:
        return f"모르는 종류 태그다: `{kind}` — 어휘를 조용히 넓히지 않는다"
    return verifier(value, known)


# ── 배출분 세기 ───────────────────────────────────────────────────────
def count_archived(directory: Path) -> int:
    """축 폴더로 배출된 항목 수를 센다.

    Args:
        directory: `docs-private/mistake/`.

    Returns:
        배출된 항목 수. 폴더가 없으면 0.
    """
    if not directory.is_dir():
        return 0
    return sum(
        len(_ARCHIVE_ITEM_RE.findall(f.read_text(encoding="utf-8", errors="replace"))) for f in directory.glob("*.md")
    )


# ── 항목 하나 ─────────────────────────────────────────────────────────
# 흐름: 줄 존재 -> 형식 -> 값 어휘 -> 동반값 유무 -> 참조 실재
def check_entry(entry: Entry, known: Known) -> tuple[str | None, str | None]:
    """항목 하나의 예방 값을 검사한다.

    Args:
        entry: 대장 항목.
        known: 대조 근거.

    Returns:
        (센 값 또는 `None`, 문제 문장 또는 `None`).
    """
    where = f"{entry.id}(L{entry.line})"
    prevention = entry.prevention
    if prevention is None:
        return None, f"{where} — `**예방**:` 줄이 없다"
    if prevention.malformed:
        return None, f"{where} — 형식 위반: 백틱 밖에 글자가 있다(괄호·산문 꼬리)"
    if prevention.value not in VALUES:
        return None, f"{where} — 모르는 값 `{prevention.value}` (허용: {' · '.join(sorted(VALUES))})"
    if prevention.value == "없음":
        if prevention.reference is not None:
            return prevention.value, f"{where} — `없음` 은 동반값을 갖지 않는다: `{prevention.reference}`"
        return prevention.value, None
    if prevention.reference is None:
        return prevention.value, f"{where} — `{prevention.value}` 는 **종류 태그를 반드시 동반**한다"
    return prevention.value, (f"{where} — {why}" if (why := verify_reference(prevention.reference, known)) else None)


def main(argv: list[str] | None = None) -> int:
    """대장 전 항목의 예방 값과 그 참조를 검사한다.

    Args:
        argv: 대장 경로를 1개 받는다. 생략하면 정본.

    Returns:
        종료코드 — 0 이면 통과.
    """
    target = Path(argv[0]) if argv else DEFAULT_LEDGER
    if not target.exists():
        print(f"❌ 대장이 없다: {target}")
        return 1

    try:
        ledger = parse_ledger(target)
    except MarkerError as exc:
        print(f"❌ {exc}")
        return 1

    known = Known(
        hooks=frozenset(parse_hook_ids((REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))),
        ruff=frozenset(parse_ruff_select(REPO_ROOT / "pyproject.toml")),
        root=REPO_ROOT,
    )

    problems: list[str] = []
    counts = dict.fromkeys(VALUES, 0)

    for entry in ledger.population:
        value, problem = check_entry(entry, known)
        if value is not None:
            counts[value] += 1
        if problem is not None:
            problems.append(problem)

    # 🔴 모집단 대조 — 갈리면 **ID 형식을 벗어난 항목**이 축·예방 두 게이트를 동시에 빠져나갔다.
    if ledger.headings_in_population != len(ledger.population):
        problems.append(
            f"마커 안 `### ` 총수 **{ledger.headings_in_population}** ≠ ID 매치 **{len(ledger.population)}** — "
            "ID 형식을 벗어난 항목이 있다(두 게이트를 동시에 조용히 빠져나간다)"
        )

    # 📉 천장 — 새 실수는 대개 `없음` 으로 태어난다. 올릴 땐 **왜 못 막는지**를 같이 적는다.
    if counts["없음"] > NONE_CEILING:
        problems.append(
            f"`없음` 이 **{counts['없음']}건**으로 천장 {NONE_CEILING} 을 넘었다 — "
            "막을 수단을 만들거나, 천장을 **의식적으로** 올리고 사유를 적는다"
        )

    # 🔴 배출을 막지 않는 바닥값 — 모집단 + 배출분.
    archived = count_archived(ARCHIVE_DIR)
    total = len(ledger.population) + archived
    if total < MIN_TOTAL:
        problems.append(
            f"모집단 {len(ledger.population)} + 배출 {archived} = **{total}** 로 바닥값 {MIN_TOTAL} 아래다 — "
            "파서나 경로가 어긋났다(실제로 줄었다면 바닥값을 **의식적으로** 내린다)"
        )

    if problems:
        print("❌ 예방 열 검사 실패")
        for line in problems[:20]:
            print(f"   - {line}")
        if len(problems) > 20:
            print(f"   … 외 {len(problems) - 20}건")
        return 1

    print(
        f"✅ 예방 열 — 기계 {counts['기계']} · 절차 {counts['절차']} · 없음 {counts['없음']}"
        f"(천장 {NONE_CEILING}) · 모집단 {len(ledger.population)} + 배출 {archived} (바닥값 {MIN_TOTAL})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
