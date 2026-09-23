"""실수 대장 라우팅 게이트 — **태그와 라우팅 표가 갈라지면 막는다** (B-10 · 문서-29).

왜 필요한가
-----------
실수 대장은 **한 세션에 다 읽을 수 없는 크기**다. 상시 규칙은 *"모든 도구 실행 전에 확인"* 이라고 말하지만
**그 크기를 매번 읽는 것은 불가능하고, 그래서 실제로 안 읽힌다.** 그래서 항목마다
**«어떤 작업에서 터지나»** 를 태그로 달고, `CLAUDE.md` 가 **작업 → 자리** 를 가리키게 한다.

그 구조는 **두 곳이 맞을 때만** 작동한다. 갈라지면 이렇게 실패한다:

===========================  ==============================================
갈라지는 모양                 그러면
===========================  ==============================================
항목에 태그가 없다             **어느 작업에서도 안 읽힌다** (영구 미도달)
표에 없는 태그를 쓴다          그 태그로 온 사람이 **주소를 못 찾는다**
표에만 있고 항목이 0건이다     🔴 **읽어도 아무것도 안 나오는 주소** (헛된 초록)
===========================  ==============================================

세 번째가 가장 위험하다 — *"읽었다"* 는 절차는 통과하는데 **내용이 없다.**
그래서 이 게이트는 **양방향**으로 대조한다.

🔴 이 게이트가 **못 하는 것** (한계 선언 — 안 적으면 초록이 과잉 해석된다)
-------------------------------------------------------------------------
- **태그가 «맞는지» 모른다.** 셸 실수에 `배포-인프라` 를 달아도 통과한다.
  기계가 볼 수 있는 건 *"달렸나"* 와 *"표에 있나"* 뿐이다. **내용은 사람이 본다.**
- **라우팅이 «도달했는지» 모른다.** 그건 훅의 일이고, 훅이 꺼졌는지는
  `check_rule_layers` 계열이 따로 본다.
- **상시 세트가 «정말 횡단인지» 모른다.** 기준(*축이 하나로 안 정해지면 상시*)은
  사람의 판정이다.

사용
----
    ... check_mistake_routing            # 전체 대조

정본 = `docs-private/AGENT_실수-오류-기록.md` · `CLAUDE.md` 의 라우팅 표.
"""

from pathlib import Path
import re
import sys

from scripts.gates._root import REPO_ROOT
from scripts.gates.doc.mistake_ledger import DEFAULT_LEDGER, MarkerError, parse_ledger

# 한글·이모지를 인쇄하므로 Windows cp949 콘솔에서 죽지 않게 먼저 방어한다(대장 D36).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 🔑 깊이를 세지 않는다 — `parents[3]` 은 폴더를 한 단계 나누는 순간 깨진다(`scripts/gates/README.md`).
LEDGER = DEFAULT_LEDGER
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"

# 🔑 실측값이다. 어림잡지 않는다 — 1구간에서 바닥값을 어림잡았다가 자기 첫 실행에서 자기를 막았다.
#    🔴 **여기에 두 번째 숫자를 적지 않는다**(대장 D67) — 상수만 사실이고,
#    올릴 때는 `uv run python -m scripts.gates.doc.check_mistake_routing` 출력으로 센다.
MIN_ITEMS = 93
# 축은 S3 에서 작은 것끼리 합칠 수 있다(1~2건 축은 라우팅 비용만 된다).
# 그래서 실측 10 이 아니라 8 로 둔다 — 여기서 잡을 실패는 **표가 통째로 비는 쪽**이다.
MIN_AXES = 8

# 라우팅 표는 마커 사이에서만 읽는다 — 산문에 백틱이 있어도 안 섞이게(D47: 앵커 없는 패턴 금지).
ROUTE_START = "<!-- 실수대장-라우팅 시작 -->"
ROUTE_END = "<!-- 실수대장-라우팅 끝 -->"
ROUTE_ROW_RE = re.compile(r"^\|[^|]*`([^`]+)`\s*\|")
# 표 행의 `(12건)` — D67 재발 방지용 대조 대상.
COUNT_RE = re.compile(r"\((\d+)건\)")


# ── ① CLAUDE.md 의 라우팅 표에서 «선언된 축» 을 거둔다 ────────────────
# 흐름: 마커 구간 잘라내기 -> 표 행의 첫 백틱 값 수집
def collect_declared_axes(text: str) -> tuple[set[str], str | None]:
    """라우팅 표에 선언된 축 이름을 모은다.

    Args:
        text: `CLAUDE.md` 전문.

    Returns:
        (선언된 축 집합, 문제 메시지 또는 None).
    """
    if ROUTE_START not in text or ROUTE_END not in text:
        return set(), (
            f"`CLAUDE.md` 에 라우팅 표 마커가 없다 ({ROUTE_START} … {ROUTE_END}) — "
            "표가 없으면 **대장에 닿는 주소가 층②에 없다**"
        )
    block = text.split(ROUTE_START, 1)[1].split(ROUTE_END, 1)[0]
    axes = {m.group(1).strip() for line in block.splitlines() if (m := ROUTE_ROW_RE.match(line))}
    return axes, None


