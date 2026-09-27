"""`CLAUDE.md` 의 규칙마다 **«무엇이 이것을 강제하나»** 를 기계가 읽게 한다.

규약 정본 = ``docs-private/FILING.md`` §1-1(규칙을 세우면 그 자리에서 층을 정한다).
트랙 **B-13 2구간**. 1구간이 **실수 대장**에 한 것의 **규칙 쪽 판**이다.

왜 이 게이트가 있나
-------------------
층②(`CLAUDE.md`)는 **매 턴 재주입**되므로 여기 적힌 것은 언제나 읽힌다. 그래서 규칙이
자꾸 여기로 모이는데, **무엇이 이미 기계에 있는지**를 아무도 세지 않았다.

🔬 실측(2026-09-27): 나흘 만에 **571 → 605줄**. 늘린 것은 대부분 **옳은 정정**이었다 —
문제는 *«옳은 추가» 에는 상한이 없다*는 것이다. **아무 신호도 없었다.**

앵커가 값을 나른다
------------------
```markdown
### 1.2 TDD (Test-Driven Development) <!-- rule:tdd 강제:없음 -->
## 6. Commit Rules <!-- rule:커밋규약 강제:훅:commit-subject-hygiene,훅:no-ai-trailers 잔류:층2 -->
```

- ``rule:`` — 규칙 이름. **대장의 `문서:CLAUDE.md#<이름>` 이 이 이름으로 걸려 있다.**
- ``강제:`` — 1구간과 **같은 어휘**(`훅:`·`규칙:`·`스크립트:`·`CI:`·`없음`). 쉼표로 여럿.
- ``잔류:`` — **강제가 있어도 본문이 남아야 하는 사유.** 없으면 **삭제 후보**다.

🔴 ``잔류:`` 가 설계의 핵심이다 — ``강제`` 만 두면 *«기계가 잡으니 지워라»* 로 읽히는데
**반례가 명문으로 있다**: 트레일러 금지는 ``no-ai-trailers`` 가 막는데도 여기 남는다.
하네스가 매 세션 반대 지시를 주입하므로 **층②에 있어야 이긴다**(대장 **D30**).

🔴 **표제 줄에 붙인다** — 별도 줄로 달면 앵커 수만큼 문서가 커져서
이 게이트가 막으려는 바로 그것을 **자기가 한다.**

무엇을 검사하나 — 여덟
-----------------------
1. 앵커마다 ``강제:`` 가 있는가
2. 값이 1구간 어휘인가
3. **참조가 실재**하는가 — 🔴 ``check_mistake_prevention.verify_reference`` **재사용**
   (파서를 두 개 만들면 두 개가 갈린다)
4. **앵커 바닥값** — 줄면 실패. 대상이 조용히 사라지는 것을 막는다
5. **«강제 있고 잔류 없음» 천장** — 줄어들 수만 있다
6. 성공 줄에 센 수를 인쇄
7. 🔴 **양방향** — 대장 ``문서:CLAUDE.md#X`` 의 ``X`` 가 앵커로 실재하는가
8. 🔴 **줄 수 천장** — *«늘리려면 같은 만큼 줄여라»*

✅ **음성 대조 표본** — 통과해야 한다:
  - ``강제:없음`` (기계가 없는 것은 정상이다. 0이 아니라 **선언**이다)
  - ``잔류:`` 가 있는 ``강제`` 항목 (남을 이유를 적었다)
  - 절 **안**의 정밀 포인터(``mv-보존`` 등) — 표제 줄이 아니어도 된다

⚠️ ``pre-push`` **로컬 전용**이다. 대상이 없으면 **실패**한다(fail-closed).
"""

from dataclasses import dataclass
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

# stdout/stderr 방어가 import 보다 먼저여야 한다 — cp949 크래시 방지(대장 D36).
from scripts.gates._root import PRIVATE, REPO_ROOT  # noqa: E402
from scripts.gates.doc.check_mistake_prevention import (  # noqa: E402
    Known,
    parse_hook_ids,
    parse_ruff_lint,
    verify_reference,
)

