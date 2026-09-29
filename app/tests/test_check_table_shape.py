r"""표 모양 게이트 단위 테스트 (트랙 B-14 2판, `문서-37` · `QA-59`).

⚠️ `tmp_path` 표본만 쓴다 — 저장소 상태에 따라 결과가 바뀌면 그건 게이트 테스트가 아니라
저장소 스냅샷이다.

🔴 **이 게이트가 존재하는 이유**: 원장은 **표로 산다**. 그런데 표가 깨져도
빌더도 다른 게이트도 **줄 단위**라 전부 통과한다 — 깨지는 것은 **읽는 화면**뿐이라
아무도 신호를 받지 못한다.

🔑 **세 결함은 한 게이트에 있어야 한다.**

1. **칸 수 어긋남** — 셀 안의 이스케이프 안 된 파이프가 칸을 쪼갠다.
2. **표를 쪼개는 빈 줄** — 행이 **표 밖으로** 나가므로 칸 수 검사의 대상에서 사라진다.
   따로 두면 **0건으로 초록**이 난다.
3. **끝 파이프 결손**(2026-09-29 신설, `QA-59`) — 🔬 **렌더는 멀쩡하다.**
   `markdown-it` 으로 재니 ``| a | b`` 와 ``| a | b |`` 가 **똑같이** ``td`` 6개였다.
   그런데도 잡는 이유는 둘이다 — ①**우리 편집 스크립트**가 행을 파이프로 잘라 마지막 칸을
   대입할 때 그 파이프를 **데이터째 날린다**(실측 재발 3회) ②앞 판 게이트가 그 행을
   «표 행이 아님» 으로 보고 **표를 거기서 끊어**, 뒤따르는 멀쩡한 행을 **고아로 오보**했다.
"""

from pathlib import Path

from scripts.gates.doc.check_doc_filing import STATE_CANONS, WORK_BUFFERS
from scripts.gates.doc.check_table_shape import audit, cell_count, counts_toward_floor

GOOD = """# 표본

| 항목 | 값 | 비고 |
|---|---|---|
| 하나 | `a \\| b` | 이스케이프된 파이프 |
| 둘 | 2 | 평범한 행 |

| 왼쪽 | 오른쪽 |
|:---|---:|
| 정렬 구분선도 정상이다 | 1 |

```
| 코드 펜스 안 | 이건 | 표가 | 아니다 |
```

문장 안의 파이프 a | b 는 표가 아니다.
"""


def inject(old: str, new: str) -> str:
    """`GOOD` 에 결함을 주입한다. 🔴 **주입 자체에 단언을 건다**(대장 `D46`).

    치환이 안 맞으면 표본이 **정상인 채로** 검사를 통과해 버린다 —
    그러면 그 테스트는 아무것도 증명하지 않는다.

    Args:
        old: `GOOD` 안에 있어야 하는 조각.
        new: 바꿔 넣을 결함.

    Returns:
        결함이 든 본문.
    """
    assert GOOD.count(old) == 1, f"표본에 {old!r} 이 1건 있어야 한다"
    broken = GOOD.replace(old, new, 1)
    assert broken != GOOD, "주입이 아무것도 안 바꿨다"
    return broken


def write(tmp_path: Path, text: str) -> Path:
    """표본 파일을 만든다.

    Args:
        tmp_path: pytest 임시 디렉터리.
        text: 파일 본문.

    Returns:
        만들어진 파일 경로.
    """
    sample = tmp_path / "sample.md"
    sample.write_text(text, encoding="utf-8")
    return sample


# ── 음성 대조 — 정상 표본은 통과해야 한다 ──────────────────────────
def test_a_clean_sample_has_no_findings(tmp_path: Path) -> None:
    """이스케이프·정렬 구분선·코드 펜스·산문 파이프가 전부 무죄여야 한다."""
    report = audit(write(tmp_path, GOOD))
    assert report.tables == 2, f"표 머리 2개를 세야 한다 — 실제 {report.tables}"
    assert report.mismatched == []
    assert report.orphans == []
    assert report.dangling == []


def test_escaped_pipe_does_not_split_a_cell() -> None:
    """GFM 은 ``\\|`` 만 예외다 — 백틱 안이어도 맨 파이프는 칸을 쪼갠다."""
    assert cell_count("| a \\| b | c |") == 2
    assert cell_count("| a | b | c |") == 3
    assert cell_count("표가 아닌 줄") is None


def test_a_leading_pipe_is_still_required() -> None:
    """🔑 앞 파이프까지 선택으로 풀면 산문이 표로 읽힌다 — 오탐은 게이트를 꺼지게 한다."""
    assert cell_count("a | b | c") is None
    assert cell_count("| a | b | c") == 3, "끝 파이프는 선택이다(GFM)"


# ── 결핍 주입 — 결함은 반드시 잡혀야 한다 ──────────────────────────
def test_a_row_with_too_few_cells_is_caught(tmp_path: Path) -> None:
    """머리보다 칸이 적은 행."""
    text = inject("| 둘 | 2 | 평범한 행 |", "| 둘 | 2 |")
    assert audit(write(tmp_path, text)).mismatched