# ── ①' 표가 «몇 건» 이라고 말하는가 ───────────────────────────────────
# 흐름: 마커 구간 -> 각 행의 축 이름 + `(N건)` -> 실측과 대조할 선언값
# 🔴 왜 있나: D67 — 건수를 두 곳에 적고 한쪽만 고쳤다. 대조하는 기계가 없으면 반드시 썩는다.
def collect_declared_counts(text: str) -> dict[str, int]:
    """라우팅 표가 축마다 선언한 건수를 모은다.

    Args:
        text: `CLAUDE.md` 전문.

    Returns:
        {축 이름: 선언 건수}. 건수를 안 적은 행은 빠진다.
    """
    if ROUTE_START not in text or ROUTE_END not in text:
        return {}
    block = text.split(ROUTE_START, 1)[1].split(ROUTE_END, 1)[0]
    declared: dict[str, int] = {}
    for line in block.splitlines():
        row = ROUTE_ROW_RE.match(line)
        count = COUNT_RE.search(line) if row else None
        if row and count:
            declared[row.group(1).strip()] = int(count.group(1))
    return declared


def main(argv: list[str] | None = None) -> int:
    """대장 태그와 라우팅 표를 양방향으로 대조한다.

    Args:
        argv: 대장 경로를 1개 받는다. 생략하면 정본.
            🔑 **경로를 받는 이유**: 하드코딩하면 결핍 주입이 **정본을 훼손하는 길밖에** 없다.
            대장은 git 밖이라 되돌릴 안전망이 없다(`FILING.md` §12-1).

    Returns:
        종료코드 — 0 이면 통과.
    """
    problems: list[str] = []
    target = Path(argv[0]) if argv else LEDGER

    if not target.exists():
        print(f"❌ 대장이 없다: {target}")
        return 1

    # 🔑 공용 파서를 쓴다 — 여기서 직접 정규식을 짜면 **덜 엄밀한 두 번째 구현**이 된다(D31).
    #    라우팅은 **라우팅 모집단**(마커 안팎 전부)을 센다. 안전 패턴도 셸 작업 때 읽혀야 한다.
    try:
        ledger = parse_ledger(target)
    except MarkerError as exc:
        print(f"❌ {exc}")
        return 1

    tagged = {entry.id: entry.axis for entry in ledger.entries if entry.axis is not None}
    untagged = [entry.id for entry in ledger.entries if entry.axis is None]
    total = len(ledger.entries)

    # 바닥값 — *0건은 «없다» 가 아니라 «못 셌다»* 다. 줄어든 것도 실패로 본다(D31).
    if total < MIN_ITEMS:
        problems.append(
            f"대장 항목이 **{total}건**으로 바닥값 {MIN_ITEMS} 아래다 — "
            "패턴이나 경로가 어긋났다(항목이 실제로 줄었다면 바닥값을 **의식적으로** 내린다)"
        )

    if untagged:
        head = " · ".join(untagged[:12]) + (" …" if len(untagged) > 12 else "")
        problems.append(f"**축 태그가 없는 항목 {len(untagged)}건** — 어느 작업에서도 안 읽힌다: {head}")

    declared, marker_problem = collect_declared_axes(CLAUDE_MD.read_text(encoding="utf-8", errors="replace"))
    if marker_problem:
        problems.append(marker_problem)

    used = set(tagged.values())
    if not marker_problem:
        if len(declared) < MIN_AXES:
            problems.append(f"라우팅 표의 축이 **{len(declared)}개**로 바닥값 {MIN_AXES} 아래다")
        # 🔴 양방향이 핵심이다. 한쪽만 보면 «읽어도 아무것도 없는 주소» 를 못 잡는다.
        orphan_tags = sorted(used - declared)
        empty_axes = sorted(declared - used)
        if orphan_tags:
            problems.append(
                f"**표에 없는 축을 쓰는 항목**이 있다 — 그 태그로는 주소를 못 찾는다: {' · '.join(orphan_tags)}"
            )
        if empty_axes:
            problems.append(
                f"🔴 **표에만 있고 항목이 0건인 축**: {' · '.join(empty_axes)} — "
                "*읽어도 아무것도 안 나오는 주소*다(절차만 통과하는 헛된 초록)"
            )

        # 🔴 D67 재발 방지 — 표가 말하는 건수와 실측을 대조한다.
        #    숫자를 두 곳에 적으면 반드시 한쪽이 썩는다. 대조하는 기계가 있으면 조용히 못 썩는다.
        measured = {axis: sum(1 for v in tagged.values() if v == axis) for axis in used}
        for axis, declared_count in collect_declared_counts(
            CLAUDE_MD.read_text(encoding="utf-8", errors="replace")
        ).items():
            actual = measured.get(axis)
            if actual is not None and actual != declared_count:
                problems.append(
                    f"라우팅 표의 축 `{axis}` 건수가 **{declared_count}** 인데 실측은 **{actual}** 이다 "
                    "— 표와 대장이 갈렸다(대장 D67)"
                )

    if problems:
        print("❌ 실수 대장 라우팅 검사 실패")
        for line in problems:
            print(f"   - {line}")
        return 1

    per_axis = {a: sum(1 for v in tagged.values() if v == a) for a in sorted(used)}
    shown = " · ".join(f"{a}:{n}" for a, n in per_axis.items())
    print(f"✅ 실수 대장 라우팅 — 항목 {total}건 전부 태그됨(바닥값 {MIN_ITEMS}) · 축 {len(used)}개 양방향 정합.")
    print(f"   {shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
