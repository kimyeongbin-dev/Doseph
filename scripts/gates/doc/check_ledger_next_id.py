"""원장의 **«다음 신규 = ID»** 선언을 실측 최대 ID +1 과 대조한다.

규약 정본 = ``docs-private/FILING.md`` §3-3(ID 는 재사용하지 않는다).

왜 이 게이트가 있나
-------------------
`DOC_TRUTH_DRIFT.md` 의 이 한 줄이 **5번 연속** 어긋났다(2026-09-21 에 2회 · 09-22 · 09-23).
원장 자신이 정정 배너를 **세 개** 달아 두고도 또 틀렸다.

🔑 **더 나쁜 것은 원인을 이미 규명해 놓았다는 점이다.** 2026-09-21 배너가
*「손으로 유지하는 다음 번호는 구조적으로 썩는다 — 대신 **세는 법**을 적는다」* 라고
**결론까지 냈는데, 줄은 그대로 손으로 유지된 채 남았다.**

⇒ **산문으로 「대신 세라」 고 적는 것은 조치가 아니다.** 읽는 사람이 그 산문에 닿을 때는
이미 위의 숫자를 믿은 뒤다. 규칙은 **실패하는 명령**이어야 한다
(``docs/QUALITY_GATES.md`` §1).

무엇을 검사하나 — 원장마다 셋
-----------------------------
1. **선언이 정확히 1건인가.** 0 이면 «선언이 없다» 가 아니라 **앵커가 깨진 것**이다.
2. **발급 ID 수가 바닥값 이상인가.** 게이트의 검사 범위는 조용히 줄어든다.
3. **선언 == 최대 발급 + 1 인가.**

🔴 **선언과 «산문 인용» 을 가른다 — 줄머리 앵커로만 센다** (대장 **D69**)
--------------------------------------------------------------------------
*"다음 신규 = `QA-41`"* 같은 문자열이 **인용문으로 3곳 더** 있다
(``FILING.md`` · ``FOLLOWUP_QUEUE.md`` §QA-39 · ``AGENT_실수-오류-기록.md``).
전부 *과거에 이 줄이 틀렸던 일*을 설명하는 산문이다 — 맨 검색으로 세면 **선언이 4건**이 된다.

그래서 선언 앵커를 **원장마다 따로 등록**한다. 형식이 실제로 다르기 때문이다:

- ``DOC_TRUTH_DRIFT`` → 굵은 문장이 **줄 머리**에서 시작한다
- ``FOLLOWUP_QUEUE`` → **현황판 표의 «총 등재» 행** 안에 있다

🔴 **한 패턴으로 통일하려 들지 않는다.** 통일하면 둘 중 하나가 산문을 줍는다.

🔴 **발급 ID 는 «배출본» 까지 세야 한다** (`문서-49`, 2026-09-29)
------------------------------------------------------------
항목 배출형 원장은 닫힌 항목을 `record/` 로 **내보낸다**(`FILING` §7-2).
원장 본문만 보면 그 번호들이 **발급된 적 없는 것처럼** 보인다.

🔬 **실측 2026-09-29**: `QA-58`·`QA-59` 를 배출하자 파일 안 최대가 `57` 이 되어,
이 게이트가 *«다음 신규 = QA-58»* 을 요구했다 — **이미 쓴 번호를 다시 내주라는 뜻**이고
**이 게이트가 막으려던 바로 그 일**이다.

🔑 **아래 취소선 항목과 같은 실패의 다른 경로다.** 취소선은 *행이 남아서* 잡혔고,
배출은 **행이 파일 밖으로 나간다.** 둘 다 «번호는 썼는데 세는 자리에 없다» 이다.

⇒ 배출 폴더(`record/`)의 **행 앵커**도 함께 센다. 🔴 **산문은 세지 않는다** —
   거기엔 *«다음 신규 = QA-60»* 같은 인용이 있어 최대값을 지어낸다(대장 `D69`).
   🔑 이 합집합은 최대값을 **올리기만** 하므로, 잘못 세도 «번호를 재사용» 쪽으로는 안 틀린다.

🔴 **발급 ID 는 취소선을 «포함» 해서 센다** (대장 **D58**)
-----------------------------------------------------------
취소된 항목(``| ~~**문서-17**~~ |``)도 **번호는 쓴 것**이다. 빼고 세면 최대값이 낮아져
**이미 쓴 번호를 다음 번호로 내준다.** 2026-09-21 에 실제로 그렇게 «결번» 을 지어냈다.

> ⚠️ **열린 것을 셀 때와 패턴이 다르다**(열림 = 취소선 **제외**).
> *같은 «문서-N» 이어도 묻는 질문이 다르면 세는 패턴이 다르다.*

✅ **음성 대조 표본** — 이것들은 **통과해야** 한다:
  - 산문 인용(``*"다음 신규 = `QA-38`"* 같은 **산문 언급**``)
  - 취소선 행이 최대값인 원장
"""

from dataclasses import dataclass
import re
import sys

# Windows 콘솔 기본 코드페이지(cp949)에서 한글 출력이 깨지거나 죽지 않도록 고정한다.
# 🔴 stdout 과 stderr 는 **서로를 보호하지 않는다** — 한쪽만 고정하면 다른 쪽이 크래시한다(대장 D36).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# stdout/stderr 방어가 import 보다 먼저여야 한다 — cp949 크래시 방지(대장 D36).
from scripts.gates._root import PRIVATE


