"""`mistake-prevention` 결핍 주입 + 음성 대조 (트랙 B-13 S6).

왜 스크립트로 남기나
--------------------
완료 판정은 *"고쳤다"* 가 아니라 **"이제 잡힌다"** 다(대장 **D21**). 그 문장을 나중에도
다시 확인할 수 있어야 하므로 **한 번 돌리고 버리는 즉석 실행으로 두지 않는다.**

🔴 **정본을 건드리지 않는다**
-----------------------------
대장은 git 밖이라 **되돌릴 안전망이 없고**, mtime 이 그 문서의 유일한 «언제» 다
(`FILING.md` §12-1). 게이트가 **경로를 인자로** 받으므로 `tmp` 사본이 정당한 검사 구역이다.
`D65` 의 *"고장난 곳에 표식을 둔다"* 는 **검사 구역을 맞추라**는 뜻이지 정본을 훼손하라는 뜻이 아니다.

⓪ 단계
------
주입 전에 **손대지 않은 사본이 Green** 인지 먼저 본다. 그게 아니면
*"주입했더니 Red"* 는 **아무것도 증명하지 않는다** — 러너가 게이트에 닿지도 못한 것일 수 있다.

사용
----
    uv run python -m scripts.injections.mistake_prevention_injection
"""

from pathlib import Path
import shutil
import sys
import tempfile

from scripts.gates._root import PRIVATE
from scripts.gates.doc.mistake_ledger import parse_ledger
from scripts.injection_harness import assert_doc_harness_live, run_doc_gate

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

#: 줄바꿈. 소스에 이스케이프를 남기지 않는다.
NL = chr(10)

GATE = "scripts.gates.doc.check_mistake_prevention"
LEDGER = PRIVATE / "AGENT_실수-오류-기록.md"

#: 표본에서 건드릴 항목 — **ID 로 고른다.**
#: 🔴 위치는 **파서로 잡는다. `index()` 로 원문을 뒤지지 않는다**(대장 **D69** 3회차).
#:    이 대장은 §0 에서 **자기 마커와 항목 형식을 예시로 인용**한다. 원문 검색은 그 예시를
#:    먼저 잡고, 그러면 주입이 **마커 밖·펜스 안**에 떨어져 **전부 무효**가 된다.
#:    실제로 그렇게 결핍 5건이 «안 잡힘» 으로 나왔다 — 게이트가 아니라 하네스가 눈멀었던 것이다.
MACHINE_ID = "D69"
PROC_ID = "D63"
NONE_ID = "D67"


def locate(text: str) -> tuple[list[str], dict[str, int], int]:
    """파서로 항목 줄 번호와 모집단 선두를 잡는다.

    Args:
        text: 대장 전문.

    Returns:
        (줄 목록, {ID: 0-기준 헤딩 줄}, 모집단 첫 항목의 0-기준 줄).
    """
    workspace = Path(tempfile.mkdtemp(prefix="locate-"))
    try:
        sample = workspace / "l.md"
        sample.write_text(text, encoding="utf-8")
        ledger = parse_ledger(sample)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    lines = text.splitlines(keepends=True)
    index = {entry.id: entry.line - 1 for entry in ledger.entries}
    first = min(entry.line - 1 for entry in ledger.population)
    return lines, index, first


def swap_prevention(lines: list[str], head: int, replacement: str) -> list[str]:
    """항목의 `**예방**:` 줄만 갈아 끼운다(빈 문자열이면 삭제).

    Args:
        lines: 대장 줄 목록.
        head: 헤딩 줄 인덱스.
        replacement: 새 예방 줄(줄바꿈 없이). 빈 문자열이면 그 줄을 지운다.

    Returns:
        바뀐 줄 목록(사본).
    """
    out = list(lines)
    for i in range(head + 1, min(head + 5, len(out))):
        if out[i].startswith("**예방**:"):
            if replacement:
                out[i] = replacement + chr(10)
            else:
                del out[i]
            return out
    message = f"항목 {head + 1} 줄에 예방 줄이 없다 — 주입 대상이 없으면 결과가 무의미하다"
    raise AssertionError(message)