def test_a_bare_pipe_inside_backticks_is_caught(tmp_path: Path) -> None:
    """백틱 안이라도 맨 파이프는 칸을 쪼갠다."""
    text = inject("`a \\| b`", "`a | b`")
    assert audit(write(tmp_path, text)).mismatched


def test_a_blank_line_between_rows_is_caught(tmp_path: Path) -> None:
    """🔴 칸 수 검사만으로는 원리적으로 못 보는 결함 — 행이 표 밖으로 나간다."""
    text = inject("| 둘 | 2 | 평범한 행 |", "\n| 둘 | 2 | 평범한 행 |")
    report = audit(write(tmp_path, text))
    assert report.orphans, "빈 줄로 떨어져 나간 행을 고아로 잡아야 한다"
    assert report.mismatched == [], "칸 수는 멀쩡하다 — 그래서 고아 검사가 따로 필요하다"


def test_separator_cell_count_mismatch_is_caught(tmp_path: Path) -> None:
    """머리와 구분선의 칸 수가 다른 표."""
    text = inject("|---|---|---|", "|---|---|")
    assert audit(write(tmp_path, text)).mismatched


def test_a_row_without_a_separator_is_an_orphan(tmp_path: Path) -> None:
    """머리 다음 줄이 구분선이 아니면 그것은 표가 아니다."""
    text = inject("|---|---|---|\n", "")
    report = audit(write(tmp_path, text))
    assert report.orphans
    assert report.tables == 1, "정상인 두 번째 표는 여전히 세어야 한다"


# ── `QA-59` — 끝 파이프 결손 ────────────────────────────────────────
def test_a_body_row_missing_its_trailing_pipe_is_caught(tmp_path: Path) -> None:
    """🔴 앞 판이 **조용히 통과**시키던 모양. 마지막 칸을 대입하는 편집이 만든다."""
    text = inject("| 둘 | 2 | 평범한 행 |", "| 둘 | 2 | 평범한 행")
    report = audit(write(tmp_path, text))
    assert len(report.dangling) == 1, f"결손 1건이어야 한다 — 실제 {report.dangling}"


def test_a_dangling_row_does_not_break_the_table(tmp_path: Path) -> None:
    """🔑 회귀 단언 — 렌더는 멀쩡하므로 **표를 끊거나 고아를 만들면 안 된다.**

    앞 판은 그 행을 «표 행이 아님» 으로 보고 거기서 표를 끊었고,
    뒤따르는 멀쩡한 행 2건을 **고아로 오보**했다(2026-09-29 실측).
    """
    text = inject(
        "| 둘 | 2 | 평범한 행 |",
        "| 둘 | 2 | 평범한 행\n| 셋 | 3 | 뒤따르는 멀쩡한 행 |",
    )
    report = audit(write(tmp_path, text))
    assert report.orphans == [], f"고아를 만들면 안 된다 — 실제 {report.orphans}"
    assert report.mismatched == [], f"칸 수는 멀쩡하다 — 실제 {report.mismatched}"
    assert report.tables == 2, "표는 여전히 2개다"
    assert len(report.dangling) == 1


def test_a_head_or_separator_missing_its_trailing_pipe_is_caught(tmp_path: Path) -> None:
    """머리 행과 구분선도 같은 검사를 받는다."""
    head = inject("| 항목 | 값 | 비고 |", "| 항목 | 값 | 비고")
    assert len(audit(write(tmp_path, head)).dangling) == 1

    separator = inject("|---|---|---|", "|---|---|---")
    report = audit(write(tmp_path, separator))
    assert len(report.dangling) == 1
    assert report.mismatched == [], "구분선 칸 수는 여전히 3이다"
    assert report.tables == 2, "구분선으로 인정돼야 표가 2개다"


# ── `QA-58` — 검사하는 것과 «세는» 것은 다르다 ─────────────────────
def test_work_buffers_are_checked_but_not_counted() -> None:
    """🔑 작업 버퍼는 **검사는 받되 바닥값에는 안 세어야** 한다.

    있다가 없어지는 것이 정상이라, 세면 기준선이 **진행 중인 작업을 따라다닌다.**
    앞 판이 그래서 상수 주석까지 거짓이 됐다(`121` 은 `PLAN.md` 가 열려 있을 때의 수였다).
    """
    assert WORK_BUFFERS, "버퍼 목록이 비면 이 테스트가 아무것도 안 본다"
    for name in [*WORK_BUFFERS, "STRUCTURE_MAP.md"]:
        assert not counts_toward_floor(Path("docs-private") / name), name


def test_every_state_canon_counts_toward_the_floor() -> None:
    """정본은 하나도 빠짐없이 세어야 한다 — 빠지면 바닥값이 조용히 느슨해진다."""
    assert STATE_CANONS, "정본 목록이 비면 바닥값이 무의미하다"
    for name in STATE_CANONS:
        assert counts_toward_floor(Path("docs-private") / name), name


def test_the_two_sets_do_not_overlap() -> None:
    """🔴 겹치면 «검사만» 과 «세기» 의 구분이 무너진다."""
    assert not (STATE_CANONS & WORK_BUFFERS)