@dataclass(frozen=True)
class Ledger:
    """대조할 원장 하나.

    Attributes:
        path: `docs-private/` 아래 파일명.
        prefix: ID 접두사 (`문서` · `QA`). 하이픈은 패턴이 붙인다.
        declare: **줄머리 앵커** 선언 패턴. 그룹 `n` 이 선언된 다음 번호.
        floor: 발급 고유 ID 수의 **바닥값** — 미만이면 파서가 깨진 것으로 본다.
        archives: 배출본이 놓이는 `docs-private/` 하위 폴더들. 거기 행 앵커도 «발급» 으로 센다.
    """

    path: str
    prefix: str
    declare: re.Pattern[str]
    floor: int
    archives: tuple[str, ...] = ()


#: 🔴 원장마다 선언 형식이 **실제로 다르다.** 한 패턴으로 통일하면 산문을 줍는다.
LEDGERS = (
    Ledger(
        path="DOC_TRUTH_DRIFT.md",
        prefix="문서",
        declare=re.compile(r"^\*\*다음 신규 = `문서-(?P<n>\d+)`", re.MULTILINE),
        floor=34,
    ),
    Ledger(
        path="FOLLOWUP_QUEUE.md",
        prefix="QA",
        declare=re.compile(r"^\| \*\*총 등재\*\*[^\n|]*\|[^\n|]*다음 신규 = `QA-(?P<n>\d+)`", re.MULTILINE),
        floor=41,
        # 🔴 §C 배출분은 `record/` 로 나간다 — 세지 않으면 그 번호를 다시 내준다(`문서-49`).
        archives=("record",),
    ),
)


def issued_ids(text: str, prefix: str) -> set[int]:
    """원장이 **발급한** ID 번호 전부.

    표 행과 제목형 **두 형식 다** 세고, 취소선 행도 **포함**한다(`FILING` §3-3 규칙 3).

    Args:
        text: 원장 본문.
        prefix: ID 접두사(하이픈 없이).

    Returns:
        발급된 번호 집합.
    """
    row = re.compile(r"^\| ~?~?\*\*" + prefix + r"-(\d+)\*\*", re.MULTILINE)
    head = re.compile(r"^#{2,4} ~?~?\*?\*?" + prefix + r"-(\d+)", re.MULTILINE)
    return {int(m) for m in row.findall(text)} | {int(m) for m in head.findall(text)}


def audit(ledger: Ledger, text: str, archived: set[int] | None = None) -> tuple[str | None, str]:
    """원장 하나를 대조한다.

    Args:
        ledger: 대조 대상.
        text: 원장 본문.
        archived: 배출본에서 읽은 발급 번호들(`문서-49`).

    Returns:
        `(문제, 요약)` — 문제가 없으면 첫 값이 `None`.
    """
    hits = ledger.declare.findall(text)
    if len(hits) != 1:
        why = "앵커가 깨졌다(0 은 «선언이 없다» 가 아니다)" if not hits else "모호하다"
        return (
            f"`{ledger.path}` 의 «다음 신규» 선언이 **{len(hits)}건** — {why}",
            "",
        )

    ids = issued_ids(text, ledger.prefix)
    if len(ids) < ledger.floor:
        return (
            f"`{ledger.path}` 의 발급 ID 가 **{len(ids)}건**으로 바닥값 {ledger.floor} 아래다 — "
            "행 형식이 바뀌어 파서가 못 읽었을 수 있다",
            "",
        )

    # 🔑 바닥값은 **원장 자신의** ID 로 본다(파서 건강 검사) — 최대값만 배출분을 합친다.
    issued = ids | (archived or set())
    declared, highest = int(hits[0]), max(issued)
    if declared != highest + 1:
        return (
            f"`{ledger.path}` 가 «다음 신규 = {ledger.prefix}-{declared}» 라고 말하는데 "
            f"**이미 {ledger.prefix}-{highest} 까지 발급**됐다 (기대 {highest + 1})",
            "",
        )
    ejected = len(issued) - len(ids)
    tail = f" · 배출분 {ejected}" if ejected else ""
    return None, f"{ledger.prefix} 발급 {len(issued)}건(최대 {highest}{tail}) · 다음 {declared}"


def main() -> int:
    """등록된 원장 전부를 대조한다.

    Returns:
        종료코드 — 0 이면 통과.
    """
    problems: list[str] = []
    summaries: list[str] = []

    for ledger in LEDGERS:
        target = PRIVATE / ledger.path
        if not target.exists():
            problems.append(f"`{ledger.path}` 가 없다 — 상태 정본은 없으면 결함이다(`FILING` §6)")
            continue
        archived: set[int] = set()
        for folder in ledger.archives:
            for snapshot in sorted((PRIVATE / folder).glob("*.md")):
                archived |= issued_ids(snapshot.read_text(encoding="utf-8", errors="replace"), ledger.prefix)
        problem, summary = audit(ledger, target.read_text(encoding="utf-8"), archived)
        if problem:
            problems.append(problem)
        else:
            summaries.append(summary)

    if problems:
        print("❌ 원장 «다음 신규» 검사 실패")
        for line in problems:
            print(f"   - {line}")
        print("   🔑 ID 는 재사용하지 않는다 — 이 줄이 틀리면 **이미 쓴 번호를 다시 내준다**.")
        print("   세는 법: 표 행 `^| **<접두사>-N**` + 제목형 `^## <접두사>-N`, **취소선 포함**.")
        print("   🔴 **배출본(`record/`)의 행도 «발급» 이다** — 원장 밖으로 나갔다고 번호가 풀리지 않는다.")
        return 1

    print(f"✅ 원장 다음 신규 — {' · '.join(summaries)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