def build_cases(original: str) -> list[tuple[str, str, int]]:
    """(이름, 주입된 전문, 기대 종료코드) 목록을 만든다.

    Args:
        original: 손대지 않은 대장 전문.

    Returns:
        검사 케이스 목록.
    """
    lines, at, first = locate(original)

    def swap(entry_id: str, replacement: str) -> str:
        out = swap_prevention(lines, at[entry_id], replacement)
        assert out != lines, "🔴 치환이 안 먹었다 — 전후가 같다"
        return "".join(out)

    def insert(block: str) -> str:
        return "".join(lines[:first]) + block + "".join(lines[first:])

    newcomer = "### D98. 새 실수" + NL + "**축**: `게이트-검사기`" + NL + "**예방**: `기계` `훅:doc-meta`" + NL * 2
    orphan = "### D97. 못 막는 새 실수" + NL + "**축**: `게이트-검사기`" + NL + "**예방**: `없음`" + NL * 2
    escape = "### D99·D45 합동 재발" + NL + "**축**: `게이트-검사기`" + NL * 2

    return [
        # ── 음성 대조 — 정상은 **통과해야** 한다.
        #    없으면 `return 1` 만 하는 게이트도 만점을 받는다(CLAUDE.md §6-1).
        ("음성 · 손대지 않은 사본", original, 0),
        ("음성 · 참조를 다른 실재 값으로", swap(PROC_ID, "**예방**: `절차` `문서:CLAUDE.md#2패스`"), 0),
        ("음성 · 신규 항목을 `기계` 로 등재", insert(newcomer), 0),
        # ── 결핍 주입 — 막아야 할 것을 **일부러** 넣는다.
        ("결핍 · 예방 줄 삭제", swap(MACHINE_ID, ""), 1),
        ("결핍 · 모르는 값", swap(NONE_ID, "**예방**: `기계입니다`"), 1),
        ("결핍 · 은퇴 훅 id(주석에만 존재)", swap(MACHINE_ID, "**예방**: `기계` `훅:canon-sync`"), 1),
        ("결핍 · 꺼진 규칙", swap(MACHINE_ID, "**예방**: `기계` `규칙:D203`"), 1),
        ("결핍 · 없는 앵커", swap(PROC_ID, "**예방**: `절차` `문서:CLAUDE.md#없는앵커`"), 1),
        ("결핍 · 산문 꼬리(형식 위반)", swap(PROC_ID, "**예방**: `절차` (`CLAUDE.md` §6-5 — 없다)"), 1),
        ("결핍 · `없음` 에 동반값", swap(NONE_ID, "**예방**: `없음` `훅:doc-meta`"), 1),
        ("결핍 · 종류 태그 없는 `기계`", swap(MACHINE_ID, "**예방**: `기계`"), 1),
        ("결핍 · 형식 이탈 항목", insert(escape), 1),
        ("결핍 · `없음` 천장 초과", insert(orphan), 1),
        ("결핍 · 모집단을 눈멀게(마커 조기 종료)", insert("<!-- 대장-항목 끝 -->" + NL * 2), 1),
    ]


def main() -> int:
    """결핍 주입과 음성 대조를 돌리고 검출률을 인쇄한다.

    Returns:
        종료코드 — 기대와 다른 케이스가 하나라도 있으면 1.
    """
    original = LEDGER.read_text(encoding="utf-8")
    workspace = Path(tempfile.mkdtemp(prefix="inject-"))
    try:
        # ⓪ 하네스가 살아 있나 — 여기서 실패하면 아래 결과는 전부 무의미하다.
        pristine = workspace / "pristine.md"
        pristine.write_text(original, encoding="utf-8")
        assert_doc_harness_live(GATE, pristine)

        rows: list[tuple[str, int, int]] = []
        for index, (name, text, expected) in enumerate(build_cases(original)):
            sample = workspace / f"case{index}.md"
            sample.write_text(text, encoding="utf-8")
            rows.append((name, run_doc_gate(GATE, sample), expected))
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    print("⓪ 하네스 살아있음 — 손대지 않은 사본이 Green")
    print()
    for name, got, expected in rows:
        mark = "✅" if got == expected else "🔴"
        print(f"  {mark} {name:34} rc={got} (기대 {expected})")

    negatives = [r for r in rows if r[2] == 0]
    injections = [r for r in rows if r[2] == 1]
    ok_neg = sum(1 for _, got, exp in negatives if got == exp)
    ok_inj = sum(1 for _, got, exp in injections if got == exp)
    print()
    print(f"결핍 주입 {ok_inj}/{len(injections)} · 음성 대조 {ok_neg}/{len(negatives)}")
    return 0 if ok_inj == len(injections) and ok_neg == len(negatives) else 1


if __name__ == "__main__":
    sys.exit(main())
