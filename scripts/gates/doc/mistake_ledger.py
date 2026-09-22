"""실수 대장 공용 파서 — **게이트 둘이 같은 수를 세게 한다** (트랙 B-13 S1).

왜 공용인가
-----------
`check_mistake_routing`(축 ↔ 라우팅 표)과 신설 `check_mistake_prevention`(예방 값)이
**같은 파일을 판다.** 파서가 둘이 되면 급조한 쪽이 **덜 엄밀한 두 번째 구현**이 되고,
두 게이트가 서로 다른 수를 세면서도 둘 다 초록을 낸다(대장 **D31**).

🔴 모집단이 **둘**이다 (대장 **D43** — 단위가 다르면 둘 다 사실이다)
--------------------------------------------------------------------
=====================  ==========================================================
모집단                  무엇
=====================  ==========================================================
**라우팅**              ``### ID.`` 전부. 안전 패턴(``A4``)처럼 *실수가 아닌* 것도
                        **축으로는 라우팅된다** — 셸 작업을 할 때 읽히는 게 맞다.
**예방**                **마커 안**(``대장-항목 시작``/``끝``). *"이 실수를 무엇이
                        막나"* 라는 물음이 **성립하는 것만**.
=====================  ==========================================================

**섞으면 한쪽이 반드시 틀린다.** 그래서 이 파서는 둘을 **각각** 돌려준다.

🔴 마커가 없으면 **예외**다 — 빈 모집단을 돌려주면 게이트가 *0건을 초록*으로 본다
(`docs/QUALITY_GATES.md` §2-3: *"검사 대상이 없으면 통과가 아니라 실패"*).

경로를 **인자로 받는다**
------------------------
정본 경로를 하드코딩하면 결핍 주입이 **정본을 훼손하는 길밖에** 없다.
대장은 git 밖이라 되돌릴 안전망이 없고, mtime 이 그 문서의 유일한 «언제» 다
(`FILING.md` §12-1). 경로를 받으면 ``tmp_path`` 사본도 정당한 검사 구역이 된다.
"""

from dataclasses import dataclass
from pathlib import Path
import re

from scripts.gates._root import PRIVATE

#: 예방 모집단의 경계. 이 밖의 ``### ID.`` 는 라우팅만 된다.
MARKER_START = "<!-- 대장-항목 시작 -->"
MARKER_END = "<!-- 대장-항목 끝 -->"

#: 정본. 게이트는 기본값으로 쓰고, 테스트·결핍 주입은 **인자로 덮는다.**
DEFAULT_LEDGER = PRIVATE / "AGENT_실수-오류-기록.md"

#: 🔑 줄머리 앵커로만 센다 — 앵커 없는 패턴은 **항상 뭔가를 돌려주고 틀렸다는 신호가 없다**(D47).
_HEAD_ID_RE = re.compile(r"^### ([A-Z]+\d+)\.\s*(.*)$")
_HEAD_ANY_RE = re.compile(r"^### ")
_AXIS_RE = re.compile(r"^\*\*축\*\*: `([^`]+)`\s*$")
_PREVENTION_RE = re.compile(r"^\*\*예방\*\*:\s*(.*)$")
_BACKTICK_RE = re.compile(r"`([^`]+)`")


class MarkerError(RuntimeError):
    """모집단 마커가 없거나 순서가 뒤집혔다 — **fail-closed** 로 멈춘다."""


@dataclass(frozen=True)
class Prevention:
    """`**예방**:` 한 줄을 뜯은 결과.

    Attributes:
        value: 첫 백틱 토큰(`기계`·`절차`·`없음`). **값의 유효성은 게이트가 판정**한다 —
            파서가 어휘를 알면 어휘가 바뀔 때마다 파서를 고쳐야 한다.
        reference: 둘째 백틱 토큰(`훅:…`·`규칙:…`·`스크립트:…`·`문서:…`). 없으면 `None`.
        malformed: 백틱 밖에 **남는 글자**가 있거나 토큰이 0개·3개 이상이다.
            괄호·산문 꼬리가 여기 걸린다 — 그러면 **참조를 기계가 대조할 수 없다.**
    """

    value: str
    reference: str | None
    malformed: bool


@dataclass(frozen=True)
class Entry:
    """대장 항목 하나.

    Attributes:
        id: `D67`·`A9`·`G1` 등. 계열이 여럿이므로 **접두사를 열거하지 않는다.**
        line: 헤딩 줄 번호(1-기준) — 위반을 보고할 때 사람이 찾아갈 좌표.
        title: 헤딩에서 ID 를 뺀 나머지.
        axis: `**축**:` 값. 없으면 `None`.
        prevention: `**예방**:` 파싱 결과. 줄 자체가 없으면 `None`.
            🔑 **`None`(줄이 없다) 과 `value="없음"`(막는 게 없다) 은 다른 사실**이다.
        in_population: 마커 안인가 = **예방 모집단인가**.
    """

    id: str
    line: int
    title: str
    axis: str | None
    prevention: Prevention | None
    in_population: bool