TARGET = REPO_ROOT / "CLAUDE.md"
LEDGER = PRIVATE / "AGENT_실수-오류-기록.md"

#: 🔴 **바닥값** — 앵커가 줄면 «위반이 없다» 가 아니라 «대상이 사라졌다» 이다.
MIN_ANCHORS = 36
#: 🔴 **천장** — 삭제 후보는 줄어들 수만 있다. 늘었다면 본문이 기계를 다시 베낀 것이다.
MAX_CANDIDATES = 0
#: 🔴 **줄 수 천장** — 2026-09-27 착수 시 605, 앵커를 표제 줄에 붙여 598 로 내려왔다.
#:    B-11 2구간이 본문을 압축하면 **이 값도 같이 내린다.**
MAX_LINES = 598

#: 🔴 **매 턴 컨텍스트에 문자열을 주입하는 파일** — 층②와 같은 무게인데 게이트가 없었다(대장 **D67**).
#:    그 훅이 *「축 `문서-닫기`(18건)」* 를 주입하는 동안 게이트는 **19** 를 인쇄했다.
#:    🔑 **거기에는 숫자를 박지 않는다** — 숫자는 반드시 낡고, 낡은 숫자가 매 턴 읽히면
#:    **틀린 사본이 항상 이기고 맞는 원본은 거의 안 읽힌다**(`D30` 의 층 불일치와 같은 모양).
#:    ⚠️ 2패스 ②가 이걸 놓쳤던 이유 — 그 수는 **파이썬 문자열 리터럴 안**에 있어서
#:    *문서를 훑는 패스가 구조적으로 못 본다.*
INJECTORS = (REPO_ROOT / "scripts" / "hooks" / "read_precondition.py",)
COUNT_IN_PROSE = re.compile(r"\d+\s*건")

ANCHOR = re.compile(r"<!-- rule:(?P<name>\S+) 강제:(?P<force>[^\s>]+)(?: 잔류:(?P<stay>[^>]*?))? -->")
#: 페이로드가 없는 앵커 — 1구간 형식이 남아 있는 것이다.
BARE = re.compile(r"<!-- rule:(\S+) -->")
#: 대장이 `CLAUDE.md` 의 앵커를 부르는 자리.
REFERS = re.compile(r"`문서:CLAUDE\.md#([^`]+)`")


@dataclass(frozen=True)
class Rule:
    """앵커 하나가 나르는 값."""

    name: str
    force: str
    stay: str

    @property
    def enforced(self) -> bool:
        """기계가 이 규칙을 잡는가."""
        return self.force != "없음"

    @property
    def candidate(self) -> bool:
        """**삭제 후보** — 기계가 잡는데 남을 이유가 없다."""
        return self.enforced and not self.stay.strip()


def collect(text: str) -> list[Rule]:
    """앵커를 전부 읽는다.

    Args:
        text: `CLAUDE.md` 본문.

    Returns:
        앵커 목록.
    """
    return [Rule(m["name"], m["force"], m["stay"] or "") for m in ANCHOR.finditer(text)]


