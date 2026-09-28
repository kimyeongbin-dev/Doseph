r"""표 모양 게이트 단위 테스트 (트랙 B-14 2판, `문서-37`).

⚠️ `tmp_path` 표본만 쓴다 — 저장소 상태에 따라 결과가 바뀌면 그건 게이트 테스트가 아니라
저장소 스냅샷이다.

🔴 **이 게이트가 존재하는 이유**: 원장은 **표로 산다**. 그런데 표가 깨져도
빌더도 다른 게이트도 **줄 단위**라 전부 통과한다 — 깨지는 것은 **읽는 화면**뿐이라
아무도 신호를 못 받는다.

🔑 **두 결함은 한 게이트에 있어야 한다.** 칸 수 검사는 *표 안의 행*을 보는데,
«표 행 사이 빈 줄» 은 행을 **표 밖으로** 내보내므로 검사 대상에서 사라진다 —
따로 두면 **0건으로 초록**이 난다.
"""

from pathlib import Path

from scripts.gates.doc.check_table_shape import audit, cell_count

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


def test_escaped_pipe_does_not_split_a_cell() -> None:
    """GFM 은 ``\\|`` 만 예외다 — 백틱 안이어도 맨 파이프는 칸을 쪼갠다."""
    assert cell_count("| a \\| b | c |") == 2
    assert cell_count("| a | b | c |") == 3
    assert cell_count("표가 아닌 줄") is None


# ── 결핍 주입 — 결함은 반드시 잡혀야 한다 ──────────────────────────
def test_a_row_with_too_few_cells_is_caught(tmp_path: Path) -> None:
    """머리보다 칸이 적은 행."""
    text = GOOD.replace("| 둘 | 2 | 평범한 행 |", "| 둘 | 2 |")
    assert audit(write(tmp_path, text)).mismatched


def test_a_bare_pipe_inside_backticks_is_caught(tmp_path: Path) -> None:
    """백틱 안이라도 맨 파이프는 칸을 쪼갠다."""
    text = GOOD.replace("`a \\| b`", "`a | b`")
    assert audit(write(tmp_path, text)).mismatched


def test_a_blank_line_between_rows_is_caught(tmp_path: Path) -> None:
    """🔴 칸 수 검사만으로는 원리적으로 못 보는 결함 — 행이 표 밖으로 나간다."""
    text = GOOD.replace("| 둘 | 2 | 평범한 행 |", "\n| 둘 | 2 | 평범한 행 |")
    report = audit(write(tmp_path, text))
    assert report.orphans, "빈 줄로 떨어져 나간 행을 고아로 잡아야 한다"
    assert report.mismatched == [], "칸 수는 멀쩡하다 — 그래서 고아 검사가 따로 필요하다"


def test_separator_cell_count_mismatch_is_caught(tmp_path: Path) -> None:
    """머리와 구분선의 칸 수가 다른 표."""
    text = GOOD.replace("|---|---|---|", "|---|---|")
    assert audit(write(tmp_path, text)).mismatched


def test_a_row_without_a_separator_is_an_orphan(tmp_path: Path) -> None:
    """머리 다음 줄이 구분선이 아니면 그것은 표가 아니다."""
    text = GOOD.replace("|---|---|---|\n", "")
    report = audit(write(tmp_path, text))
    assert report.orphans
    assert report.tables == 1, "정상인 두 번째 표는 여전히 세어야 한다"