@dataclass(frozen=True)
class Ledger:
    """파싱된 대장 전체.

    Attributes:
        entries: **라우팅 모집단** — 마커 안팎 전부.
        headings_in_population: 마커 안 `### ` **총수**. `len(population)` 과 갈리면
            🔴 **ID 형식을 벗어난 항목**이 있다 — 축·예방 두 게이트를 동시에 빠져나간다.
    """

    entries: tuple[Entry, ...]
    headings_in_population: int

    @property
    def population(self) -> tuple[Entry, ...]:
        """**예방 모집단** — 마커 안 항목만.

        Returns:
            마커 안에 있는 항목들.
        """
        return tuple(entry for entry in self.entries if entry.in_population)


# ── 예방 한 줄 뜯기 ───────────────────────────────────────────────────
# 흐름: 줄머리 확인 -> 백틱 토큰 수집 -> 남는 글자로 형식위반 판정
def parse_prevention(line: str) -> Prevention | None:
    """`**예방**:` 줄을 (값, 참조, 형식위반) 로 뜯는다.

    Args:
        line: 대장의 한 줄.

    Returns:
        `**예방**:` 줄이면 `Prevention`, 아니면 `None`.
    """
    matched = _PREVENTION_RE.match(line)
    if matched is None:
        return None

    rest = matched.group(1)
    tokens = _BACKTICK_RE.findall(rest)
    leftover = _BACKTICK_RE.sub("", rest).strip()

    # 🔴 남는 글자가 곧 형식위반이다 — 괄호·설명·이모지가 여기 걸린다.
    malformed = bool(leftover) or not tokens or len(tokens) > 2
    return Prevention(
        value=tokens[0] if tokens else "",
        reference=tokens[1] if len(tokens) > 1 else None,
        malformed=malformed,
    )


# ── 메타 블록 ─────────────────────────────────────────────────────────
# 흐름: 헤딩 다음 줄부터 **빈 줄 직전까지** — 본문이 필드명을 인용해도 안 먹는다
def _meta_block(lines: list[str], head_index: int) -> list[str]:
    """헤딩 바로 아래의 연속 줄(메타 블록)을 돌려준다.

    Args:
        lines: 대장 전체 줄.
        head_index: 헤딩 줄의 인덱스.

    Returns:
        빈 줄을 만나기 전까지의 줄들.
    """
    block: list[str] = []
    for index in range(head_index + 1, len(lines)):
        if not lines[index].strip():
            break
        block.append(lines[index])
    return block


# ── 대장 파싱 ─────────────────────────────────────────────────────────
# 흐름: 마커 경계 확정 -> 헤딩 수집 -> 메타 블록에서 축·예방 -> 두 모집단
def parse_ledger(path: Path | None = None) -> Ledger:
    """대장을 읽어 항목과 두 모집단을 만든다.

    Args:
        path: 대장 경로. 생략하면 정본(`DEFAULT_LEDGER`).

    Returns:
        파싱 결과.

    Raises:
        MarkerError: 모집단 마커가 없거나 끝이 시작보다 앞이다.
    """
    target = DEFAULT_LEDGER if path is None else path
    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()

    start = next((i for i, line in enumerate(lines) if MARKER_START in line), None)
    end = next((i for i, line in enumerate(lines) if MARKER_END in line), None)
    if start is None or end is None or end <= start:
        message = (
            f"모집단 마커를 못 찾았다 ({MARKER_START} … {MARKER_END}) — "
            "빈 모집단을 돌려주면 게이트가 **0건을 초록**으로 본다"
        )
        raise MarkerError(message)

    entries: list[Entry] = []
    for index, line in enumerate(lines):
        head = _HEAD_ID_RE.match(line)
        if head is None:
            continue
        block = _meta_block(lines, index)
        axis = next((m.group(1) for raw in block if (m := _AXIS_RE.match(raw))), None)
        prevention = next((p for raw in block if (p := parse_prevention(raw)) is not None), None)
        entries.append(
            Entry(
                id=head.group(1),
                line=index + 1,
                title=head.group(2).strip(),
                axis=axis,
                prevention=prevention,
                in_population=start < index < end,
            )
        )

    headings = sum(1 for i in range(start + 1, end) if _HEAD_ANY_RE.match(lines[i]))
    return Ledger(entries=tuple(entries), headings_in_population=headings)