def audit(text: str, ledger: str, known: Known) -> tuple[list[str], list[Rule]]:
    """여덟 검사를 돌린다.

    Args:
        text: `CLAUDE.md` 본문.
        ledger: 실수 대장 본문.
        known: 참조 대조 근거.

    Returns:
        `(문제 목록, 앵커 목록)`.
    """
    problems: list[str] = []
    rules = collect(text)
    seen = {r.name for r in rules}

    # ① 페이로드 없는 앵커 — `강제:` 가 빠졌다
    problems.extend(
        f"앵커 `{name}` 에 `강제:` 가 없다 — «무엇이 이것을 강제하나» 가 빈칸이면 셀 수 없다"
        for name in BARE.findall(text)
        if name not in seen
    )

    # ② · ③ 어휘와 참조 — 🔴 1구간 검증기를 그대로 쓴다
    problems.extend(
        f"앵커 `{rule.name}` 의 `강제:{reference.strip()}` — {why}"
        for rule in rules
        if rule.enforced
        for reference in rule.force.split(",")
        if (why := verify_reference(reference.strip(), known)) is not None
    )

    # ④ 바닥값
    if len(rules) < MIN_ANCHORS:
        problems.append(
            f"앵커가 **{len(rules)}개**로 바닥값 {MIN_ANCHORS} 아래다 — "
            "절이 사라졌거나 형식이 바뀌어 파서가 못 읽었다(0은 «깨끗함» 이 아니다)"
        )

    # ⑤ 삭제 후보 천장
    candidates = [r.name for r in rules if r.candidate]
    if len(candidates) > MAX_CANDIDATES:
        head = " · ".join(candidates[:5])
        problems.append(
            f"«강제 있고 잔류 없음» 이 **{len(candidates)}건**으로 천장 {MAX_CANDIDATES} 을 넘었다: {head} — "
            "기계가 잡는 것을 본문이 다시 서술했거나, 남을 이유를 안 적었다"
        )

    # ⑦ 양방향 — 대장이 부르는 앵커가 실재하는가
    problems.extend(
        f"대장이 `문서:CLAUDE.md#{name}` 를 부르는데 그 앵커가 없다 — 읽어도 아무것도 안 나온다"
        for name in sorted(set(REFERS.findall(ledger)))
        if name not in seen
    )

    # ⑧ 줄 수 천장
    count = len(text.splitlines())
    if count > MAX_LINES:
        problems.append(
            f"`CLAUDE.md` 가 **{count}줄**로 천장 {MAX_LINES} 을 넘었다 — "
            "늘리려면 **같은 만큼 줄인다**(옳은 추가에도 상한이 있다)"
        )

    # ⑨ 주입 문자열에 건수가 박혔나 (대장 D67 이 B-13 에 넘긴 판단)
    problems.extend(check_injectors())

    return problems, rules


def check_injectors() -> list[str]:
    """**매 턴 주입되는 문구**에 숫자가 박혔는지 본다 (대장 **D67**).

    🔴 **fail-closed** — 파일이 없으면 «깨끗하다» 가 아니라 **대상이 사라진 것**이다.

    Returns:
        문제 목록.
    """
    problems: list[str] = []
    for path in INJECTORS:
        if not path.is_file():
            problems.append(f"주입 파일이 없다: `{path.name}` — 대상이 사라진 것을 «깨끗함» 으로 읽지 않는다")
            continue
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue  # 주석은 주입되지 않는다
            if COUNT_IN_PROSE.search(line):
                problems.append(
                    f"`{path.name}:{no}` 가 주입 문구에 **건수**를 박았다 — "
                    "매 턴 읽히는 자리의 숫자는 반드시 낡는다(`D67`). 세는 명령을 대신 적는다"
                )
    return problems


def main() -> int:
    """규칙 앵커를 대조한다.

    Returns:
        종료코드 — 0 이면 통과.
    """
    if not TARGET.is_file():
        print(f"❌ `{TARGET.name}` 가 없다 — 층② 정본은 없으면 결함이다")
        return 1

    text = TARGET.read_text(encoding="utf-8")
    known = Known(
        hooks=frozenset(parse_hook_ids((REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))),
        **dict(zip(("ruff", "ignored"), map(frozenset, parse_ruff_lint(REPO_ROOT / "pyproject.toml")), strict=True)),
        root=REPO_ROOT,
    )
    problems, rules = audit(text, LEDGER.read_text(encoding="utf-8"), known)

    if problems:
        print("❌ 규칙 강제 열 검사 실패")
        for line in problems:
            print(f"   - {line}")
        print("   🔑 규칙은 **실패하는 명령**이어야 한다 — 산문으로 적은 결론은 조치가 아니다(대장 D71).")
        return 1

    enforced = sum(1 for r in rules if r.enforced)
    print(
        f"✅ 규칙 강제 열 — 앵커 {len(rules)}개(바닥값 {MIN_ANCHORS}) · "
        f"강제 {enforced} · 없음 {len(rules) - enforced} · 삭제후보 {sum(1 for r in rules if r.candidate)} · "
        f"{len(text.splitlines())}줄(천장 {MAX_LINES})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
